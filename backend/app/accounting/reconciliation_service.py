"""Turns matching_engine suggestions into PaymentMatch rows, and turns an
approved PaymentMatch into a real, auditable Payment. Every state change
here is explicit and reversible -- approving creates a Payment; reversing
voids it (never deletes -- the original Payment row stays as an audit
record) and resets the bank transaction back to unmatched."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting import matching_engine, payment_engine
from app.accounting.period_assignment import assign_vat_period_on_payment
from app.models.accounting import AccountingTransaction, Payment
from app.models.banking import BankTransaction, PaymentMatch
from app.models.enums import ReconciliationStatus


class ReconciliationError(Exception):
    pass


def generate_suggestions(db: Session, bank_tx: BankTransaction) -> list[PaymentMatch]:
    """Idempotent: clears any existing SUGGESTED matches for this transaction
    before regenerating, so re-running never duplicates suggestions. Matches
    that are already APPROVED are left untouched."""
    db.query(PaymentMatch).filter(
        PaymentMatch.bank_transaction_id == bank_tx.id, PaymentMatch.status == "SUGGESTED"
    ).delete()

    combined = matching_engine.find_combined_match(db, bank_tx)
    candidates = combined if combined else matching_engine.find_single_matches(db, bank_tx)[:3]

    matches = []
    for candidate in candidates:
        if candidate.confidence == "NONE":
            continue
        match = PaymentMatch(
            tenant_id=bank_tx.tenant_id,
            company_id=bank_tx.company_id,
            bank_transaction_id=bank_tx.id,
            accounting_transaction_id=candidate.accounting_transaction_id,
            allocated_amount=candidate.suggested_allocation,
            confidence_score=candidate.score,
            confidence_level=candidate.confidence,
            match_signals=candidate.signals,
            status="SUGGESTED",
        )
        db.add(match)
        matches.append(match)

    if matches:
        bank_tx.reconciliation_status = ReconciliationStatus.suggested_match
    elif bank_tx.reconciliation_status == ReconciliationStatus.imported:
        bank_tx.reconciliation_status = ReconciliationStatus.unmatched

    db.flush()
    return matches


def approve_match(db: Session, match: PaymentMatch, user_id: int, payment_date=None) -> Payment:
    if match.status != "SUGGESTED":
        raise ReconciliationError(f"Match is {match.status}, not SUGGESTED")

    bank_tx = match.bank_transaction
    acc_tx: AccountingTransaction = match.accounting_transaction

    payment = Payment(
        tenant_id=match.tenant_id,
        company_id=match.company_id,
        transaction_id=acc_tx.id,
        amount=match.allocated_amount,
        payment_date=payment_date or bank_tx.booking_date,
        reference=f"Bank reconciliation: {bank_tx.payment_reference or bank_tx.description or bank_tx.id}",
        bank_transaction_id=bank_tx.id,
        created_by_user_id=user_id,
    )
    db.add(payment)
    db.flush()

    # Phase 19 (audit 6.2): a bank-matched payment is just as much a payment as
    # one recorded through POST /transactions/{id}/payments, so a cash-based
    # company's VAT period must be assigned here too. The effective date is the
    # same one the Payment row was created with (explicit payment_date, else
    # the bank transaction's booking date).
    assign_vat_period_on_payment(db, acc_tx, payment.payment_date)

    match.status = "APPROVED"
    match.approved_by_user_id = user_id
    match.approved_at = datetime.now(timezone.utc)
    match.payment_id = payment.id

    acc_tx.payment_status = payment_engine.compute_payment_status(
        acc_tx.gross_amount, acc_tx.due_date, acc_tx.payments, datetime.now(timezone.utc).date()
    )

    _refresh_bank_transaction_status(db, bank_tx)
    db.flush()
    return payment


def reject_match(db: Session, match: PaymentMatch) -> None:
    if match.status != "SUGGESTED":
        raise ReconciliationError(f"Match is {match.status}, not SUGGESTED")
    match.status = "REJECTED"
    _refresh_bank_transaction_status(db, match.bank_transaction)
    db.flush()


def reverse_match(db: Session, match: PaymentMatch, user_id: int, reason: str) -> None:
    """Undo an approved match: void the Payment (never delete it -- it stays
    as an audit record) and recompute both sides' status."""
    if match.status != "APPROVED":
        raise ReconciliationError(f"Match is {match.status}, not APPROVED")
    if match.payment_id is None:
        raise ReconciliationError("Approved match has no linked payment to reverse")

    payment = db.get(Payment, match.payment_id)
    payment.voided = True
    payment.voided_by_user_id = user_id
    payment.voided_at = datetime.now(timezone.utc)
    payment.void_reason = reason

    match.status = "REVERSED"

    acc_tx = match.accounting_transaction
    acc_tx.payment_status = payment_engine.compute_payment_status(
        acc_tx.gross_amount, acc_tx.due_date, acc_tx.payments, datetime.now(timezone.utc).date()
    )

    _refresh_bank_transaction_status(db, match.bank_transaction)
    db.flush()


def exclude_transaction(db: Session, bank_tx: BankTransaction) -> None:
    """Mark a bank transaction as deliberately outside the reconciliation
    workflow (e.g. a bank fee, an internal transfer) -- not every transaction
    needs to match an invoice."""
    bank_tx.reconciliation_status = ReconciliationStatus.excluded
    db.flush()


def _refresh_bank_transaction_status(db: Session, bank_tx: BankTransaction) -> None:
    # The app's session is autoflush=False, so the caller's just-made match.status
    # change (not yet flushed) would otherwise be invisible to this query.
    db.flush()
    matches = (
        db.query(PaymentMatch)
        .filter(PaymentMatch.bank_transaction_id == bank_tx.id, PaymentMatch.status == "APPROVED")
        .all()
    )
    if not matches:
        remaining_suggestions = (
            db.query(PaymentMatch)
            .filter(PaymentMatch.bank_transaction_id == bank_tx.id, PaymentMatch.status == "SUGGESTED")
            .count()
        )
        bank_tx.reconciliation_status = (
            ReconciliationStatus.suggested_match if remaining_suggestions else ReconciliationStatus.unmatched
        )
        return

    total_allocated = sum((m.allocated_amount for m in matches), Decimal("0"))
    if abs(total_allocated - abs(bank_tx.amount)) <= Decimal("0.01"):
        bank_tx.reconciliation_status = ReconciliationStatus.matched
    else:
        bank_tx.reconciliation_status = ReconciliationStatus.partially_matched
