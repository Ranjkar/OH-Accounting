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
from app.reporting.report_i18n import DEFAULT_LOCALE, t

PNL_ROW_KEYS = [
    "revenue", "cost_of_sales", "gross_profit", "operating_expenses", "uncategorized_expenses",
    "personnel_expenses", "ebitda", "depreciation", "ebit", "interest_expense", "profit_before_tax",
    "tax_expense", "net_profit",
]
PNL_HIGHLIGHT_KEYS = {"gross_profit", "ebitda", "ebit", "net_profit"}


def _generated_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ---- Profit and Loss ----


def render_pnl_pdf(company: Company, period_label: str, pnl: dict, locale: str = DEFAULT_LOCALE) -> bytes:
    ns = "pnl"
    pdf = PdfReportBuilder(
        title=t(locale, ns, "title"), company_name=company.name, subtitle=period_label, generated_at=_generated_at(), locale=locale
    )
    pdf.heading(t(locale, ns, "summary_heading"))
    for key in PNL_ROW_KEYS:
        pdf.key_value_row(t(locale, ns, key), str(pnl[key]), highlight=key in PNL_HIGHLIGHT_KEYS)
    pdf.text(pnl.get("tax_expense_note", ""), size=8)
    return pdf.to_bytes()


def render_pnl_xlsx(company: Company, period_label: str, pnl: dict, locale: str = DEFAULT_LOCALE) -> bytes:
    ns = "pnl"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = t(locale, ns, "sheet_title")
    ws.append([f"OnHolland Accounting -- {t(locale, ns, 'title')}"])
    ws.append([f"{company.name} ({company.vat_number or t(locale, 'common', 'no_vat_number')})"])
    ws.append([period_label])
    ws.append([company.vat_accounting_basis.value])
    ws.append([])
    for key in PNL_ROW_KEYS:
        # Real numeric cell (Decimal), not str(), so Excel can sum/format it.
        ws.append([t(locale, ns, key), pnl[key]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_pnl_csv(pnl: dict) -> bytes:
    """Line-item keys stay their stable, canonical snake_case form --
    never translated, see financial_report.render_csv's docstring."""
    buf = io.StringIO()
    buf.write("﻿")
    writer = csv.writer(buf)
    writer.writerow(["line", "amount"])
    for key in PNL_ROW_KEYS:
        writer.writerow([key, pnl[key]])
    return buf.getvalue().encode("utf-8")


# ---- Balance sheet ----


def render_balance_sheet_pdf(company: Company, as_of_label: str, bs: dict, locale: str = DEFAULT_LOCALE) -> bytes:
    ns = "balanceSheet"
    pdf = PdfReportBuilder(title=t(locale, ns, "title"), company_name=company.name, subtitle=as_of_label, generated_at=_generated_at(), locale=locale)
    pdf.heading(t(locale, ns, "assets_heading"))
    for label, value in bs["assets"].items():
        pdf.key_value_row(t(locale, ns, label), str(value), highlight=label == "total")
    pdf.heading(t(locale, ns, "liabilities_heading"))
    for label, value in bs["liabilities"].items():
        pdf.key_value_row(t(locale, ns, label), str(value), highlight=label == "total")
    pdf.heading(t(locale, ns, "equity_heading"))
    for label, value in bs["equity"].items():
        pdf.key_value_row(t(locale, ns, label), str(value), highlight=label == "total")
    pdf.heading(t(locale, ns, "balance_check_heading"))
    pdf.key_value_row(t(locale, ns, "balanced_label"), t(locale, "common", "yes") if bs["is_balanced"] else t(locale, ns, "imbalance_label"), highlight=not bs["is_balanced"])
    pdf.key_value_row(t(locale, ns, "imbalance_amount_label"), str(bs["imbalance_amount"]))
    if bs.get("missing_opening_balance_warning"):
        pdf.text(bs["missing_opening_balance_warning"], size=8, color=(0.73, 0.11, 0.11))
    return pdf.to_bytes()


def render_balance_sheet_xlsx(company: Company, as_of_label: str, bs: dict, locale: str = DEFAULT_LOCALE) -> bytes:
    ns = "balanceSheet"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = t(locale, ns, "sheet_title")
    ws.append([f"OnHolland Accounting -- {t(locale, ns, 'title')}"])
    ws.append([company.name])
    ws.append([as_of_label])
    for section, heading_key in (("assets", "assets_heading"), ("liabilities", "liabilities_heading"), ("equity", "equity_heading")):
        ws.append([])
        ws.append([t(locale, ns, heading_key)])
        for label, value in bs[section].items():
            # Real numeric cell (Decimal), not str().
            ws.append([t(locale, ns, label), value])
    ws.append([])
    ws.append([t(locale, ns, "balanced_label"), t(locale, "common", "yes") if bs["is_balanced"] else t(locale, "common", "no")])
    ws.append([t(locale, ns, "imbalance_amount_label"), bs["imbalance_amount"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_balance_sheet_csv(bs: dict) -> bytes:
    buf = io.StringIO()
    buf.write("﻿")
    writer = csv.writer(buf)
    writer.writerow(["section", "line", "amount"])
    for section in ("assets", "liabilities", "equity"):
        for label, value in bs[section].items():
            writer.writerow([section, label, value])
    writer.writerow(["", "is_balanced", bs["is_balanced"]])
    writer.writerow(["", "imbalance_amount", bs["imbalance_amount"]])
    return buf.getvalue().encode("utf-8")


# ---- Budget vs actual ----


def render_budget_vs_actual_pdf(company: Company, variance: dict, locale: str = DEFAULT_LOCALE) -> bytes:
    ns = "budgetVsActual"
    pdf = PdfReportBuilder(
        title=t(locale, ns, "title"), company_name=company.name, subtitle=f"{variance['budget_name']} (v{variance['version']}, {variance['status']})",
        generated_at=_generated_at(), locale=locale,
    )
    pdf.heading(t(locale, ns, "lines_heading"))
    pdf.table(
        [t(locale, ns, "col_category"), t(locale, ns, "col_month"), t(locale, ns, "col_budgeted"), t(locale, ns, "col_actual"), t(locale, ns, "col_variance")],
        [[row["category"], str(row["month"]), str(row["budgeted"]), str(row["actual"]), str(row["variance"])] for row in variance["lines"]],
        col_widths=[140, 50, 90, 90, 90],
    )
    pdf.key_value_row(t(locale, ns, "total_budgeted_label"), str(variance["total_budgeted"]))
    pdf.key_value_row(t(locale, ns, "total_actual_label"), str(variance["total_actual"]))
    pdf.key_value_row(t(locale, ns, "total_variance_label"), str(variance["total_variance"]), highlight=True)
    return pdf.to_bytes()


def render_budget_vs_actual_csv(variance: dict) -> bytes:
    buf = io.StringIO()
    buf.write("﻿")
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
    buf.write("﻿")
    writer = csv.writer(buf)
    writer.writerow(["scenario", "total_forecast_profit", "scenario_net_cash_change"])
    for row in comparison["comparison"]:
        writer.writerow([row["name"], row["total_forecast_profit"], row["scenario_net_cash_change"]])
    return buf.getvalue().encode("utf-8")
