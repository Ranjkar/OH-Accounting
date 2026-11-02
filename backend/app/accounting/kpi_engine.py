"""Transparent financial KPIs. Every function returns {value, formula,
source, period, explanation, missing_data} -- when the inputs needed for a
ratio are not available (e.g. no opening inventory, no fixed assets
recorded), `value` is None and `missing_data` explains why, rather than
showing a misleading number built on a silent zero."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting import financial_reports as fr

ZERO = Decimal("0")


def _kpi(value, formula: str, source: str, period: str, explanation: str, missing_data: str | None = None) -> dict:
    return {"value": value, "formula": formula, "source": source, "period": period, "explanation": explanation, "missing_data": missing_data}


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator * 100).quantize(Decimal("0.1"))


def profitability_kpis(db: Session, company_id: int, period: fr.DateRange) -> dict:
    pnl = fr.profit_and_loss(db, company_id, period)
    bs = fr.balance_sheet(db, company_id, period.end)
    period_label = f"{period.start} to {period.end}"

    gross_margin = _pct(pnl["gross_profit"], pnl["revenue"])
    operating_margin = _pct(pnl["ebit"], pnl["revenue"])
    net_margin = _pct(pnl["net_profit"], pnl["revenue"])
    roa = _pct(pnl["net_profit"], bs["assets"]["total"]) if bs["assets"]["total"] else None

    return {
        "gross_margin_pct": _kpi(
            gross_margin, "Gross profit / Revenue * 100", "profit_and_loss", period_label,
            "Share of revenue left after cost of sales.",
            None if pnl["revenue"] else "No revenue recorded in this period.",
        ),
        "operating_margin_pct": _kpi(
            operating_margin, "EBIT / Revenue * 100", "profit_and_loss", period_label,
            "Share of revenue left after all operating costs, before interest and tax.",
            None if pnl["revenue"] else "No revenue recorded in this period.",
        ),
        "net_profit_margin_pct": _kpi(
            net_margin, "Net profit / Revenue * 100", "profit_and_loss", period_label,
            "Share of revenue converted into net profit.",
            None if pnl["revenue"] else "No revenue recorded in this period.",
        ),
        "return_on_assets_pct": _kpi(
            roa, "Net profit / Total assets * 100", "profit_and_loss + balance_sheet", period_label,
            "Net profit generated per euro of total assets.",
            None if bs["assets"]["total"] else "No assets recorded as of the end of this period.",
        ),
    }


def liquidity_kpis(db: Session, company_id: int, as_of_date: date) -> dict:
    bs = fr.balance_sheet(db, company_id, as_of_date)
    period_label = f"as of {as_of_date}"
    current_assets = bs["assets"]["cash_and_bank"] + bs["assets"]["accounts_receivable"] + bs["assets"]["inventory"] + bs["assets"]["other_assets"]
    current_liabilities = bs["liabilities"]["accounts_payable"] + bs["liabilities"]["vat_payable"]
    quick_assets = current_assets - bs["assets"]["inventory"]

    def _ratio(numerator: Decimal) -> Decimal | None:
        return (numerator / current_liabilities).quantize(Decimal("0.01")) if current_liabilities else None

    no_liabilities_note = "No current liabilities recorded -- ratio is undefined, not infinite." if current_liabilities == 0 else None

    return {
        "current_ratio": _kpi(
            _ratio(current_assets),
            "Current assets / Current liabilities", "balance_sheet", period_label,
            "Ability to cover short-term liabilities with short-term assets. Above 1 is generally healthy.",
            no_liabilities_note,
        ),
        "quick_ratio": _kpi(
            _ratio(quick_assets),
            "(Current assets - Inventory) / Current liabilities", "balance_sheet", period_label,
            "Like the current ratio but excludes inventory, which is slower to convert to cash.",
            no_liabilities_note,
        ),
        "cash_ratio": _kpi(
            _ratio(bs["assets"]["cash_and_bank"]),
            "Cash and bank / Current liabilities", "balance_sheet", period_label,
            "Ability to cover short-term liabilities with cash on hand alone -- the most conservative liquidity measure.",
            no_liabilities_note,
        ),
    }


def efficiency_kpis(db: Session, company_id: int, period: fr.DateRange) -> dict:
    pnl = fr.profit_and_loss(db, company_id, period)
    ar = fr.debtors(db, company_id, period.end)["total_outstanding"]
    ap = fr.creditors(db, company_id, period.end)["total_outstanding"]
    days_in_period = max((period.end - period.start).days, 1)
    period_label = f"{period.start} to {period.end}"

    ar_days = (ar / pnl["revenue"] * days_in_period).quantize(Decimal("0.1")) if pnl["revenue"] else None
    total_purchases = pnl["cost_of_sales"] + pnl["operating_expenses"] + pnl["uncategorized_expenses"] + pnl["personnel_expenses"] + pnl["depreciation"] + pnl["interest_expense"]
    ap_days = (ap / total_purchases * days_in_period).quantize(Decimal("0.1")) if total_purchases else None

    return {
        "accounts_receivable_days": _kpi(
            ar_days, "Accounts receivable / Revenue * days in period", "balance_sheet + profit_and_loss", period_label,
            "Average number of days it takes to collect payment after a sale.",
            None if pnl["revenue"] else "No revenue recorded in this period.",
        ),
        "accounts_payable_days": _kpi(
            ap_days, "Accounts payable / Total purchases * days in period", "balance_sheet + profit_and_loss", period_label,
            "Average number of days taken to pay suppliers.",
            None if total_purchases else "No purchases recorded in this period.",
        ),
        "inventory_turnover": _kpi(
            None, "Cost of sales / Average inventory", "profit_and_loss + balance_sheet", period_label,
            "How many times inventory is sold and replaced over the period.",
            "Inventory turnover requires tracked inventory movements; this ledger only records a manually-entered "
            "inventory balance, not purchase/sale quantities, so this KPI cannot be computed.",
        ),
    }


def business_performance_kpis(db: Session, company_id: int, period: fr.DateRange) -> dict:
    current = fr.profit_and_loss(db, company_id, period)
    previous = fr.profit_and_loss(db, company_id, fr.previous_period(period))
    period_label = f"{period.start} to {period.end}"

    revenue_growth = _pct(current["revenue"] - previous["revenue"], previous["revenue"])
    current_expenses = current["cost_of_sales"] + current["operating_expenses"] + current["uncategorized_expenses"] + current["personnel_expenses"] + current["depreciation"] + current["interest_expense"]
    previous_expenses = previous["cost_of_sales"] + previous["operating_expenses"] + previous["uncategorized_expenses"] + previous["personnel_expenses"] + previous["depreciation"] + previous["interest_expense"]
    expense_growth = _pct(current_expenses - previous_expenses, previous_expenses)

    recurring = current["personnel_expenses"] + current["depreciation"] + current["interest_expense"]
    recurring_ratio = _pct(recurring, current_expenses) if current_expenses else None

    revenue_breakdown = fr.revenue_breakdown(db, company_id, period)
    top_customer_pct = revenue_breakdown[0]["pct_of_total"] if revenue_breakdown else None
    expense_breakdown = fr.expense_breakdown(db, company_id, period)
    top_supplier_pct = expense_breakdown[0]["pct_of_total"] if expense_breakdown else None

    return {
        "revenue_growth_pct": _kpi(
            revenue_growth, "(Revenue this period - Revenue previous period) / Revenue previous period * 100",
            "profit_and_loss", period_label, "Period-over-period revenue growth.",
            None if previous["revenue"] else "No revenue in the previous comparable period -- growth is undefined.",
        ),
        "expense_growth_pct": _kpi(
            expense_growth, "(Expenses this period - Expenses previous period) / Expenses previous period * 100",
            "profit_and_loss", period_label, "Period-over-period total expense growth.",
            None if previous_expenses else "No expenses in the previous comparable period -- growth is undefined.",
        ),
        "recurring_expense_ratio_pct": _kpi(
            recurring_ratio, "(Personnel + Depreciation + Interest) / Total expenses * 100", "profit_and_loss", period_label,
            "Share of expenses that are typically fixed/recurring rather than discretionary.",
            None if current_expenses else "No expenses recorded in this period.",
        ),
        "customer_concentration_top1_pct": _kpi(
            top_customer_pct, "Largest single customer's revenue / Total revenue * 100", "revenue_breakdown", period_label,
            "Revenue share from the single largest customer -- a high value means dependency risk.",
            "No sales transactions recorded in this period." if not revenue_breakdown else None,
        ),
        "supplier_concentration_top1_pct": _kpi(
            top_supplier_pct, "Largest expense category's total / Total expenses * 100", "expense_breakdown", period_label,
            "Spend share in the single largest expense category -- grouped by category, not by individual supplier name.",
            "No purchase transactions recorded in this period." if not expense_breakdown else None,
        ),
    }


def all_kpis(db: Session, company_id: int, period: fr.DateRange) -> dict:
    return {
        "profitability": profitability_kpis(db, company_id, period),
        "liquidity": liquidity_kpis(db, company_id, period.end),
        "efficiency": efficiency_kpis(db, company_id, period),
        "business_performance": business_performance_kpis(db, company_id, period),
    }
