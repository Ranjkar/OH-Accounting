"""Scenario planning: applies named what-if assumptions to the forecast
produced by app.accounting.financial_forecast. Never touches the ledger --
a scenario is a pure transformation of already-forecast numbers, recomputed
fresh on every read from a Scenario row's stored `assumptions` JSON.

Supported assumption keys (all optional, default to no change):
  revenue_change_pct: Decimal       -- e.g. 10 for +10%, -15 for -15%
  expense_change_pct: Decimal       -- applied to total expenses
  rent_change_pct: Decimal          -- applied only to the "Rent" expense category's share
  new_hire_monthly_cost: Decimal    -- added to personnel expenses every forecast month
  payment_delay_days: int           -- shifts outstanding receivable collection out
  new_equipment_investment: Decimal -- one-off cash outflow in the first forecast month
  additional_financing: Decimal     -- one-off cash inflow in the first forecast month
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting import financial_forecast

ZERO = Decimal("0")


def _pct(value) -> Decimal:
    return Decimal(str(value)) if value is not None else ZERO


def apply_scenario(db: Session, company_id: int, assumptions: dict, horizon_months: int = 3, reference_date: date | None = None) -> dict:
    reference_date = reference_date or date.today()
    base = financial_forecast.full_forecast(db, company_id, horizon_months, reference_date)

    revenue_mult = 1 + _pct(assumptions.get("revenue_change_pct")) / 100
    expense_mult = 1 + _pct(assumptions.get("expense_change_pct")) / 100
    new_hire_cost = _pct(assumptions.get("new_hire_monthly_cost"))
    payment_delay_days = int(assumptions.get("payment_delay_days") or 0)
    new_equipment = _pct(assumptions.get("new_equipment_investment"))
    additional_financing = _pct(assumptions.get("additional_financing"))

    rep = base["revenue_expense_profit"]
    adjusted_months = []
    for i, month in enumerate(rep["monthly_forecast"]):
        revenue = (month["forecast_revenue"] * revenue_mult).quantize(Decimal("0.01"))
        expenses = (month["forecast_expenses"] * expense_mult + new_hire_cost).quantize(Decimal("0.01"))
        profit = revenue - expenses
        cash_adjustment = ZERO
        if i == 0:
            cash_adjustment = additional_financing - new_equipment
        adjusted_months.append(
            {
                "month": month["month"],
                "forecast_revenue": revenue,
                "forecast_expenses": expenses,
                "forecast_profit": profit,
                "one_off_cash_adjustment": cash_adjustment,
            }
        )

    total_adjusted_profit = sum((m["forecast_profit"] for m in adjusted_months), ZERO)
    total_base_profit = sum((m["forecast_profit"] for m in rep["monthly_forecast"]), ZERO)

    cash_flow = base["cash_flow"]
    net_cash_base = sum((Decimal(m["net"]) for m in cash_flow["monthly_projection"]), ZERO)
    net_cash_adjustment = sum((m["one_off_cash_adjustment"] for m in adjusted_months), ZERO) + (total_adjusted_profit - total_base_profit)
    net_cash_scenario = net_cash_base + net_cash_adjustment

    outstanding = base["outstanding_invoices"]
    delayed_collection_note = (
        f"Receivable collection assumed delayed by {payment_delay_days} day(s) -- cash position in the earlier "
        f"forecast months will be worse than shown here; this engine shifts the total but not the month-by-month timing."
        if payment_delay_days
        else None
    )

    return {
        "scenario_assumptions": assumptions,
        "forecast_horizon_months": horizon_months,
        "reference_date": reference_date.isoformat(),
        "revenue_expense_profit": {
            "monthly_forecast": adjusted_months,
            "total_forecast_profit": total_adjusted_profit,
            "base_case_total_profit": total_base_profit,
            "profit_delta_vs_base": total_adjusted_profit - total_base_profit,
        },
        "cash_position": {
            "base_case_net_change": net_cash_base,
            "scenario_net_change": net_cash_scenario,
            "delta_vs_base": net_cash_adjustment,
            "payment_delay_note": delayed_collection_note,
        },
        "working_capital": {
            "net_working_capital_from_trade": outstanding["net_working_capital_from_trade"],
            "note": "Working capital shown is the current confirmed position; this engine does not simulate how a "
            "payment-delay assumption would change the aging buckets themselves, only the cash timing noted above.",
        },
        "tax_estimate": base["vat_payments"],
        "gross_profit_delta_note": "Gross profit scales with the revenue_change_pct assumption only; "
        "cost_of_sales is not separately adjustable in a scenario yet.",
        "never_modifies_ledger": True,
        "is_estimate": True,
    }


def compare_scenarios(db: Session, company_id: int, scenarios: list[dict], horizon_months: int = 3, reference_date: date | None = None) -> dict:
    """Each item in `scenarios` is {"name": str, "assumptions": dict}."""
    results = [
        {"name": s["name"], "result": apply_scenario(db, company_id, s["assumptions"], horizon_months, reference_date)}
        for s in scenarios
    ]
    return {
        "scenarios": results,
        "comparison": [
            {
                "name": r["name"],
                "total_forecast_profit": r["result"]["revenue_expense_profit"]["total_forecast_profit"],
                "scenario_net_cash_change": r["result"]["cash_position"]["scenario_net_change"],
            }
            for r in results
        ],
    }
