"""Deterministic validation of extracted invoice fields.

This checks mathematical and structural consistency only. It never judges
legal VAT deductibility — that is an accountant/Phase 3 decision, not
something this engine or the AI infers.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.accounting.ledger_service import LEDGER_SIDE_BY_DOCUMENT_TYPE
from app.models.document import Document, ExtractedInvoiceFields
from app.models.enums import DocumentType, ValidationSeverity

AMOUNT_TOLERANCE = 0.02
VALID_NL_VAT_RATES = {0.0, 9.0, 21.0}
CURRENCY_ALLOWLIST = {"EUR", "USD", "GBP"}


@dataclass(frozen=True)
class ValidationFinding:
    rule_code: str
    severity: ValidationSeverity
    message: str


def validate_document(document: Document, fields: ExtractedInvoiceFields | None) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []

    if document.is_duplicate:
        findings.append(
            ValidationFinding(
                "DUPLICATE_DOCUMENT",
                ValidationSeverity.error,
                f"This file matches document #{document.duplicate_of_document_id} already on record.",
            )
        )

    if fields is None:
        return findings

    net, vat, gross = fields.net_amount, fields.vat_amount, fields.gross_amount

    if net is not None and vat is not None and gross is not None:
        if abs((net + vat) - gross) > AMOUNT_TOLERANCE:
            findings.append(
                ValidationFinding(
                    "AMOUNT_MISMATCH",
                    ValidationSeverity.error,
                    f"Net ({net}) + VAT ({vat}) does not equal gross ({gross}).",
                )
            )
    elif gross is None or net is None or vat is None:
        findings.append(
            ValidationFinding(
                "MISSING_VAT_BREAKDOWN",
                ValidationSeverity.warning,
                "Net, VAT and gross amount are not all present.",
            )
        )

    if net is not None and vat is not None and fields.vat_rate is not None and net != 0:
        expected_vat = net * (fields.vat_rate / 100)
        if abs(expected_vat - vat) > max(AMOUNT_TOLERANCE, abs(net) * 0.005):
            findings.append(
                ValidationFinding(
                    "VAT_RATE_INCONSISTENT",
                    ValidationSeverity.warning,
                    f"VAT amount ({vat}) does not match {fields.vat_rate}% of net ({net}).",
                )
            )

    if fields.vat_rate is not None and fields.vat_rate not in VALID_NL_VAT_RATES:
        findings.append(
            ValidationFinding(
                "UNUSUAL_VAT_RATE",
                ValidationSeverity.info,
                f"VAT rate {fields.vat_rate}% is not a standard Dutch rate (0%, 9%, 21%); "
                "may be reverse-charge, EU, or non-NL.",
            )
        )

    if document.document_type in (DocumentType.sales_invoice, DocumentType.purchase_invoice):
        if not fields.invoice_number:
            findings.append(
                ValidationFinding(
                    "MISSING_INVOICE_NUMBER",
                    ValidationSeverity.error,
                    "Invoice number is required for sales and purchase invoices.",
                )
            )

    if document.document_type == DocumentType.credit_note and not fields.credit_note_reference:
        findings.append(
            ValidationFinding(
                "MISSING_CREDIT_NOTE_REFERENCE",
                ValidationSeverity.warning,
                "Credit note has no reference to the original invoice.",
            )
        )

    if fields.invoice_date and fields.due_date:
        try:
            inv_date = _as_date(fields.invoice_date)
            due_date = _as_date(fields.due_date)
            if due_date < inv_date:
                findings.append(
                    ValidationFinding(
                        "DUE_DATE_BEFORE_INVOICE_DATE",
                        ValidationSeverity.error,
                        f"Due date ({due_date}) is before invoice date ({inv_date}).",
                    )
                )
        except (ValueError, TypeError):
            findings.append(
                ValidationFinding(
                    "INVALID_DATE", ValidationSeverity.error, "Invoice date or due date is not a valid date."
                )
            )

    if fields.currency and fields.currency.upper() not in CURRENCY_ALLOWLIST:
        findings.append(
            ValidationFinding(
                "UNRECOGNIZED_CURRENCY",
                ValidationSeverity.info,
                f"Currency '{fields.currency}' is not in the common allow-list; verify manually.",
            )
        )

    if fields.supplier_name and fields.customer_name and fields.supplier_name == fields.customer_name:
        findings.append(
            ValidationFinding(
                "SUPPLIER_CUSTOMER_IDENTICAL",
                ValidationSeverity.warning,
                "Supplier and customer name are identical.",
            )
        )

    if document.upload_category is not None and document.document_type is not None:
        expected_side = LEDGER_SIDE_BY_DOCUMENT_TYPE.get(document.document_type)
        if expected_side is not None and expected_side != document.upload_category:
            findings.append(
                ValidationFinding(
                    "UPLOAD_CATEGORY_MISMATCH",
                    ValidationSeverity.error,
                    f"Uploaded via the {document.upload_category.value.lower()} screen, but this document reads "
                    f"as a {expected_side.value.lower()}-side {document.document_type.value}. "
                    "Verify which company is the supplier and which is the customer before approving.",
                )
            )

    return findings


# Business-duplicate matching: same counterparty + invoice number/date/amount
# on a different physical file. A warning, never an auto-reject -- two
# genuinely different documents can share these fields by coincidence.
BUSINESS_DUPLICATE_AMOUNT_TOLERANCE = 0.01


def check_business_duplicate(db: Session, document: Document, fields: ExtractedInvoiceFields) -> ValidationFinding | None:
    if not fields.invoice_number or fields.gross_amount is None:
        return None

    counterparty_vat = fields.supplier_vat_number or fields.customer_vat_number
    candidates = (
        db.query(Document)
        .join(ExtractedInvoiceFields, ExtractedInvoiceFields.document_id == Document.id)
        .filter(
            Document.company_id == document.company_id,
            Document.id != document.id,
            ExtractedInvoiceFields.invoice_number == fields.invoice_number,
        )
        .all()
    )
    for other in candidates:
        other_fields = other.fields
        if other_fields is None or other_fields.gross_amount is None:
            continue
        if abs(other_fields.gross_amount - fields.gross_amount) > BUSINESS_DUPLICATE_AMOUNT_TOLERANCE:
            continue
        other_vat = other_fields.supplier_vat_number or other_fields.customer_vat_number
        if counterparty_vat and other_vat and counterparty_vat != other_vat:
            continue
        if fields.invoice_date and other_fields.invoice_date and fields.invoice_date != other_fields.invoice_date:
            continue
        return ValidationFinding(
            "POTENTIAL_BUSINESS_DUPLICATE",
            ValidationSeverity.warning,
            f"Document #{other.id} ({other.original_filename}) has the same invoice number, counterparty, "
            f"and amount. Verify this is not a duplicate before approving.",
        )
    return None


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)
