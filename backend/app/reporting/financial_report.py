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


def render_pdf(data: dict) -> bytes:
    company: Company = data["company"]
    fy: FinancialYear = data["financial_year"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    pdf = PdfReportBuilder(
        title="Financial Overview Report",
        company_name=f"{company.name} ({company.vat_number or 'no VAT number on file'})",
        subtitle=f"Financial year {fy.year} ({fy.start_date} to {fy.end_date})",
        generated_at=generated,
    )

    pdf.heading("Income and expense overview, by period")
    pdf.table(
        ["Period", "Sales (net)", "Purchases (net)", "Net", "Txns"],
        [
            [p["label"], str(p["sales_net"]), str(p["purchases_net"]), str(p["income_minus_expense"]), str(p["transaction_count"])]
            for p in data["periods_summary"]
        ],
        col_widths=[80, 110, 110, 110, 60],
    )
    pdf.key_value_row("Total sales (net)", str(data["total_sales_net"]))
    pdf.key_value_row("Total purchases (net)", str(data["total_purchases_net"]))
    pdf.key_value_row("Net income", str(data["net_income"]), highlight=True)

    pdf.heading("Payment status")
    for status, count in data["payment_status_counts"].items():
        pdf.key_value_row(status, str(count))

    pdf.heading("Outstanding invoices")
    if not data["outstanding_invoices"]:
        pdf.text("No outstanding invoices.", color=(0.08, 0.5, 0.24))
    else:
        pdf.table(
            ["Counterparty", "Invoice #", "Due date", "Remaining", "Status"],
            [
                [
                    o["counterparty_name"] or "n/a",
                    o["invoice_number"] or "n/a",
                    o["due_date"] or "n/a",
                    str(o["remaining_balance"]),
                    o["payment_status"],
                ]
                for o in data["outstanding_invoices"]
            ],
            col_widths=[150, 90, 90, 90, 80],
        )

    return pdf.to_bytes()


def render_xlsx(data: dict) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Overview"
    ws.append(["OnHolland Accounting — Financial Overview Report"])
    ws.append([f"Company: {data['company'].name}"])
    ws.append([f"Financial year: {data['financial_year'].year}"])
    ws.append([])
    ws.append(["Period", "Sales (net)", "Purchases (net)", "Net", "Transactions"])
    for p in data["periods_summary"]:
        ws.append([p["label"], str(p["sales_net"]), str(p["purchases_net"]), str(p["income_minus_expense"]), p["transaction_count"]])
    ws.append([])
    ws.append(["Total sales (net)", str(data["total_sales_net"])])
    ws.append(["Total purchases (net)", str(data["total_purchases_net"])])
    ws.append(["Net income", str(data["net_income"])])

    ws2 = wb.create_sheet("Outstanding invoices")
    ws2.append(["Counterparty", "Invoice #", "Due date", "Remaining balance", "Status"])
    for o in data["outstanding_invoices"]:
        ws2.append([o["counterparty_name"], o["invoice_number"], o["due_date"], str(o["remaining_balance"]), o["payment_status"]])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_csv(data: dict) -> bytes:
    buf = io.StringIO()
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
