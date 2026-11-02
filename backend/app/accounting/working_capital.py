"""Working capital and payment-behavior intelligence, extending Phase 6's
payment reconciliation (app.accounting.reconciliation_service /
app.accounting.matching_engine) and app.accounting.financial_reports'
debtors/creditors. Read-only: never initiates a payment or a collection
action."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting import financial_reports as fr
from app.models.accounting import AccountingTransaction
from app.models.enums import LedgerSide

ZERO = Decimal("0")
OVERDUE_ALERT_DAYS = 7


def customer_payment_behavior(db: Session, company_id: int, period: fr.DateRange) -> list[dict]:
    """Average days-to-pay per customer, from invoice_date to the date each
    invoice was fully settled. Only invoices paid in full are counted --
    partially-paid invoices have no settlement date yet."""
    sales = (
        db.query(AccountingTransaction)
        .filter(
            AccountingTransaction.company_id == company_id,
            AccountingTransaction.ledger_side == LedgerSide.sales,
            AccountingTransaction.invoice_date >= period.start,
            AccountingTransaction.invoice_date <= period.end,
        )
        .all()
    )
    by_customer: dict[str, list[int]] = defaultdict(list)
    for t in sales:
        valid_payments = sorted((p for p in t.payments if not p.voided), key=lambda p: p.payment_date)
        if not valid_payments:
            continue
        paid_total = sum((p.amount for p in valid_payments), ZERO)
        if paid_total < t.gross_amount:
            continue
        settled_on = valid_payments[-1].payment_date
        by_customer[t.counterparty_name or "Unknown"].append((settled_on - t.invoice_date).days)

    return sorted(
        [
            {"counterparty_name": name, "invoices_settled": len(days), "average_days_to_pay": round(sum(days) / len(days), 1)}
            for name, days in by_customer.items()
        ],
        key=lambda r: r["average_days_to_pay"],
        reverse=True,
    )


def supplier_payment_trends(db: Session, company_id: int, period: fr.DateRange) -> list[dict]:
    purchases = (
        db.query(AccountingTransaction)
        .filter(
            AccountingTransaction.company_id == company_id,
            AccountingTransaction.ledger_side == LedgerSide.purchases,
            AccountingTransaction.invoice_date >= period.start,
            AccountingTransaction.invoice_date <= period.end,
        )
        .all()
    )
    by_supplier: dict[str, list[int]] = defaultdict(list)
    for t in purchases:
        valid_payments = sorted((p for p in t.payments if not p.voided), key=lambda p: p.payment_date)
        if not valid_payments:
            continue
        paid_total = sum((p.amount for p in valid_payments), ZERO)
        if paid_total < t.gross_amount:
            continue
        settled_on = valid_payments[-1].payment_date
        by_supplier[t.counterparty_name or "Unknown"].append((settled_on - t.invoice_date).days)

    return sorted(
        [
            {"counterparty_name": name, "invoices_settled": len(days), "average_days_to_pay": round(sum(days) / len(days), 1)}
            for name, days in by_supplier.items()
        ],
        key=lambda r: r["average_days_to_pay"],
        reverse=True,
    )


def payment_delay_alerts(db: Session, company_id: int, as_of_date: date) -> list[dict]:
    """Receivables newly overdue within the last OVERDUE_ALERT_DAYS, or
    aged into the worst (90+) bucket -- the two situations worth an
    accountant's immediate attention rather than routine aging."""
    result = fr.debtors(db, company_id, as_of_date)
    alerts = []
    for item in result["items"]:
        if item["aging_bucket"] == "90+":
            alerts.append({**item, "alert_reason": "Over 90 days overdue"})
        elif 0 < item["days_overdue"] <= OVERDUE_ALERT_DAYS:
            alerts.append({**item, "alert_reason": f"Newly overdue within the last {OVERDUE_ALERT_DAYS} days"})
    return alerts


def working_capital_trend(db: Session, company_id: int, periods: list[fr.DateRange]) -> list[dict]:
    trend = []
    for period in periods:
        ar = fr.debtors(db, company_id, period.end)["total_outstanding"]
        ap = fr.creditors(db, company_id, period.end)["total_outstanding"]
        trend.append({"period_end": period.end.isoformat(), "accounts_receivable": ar, "accounts_payable": ap, "net_working_capital": ar - ap})
    return trend


def cash_conversion_cycle(db: Session, company_id: int, period: fr.DateRange) -> dict:
    """DSO + DIO - DPO. Inventory days-outstanding (DIO) cannot be computed
    without tracked inventory movement (see kpi_engine.efficiency_kpis), so
    this is reported as unavailable rather than assuming zero inventory
    days, which would understate the real cycle."""
    from app.accounting import kpi_engine

    efficiency = kpi_engine.efficiency_kpis(db, company_id, period)
    dso = efficiency["accounts_receivable_days"]["value"]
    dpo = efficiency["accounts_payable_days"]["value"]

    return {
        "period_start": period.start.isoformat(),
        "period_end": period.end.isoformat(),
        "days_sales_outstanding": dso,
        "days_payable_outstanding": dpo,
        "days_inventory_outstanding": None,
        "cash_conversion_cycle_days": None,
        "missing_data": "Days inventory outstanding cannot be computed (no tracked inventory movement) -- the full "
        "cash conversion cycle is therefore not calculated rather than presented with inventory days assumed as zero.",
    }


def customer_concentration(db: Session, company_id: int, period: fr.DateRange, top_n: int = 5) -> dict:
    breakdown = fr.revenue_breakdown(db, company_id, period)
    return {
        "top_customers": breakdown[:top_n],
        "total_customers": len(breakdown),
        "missing_data": "No sales transactions in this period." if not breakdown else None,
    }


def supplier_dependency(db: Session, company_id: int, period: fr.DateRange, top_n: int = 5) -> dict:
    breakdown = fr.expense_breakdown(db, company_id, period)
    return {
        "top_expense_categories": breakdown[:top_n],
        "missing_data": "No purchase transactions in this period -- note this groups by expense category, not "
        "individual supplier, since suppliers are not a first-class entity in this ledger." if not breakdown else
        "Grouped by expense category, not individual supplier, since suppliers are not a first-class entity in this ledger.",
    }
