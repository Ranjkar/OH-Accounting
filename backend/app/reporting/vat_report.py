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


def render_pdf(data: dict) -> bytes:
    company: Company = data["company"]
    vat_return: VatReturn = data["vat_return"]
    period = data["period"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    pdf = PdfReportBuilder(
        title="VAT Return Report",
        company_name=f"{company.name} ({company.vat_number or 'no VAT number on file'})",
        subtitle=f"Period: {period.label} ({period.start_date} to {period.end_date}) - Status: {vat_return.status.value}",
        generated_at=generated,
    )

    pdf.heading("Declaration box breakdown")
    pdf.table(
        ["Box", "Description", "Net", "VAT"],
        [
            [
                code,
                label,
                str(data["box_totals"][code][0]) if data["box_totals"][code][0] is not None else "n/a",
                str(data["box_totals"][code][1]) if data["box_totals"][code][1] is not None else "n/a",
            ]
            for code, label, _, _ in BOX_ROWS
        ],
        col_widths=[40, 280, 90, 90],
    )
    pdf.key_value_row("5a - Total VAT payable", str(data["box_5a_vat"]))
    pdf.key_value_row("5b - Deductible input VAT", str(data["box_5b_vat"]))
    pdf.key_value_row("5g - Net VAT payable / refundable", str(data["net_payable"]), highlight=True)

    pdf.heading("Sales and purchase overview")
    pdf.key_value_row("Total sales (net)", str(data["sales_total_net"]))
    pdf.key_value_row("Total purchases (net)", str(data["purchases_total_net"]))

    pdf.heading("VAT by rate")
    for rate, amount in data["sales_vat_by_rate"].items():
        pdf.key_value_row(f"Sales VAT at {rate}%", str(amount))
    for rate, amount in data["purchase_vat_by_rate"].items():
        pdf.key_value_row(f"Purchase VAT at {rate}%", str(amount))

    pdf.heading("Reverse-charge overview")
    pdf.key_value_row("Reverse-charge / import / EU-acquisition lines", str(data["reverse_charge_line_count"]))
    pdf.key_value_row("Net amount", str(data["reverse_charge_net_total"]))

    pdf.heading("Input VAT summary (deductible, by eligibility)")
    for eligibility, amount in data["deductible_by_eligibility"].items():
        pdf.key_value_row(eligibility, str(amount))

    pdf.heading("Reconciliation findings")
    if not (data["pending_documents"] or data["duplicate_documents"] or data["validation_errors"] or data["unresolved_fx_transaction_ids"]):
        pdf.text("No outstanding issues.", color=(0.08, 0.5, 0.24))
    else:
        for d in data["pending_documents"]:
            pdf.text(f"Pending document: {d['original_filename']} ({d['status']})")
        for d in data["duplicate_documents"]:
            pdf.text(f"Duplicate document: {d['original_filename']}")
        for v in data["validation_errors"]:
            pdf.text(f"Validation error on document #{v['document_id']}: {v['message']}")
        for tid in data["unresolved_fx_transaction_ids"]:
            pdf.text(f"Transaction #{tid} needs an FX rate before inclusion")

    return pdf.to_bytes()


def render_xlsx(data: dict) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "VAT Return"
    ws.append(["OnHolland Accounting — VAT Return Report"])
    ws.append([f"Company: {data['company'].name} ({data['company'].vat_number or ''})"])
    ws.append([f"Period: {data['period'].label} ({data['period'].start_date} to {data['period'].end_date})"])
    ws.append([f"Status: {data['vat_return'].status.value}"])
    ws.append([])
    ws.append(["Box", "Description", "Net", "VAT"])
    for code, label, _, _ in BOX_ROWS:
        net, vat = data["box_totals"][code]
        ws.append([code, label, str(net) if net is not None else "", str(vat) if vat is not None else ""])
    ws.append([])
    ws.append(["5a", "Total VAT payable", "", str(data["box_5a_vat"])])
    ws.append(["5b", "Deductible input VAT", "", str(data["box_5b_vat"])])
    ws.append(["5g", "Net VAT payable / refundable", "", str(data["net_payable"])])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_csv(data: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["box", "description", "net", "vat"])
    for code, label, _, _ in BOX_ROWS:
        net, vat = data["box_totals"][code]
        writer.writerow([code, label, net if net is not None else "", vat if vat is not None else ""])
    writer.writerow(["5a", "Total VAT payable", "", data["box_5a_vat"]])
    writer.writerow(["5b", "Deductible input VAT", "", data["box_5b_vat"]])
    writer.writerow(["5g", "Net VAT payable / refundable", "", data["net_payable"]])
    return buf.getvalue().encode("utf-8")
