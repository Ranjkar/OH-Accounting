"""Deterministic cash-flow forecasting from actual accounting and payment
data. No AI involved -- every figure here is either an actual recorded
amount or a disclosed, labeled projection built from it. Never presents a
projection as a confirmed bank balance."""

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from app.accounting import payment_engine
from app.models.accounting import AccountingTransaction, VatReturn
from app.models.banking import BankTransaction
from app.models.enums import LedgerSide, PaymentStatus, RecurringStatus, VatReturnStatus
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.recurring import RecurringPattern

ZERO = Decimal("0")


def build_cash_flow_forecast(db: Session, company_id: int, months_ahead: int = 3) -> dict:
    today = date.today()

    bank_movement = (
        db.query(BankTransaction).filter(BankTransaction.company_id == company_id).all()
    )
    net_bank_movement = sum((t.amount for t in bank_movement), ZERO)

    outstanding = (
        db.query(AccountingTransaction)
        .filter(
            AccountingTransaction.company_id == company_id,
            AccountingTransaction.payment_status.in_([PaymentStatus.unpaid, PaymentStatus.partially_paid, PaymentStatus.overdue]),
        )
        .all()
    )
    incoming = [t for t in outstanding if t.ledger_side == LedgerSide.sales]
    outgoing = [t for t in outstanding if t.ledger_side == LedgerSide.purchases]

    expected_incoming_total = sum((payment_engine.remaining_balance(t.gross_amount, t.payments) for t in incoming), ZERO)
    expected_outgoing_total = sum((payment_engine.remaining_balance(t.gross_amount, t.payments) for t in outgoing), ZERO)

    recurring = (
        db.query(RecurringPattern)
        .filter(RecurringPattern.company_id == company_id, RecurringPattern.status != RecurringStatus.stopped)
        .all()
    )
    recurring_monthly_equivalent = sum((_monthly_equivalent(r) for r in recurring), ZERO)

    vat_returns = (
        db.query(VatReturn)
        .join(VatPeriod, VatReturn.vat_period_id == VatPeriod.id)
        .join(FinancialYear, VatPeriod.financial_year_id == FinancialYear.id)
        .filter(FinancialYear.company_id == company_id, VatReturn.status.notin_([VatReturnStatus.approved, VatReturnStatus.locked]))
        .all()
    )
    forecast_vat_payable = sum((r.net_payable for r in vat_returns if r.net_payable > 0), ZERO)
    forecast_vat_refundable = -sum((r.net_payable for r in vat_returns if r.net_payable < 0), ZERO)

    monthly_projection = []
    for i in range(months_ahead):
        month_start = (today.replace(day=1) + relativedelta(months=i))
        month_end = month_start + relativedelta(months=1)
        month_incoming = sum(
            (payment_engine.remaining_balance(t.gross_amount, t.payments) for t in incoming if t.due_date and month_start <= t.due_date < month_end),
            ZERO,
        )
        month_outgoing = sum(
            (payment_engine.remaining_balance(t.gross_amount, t.payments) for t in outgoing if t.due_date and month_start <= t.due_date < month_end),
            ZERO,
        )
        month_recurring = sum(
            (r.expected_amount for r in recurring if r.next_expected_date and month_start <= r.next_expected_date < month_end),
            ZERO,
        )
        monthly_projection.append(
            {
                "month": month_start.strftime("%Y-%m"),
                "expected_incoming": str(month_incoming),
                "expected_outgoing": str(month_outgoing + month_recurring),
                "net": str(month_incoming - month_outgoing - month_recurring),
                "is_estimate": True,
            }
        )

    return {
        "as_of": today.isoformat(),
        "net_bank_transaction_movement": str(net_bank_movement),
        "net_bank_transaction_movement_disclaimer": (
            "Sum of all imported bank transactions for this company -- not a live bank balance. "
            "Confirm against your actual bank statement; only transactions that have been imported are included."
        ),
        "expected_incoming_total": str(expected_incoming_total),
        "expected_outgoing_total": str(expected_outgoing_total),
        "outstanding_sales_invoice_count": len(incoming),
        "outstanding_purchase_invoice_count": len(outgoing),
        "recurring_expenses_monthly_equivalent": str(recurring_monthly_equivalent),
        "recurring_pattern_count": len(recurring),
        "forecast_vat_payable": str(forecast_vat_payable),
        "forecast_vat_refundable": str(forecast_vat_refundable),
        "forecast_vat_disclaimer": "Based on VAT returns not yet approved/locked; figures change until a return is finalized.",
        "monthly_projection": monthly_projection,
        "monthly_projection_disclaimer": "Estimates based on invoice due dates and detected recurring patterns, not confirmed future payments.",
    }


def _monthly_equivalent(pattern: RecurringPattern) -> Decimal:
    from app.models.enums import RecurringFrequency

    divisor = {
        RecurringFrequency.weekly: Decimal("0.25"),
        RecurringFrequency.monthly: Decimal("1"),
        RecurringFrequency.quarterly: Decimal("3"),
        RecurringFrequency.annual: Decimal("12"),
    }.get(pattern.frequency, Decimal("1"))
    return (pattern.expected_amount / divisor).quantize(Decimal("0.01"))
