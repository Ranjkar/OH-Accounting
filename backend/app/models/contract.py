"""Phase 26: annual accounting-services agreements and electronic signatures.

Design notes (the parts that are not obvious from the columns):

* A Contract carries the *editable* commercial terms while it is a DRAFT.
  Approval freezes them into an immutable ContractVersion (rendered content
  JSON + branded PDF + SHA-256 of both). Signing produces a second, final
  ContractVersion (same content + a signature-evidence page). No API ever
  updates or deletes a ContractVersion row or its file.
* Signing links are random 256-bit tokens; only the SHA-256 hash is stored
  (same pattern as PasswordResetToken / CompanyInvitation). One signature
  row per contract (unique contract_id) is what makes a replayed or
  concurrent sign request fail, regardless of application-level checks.
* Renewal dedupe: `renews_contract_id` is UNIQUE, so two scheduler runs (or
  a scheduler run racing an admin click) cannot both create a renewal for
  the same expiring agreement. Reminder dedupe: UNIQUE (contract_id, kind).
* The signature recorded here is a SIMPLE electronic signature (eIDAS
  art. 3(10)): possession of the emailed link + typed name + explicit
  consent. It is not advanced or qualified; `signing_method` /
  `provider_name` exist so a stronger external provider adapter
  (app/services/signing_provider.py) can record what it did instead.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import ContractStatus, ContractTemplateVersionStatus, ContractVersionKind, SigningInvitationStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ContractTemplate(Base):
    __tablename__ = "contract_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    versions: Mapped[list["ContractTemplateVersion"]] = relationship(back_populates="template", order_by="ContractTemplateVersion.version_no")


class ContractTemplateVersion(Base):
    """Immutable once APPROVED. `content` = {"nl": {"title", "clauses": [{"key",
    "heading", "body"}]}, "en": {...}}; clause bodies may use {placeholders}
    substituted at render time (see app.services.contract_templates)."""

    __tablename__ = "contract_template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version_no", name="uq_contract_template_version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("contract_templates.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[ContractTemplateVersionStatus] = mapped_column(
        Enum(ContractTemplateVersionStatus, name="contract_template_version_status"), default=ContractTemplateVersionStatus.draft
    )
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    # Commercial defaults copied onto a new contract. Deliberately nullable:
    # the built-in template ships WITHOUT a fee -- an administrator must set
    # pricing before a contract can be approved (never invented by code).
    default_services: Mapped[list] = mapped_column(JSON, default=list)
    default_monthly_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    default_payment_terms_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_term_months: Mapped[int] = mapped_column(Integer, default=12)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    template: Mapped["ContractTemplate"] = relationship(back_populates="versions")


class ContractSettings(Base):
    """One row per tenant, created lazily with defaults."""

    __tablename__ = "contract_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), unique=True)
    reminder_days: Mapped[list] = mapped_column(JSON, default=lambda: [60, 30, 14])
    signing_link_expire_days: Mapped[int] = mapped_column(Integer, default=14)
    signing_reminder_days: Mapped[int] = mapped_column(Integer, default=7)
    auto_create_on_company_create: Mapped[bool] = mapped_column(Boolean, default=True)
    default_language: Mapped[str] = mapped_column(String(5), default="nl")
    notification_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reply_to_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        Index("ix_contracts_tenant_status", "tenant_id", "status"),
        Index("ix_contracts_tenant_end_date", "tenant_id", "end_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[ContractStatus] = mapped_column(Enum(ContractStatus, name="contract_status"), default=ContractStatus.draft)
    language: Mapped[str] = mapped_column(String(5), default="nl")
    template_version_id: Mapped[int | None] = mapped_column(ForeignKey("contract_template_versions.id"), nullable=True)

    # Term
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    term_months: Mapped[int] = mapped_column(Integer, default=12)

    # Commercial terms (editable only while DRAFT)
    services: Mapped[list] = mapped_column(JSON, default=list)  # [{"code": "...", "label": "..."}]
    monthly_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    payment_terms_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_clauses: Mapped[list | None] = mapped_column(JSON, nullable=True)  # overrides template clauses when set

    # Signer (authorised representative of the client)
    signer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signer_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Renewal chain
    renews_contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), nullable=True, unique=True)
    renewal_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    renewal_disabled_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Lifecycle timestamps
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_source: Mapped[str] = mapped_column(String(30), default="manual")  # manual | company_created | renewal
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    termination_effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    company: Mapped["Company"] = relationship()
    versions: Mapped[list["ContractVersion"]] = relationship(back_populates="contract", order_by="ContractVersion.version_no")
    invitations: Mapped[list["ContractSigningInvitation"]] = relationship(back_populates="contract", order_by="ContractSigningInvitation.id")
    events: Mapped[list["ContractEvent"]] = relationship(back_populates="contract", order_by="ContractEvent.id")
    signature: Mapped["ContractSignature | None"] = relationship(back_populates="contract", uselist=False)


class ContractVersion(Base):
    """Immutable document snapshot. `content` is the fully rendered agreement
    (parties, term, services, fees, clauses with placeholders substituted);
    `content_hash` is SHA-256 of its canonical JSON, `pdf_sha256` of the PDF
    bytes stored at `pdf_storage_path` (served only through an authenticated
    or token-checked endpoint, never a static URL)."""

    __tablename__ = "contract_versions"
    __table_args__ = (UniqueConstraint("contract_id", "version_no", name="uq_contract_version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    kind: Mapped[ContractVersionKind] = mapped_column(Enum(ContractVersionKind, name="contract_version_kind"))
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    pdf_storage_path: Mapped[str] = mapped_column(String(500))
    pdf_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    contract: Mapped["Contract"] = relationship(back_populates="versions")


class ContractSigningInvitation(Base):
    __tablename__ = "contract_signing_invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    contract_version_id: Mapped[int] = mapped_column(ForeignKey("contract_versions.id"))
    signer_name: Mapped[str] = mapped_column(String(255))
    signer_email: Mapped[str] = mapped_column(String(255))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[SigningInvitationStatus] = mapped_column(
        Enum(SigningInvitationStatus, name="signing_invitation_status"), default=SigningInvitationStatus.pending
    )
    is_renewal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    email_outbox_id: Mapped[int | None] = mapped_column(ForeignKey("email_outbox.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    contract: Mapped["Contract"] = relationship(back_populates="invitations")


class ContractSignature(Base):
    """Signing evidence. GDPR minimisation: only what is needed to evidence
    WHO signed WHAT and WHEN -- name as typed, the invited email address, the
    consent text shown, the hash of the document signed, timestamps, and the
    request's IP/user agent (retained with the contract under the statutory
    7-year bookkeeping retention, see docs/gdpr-data-governance.md)."""

    __tablename__ = "contract_signatures"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), unique=True)
    invitation_id: Mapped[int] = mapped_column(ForeignKey("contract_signing_invitations.id"))
    contract_version_id: Mapped[int] = mapped_column(ForeignKey("contract_versions.id"))  # what was signed
    signed_version_id: Mapped[int | None] = mapped_column(ForeignKey("contract_versions.id"), nullable=True)  # final PDF
    signer_name_typed: Mapped[str] = mapped_column(String(255))
    signer_email: Mapped[str] = mapped_column(String(255))
    consent_text: Mapped[str] = mapped_column(Text)
    consent_given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    signing_method: Mapped[str] = mapped_column(String(50))
    provider_name: Mapped[str] = mapped_column(String(50))
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_sha256: Mapped[str] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    contract: Mapped["Contract"] = relationship(back_populates="signature")


class ContractEvent(Base):
    """Per-contract timeline, append-only. Admin actions additionally write
    an AuditLog row (the tenant-wide trail); signer/system actions have no
    acting User so they live only here."""

    __tablename__ = "contract_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    actor_type: Mapped[str] = mapped_column(String(10))  # user | signer | system
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    contract: Mapped["Contract"] = relationship(back_populates="events")


class ContractReminder(Base):
    """One row per (contract, reminder kind) -- the UNIQUE constraint is the
    duplicate-email guard, not application logic."""

    __tablename__ = "contract_reminders"
    __table_args__ = (UniqueConstraint("contract_id", "kind", name="uq_contract_reminder_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    scheduled_for: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))  # sent | skipped_disabled | failed
    email_outbox_id: Mapped[int | None] = mapped_column(ForeignKey("email_outbox.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
