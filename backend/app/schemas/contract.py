from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import ContractStatus, ContractTemplateVersionStatus, ContractVersionKind, SigningInvitationStatus


class ServiceItem(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=255)


class ClauseItem(BaseModel):
    key: str | None = None
    heading: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=5000)


class ContractCreate(BaseModel):
    company_id: int
    language: str | None = None
    start_date: date | None = None
    template_version_id: int | None = None


class ContractUpdate(BaseModel):
    language: str | None = None
    start_date: date | None = None
    term_months: int | None = Field(default=None, ge=1, le=60)
    services: list[ServiceItem] | None = None
    monthly_fee: Decimal | None = Field(default=None, ge=0)
    fee_description: str | None = Field(default=None, max_length=500)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    custom_clauses: list[ClauseItem] | None = None
    signer_name: str | None = Field(default=None, max_length=255)
    signer_email: EmailStr | None = None
    signer_title: str | None = Field(default=None, max_length=255)


class ReasonBody(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class TerminateBody(ReasonBody):
    effective_date: date | None = None


class NonRenewalBody(ReasonBody):
    disabled: bool = True


class ContractVersionOut(BaseModel):
    id: int
    version_no: int
    kind: ContractVersionKind
    content_hash: str
    pdf_sha256: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InvitationOut(BaseModel):
    id: int
    signer_name: str
    signer_email: str
    status: SigningInvitationStatus
    is_renewal: bool
    created_at: datetime
    expires_at: datetime
    first_viewed_at: datetime | None
    used_at: datetime | None
    email_outbox_id: int | None
    email_status: str | None = None
    model_config = ConfigDict(from_attributes=True)


class SignatureOut(BaseModel):
    id: int
    signer_name_typed: str
    signer_email: str
    signed_at: datetime
    signing_method: str
    provider_name: str
    document_sha256: str
    signed_version_id: int | None
    consent_text: str
    model_config = ConfigDict(from_attributes=True)


class EventOut(BaseModel):
    id: int
    event_type: str
    actor_type: str
    actor_user_id: int | None
    actor_name: str | None = None
    data: dict | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ContractOut(BaseModel):
    id: int
    tenant_id: int
    company_id: int
    company_name: str | None = None
    reference: str
    status: ContractStatus
    language: str
    template_version_id: int | None
    start_date: date
    end_date: date
    term_months: int
    services: list[dict]
    monthly_fee: Decimal | None
    fee_description: str | None
    currency: str
    payment_terms_days: int | None
    notice_period_days: int | None
    custom_clauses: list[dict] | None
    signer_name: str | None
    signer_email: str | None
    signer_title: str | None
    renews_contract_id: int | None
    renewal_contract_id: int | None = None
    renewal_disabled: bool
    renewal_disabled_reason: str | None
    created_source: str
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    sent_at: datetime | None
    viewed_at: datetime | None
    signed_at: datetime | None
    activated_at: datetime | None
    expired_at: datetime | None
    cancelled_at: datetime | None
    terminated_at: datetime | None
    termination_effective_date: date | None
    closure_reason: str | None
    signing_status: str = "not_sent"  # not_sent | awaiting | viewed | signed | expired | withdrawn
    days_until_expiry: int | None = None
    model_config = ConfigDict(from_attributes=True)


class ContractDetailOut(ContractOut):
    versions: list[ContractVersionOut]
    invitations: list[InvitationOut]
    signature: SignatureOut | None
    events: list[EventOut]
    approval_missing: list[str]
    renews_reference: str | None = None
    renewal_reference: str | None = None


class SendResult(BaseModel):
    contract: ContractOut
    invitation: InvitationOut
    email_sent: bool
    signing_link: str | None  # only when the email could not be sent (same convention as company invitations)


class RenewalResult(BaseModel):
    contract: ContractOut
    created: bool


class TemplateVersionOut(BaseModel):
    id: int
    template_id: int
    version_no: int
    status: ContractTemplateVersionStatus
    content: dict
    default_services: list
    default_monthly_fee: Decimal | None
    default_payment_terms_days: int | None
    default_notice_period_days: int | None
    default_term_months: int
    change_note: str | None
    created_at: datetime
    approved_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class TemplateVersionCreate(BaseModel):
    content: dict
    default_services: list[dict] = []
    default_monthly_fee: Decimal | None = Field(default=None, ge=0)
    default_payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    default_notice_period_days: int | None = Field(default=None, ge=0, le=365)
    default_term_months: int = Field(default=12, ge=1, le=60)
    change_note: str | None = Field(default=None, max_length=1000)


class SettingsOut(BaseModel):
    reminder_days: list[int]
    signing_link_expire_days: int
    signing_reminder_days: int
    auto_create_on_company_create: bool
    default_language: str
    notification_email: str | None
    reply_to_email: str | None
    feature_enabled: bool
    email_automation_enabled: bool
    signing_provider: str
    model_config = ConfigDict(from_attributes=True)


class SettingsUpdate(BaseModel):
    reminder_days: list[int] | None = None
    signing_link_expire_days: int | None = Field(default=None, ge=1, le=90)
    signing_reminder_days: int | None = Field(default=None, ge=1, le=60)
    auto_create_on_company_create: bool | None = None
    default_language: str | None = None
    notification_email: EmailStr | None = None
    reply_to_email: EmailStr | None = None


# ---- public signing portal ----


class SigningPageOut(BaseModel):
    reference: str
    status: ContractStatus
    language: str
    content: dict
    signer_name: str
    signer_email_hint: str
    consent_text: str
    expires_at: datetime
    already_signed: bool
    signed_at: datetime | None
    signed_pdf_sha256: str | None
    assurance_notice: str


class SignBody(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    consent: bool
