"""VAT return report: summary, box breakdown, sales/purchase overview, input
VAT summary, reverse-charge overview, and reconciliation findings -- all in
one professionally formatted document, generated purely from database
records (never from AI output)."""

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

import openpyxl
from sqlalchemy.orm import Session

from app.accounting import reconciliation
from app.models.accounting import AccountingTransaction, VatReturn
from app.models.company import Company
from app.models.enums import InputVatEligibility, LedgerSide
from app.reporting.pdf_builder import PdfReportBuilder
from app.reporting.report_i18n import DEFAULT_LOCALE, box_description, t

BOX_ROWS = [
    ("1a", "Domestic sales, high rate (21%)", "box_1a_net", "box_1a_vat"),
    ("1b", "Domestic sales, low rate (9%)", "box_1b_net", "box_1b_vat"),
    ("1c", "Domestic sales, other rate", "box_1c_net", "box_1c_vat"),
    ("1d", "Private use correction", None, "box_1d_vat"),
    ("1e", "Domestic zero-rated / exempt sales", "box_1e_net", None),
    ("2a", "Domestic reverse-charge received", "box_2a_net", "box_2a_vat"),
    ("3a", "Export (outside EU)", "box_3a_net", None),
    ("3b", "EU supply", "box_3b_net", None),
    ("3c", "EU distance sale", "box_3c_net", None),
    ("4a", "Import (outside EU)", "box_4a_net", "box_4a_vat"),
    ("4b", "EU acquisition", "box_4b_net", "box_4b_vat"),
]


def build_vat_report_data(db: Session, vat_return: VatReturn, company: Company) -> dict:
    period = vat_return.vat_period
    recon = reconciliation.build_reconciliation(db, company.id, period)

    transactions = (
        db.query(AccountingTransaction)
        .filter(AccountingTransaction.company_id == company.id, AccountingTransaction.vat_period_id == period.id)
        .all()
    )
    reverse_charge_lines = [
        line
        for t in transactions
        if t.ledger_side == LedgerSide.purchases
        for line in t.line_items
        if line.vat_treatment.value in ("DOMESTIC_REVERSE_CHARGE_RECEIVED", "IMPORT_NON_EU", "EU_ACQUISITION")
    ]
    deductible_by_eligibility: dict[str, Decimal] = {}
    for t in transactions:
        if t.ledger_side != LedgerSide.purchases:
            continue
        for line in t.line_items:
            key = line.input_vat_eligibility.value if line.input_vat_eligibility else "NOT_SET"
            deductible_by_eligibility[key] = deductible_by_eligibility.get(key, Decimal("0")) + (line.deductible_vat_amount or Decimal("0"))

    return {
        "company": company,
        "vat_return": vat_return,
        "period": period,
        "box_totals": {
            "1a": (vat_return.box_1a_net, vat_return.box_1a_vat),
            "1b": (vat_return.box_1b_net, vat_return.box_1b_vat),
            "1c": (vat_return.box_1c_net, vat_return.box_1c_vat),
            "1d": (None, vat_return.box_1d_vat),
            "1e": (vat_return.box_1e_net, None),
            "2a": (vat_return.box_2a_net, vat_return.box_2a_vat),
            "3a": (vat_return.box_3a_net, None),
            "3b": (vat_return.box_3b_net, None),
            "3c": (vat_return.box_3c_net, None),
            "4a": (vat_return.box_4a_net, vat_return.box_4a_vat),
            "4b": (vat_return.box_4b_net, vat_return.box_4b_vat),
        },
        "box_5a_vat": vat_return.box_5a_vat,
        "box_5b_vat": vat_return.box_5b_vat,
        "net_payable": vat_return.net_payable,
        "sales_total_net": recon["sales_total_net"],
        "purchases_total_net": recon["purchases_total_net"],
        "sales_vat_by_rate": recon["sales_vat_by_rate"],
        "purchase_vat_by_rate": recon["purchase_vat_by_rate"],
        "reverse_charge_line_count": len(reverse_charge_lines),
        "reverse_charge_net_total": sum((l.net_amount for l in reverse_charge_lines), Decimal("0")),
        "deductible_by_eligibility": deductible_by_eligibility,
        "pending_documents": recon["pending_documents"],
        "duplicate_documents": recon["duplicate_documents"],
        "validation_errors": recon["validation_errors"],
        "unresolved_fx_transaction_ids": recon["unresolved_fx_transaction_ids"],
    }


