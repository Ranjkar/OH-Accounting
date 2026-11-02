"""Deterministic bank-transaction-to-invoice matching. Every score is a sum
of named, inspectable signals -- never an opaque model output -- and nothing
here writes a Payment or changes an invoice's status by itself. It only ever
proposes PaymentMatch rows with status=SUGGESTED; turning a suggestion into
a real Payment always requires an explicit accountant action
(reconciliation_service.approve_match)."""

import itertools
import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting import payment_engine
from app.models.accounting import AccountingTransaction
from app.models.banking import BankTransaction
from app.models.enums import PaymentStatus

AMOUNT_EXACT_TOLERANCE = Decimal("0.01")
MAX_CANDIDATES_CONSIDERED = 25
MAX_COMBINATION_SIZE = 3


@dataclass(frozen=True)
class MatchCandidate:
    accounting_transaction_id: int
    score: Decimal
    confidence: str
    signals: dict
    suggested_allocation: Decimal


def normalize_iban(iban: str) -> str:
    return re.sub(r"\s+", "", iban).upper()


def _normalize_name(name: str) -> str:
    name = name.lower()
    for suffix in (" b.v.", " bv", " n.v.", " nv", " vof", " b.v", " holding"):
        name = name.replace(suffix, "")
    return re.sub(r"[^a-z0-9]", "", name)


def _names_match(a: str, b: str) -> bool:
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return False
    return na in nb or nb in na


def _confidence_for(score: Decimal) -> str:
    # 65 = exact amount (40) + invoice number found in the reference (25) --
    # on its own already about as certain as deterministic matching gets,
    # so it earns HIGH without needing a third incidental signal too.
    if score >= 65:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    if score > 0:
        return "LOW"
    return "NONE"


def score_single(bank_tx: BankTransaction, acc_tx: AccountingTransaction, remaining: Decimal) -> MatchCandidate:
    bank_amount_abs = abs(bank_tx.amount)
    signals: dict = {}
    score = Decimal("0")

    if remaining > 0 and abs(bank_amount_abs - remaining) <= AMOUNT_EXACT_TOLERANCE:
        score += Decimal("40")
        signals["exact_amount"] = True
    elif remaining > 0 and bank_amount_abs < remaining:
        coverage = bank_amount_abs / remaining
        score += Decimal("15") * coverage
        signals["partial_amount_coverage"] = str(coverage.quantize(Decimal("0.01")))
    elif remaining > 0:
        # Surfaced as a low-confidence candidate rather than dropped entirely --
        # an overpayment still needs a human decision (partial allocation vs.
        # refund), which can't happen if the engine never shows it.
        score += Decimal("5")
        signals["amount_exceeds_remaining_balance"] = True

    text = f"{bank_tx.payment_reference or ''} {bank_tx.description or ''}".lower()
    if acc_tx.invoice_number and acc_tx.invoice_number.lower() in text:
        score += Decimal("25")
        signals["invoice_number_found_in_reference"] = True

    if bank_tx.counterparty_iban and acc_tx.counterparty_iban:
        if normalize_iban(bank_tx.counterparty_iban) == normalize_iban(acc_tx.counterparty_iban):
            score += Decimal("20")
            signals["iban_match"] = True

    if bank_tx.counterparty_name and acc_tx.counterparty_name and _names_match(bank_tx.counterparty_name, acc_tx.counterparty_name):
        score += Decimal("10")
        signals["counterparty_name_match"] = True

    if bank_tx.booking_date and acc_tx.due_date:
        delta_days = abs((bank_tx.booking_date - acc_tx.due_date).days)
        if delta_days <= 3:
            score += Decimal("5")
            signals["date_proximity_days"] = delta_days

    score = min(score, Decimal("100"))
    allocation = min(bank_amount_abs, remaining) if remaining > 0 else bank_amount_abs
    return MatchCandidate(acc_tx.id, score, _confidence_for(score), signals, allocation)


def candidate_accounting_transactions(db: Session, bank_tx: BankTransaction) -> list[AccountingTransaction]:
    return (
        db.query(AccountingTransaction)
        .filter(
            AccountingTransaction.company_id == bank_tx.company_id,
            AccountingTransaction.payment_status.in_(
                [PaymentStatus.unpaid, PaymentStatus.partially_paid, PaymentStatus.overdue]
            ),
        )
        .order_by(AccountingTransaction.invoice_date.desc())
        .limit(MAX_CANDIDATES_CONSIDERED)
        .all()
    )


def find_single_matches(db: Session, bank_tx: BankTransaction) -> list[MatchCandidate]:
    """One bank transaction <-> one invoice: exact match, partial payment, or
    a bank amount that exceeds a single invoice's balance (overpayment)."""
    candidates = []
    for acc_tx in candidate_accounting_transactions(db, bank_tx):
        remaining = payment_engine.remaining_balance(acc_tx.gross_amount, acc_tx.payments)
        candidate = score_single(bank_tx, acc_tx, remaining)
        if candidate.score > 0:
            candidates.append(candidate)
    return sorted(candidates, key=lambda c: c.score, reverse=True)


def find_combined_match(db: Session, bank_tx: BankTransaction) -> list[MatchCandidate] | None:
    """One bank transaction covering several invoices in a single combined
    payment: look for a small combination of same-counterparty outstanding
    invoices whose remaining balances sum to the bank amount.

    Bounded to MAX_COMBINATION_SIZE invoices -- a real combined payment is
    a handful of invoices, not an unbounded subset-sum search."""
    bank_amount_abs = abs(bank_tx.amount)
    same_counterparty = [
        acc_tx
        for acc_tx in candidate_accounting_transactions(db, bank_tx)
        if bank_tx.counterparty_name and acc_tx.counterparty_name and _names_match(bank_tx.counterparty_name, acc_tx.counterparty_name)
    ]
    if len(same_counterparty) < 2:
        return None

    for size in range(2, min(MAX_COMBINATION_SIZE, len(same_counterparty)) + 1):
        for combo in itertools.combinations(same_counterparty, size):
            balances = [payment_engine.remaining_balance(t.gross_amount, t.payments) for t in combo]
            if any(b <= 0 for b in balances):
                continue
            total = sum(balances, Decimal("0"))
            if abs(total - bank_amount_abs) <= AMOUNT_EXACT_TOLERANCE:
                return [
                    MatchCandidate(
                        t.id,
                        Decimal("65"),  # combined matches are confidently-identified but never "exact single" grade
                        "MEDIUM",
                        {"combined_payment": True, "counterparty_name_match": True, "component_count": len(combo)},
                        balance,
                    )
                    for t, balance in zip(combo, balances)
                ]
    return None
