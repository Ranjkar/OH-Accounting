from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import BankConsentStatus, BankSourceFormat, ReconciliationStatus


class BankAccountCreate(BaseModel):
    company_id: int
    iban: str
    account_name: str
    currency: str = "EUR"


class BankAccountOut(BaseModel):
    id: int
    company_id: int
    iban: str
    account_name: str
    currency: str
    consent_status: BankConsentStatus
    provider_name: str | None
    consent_granted_at: datetime | None
    consent_expires_at: datetime | None
    last_synced_at: datetime | None
    last_sync_error: str | None
    pending_provider_accounts: list[dict] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OpenBankingConnectRequest(BaseModel):
    redirect_uri: str
    bank_id: str | None = None


class OpenBankingCallbackRequest(BaseModel):
    callback_params: dict = {}


class OpenBankingCallbackOut(BaseModel):
    account: BankAccountOut
    candidates: list[dict]


class OpenBankingSelectAccountRequest(BaseModel):
    provider_account_id: str


class BankImportBatchOut(BaseModel):
    id: int
    bank_account_id: int
    source_format: BankSourceFormat
    original_filename: str
    transaction_count: int
    duplicate_count: int
    error_count: int
    error_message: str | None
    imported_by_user_id: int
    imported_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentMatchOut(BaseModel):
    id: int
    bank_transaction_id: int
    accounting_transaction_id: int
    allocated_amount: Decimal
    confidence_score: Decimal
    confidence_level: str
    match_signals: dict
    status: str
    created_at: datetime
    approved_by_user_id: int | None
    approved_at: datetime | None
    payment_id: int | None

    model_config = ConfigDict(from_attributes=True)


class BankTransactionOut(BaseModel):
    id: int
    bank_account_id: int
    import_batch_id: int
    external_transaction_id: str | None
    booking_date: date
    value_date: date | None
    amount: Decimal
    currency: str
    counterparty_name: str | None
    counterparty_iban: str | None
    payment_reference: str | None
    description: str | None
    source_format: BankSourceFormat
    reconciliation_status: ReconciliationStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BankTransactionDetailOut(BankTransactionOut):
    matches: list[PaymentMatchOut]


class ReverseMatchRequest(BaseModel):
    reason: str
