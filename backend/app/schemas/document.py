from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentStatus, DocumentType, LedgerSide, PaymentStatus, ValidationSeverity


class ValidationResultOut(BaseModel):
    rule_code: str
    severity: ValidationSeverity
    message: str

    model_config = ConfigDict(from_attributes=True)


class LineItemOut(BaseModel):
    line_number: int
    description: str | None
    quantity: float | None
    unit_price: float | None
    net_amount: float | None
    vat_rate: float | None
    vat_amount: float | None
    gross_amount: float | None
    source_ref: str | None

    model_config = ConfigDict(from_attributes=True)


class ExtractedFieldsOut(BaseModel):
    invoice_number: str | None
    invoice_date: date | None
    due_date: date | None
    supplier_name: str | None
    supplier_address: str | None
    supplier_vat_number: str | None
    customer_name: str | None
    customer_vat_number: str | None
    description: str | None
    net_amount: float | None
    vat_rate: float | None
    vat_amount: float | None
    gross_amount: float | None
    currency: str | None
    payment_terms: str | None
    iban: str | None
    credit_note_reference: str | None
    payment_status: PaymentStatus
    field_sources: dict[str, str] | None
    review_status: str
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ExtractedFieldsUpdate(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    supplier_name: str | None = None
    supplier_address: str | None = None
    supplier_vat_number: str | None = None
    customer_name: str | None = None
    customer_vat_number: str | None = None
    description: str | None = None
    net_amount: float | None = None
    vat_rate: float | None = None
    vat_amount: float | None = None
    gross_amount: float | None = None
    currency: str | None = None
    payment_terms: str | None = None
    iban: str | None = None
    credit_note_reference: str | None = None
    payment_status: PaymentStatus | None = None


class DocumentOut(BaseModel):
    id: int
    company_id: int
    financial_year_id: int | None
    original_filename: str
    content_type: str
    file_size: int
    status: DocumentStatus
    document_type: DocumentType | None
    classification_confidence: float | None
    is_duplicate: bool
    duplicate_of_document_id: int | None
    error_message: str | None
    created_at: datetime
    processed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailOut(DocumentOut):
    fields: ExtractedFieldsOut | None
    line_items: list[LineItemOut]
    validation_results: list[ValidationResultOut]


class RejectRequest(BaseModel):
    reason: str


class ApproveDocumentRequest(BaseModel):
    credit_note_ledger_side: LedgerSide | None = None  # required only when the document is a credit note


class ReassignRequest(BaseModel):
    company_id: int | None = None
    financial_year_id: int | None = None
