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


class CompanyOut(BaseModel):
    id: int
    name: str
    kvk_number: str | None
    vat_number: str | None
    address: str | None
    vat_frequency: VatFrequency
    vat_accounting_basis: VatAccountingBasis
    input_vat_pro_rata_percentage: Decimal | None

    model_config = ConfigDict(from_attributes=True)


class CompanyUpdate(BaseModel):
    vat_accounting_basis: VatAccountingBasis | None = None
    input_vat_pro_rata_percentage: Decimal | None = None


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
    raw_token: str


class AcceptInvitationRequest(BaseModel):
    token: str


class CompanyAccessOut(BaseModel):
    user_id: int
    email: str
    full_name: str
    role: UserRole
