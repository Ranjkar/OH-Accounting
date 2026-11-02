"""Deterministic payment-status computation. Never infers payment from
invoice text or metadata -- only from recorded Payment rows."""

from datetime import date
from decimal import Decimal

from app.models.accounting import Payment
from app.models.enums import PaymentStatus

ZERO = Decimal("0")


def total_paid(payments: list[Payment]) -> Decimal:
    return sum((p.amount for p in payments if not p.voided), ZERO)


def compute_payment_status(
    gross_amount: Decimal, due_date: date | None, payments: list[Payment], today: date
) -> PaymentStatus:
    if gross_amount <= 0:
        return PaymentStatus.unknown  # credit notes / zero-value entries aren't "paid" in this sense

    paid = total_paid(payments)
    if paid >= gross_amount:
        return PaymentStatus.paid
    if due_date and due_date < today:
        return PaymentStatus.overdue
    if paid > 0:
        return PaymentStatus.partially_paid
    return PaymentStatus.unpaid


def remaining_balance(gross_amount: Decimal, payments: list[Payment]) -> Decimal:
    return gross_amount - total_paid(payments)
