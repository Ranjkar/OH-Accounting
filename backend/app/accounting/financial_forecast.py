"""Extends Phase 6's cash-flow forecasting (app.accounting.cash_flow) with
revenue/expense/profit/outstanding-invoice/VAT/tax forecasts. Reuses that
module's build_cash_flow_forecast() for the cash component instead of
reimplementing bank-movement logic -- this module only adds trend-based
projection on top of app.accounting.financial_reports' deterministic
historical figures.

Every forecast returned here carries its horizon, the historical data period
it was built from, its assumptions, and an explicit uncertainty range. None
of this is ever presented as a guaranteed outcome -- it is always a
projection of a simple historical trend, clearly labeled as such.
"""

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from app.accounting import financial_reports as fr
from app.accounting.cash_flow import build_cash_flow_forecast
from app.models.financial_year import FinancialYear, VatPeriod

ZERO = Decimal("0")
TREND_HISTORY_MONTHS = 3
UNCERTAINTY_PCT = Decimal("20")  # +/- band around a simple trend projection -- a stated assumption, not a statistical model


def _monthly_history(db: Session, company_id: int, reference_date: date, months: int) -> list[dict]:
    history = []
    for i in range(months, 0, -1):
        month_start = reference_date.replace(day=1) - relativedelta(months=i)
        period = fr.resolve_period(fr.ReportPeriod.monthly, month_start)
        history.append(fr.profit_and_loss(db, company_id, period))
    return history


def _trend_average(values: list[Decimal]) -> Decimal:
    if not values:
        return ZERO
    return (sum(values, ZERO) / len(values)).quantize(Decimal("0.01"))


def revenue_expense_profit_forecast(db: Session, company_id: int, horizon_months: int = 3, reference_date: date | None = None) -> dict:
    reference_date = reference_date or date.today()
    history = _monthly_history(db, company_id, reference_date, TREND_HISTORY_MONTHS)

    avg_revenue = _trend_average([h["revenue"] for h in history])
    avg_expenses = _trend_average([
        h["cost_of_sales"] + h["operating_expenses"] + h["uncategorized_expenses"] + h["personnel_expenses"]
        + h["depreciation"] + h["interest_expense"]
        for h in history
    ])
    avg_profit = _trend_average([h["net_profit"] for h in history])

    months = []
    for i in range(horizon_months):
        month_start = reference_date.replace(day=1) + relativedelta(months=i)
        months.append(
            {
                "month": month_start.strftime("%Y-%m"),
                "forecast_revenue": avg_revenue,
                "forecast_expenses": avg_expenses,
                "forecast_profit": avg_profit,
                "low_estimate_profit": (avg_profit * (1 - UNCERTAINTY_PCT / 100)).quantize(Decimal("0.01")),
                "high_estimate_profit": (avg_profit * (1 + UNCERTAINTY_PCT / 100)).quantize(Decimal("0.01")),
            }
        )

    return {
        "forecast_horizon_months": horizon_months,
        "historical_data_period": {
            "start": (reference_date.replace(day=1) - relativedelta(months=TREND_HISTORY_MONTHS)).isoformat(),
            "end": reference_date.isoformat(),
            "months_used": len(history),
        },
        "assumptions": [
            f"Simple average of the last {TREND_HISTORY_MONTHS} calendar month(s) of actuals, carried forward flat.",
            f"Uncertainty band is +/-{UNCERTAINTY_PCT}% around the profit trend -- a stated assumption, not a statistical confidence interval.",
            "Does not account for seasonality beyond what is already present in the averaged months.",
        ],
        "monthly_forecast": months,
        "is_estimate": True,
        "disclaimer": "This is a trend projection, not a guaranteed outcome. Confirm against actual invoices, "
        "payments, and bank activity as they occur.",
    }


def outstanding_invoice_forecast(db: Session, company_id: int, as_of_date: date | None = None) -> dict:
    """Expected collections/payments from invoices already on the books --
    these are CONFIRMED receivables/payables, not a trend projection."""
    as_of_date = as_of_date or date.today()
    debtors = fr.debtors(db, company_id, as_of_date)
    creditors = fr.creditors(db, company_id, as_of_date)
    return {
        "as_of_date": as_of_date.isoformat(),
        "confirmed_receivables_outstanding": debtors["total_outstanding"],
        "receivables_aging": debtors["aging_summary"],
        "confirmed_payables_outstanding": creditors["total_outstanding"],
        "payables_aging": creditors["aging_summary"],
        "net_working_capital_from_trade": debtors["total_outstanding"] - creditors["total_outstanding"],
        "is_estimate": False,
        "note": "Based on invoices and due dates already recorded -- confirmed amounts owed, not a forecast of new business.",
    }


def vat_payment_forecast(db: Session, company_id: int, as_of_date: date | None = None) -> dict:
    as_of_date = as_of_date or date.today()
    upcoming_periods = (
        db.query(VatPeriod)
        .join(FinancialYear, VatPeriod.financial_year_id == FinancialYear.id)
        .filter(FinancialYear.company_id == company_id, VatPeriod.end_date >= as_of_date)
        .all()
    )
    rows = []
    for period in sorted(upcoming_periods, key=lambda p: p.payment_deadline)[:4]:
        totals = fr.vat_overview(db, company_id, fr.DateRange(period.start_date, period.end_date))
        net_payable = sum((r["net_payable"] for r in totals), ZERO)
        rows.append(
            {
                "vat_period_id": period.id,
                "period_label": period.label,
                "payment_deadline": period.payment_deadline.isoformat(),
                "estimated_net_payable": net_payable,
                "is_final": period.status.value in ("filed", "paid"),
            }
        )
    return {
        "as_of_date": as_of_date.isoformat(),
        "upcoming_vat_payments": rows,
        "is_estimate": True,
        "disclaimer": "Figures for periods not yet filed are estimates based on transactions posted so far and will "
        "change as more invoices are recorded for that period.",
    }


def tax_liability_forecast(db: Session, company_id: int, horizon_months: int = 3, reference_date: date | None = None) -> dict:
    """Corporate income tax is not tracked by this system -- only Dutch VAT.
    Never fabricates a corporate tax estimate; VAT is reported separately
    via vat_payment_forecast."""
    return {
        "forecast_horizon_months": horizon_months,
        "corporate_income_tax_estimate": None,
        "note": "Corporate income tax is not calculated by this system (Dutch VAT only) -- see vat_payment_forecast "
        "for the VAT position instead. No corporate tax figure is ever estimated or fabricated here.",
        "is_estimate": False,
    }


def full_forecast(db: Session, company_id: int, horizon_months: int = 3, reference_date: date | None = None) -> dict:
    """Assembles the cash-flow forecast (reused from Phase 6, never
    reimplemented) alongside the revenue/expense/profit, outstanding-invoice,
    and VAT forecasts added in this module."""
    reference_date = reference_date or date.today()
    return {
        "reference_date": reference_date.isoformat(),
        "cash_flow": build_cash_flow_forecast(db, company_id, horizon_months),
        "revenue_expense_profit": revenue_expense_profit_forecast(db, company_id, horizon_months, reference_date),
        "outstanding_invoices": outstanding_invoice_forecast(db, company_id, reference_date),
        "vat_payments": vat_payment_forecast(db, company_id, reference_date),
        "tax_liability": tax_liability_forecast(db, company_id, horizon_months, reference_date),
    }
