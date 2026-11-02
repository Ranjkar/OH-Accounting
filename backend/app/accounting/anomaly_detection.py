"""Transparent, rule-based anomaly detection. Every rule names its evidence
explicitly -- there is no opaque "fraud score". These are leads for an
accountant to investigate, never a verdict: nothing here ever labels a
transaction fraudulent, only flags a pattern worth a human look."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting.matching_engine import normalize_iban
from app.models.accounting import AccountingTransaction, Payment
from app.models.anomaly import AnomalyFlag
from app.models.banking import BankTransaction
from app.models.enums import AnomalySeverity, LedgerSide, ReconciliationStatus

UNMATCHED_AGING_DAYS = 14
EXPENSE_INCREASE_THRESHOLD_PCT = Decimal("50")


def _clear_open_flags(db: Session, company_id: int, rule_code: str) -> None:
    db.query(AnomalyFlag).filter(
        AnomalyFlag.company_id == company_id, AnomalyFlag.rule_code == rule_code, AnomalyFlag.status == "OPEN"
    ).delete()


def detect_duplicate_payments(db: Session, company_id: int, tenant_id: int) -> list[AnomalyFlag]:
    """Two non-voided payments on different transactions, same amount and
    date -- a classic double-payment pattern."""
    _clear_open_flags(db, company_id, "DUPLICATE_PAYMENT")
    payments = (
        db.query(Payment)
        .join(AccountingTransaction, Payment.transaction_id == AccountingTransaction.id)
        .filter(AccountingTransaction.company_id == company_id, Payment.voided.is_(False))
        .all()
    )
    groups: dict[tuple, list[Payment]] = defaultdict(list)
    for p in payments:
        groups[(p.amount, p.payment_date)].append(p)

    flags = []
    for (amount, pay_date), group in groups.items():
        distinct_transactions = {p.transaction_id for p in group}
        if len(group) > 1 and len(distinct_transactions) > 1:
            flag = AnomalyFlag(
                tenant_id=tenant_id, company_id=company_id, rule_code="DUPLICATE_PAYMENT",
                severity=AnomalySeverity.warning,
                message=f"{len(group)} payments of {amount} on {pay_date} across {len(distinct_transactions)} different invoices -- verify this isn't a duplicate payment.",
                evidence={"amount": str(amount), "payment_date": str(pay_date), "payment_ids": [p.id for p in group], "transaction_ids": list(distinct_transactions)},
                related_entity_type="payment", related_entity_id=group[0].id,
            )
            db.add(flag)
            flags.append(flag)
    db.flush()
    return flags


def detect_supplier_bank_detail_changes(db: Session, company_id: int, tenant_id: int) -> list[AnomalyFlag]:
    """Same supplier name, a new IBAN never seen before for them -- a common
    invoice-fraud indicator (attacker redirects payment to a new account)."""
    _clear_open_flags(db, company_id, "SUPPLIER_BANK_DETAILS_CHANGED")
    transactions = (
        db.query(AccountingTransaction)
        .filter(
            AccountingTransaction.company_id == company_id,
            AccountingTransaction.ledger_side == LedgerSide.purchases,
            AccountingTransaction.counterparty_iban.isnot(None),
        )
        .order_by(AccountingTransaction.invoice_date)
        .all()
    )
    known_ibans: dict[str, set[str]] = defaultdict(set)
    flags = []
    for tx in transactions:
        name_key = (tx.counterparty_name or "").strip().lower()
        iban = normalize_iban(tx.counterparty_iban)
        if name_key in known_ibans and known_ibans[name_key] and iban not in known_ibans[name_key]:
            flag = AnomalyFlag(
                tenant_id=tenant_id, company_id=company_id, rule_code="SUPPLIER_BANK_DETAILS_CHANGED",
                severity=AnomalySeverity.critical,
                message=f"Invoice #{tx.id} from '{tx.counterparty_name}' uses a different IBAN ({tx.counterparty_iban}) than previously seen for this supplier. Verify directly with the supplier before paying.",
                evidence={"new_iban": tx.counterparty_iban, "previously_seen_ibans": list(known_ibans[name_key]), "transaction_id": tx.id},
                related_entity_type="accounting_transaction", related_entity_id=tx.id,
            )
            db.add(flag)
            flags.append(flag)
        known_ibans[name_key].add(iban)
    db.flush()
    return flags


def detect_unexpected_expense_increases(db: Session, company_id: int, tenant_id: int) -> list[AnomalyFlag]:
    _clear_open_flags(db, company_id, "UNEXPECTED_EXPENSE_INCREASE")
    transactions = (
        db.query(AccountingTransaction)
        .filter(AccountingTransaction.company_id == company_id, AccountingTransaction.ledger_side == LedgerSide.purchases)
        .order_by(AccountingTransaction.invoice_date)
        .all()
    )
    history: dict[str, list[Decimal]] = defaultdict(list)
    flags = []
    for tx in transactions:
        name_key = (tx.counterparty_name or "").strip().lower()
        prior = history[name_key]
        if len(prior) >= 2:
            avg_prior = sum(prior, Decimal("0")) / len(prior)
            if avg_prior > 0:
                increase_pct = ((tx.net_amount - avg_prior) / avg_prior) * 100
                if increase_pct > EXPENSE_INCREASE_THRESHOLD_PCT:
                    flag = AnomalyFlag(
                        tenant_id=tenant_id, company_id=company_id, rule_code="UNEXPECTED_EXPENSE_INCREASE",
                        severity=AnomalySeverity.info,
                        message=f"Invoice #{tx.id} from '{tx.counterparty_name}' is {increase_pct:.0f}% above this supplier's average of {avg_prior.quantize(Decimal('0.01'))}.",
                        evidence={"amount": str(tx.net_amount), "historical_average": str(avg_prior.quantize(Decimal("0.01"))), "increase_pct": str(increase_pct.quantize(Decimal("0.1"))), "transaction_id": tx.id},
                        related_entity_type="accounting_transaction", related_entity_id=tx.id,
                    )
                    db.add(flag)
                    flags.append(flag)
        history[name_key].append(tx.net_amount)
    db.flush()
    return flags


def detect_aging_unmatched_payments(db: Session, company_id: int, tenant_id: int) -> list[AnomalyFlag]:
    _clear_open_flags(db, company_id, "UNMATCHED_PAYMENT_AGING")
    cutoff = date.today() - timedelta(days=UNMATCHED_AGING_DAYS)
    stale = (
        db.query(BankTransaction)
        .filter(
            BankTransaction.company_id == company_id,
            BankTransaction.reconciliation_status.in_([ReconciliationStatus.unmatched, ReconciliationStatus.suggested_match]),
            BankTransaction.booking_date < cutoff,
        )
        .all()
    )
    flags = []
    for tx in stale:
        flag = AnomalyFlag(
            tenant_id=tenant_id, company_id=company_id, rule_code="UNMATCHED_PAYMENT_AGING",
            severity=AnomalySeverity.warning,
            message=f"Bank transaction of {tx.amount} {tx.currency} on {tx.booking_date} has been unmatched for over {UNMATCHED_AGING_DAYS} days.",
            evidence={"amount": str(tx.amount), "booking_date": str(tx.booking_date), "days_unmatched": (date.today() - tx.booking_date).days},
            related_entity_type="bank_transaction", related_entity_id=tx.id,
        )
        db.add(flag)
        flags.append(flag)
    db.flush()
    return flags


def run_all_rules(db: Session, company_id: int, tenant_id: int) -> list[AnomalyFlag]:
    flags = []
    flags += detect_duplicate_payments(db, company_id, tenant_id)
    flags += detect_supplier_bank_detail_changes(db, company_id, tenant_id)
    flags += detect_unexpected_expense_increases(db, company_id, tenant_id)
    flags += detect_aging_unmatched_payments(db, company_id, tenant_id)
    return flags
