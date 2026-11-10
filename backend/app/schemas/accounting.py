from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    InputVatEligibility,
    LedgerSide,
    PaymentStatus,
    TransactionApprovalStatus,
    TransactionType,
    VatReturnStatus,
    VatTreatment,
)


class TransactionLineItemOut(BaseModel):
    line_number: int
    description: str | None
    net_amount: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    gross_amount: Decimal
    vat_treatment: VatTreatment
    input_vat_eligibility: InputVatEligibility | None
    deductible_vat_amount: Decimal | None

    model_config = ConfigDict(from_attributes=True)


class PaymentOut(BaseModel):
    id: int
    amount: Decimal
    payment_date: date
    reference: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentCreate(BaseModel):
    # Phase 19 (audit finding 8.8): `amount` had no bound at all, so a zero or
    # negative payment was accepted, committed, and fed into
    # payment_engine.compute_payment_status. A negative payment inflates
    # remaining_balance, can flip a settled invoice back to UNPAID, and
    # corrupts debtors/creditors aging, the cash-flow statement and DSO.
    # Correcting a wrongly-recorded payment is what the void path exists for
    # (reconciliation_service voids, never deletes) -- not a negative row.
    # Precision is left to the MONEY column (Numeric(14,2)) rather than being
    # re-specified here, so this constrains only what the finding requires.
    amount: Decimal = Field(gt=0)
    payment_date: date
    reference: str | None = None


class TransactionOut(BaseModel):
    id: int
    company_id: int
    financial_year_id: int
    vat_period_id: int | None
    source_document_id: int | None
    corrects_transaction_id: int | None
    transaction_type: TransactionType
    ledger_side: LedgerSide
    invoice_number: str | None
    counterparty_name: str | None
    counterparty_vat_number: str | None
    counterparty_country_code: str | None
    counterparty_iban: str | None
    invoice_date: date
    delivery_date: date | None
    due_date: date | None
    received_date: date | None
    currency: str
    fx_rate_to_eur: Decimal | None
    net_amount: Decimal
    vat_amount: Decimal
    gross_amount: Decimal
    net_amount_eur: Decimal | None
    vat_amount_eur: Decimal | None
    gross_amount_eur: Decimal | None
    payment_status: PaymentStatus
    approval_status: TransactionApprovalStatus
    accounting_classification: str | None
    expense_category: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionDetailOut(TransactionOut):
    line_items: list[TransactionLineItemOut]
    payments: list[PaymentOut]
    amount_paid: Decimal
    remaining_balance: Decimal


class ManualLineItemIn(BaseModel):
    description: str | None = None
    net_amount: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    vat_treatment: VatTreatment
    input_vat_eligibility: InputVatEligibility | None = None


class ManualEntryCreate(BaseModel):
    company_id: int
    financial_year_id: int
    ledger_side: LedgerSide
    invoice_date: date
    due_date: date | None = None
    currency: str = "EUR"
    fx_rate_to_eur: Decimal | None = None
    counterparty_name: str | None = None
    counterparty_vat_number: str | None = None
    accounting_classification: str | None = None
    line_items: list[ManualLineItemIn]


class TransactionUpdate(BaseModel):
    fx_rate_to_eur: Decimal | None = None
    due_date: date | None = None
    accounting_classification: str | None = None


class LineItemEligibilityUpdate(BaseModel):
    input_vat_eligibility: InputVatEligibility


class CorrectionCreate(BaseModel):
    financial_year_id: int
    line_items: list[ManualLineItemIn]


class VatReturnOut(BaseModel):
    id: int
    company_id: int
    vat_period_id: int
    status: VatReturnStatus
    rules_version: str
    box_1a_net: Decimal
    box_1a_vat: Decimal
    box_1b_net: Decimal
    box_1b_vat: Decimal
    box_1c_net: Decimal
    box_1c_vat: Decimal
    box_1d_vat: Decimal
    box_1e_net: Decimal
    box_2a_net: Decimal
    box_2a_vat: Decimal
    box_3a_net: Decimal
    box_3b_net: Decimal
    box_3c_net: Decimal
    box_4a_net: Decimal
    box_4a_vat: Decimal
    box_4b_net: Decimal
    box_4b_vat: Decimal
    box_5a_vat: Decimal
    box_5b_vat: Decimal
    net_payable: Decimal
    computed_at: datetime | None
    approved_by_user_id: int | None
    approved_at: datetime | None
    locked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ReconciliationOut(BaseModel):
    vat_return: VatReturnOut
    sales_total_net: Decimal
    purchases_total_net: Decimal
    sales_vat_by_rate: dict[str, Decimal]
    purchase_vat_by_rate: dict[str, Decimal]
    pending_documents: list[dict]
    duplicate_documents: list[dict]
    validation_errors: list[dict]
    unresolved_fx_transaction_ids: list[int]
    corrections: list[TransactionOut]
