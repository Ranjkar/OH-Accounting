"""Financial overview report: income/expense totals per VAT period within a
financial year (serves as the monthly/quarterly/annual comparison view),
payment status breakdown, and outstanding invoices -- all from ledger data."""

import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal

import openpyxl
from sqlalchemy.orm import Session

from app.accounting import payment_engine
from app.models.accounting import AccountingTransaction
from app.models.company import Company
from app.models.enums import LedgerSide, PaymentStatus
from app.models.financial_year import FinancialYear
from app.reporting.pdf_builder import PdfReportBuilder
from app.reporting.report_i18n import DEFAULT_LOCALE, t


def build_financial_overview_data(db: Session, company: Company, financial_year: FinancialYear) -> dict:
    transactions = (
        db.query(AccountingTransaction)
        .filter(AccountingTransaction.company_id == company.id, AccountingTransaction.financial_year_id == financial_year.id)
        .all()
    )

    periods_summary = []
    for period in sorted(financial_year.vat_periods, key=lambda p: p.start_date):
        period_tx = [t for t in transactions if t.vat_period_id == period.id]
        sales_net = sum((t.net_amount for t in period_tx if t.ledger_side == LedgerSide.sales), Decimal("0"))
        purchases_net = sum((t.net_amount for t in period_tx if t.ledger_side == LedgerSide.purchases), Decimal("0"))
        periods_summary.append(
            {
                "label": period.label,
                "sales_net": sales_net,
                "purchases_net": purchases_net,
                "income_minus_expense": sales_net - purchases_net,
                "transaction_count": len(period_tx),
            }
        )

    total_sales = sum((p["sales_net"] for p in periods_summary), Decimal("0"))
    total_purchases = sum((p["purchases_net"] for p in periods_summary), Decimal("0"))

    payment_status_counts: dict[str, int] = {}
    outstanding = []
    today = date.today()
    for t in transactions:
        payment_status_counts[t.payment_status.value] = payment_status_counts.get(t.payment_status.value, 0) + 1
        if t.payment_status in (PaymentStatus.unpaid, PaymentStatus.partially_paid, PaymentStatus.overdue):
            remaining = payment_engine.remaining_balance(t.gross_amount, t.payments)
            if remaining > 0:
                outstanding.append(
                    {
                        "transaction_id": t.id,
                        "counterparty_name": t.counterparty_name,
                        "invoice_number": t.invoice_number,
                        "due_date": str(t.due_date) if t.due_date else None,
                        "remaining_balance": remaining,
                        "payment_status": t.payment_status.value,
                    }
                )

    return {
        "company": company,
        "financial_year": financial_year,
        "periods_summary": periods_summary,
        "total_sales_net": total_sales,
        "total_purchases_net": total_purchases,
        "net_income": total_sales - total_purchases,
        "payment_status_counts": payment_status_counts,
        "outstanding_invoices": sorted(outstanding, key=lambda o: o["due_date"] or ""),
        "generated_at": today,
    }


