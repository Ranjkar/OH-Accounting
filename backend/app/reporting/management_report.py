"""Phase 8 management-report exports (P&L, Balance Sheet, Budget vs Actual,
Scenario comparison). Reuses PdfReportBuilder and the openpyxl/csv pattern
from financial_report.py/vat_report.py rather than a new rendering engine.
Every report states company, period, generation timestamp, accounting
basis, and whether a figure is actual or forecast."""

import csv
import io
from datetime import datetime, timezone

import openpyxl

from app.models.company import Company
from app.reporting.pdf_builder import PdfReportBuilder


def _generated_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _header_lines(company: Company, period_label: str) -> list[str]:
    return [
        f"Company: {company.name} ({company.vat_number or 'no VAT number on file'})",
        f"Period: {period_label}",
        f"Accounting basis: {company.vat_accounting_basis.value}",
    ]


# ---- Profit and Loss ----


def render_pnl_pdf(company: Company, period_label: str, pnl: dict) -> bytes:
    pdf = PdfReportBuilder(
        title="Profit & Loss Statement", company_name=company.name, subtitle=period_label, generated_at=_generated_at()
    )
    pdf.heading("Summary (all figures actual, accrual basis)")
    rows = [
        ("Revenue", pnl["revenue"]), ("Cost of sales", pnl["cost_of_sales"]), ("Gross profit", pnl["gross_profit"]),
        ("Operating expenses", pnl["operating_expenses"]), ("Uncategorized expenses", pnl["uncategorized_expenses"]),
        ("Personnel expenses", pnl["personnel_expenses"]), ("EBITDA", pnl["ebitda"]), ("Depreciation", pnl["depreciation"]),
        ("EBIT", pnl["ebit"]), ("Interest expense", pnl["interest_expense"]), ("Profit before tax", pnl["profit_before_tax"]),
        ("Tax expense", pnl["tax_expense"]), ("Net profit", pnl["net_profit"]),
    ]
    for label, value in rows:
        pdf.key_value_row(label, str(value), highlight=label in ("Gross profit", "EBITDA", "EBIT", "Net profit"))
    pdf.text(pnl.get("tax_expense_note", ""), size=8)
    return pdf.to_bytes()


def render_pnl_xlsx(company: Company, period_label: str, pnl: dict) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Profit and Loss"
    ws.append(["OnHolland Accounting -- Profit & Loss Statement"])
    for line in _header_lines(company, period_label):
        ws.append([line])
    ws.append([f"Generated {_generated_at()}"])
    ws.append([])
    for label, key in [
        ("Revenue", "revenue"), ("Cost of sales", "cost_of_sales"), ("Gross profit", "gross_profit"),
        ("Operating expenses", "operating_expenses"), ("Uncategorized expenses", "uncategorized_expenses"),
        ("Personnel expenses", "personnel_expenses"), ("EBITDA", "ebitda"), ("Depreciation", "depreciation"),
        ("EBIT", "ebit"), ("Interest expense", "interest_expense"), ("Profit before tax", "profit_before_tax"),
        ("Tax expense", "tax_expense"), ("Net profit", "net_profit"),
    ]:
        ws.append([label, str(pnl[key])])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_pnl_csv(pnl: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["line", "amount"])
    for key in ("revenue", "cost_of_sales", "gross_profit", "operating_expenses", "uncategorized_expenses",
                "personnel_expenses", "ebitda", "depreciation", "ebit", "interest_expense", "profit_before_tax",
                "tax_expense", "net_profit"):
        writer.writerow([key, pnl[key]])
    return buf.getvalue().encode("utf-8")


# ---- Balance sheet ----


