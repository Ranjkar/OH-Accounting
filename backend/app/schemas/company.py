from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import CompanyInvitationStatus, UserRole, VatAccountingBasis, VatFrequency, VatPeriodStatus


class CompanyCreate(BaseModel):
    name: str
    kvk_number: str | None = None
    vat_number: str | None = None
    address: str | None = None
    vat_frequency: VatFrequency = VatFrequency.quarterly
    # Phase 22 (all optional so the pre-wizard quick form keeps working).
    rsin: str | None = None
    vat_registered: bool = True
    kor_participant: bool = False
    business_activity: str | None = None
    email: str | None = None
    phone: str | None = None


class CompanyOut(BaseModel):
    id: int
    name: str
    kvk_number: str | None
    vat_number: str | None
    address: str | None
    vat_frequency: VatFrequency
    vat_accounting_basis: VatAccountingBasis
    input_vat_pro_rata_percentage: Decimal | None
    rsin: str | None = None
    vat_registered: bool = True
    kor_participant: bool = False
    business_activity: str | None = None
    email: str | None = None
    phone: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CompanyUpdate(BaseModel):
    vat_accounting_basis: VatAccountingBasis | None = None
    input_vat_pro_rata_percentage: Decimal | None = None


# ---- Phase 22: company setup wizard drafts ----


class SetupDraftData(BaseModel):
    """The wizard's answers. Everything optional: a draft may be saved at
    any step. `complete_setup_draft` is what enforces required/conditional
    fields, via app.api.v1.company_setup.validate_draft."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    legal_form_code: str | None = None
    kvk_number: str | None = None
    kvk_verified: bool = False
    vat_number: str | None = None
    rsin: str | None = None
    address: str | None = None
    business_activity: str | None = None
    email: str | None = None
    phone: str | None = None
    vat_registered: bool | None = None
    vat_frequency: VatFrequency | None = None
    vat_accounting_basis: VatAccountingBasis | None = None
    kor_participant: bool | None = None
    financial_year: int | None = None
    bank_iban: str | None = None
    bank_account_name: str | None = None
    bank_skipped: bool = False


class SetupDraftUpdate(BaseModel):
    data: SetupDraftData
    current_step: int = 0


class SetupDraftOut(BaseModel):
    id: int
    data: dict
    current_step: int
    created_company_id: int | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class SetupValidationIssue(BaseModel):
    field: str
    code: str  # required | invalid | duplicate
    message: str


class SetupValidationOut(BaseModel):
    ok: bool
    issues: list[SetupValidationIssue]
    warnings: list[SetupValidationIssue]


class SetupCompleteOut(BaseModel):
    company: CompanyOut
    financial_year_id: int | None
    bank_account_id: int | None
    already_completed: bool


class VatPeriodOut(BaseModel):
    id: int
    label: str
    start_date: date
    end_date: date
    filing_deadline: date
    payment_deadline: date
    status: VatPeriodStatus

    model_config = ConfigDict(from_attributes=True)


class FinancialYearCreate(BaseModel):
    year: int


class FinancialYearOut(BaseModel):
    id: int
    year: int
    start_date: date
    end_date: date
    is_locked: bool
    locked_at: datetime | None
    vat_periods: list[VatPeriodOut] = []

    model_config = ConfigDict(from_attributes=True)


class CompanyInvitationCreate(BaseModel):
    invited_email: EmailStr
    intended_role: UserRole = UserRole.accountant


class CompanyInvitationOut(BaseModel):
    id: int
    company_id: int
    invited_email: str
    intended_role: UserRole
    status: CompanyInvitationStatus
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CompanyInvitationCreateResult(BaseModel):
    invitation: CompanyInvitationOut
    raw_token: str | None
    email_sent: bool = False


class AcceptInvitationRequest(BaseModel):
    token: str


class CompanyAccessOut(BaseModel):
    user_id: int
    email: str
    full_name: str
    role: UserRole