def render_pdf(data: dict, locale: str = DEFAULT_LOCALE) -> bytes:
    """See vat_report.render_pdf's docstring for the general rule: only
    report prose/labels change with `locale`, never amounts, enum
    values, or identifiers."""
    company: Company = data["company"]
    fy: FinancialYear = data["financial_year"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ns = "financialOverview"

    pdf = PdfReportBuilder(
        title=t(locale, ns, "title"),
        company_name=f"{company.name} ({company.vat_number or t(locale, 'common', 'no_vat_number')})",
        subtitle=t(locale, ns, "subtitle", year=fy.year, start=fy.start_date, end=fy.end_date),
        generated_at=generated,
        locale=locale,
    )

    pdf.heading(t(locale, ns, "income_expense_heading"))
    pdf.table(
        [t(locale, ns, "col_period"), t(locale, ns, "col_sales_net"), t(locale, ns, "col_purchases_net"), t(locale, ns, "col_net"), t(locale, ns, "col_txns")],
        [
            [p["label"], str(p["sales_net"]), str(p["purchases_net"]), str(p["income_minus_expense"]), str(p["transaction_count"])]
            for p in data["periods_summary"]
        ],
        col_widths=[80, 110, 110, 110, 60],
    )
    pdf.key_value_row(t(locale, ns, "total_sales_net"), str(data["total_sales_net"]))
    pdf.key_value_row(t(locale, ns, "total_purchases_net"), str(data["total_purchases_net"]))
    pdf.key_value_row(t(locale, ns, "net_income"), str(data["net_income"]), highlight=True)

    pdf.heading(t(locale, ns, "payment_status_heading"))
    for status, count in data["payment_status_counts"].items():
        pdf.key_value_row(status, str(count))

    pdf.heading(t(locale, ns, "outstanding_invoices_heading"))
    if not data["outstanding_invoices"]:
        pdf.text(t(locale, ns, "no_outstanding_invoices"), color=(0.08, 0.5, 0.24))
    else:
        na = t(locale, "common", "na")
        pdf.table(
            [t(locale, ns, "col_counterparty"), t(locale, ns, "col_invoice_number"), t(locale, ns, "col_due_date"), t(locale, ns, "col_remaining"), t(locale, ns, "col_status")],
            [
                [
                    o["counterparty_name"] or na,
                    o["invoice_number"] or na,
                    o["due_date"] or na,
                    str(o["remaining_balance"]),
                    o["payment_status"],
                ]
                for o in data["outstanding_invoices"]
            ],
            col_widths=[150, 90, 90, 90, 80],
        )

    return pdf.to_bytes()


def render_xlsx(data: dict, locale: str = DEFAULT_LOCALE) -> bytes:
    ns = "financialOverview"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = t(locale, ns, "sheet_overview")
    ws.append([f"OnHolland Accounting — {t(locale, ns, 'title')}"])
    ws.append([f"{data['company'].name}"])
    ws.append([t(locale, ns, "subtitle", year=data["financial_year"].year, start=data["financial_year"].start_date, end=data["financial_year"].end_date)])
    ws.append([])
    ws.append([t(locale, ns, "col_period"), t(locale, ns, "col_sales_net"), t(locale, ns, "col_purchases_net"), t(locale, ns, "col_net"), t(locale, ns, "col_txns")])
    for p in data["periods_summary"]:
        # Real numeric cell types (Decimal/int), not str() -- so Excel
        # can sum/format these columns, not just display them as text.
        ws.append([p["label"], p["sales_net"], p["purchases_net"], p["income_minus_expense"], p["transaction_count"]])
    ws.append([])
    ws.append([t(locale, ns, "total_sales_net"), data["total_sales_net"]])
    ws.append([t(locale, ns, "total_purchases_net"), data["total_purchases_net"]])
    ws.append([t(locale, ns, "net_income"), data["net_income"]])

    ws2 = wb.create_sheet(t(locale, ns, "sheet_outstanding"))
    ws2.append([t(locale, ns, "col_counterparty"), t(locale, ns, "col_invoice_number"), t(locale, ns, "col_due_date"), t(locale, ns, "col_remaining"), t(locale, ns, "col_status")])
    for o in data["outstanding_invoices"]:
        ws2.append([o["counterparty_name"], o["invoice_number"], o["due_date"], o["remaining_balance"], o["payment_status"]])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_csv(data: dict) -> bytes:
    """Headers stay in their stable, canonical snake_case form (never
    translated) -- this format is for machine import/export, not for
    reading, see the Phase 16.2 report's CSV section. UTF-8 BOM prefix
    so Excel (particularly on Windows, in any non-English locale)
    correctly auto-detects UTF-8 instead of mis-decoding accented
    counterparty names as Windows-1252."""
    buf = io.StringIO()
    buf.write("﻿")
    writer = csv.writer(buf)
    writer.writerow(["period", "sales_net", "purchases_net", "net", "transaction_count"])
    for p in data["periods_summary"]:
        writer.writerow([p["label"], p["sales_net"], p["purchases_net"], p["income_minus_expense"], p["transaction_count"]])
    writer.writerow([])
    writer.writerow(["outstanding_invoices"])
    writer.writerow(["counterparty", "invoice_number", "due_date", "remaining_balance", "payment_status"])
    for o in data["outstanding_invoices"]:
        writer.writerow([o["counterparty_name"], o["invoice_number"], o["due_date"], o["remaining_balance"], o["payment_status"]])
    return buf.getvalue().encode("utf-8")