def render_balance_sheet_pdf(company: Company, as_of_label: str, bs: dict) -> bytes:
    pdf = PdfReportBuilder(title="Balance Sheet", company_name=company.name, subtitle=as_of_label, generated_at=_generated_at())
    pdf.heading("Assets")
    for label, value in bs["assets"].items():
        pdf.key_value_row(label.replace("_", " ").title(), str(value), highlight=label == "total")
    pdf.heading("Liabilities")
    for label, value in bs["liabilities"].items():
        pdf.key_value_row(label.replace("_", " ").title(), str(value), highlight=label == "total")
    pdf.heading("Equity")
    for label, value in bs["equity"].items():
        pdf.key_value_row(label.replace("_", " ").title(), str(value), highlight=label == "total")
    pdf.heading("Balance check")
    pdf.key_value_row("Balanced", "Yes" if bs["is_balanced"] else "NO -- see imbalance below", highlight=not bs["is_balanced"])
    pdf.key_value_row("Imbalance amount", str(bs["imbalance_amount"]))
    if bs.get("missing_opening_balance_warning"):
        pdf.text(bs["missing_opening_balance_warning"], size=8, color=(0.73, 0.11, 0.11))
    return pdf.to_bytes()


def render_balance_sheet_xlsx(company: Company, as_of_label: str, bs: dict) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Balance Sheet"
    ws.append(["OnHolland Accounting -- Balance Sheet"])
    ws.append([f"Company: {company.name}"])
    ws.append([as_of_label])
    ws.append([f"Generated {_generated_at()}"])
    for section in ("assets", "liabilities", "equity"):
        ws.append([])
        ws.append([section.title()])
        for label, value in bs[section].items():
            ws.append([label.replace("_", " ").title(), str(value)])
    ws.append([])
    ws.append(["Balanced", "Yes" if bs["is_balanced"] else "No"])
    ws.append(["Imbalance amount", str(bs["imbalance_amount"])])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_balance_sheet_csv(bs: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["section", "line", "amount"])
    for section in ("assets", "liabilities", "equity"):
        for label, value in bs[section].items():
            writer.writerow([section, label, value])
    writer.writerow(["", "is_balanced", bs["is_balanced"]])
    writer.writerow(["", "imbalance_amount", bs["imbalance_amount"]])
    return buf.getvalue().encode("utf-8")


# ---- Budget vs actual ----


def render_budget_vs_actual_pdf(company: Company, variance: dict) -> bytes:
    pdf = PdfReportBuilder(
        title="Budget vs Actual", company_name=company.name, subtitle=f"{variance['budget_name']} (v{variance['version']}, {variance['status']})",
        generated_at=_generated_at(),
    )
    pdf.heading("Lines (actual vs budgeted)")
    pdf.table(
        ["Category", "Month", "Budgeted", "Actual", "Variance"],
        [[row["category"], str(row["month"]), str(row["budgeted"]), str(row["actual"]), str(row["variance"])] for row in variance["lines"]],
        col_widths=[140, 50, 90, 90, 90],
    )
    pdf.key_value_row("Total budgeted", str(variance["total_budgeted"]))
    pdf.key_value_row("Total actual", str(variance["total_actual"]))
    pdf.key_value_row("Total variance", str(variance["total_variance"]), highlight=True)
    return pdf.to_bytes()


def render_budget_vs_actual_csv(variance: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["category", "month", "budgeted", "actual", "variance", "variance_pct"])
    for row in variance["lines"]:
        writer.writerow([row["category"], row["month"], row["budgeted"], row["actual"], row["variance"], row["variance_pct"]])
    writer.writerow([])
    writer.writerow(["total_budgeted", variance["total_budgeted"]])
    writer.writerow(["total_actual", variance["total_actual"]])
    writer.writerow(["total_variance", variance["total_variance"]])
    return buf.getvalue().encode("utf-8")


# ---- Scenario comparison ----


def render_scenario_comparison_csv(comparison: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["scenario", "total_forecast_profit", "scenario_net_cash_change"])
    for row in comparison["comparison"]:
        writer.writerow([row["name"], row["total_forecast_profit"], row["scenario_net_cash_change"]])
    return buf.getvalue().encode("utf-8")
