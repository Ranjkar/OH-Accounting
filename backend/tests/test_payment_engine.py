from datetime import date
from decimal import Decimal

from app.accounting import payment_engine
from app.models.accounting import Payment


def _payment(amount: str) -> Payment:
    return Payment(amount=Decimal(amount), payment_date=date(2026, 1, 1))


def test_no_payments_before_due_date_is_unpaid():
    status = payment_engine.compute_payment_status(Decimal("121.00"), date(2026, 6, 1), [], date(2026, 1, 1))
    assert status.value == "UNPAID"


def test_no_payments_past_due_date_is_overdue():
    status = payment_engine.compute_payment_status(Decimal("121.00"), date(2026, 1, 1), [], date(2026, 6, 1))
    assert status.value == "OVERDUE"


def test_full_payment_is_paid_even_if_past_due():
    payments = [_payment("121.00")]
    status = payment_engine.compute_payment_status(Decimal("121.00"), date(2026, 1, 1), payments, date(2026, 6, 1))
    assert status.value == "PAID"


def test_overpayment_is_still_paid():
    payments = [_payment("150.00")]
    status = payment_engine.compute_payment_status(Decimal("121.00"), date(2026, 1, 1), payments, date(2026, 6, 1))
    assert status.value == "PAID"


def test_partial_payment_before_due_date_is_partially_paid():
    payments = [_payment("50.00")]
    status = payment_engine.compute_payment_status(Decimal("121.00"), date(2026, 6, 1), payments, date(2026, 1, 1))
    assert status.value == "PARTIALLY_PAID"


def test_partial_payment_past_due_date_is_overdue_not_partially_paid():
    payments = [_payment("50.00")]
    status = payment_engine.compute_payment_status(Decimal("121.00"), date(2026, 1, 1), payments, date(2026, 6, 1))
    assert status.value == "OVERDUE"


def test_multiple_partial_payments_sum_correctly():
    payments = [_payment("30.00"), _payment("30.00"), _payment("30.00")]
    assert payment_engine.total_paid(payments) == Decimal("90.00")
    status = payment_engine.compute_payment_status(Decimal("121.00"), date(2026, 6, 1), payments, date(2026, 1, 1))
    assert status.value == "PARTIALLY_PAID"


def test_credit_note_zero_or_negative_gross_is_unknown():
    assert payment_engine.compute_payment_status(Decimal("-121.00"), None, [], date(2026, 1, 1)).value == "UNKNOWN"
    assert payment_engine.compute_payment_status(Decimal("0"), None, [], date(2026, 1, 1)).value == "UNKNOWN"


def test_remaining_balance():
    payments = [_payment("50.00")]
    assert payment_engine.remaining_balance(Decimal("121.00"), payments) == Decimal("71.00")


def test_no_due_date_and_no_payments_is_unpaid_not_overdue():
    status = payment_engine.compute_payment_status(Decimal("121.00"), None, [], date(2026, 6, 1))
    assert status.value == "UNPAID"
