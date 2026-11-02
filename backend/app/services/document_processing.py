"""Orchestrates the per-document processing pipeline: text/row extraction,
AI extraction (for PDFs/images), deterministic validation, and status transitions.

Runs in-process via FastAPI BackgroundTasks — no Celery/Redis. A single
document's OCR+AI round trip takes a few seconds; add a real task queue
if upload volume or multi-worker scaling later requires durability across
process restarts.
"""

import logging
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.document import (
    Document,
    DocumentExtraction,
    DocumentLineItem,
    DocumentProcessingAttempt,
    DocumentValidationResult,
    ExtractedInvoiceFields,
)
from app.models.enums import DocumentStatus, DocumentType, ProcessingAttemptStatus
from app.core.config import settings
from app.services import ai_provider, ocr_provider, storage, text_extraction
from app.services.file_validation import CONTENT_TYPES
from app.services.spreadsheet_parser import parse_rows
from app.services.validation_engine import validate_document

logger = logging.getLogger(__name__)

MIME_TO_KIND = {v: k for k, v in CONTENT_TYPES.items()}


class DocumentApprovedError(Exception):
    pass


def _parse_date(value: str | None) -> date | None:
    """The extraction prompt asks for ISO 8601, but tolerate common Dutch/EU
    DD-MM-YYYY output too rather than silently dropping a valid date."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        pass
    try:
        return datetime.strptime(value[:10], "%d-%m-%Y").date()
    except ValueError:
        return None


def _normalize_document_type(value: str | None) -> DocumentType | None:
    if not value:
        return None
    try:
        return DocumentType(value.upper())
    except ValueError:
        return DocumentType.other


def process_document(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise ValueError(f"Document {document_id} not found")
    if document.status == DocumentStatus.approved:
        raise DocumentApprovedError("Cannot reprocess an approved document")

    attempt_number = len(document.processing_attempts) + 1
    attempt = DocumentProcessingAttempt(
        document_id=document.id,
        attempt_number=attempt_number,
        status=ProcessingAttemptStatus.running,
    )
    document.status = DocumentStatus.processing
    db.add(attempt)
    db.commit()

    try:
        _run_pipeline(db, document, attempt)
    except Exception as exc:
        logger.warning("Document %s processing attempt %s failed", document.id, attempt_number)
        db.rollback()
        document = db.get(Document, document_id)
        attempt = db.get(DocumentProcessingAttempt, attempt.id)
        document.status = DocumentStatus.failed
        document.error_message = str(exc)[:2000]
        attempt.status = ProcessingAttemptStatus.failed
        attempt.error_message = str(exc)[:2000]
        attempt.finished_at = datetime.now(timezone.utc)
        db.commit()
    return document


def _run_pipeline(db: Session, document: Document, attempt: DocumentProcessingAttempt) -> None:
    content = storage.read(document.storage_path)
    kind = MIME_TO_KIND.get(document.content_type, "pdf")

    if kind in ("xlsx", "csv"):
        _process_spreadsheet(db, document, content, kind)
    else:
        _process_text_document(db, document, content, kind, attempt.attempt_number)

    findings = validate_document(document, document.fields)
    db.query(DocumentValidationResult).filter(DocumentValidationResult.document_id == document.id).delete()
    for finding in findings:
        db.add(
            DocumentValidationResult(
                document_id=document.id,
                rule_code=finding.rule_code,
                severity=finding.severity,
                message=finding.message,
            )
        )

    has_error = any(f.severity.value == "error" for f in findings)
    low_confidence = (
        document.classification_confidence is not None
        and document.classification_confidence < settings.extraction_confidence_threshold
    )
    if has_error or low_confidence:
        document.status = DocumentStatus.needs_review
    else:
        document.status = DocumentStatus.extracted

    document.processed_at = datetime.now(timezone.utc)
    attempt.status = ProcessingAttemptStatus.succeeded
    attempt.finished_at = datetime.now(timezone.utc)
    db.commit()


def _process_spreadsheet(db: Session, document: Document, content: bytes, kind: str) -> None:
    rows, doc_type = parse_rows(content, kind)
    document.document_type = doc_type
    document.classification_confidence = 1.0  # deterministic parse, not AI-classified

    db.query(DocumentLineItem).filter(DocumentLineItem.document_id == document.id).delete()
    for row in rows:
        db.add(
            DocumentLineItem(
                document_id=document.id,
                line_number=row["line_number"],
                description=row.get("description"),
                quantity=row.get("quantity"),
                unit_price=row.get("unit_price"),
                net_amount=row.get("net_amount"),
                vat_rate=row.get("vat_rate"),
                vat_amount=row.get("vat_amount"),
                gross_amount=row.get("gross_amount"),
                source_ref=row.get("source_ref"),
            )
        )
    db.flush()


def _process_text_document(db: Session, document: Document, content: bytes, kind: str, attempt_number: int) -> None:
    ocr = ocr_provider.get_ocr_provider()
    if kind == "pdf":
        text, _used_ocr = text_extraction.extract_pdf_text(content, ocr)
    else:
        text = text_extraction.extract_image_text(content, ocr)

    provider = ai_provider.get_ai_provider()
    extraction = provider.extract_invoice_fields(
        text, client_company_name=document.company.name, client_vat_number=document.company.vat_number
    )

    db.add(
        DocumentExtraction(
            document_id=document.id,
            attempt_number=attempt_number,
            provider=type(provider).__name__,
            model_name=getattr(settings, "anthropic_model", None),
            raw_response=extraction.model_dump(),
        )
    )

    document.document_type = _normalize_document_type(extraction.document_type)
    document.classification_confidence = extraction.classification_confidence

    fields = document.fields
    if fields is None:
        fields = ExtractedInvoiceFields(document_id=document.id)
        db.add(fields)

    fields.invoice_number = extraction.invoice_number
    fields.invoice_date = _parse_date(extraction.invoice_date)
    fields.due_date = _parse_date(extraction.due_date)
    fields.supplier_name = extraction.supplier_name
    fields.supplier_address = extraction.supplier_address
    fields.supplier_vat_number = extraction.supplier_vat_number
    fields.customer_name = extraction.customer_name
    fields.customer_vat_number = extraction.customer_vat_number
    fields.description = extraction.description
    fields.net_amount = extraction.net_amount
    fields.vat_rate = extraction.vat_rate
    fields.vat_amount = extraction.vat_amount
    fields.gross_amount = extraction.gross_amount
    fields.currency = extraction.currency
    fields.payment_terms = extraction.payment_terms
    fields.iban = extraction.iban
    fields.credit_note_reference = extraction.credit_note_reference
    fields.field_sources = extraction.field_sources
    fields.review_status = "pending"

    db.query(DocumentLineItem).filter(DocumentLineItem.document_id == document.id).delete()
    for i, item in enumerate(extraction.line_items, start=1):
        db.add(
            DocumentLineItem(
                document_id=document.id,
                line_number=i,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                net_amount=item.net_amount,
                vat_rate=item.vat_rate,
                vat_amount=item.vat_amount,
                gross_amount=item.gross_amount,
                source_ref=item.source_ref,
            )
        )
    db.flush()
