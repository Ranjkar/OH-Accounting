from pydantic import BaseModel, Field


class LineItemExtraction(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    net_amount: float | None = None
    vat_rate: float | None = None
    vat_amount: float | None = None
    gross_amount: float | None = None
    source_ref: str | None = None


class InvoiceExtraction(BaseModel):
    """Structured invoice fields as returned by the AI provider. Every field is
    optional — a missing value must stay null, never be guessed."""

    document_type: str | None = None
    classification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None

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

    line_items: list[LineItemExtraction] = Field(default_factory=list)
    field_sources: dict[str, str] = Field(default_factory=dict)