def render_pdf(data: dict, locale: str = DEFAULT_LOCALE) -> bytes:
    """`locale` only changes the surrounding report prose/labels (see
    report_i18n.VAT_REPORT) -- box codes, VAT percentages, enum values,
    company/customer names and all amounts are never translated, and the
    Dutch-language version remains the canonical one actually filed with
    the Belastingdienst."""
    company: Company = data["company"]
    vat_return: VatReturn = data["vat_return"]
    period = data["period"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    pdf = PdfReportBuilder(
        title=t(locale, "vat", "title"),
        company_name=f"{company.name} ({company.vat_number or t(locale, 'common', 'no_vat_number')})",
        subtitle=t(locale, "vat", "period_label", label=period.label, start=period.start_date, end=period.end_date, status=vat_return.status.value),
        generated_at=generated,
        locale=locale,
    )

    pdf.heading(t(locale, "vat", "box_breakdown_heading"))
    pdf.table(
        [t(locale, "vat", "col_box"), t(locale, "vat", "col_description"), t(locale, "vat", "col_net"), t(locale, "vat", "col_vat")],
        [
            [
                code,
                box_description(locale, code),
                str(data["box_totals"][code][0]) if data["box_totals"][code][0] is not None else t(locale, "common", "na"),
                str(data["box_totals"][code][1]) if data["box_totals"][code][1] is not None else t(locale, "common", "na"),
            ]
            for code, _, _, _ in BOX_ROWS
        ],
        col_widths=[40, 280, 90, 90],
    )
    pdf.key_value_row(t(locale, "vat", "box_5a"), str(data["box_5a_vat"]))
    pdf.key_value_row(t(locale, "vat", "box_5b"), str(data["box_5b_vat"]))
    pdf.key_value_row(t(locale, "vat", "box_5g"), str(data["net_payable"]), highlight=True)

    pdf.heading(t(locale, "vat", "sales_purchase_heading"))
    pdf.key_value_row(t(locale, "vat", "total_sales_net"), str(data["sales_total_net"]))
    pdf.key_value_row(t(locale, "vat", "total_purchases_net"), str(data["purchases_total_net"]))

    pdf.heading(t(locale, "vat", "vat_by_rate_heading"))
    for rate, amount in data["sales_vat_by_rate"].items():
        pdf.key_value_row(t(locale, "vat", "sales_vat_at", rate=rate), str(amount))
    for rate, amount in data["purchase_vat_by_rate"].items():
        pdf.key_value_row(t(locale, "vat", "purchase_vat_at", rate=rate), str(amount))

    pdf.heading(t(locale, "vat", "reverse_charge_heading"))
    pdf.key_value_row(t(locale, "vat", "reverse_charge_lines"), str(data["reverse_charge_line_count"]))
    pdf.key_value_row(t(locale, "vat", "net_amount"), str(data["reverse_charge_net_total"]))

    pdf.heading(t(locale, "vat", "input_vat_heading"))
    for eligibility, amount in data["deductible_by_eligibility"].items():
        pdf.key_value_row(eligibility, str(amount))

    pdf.heading(t(locale, "vat", "reconciliation_heading"))
    if not (data["pending_documents"] or data["duplicate_documents"] or data["validation_errors"] or data["unresolved_fx_transaction_ids"]):
        pdf.text(t(locale, "vat", "no_outstanding_issues"), color=(0.08, 0.5, 0.24))
    else:
        for d in data["pending_documents"]:
            pdf.text(t(locale, "vat", "pending_document", name=d["original_filename"], status=d["status"]))
        for d in data["duplicate_documents"]:
            pdf.text(t(locale, "vat", "duplicate_document", name=d["original_filename"]))
        for v in data["validation_errors"]:
            pdf.text(t(locale, "vat", "validation_error", id=v["document_id"], message=v["message"]))
        for tid in data["unresolved_fx_transaction_ids"]:
            pdf.text(t(locale, "vat", "fx_needed", id=tid))

    return pdf.to_bytes()


def render_xlsx(data: dict, locale: str = DEFAULT_LOCALE) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = t(locale, "vat", "title")[:31]  # Excel sheet-name length limit
    ws.append([f"OnHolland Accounting — {t(locale, 'vat', 'title')}"])
    ws.append([f"{data['company'].name} ({data['company'].vat_number or t(locale, 'common', 'no_vat_number')})"])
    ws.append([t(locale, "vat", "period_label", label=data["period"].label, start=data["period"].start_date, end=data["period"].end_date, status=data["vat_return"].status.value)])
    ws.append([])
    ws.append([t(locale, "vat", "col_box"), t(locale, "vat", "col_description"), t(locale, "vat", "col_net"), t(locale, "vat", "col_vat")])
    for code, label, _, _ in BOX_ROWS:
        net, vat = data["box_totals"][code]
        # Real numeric cells (Decimal), not str(), where a value exists.
        ws.append([code, box_description(locale, code), net if net is not None else "", vat if vat is not None else ""])
    ws.append([])
    ws.append([t(locale, "vat", "box_5a"), "", "", data["box_5a_vat"]])
    ws.append([t(locale, "vat", "box_5b"), "", "", data["box_5b_vat"]])
    ws.append([t(locale, "vat", "box_5g"), "", "", data["net_payable"]])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_csv(data: dict) -> bytes:
    """Headers and box descriptions stay in their stable, canonical
    English form -- never translated, see financial_report.render_csv's
    docstring. UTF-8 BOM so Excel (any non-English locale, especially on
    Windows) correctly auto-detects UTF-8 instead of mis-decoding
    non-ASCII content as Windows-1252."""
    buf = io.StringIO()
    buf.write("﻿")
    writer = csv.writer(buf)
    writer.writerow(["box", "description", "net", "vat"])
    for code, label, _, _ in BOX_ROWS:
        net, vat = data["box_totals"][code]
        writer.writerow([code, label, net if net is not None else "", vat if vat is not None else ""])
    writer.writerow(["5a", "Total VAT payable", "", data["box_5a_vat"]])
    writer.writerow(["5b", "Deductible input VAT", "", data["box_5b_vat"]])
    writer.writerow(["5g", "Net VAT payable / refundable", "", data["net_payable"]])
    return buf.getvalue().encode("utf-8")
