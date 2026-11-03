from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import LegalFormCode, LiabilityType, PartnerType


class LegalFormDefinitionOut(BaseModel):
    id: int
    code: LegalFormCode
    name_nl: str
    name_en: str
    has_legal_personality: bool
    liability: LiabilityType
    min_partners: int
    max_partners: int | None
    requires_kvk_registration: bool
    subject_to_income_tax: bool
    subject_to_corporate_income_tax: bool
    subject_to_vat_by_default: bool
    payroll_tax_applies_if_employees: bool
    notes: str | None

    model_config = ConfigDict(from_attributes=True)


class CompanyLegalFormCreate(BaseModel):
    company_id: int
    legal_form_code: LegalFormCode
    effective_from: date


class CompanyLegalFormOut(BaseModel):
    id: int
    company_id: int
    legal_form_code: LegalFormCode
    effective_from: date
    effective_to: date | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PartnerCreate(BaseModel):
    company_id: int
    name: str
    partner_type: PartnerType = PartnerType.general
    profit_share_percentage: Decimal
    entrepreneur_hours_eligible: bool = False
    effective_from: date


class PartnerOut(BaseModel):
    id: int
    company_id: int
    name: str
    partner_type: PartnerType
    profit_share_percentage: Decimal
    entrepreneur_hours_eligible: bool
    effective_from: date
    effective_to: date | None

    model_config = ConfigDict(from_attributes=True)


class ShareholderCreate(BaseModel):
    company_id: int
    name: str
    ownership_percentage: Decimal
    is_director: bool = False
    is_dga: bool = False
    effective_from: date


class ShareholderOut(BaseModel):
    id: int
    company_id: int
    name: str
    ownership_percentage: Decimal
    is_director: bool
    is_dga: bool
    effective_from: date
    effective_to: date | None

    model_config = ConfigDict(from_attributes=True)
