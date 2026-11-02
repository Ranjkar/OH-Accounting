from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import NoteStatus, NoteType, VatReturnStatus


class CompletenessRow(BaseModel):
    requirement: str
    complete: bool
    detail: str


class PeriodCompleteness(BaseModel):
    vat_period_id: int
    label: str
    start_date: date
    end_date: date
    filing_deadline: date
    vat_return_status: VatReturnStatus | None
    rows: list[CompletenessRow]


class NoteOut(BaseModel):
    id: int
    note_type: NoteType
    status: NoteStatus
    body: str
    related_entity_type: str | None
    related_entity_id: int | None
    author_user_id: int
    created_at: datetime
    resolved_at: datetime | None

    class Config:
        from_attributes = True


class CompanyWorkspace(BaseModel):
    company_id: int
    company_name: str
    vat_frequency: str
    vat_accounting_basis: str
    financial_year_count: int
    sales_invoice_count: int
    purchase_invoice_count: int
    transaction_count: int
    payment_count: int
    document_count: int
    documents_awaiting_approval: int
    open_notes: int
    open_customer_questions: int
    vat_returns: list[dict]
    period_completeness: list[PeriodCompleteness]
    notes: list[NoteOut]
