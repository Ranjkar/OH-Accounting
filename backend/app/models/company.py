from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import VatAccountingBasis, VatFrequency
from app.models.user import user_companies


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255))
    kvk_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vat_frequency: Mapped[VatFrequency] = mapped_column(
        Enum(VatFrequency, name="vat_frequency"), default=VatFrequency.quarterly
    )
    vat_accounting_basis: Mapped[VatAccountingBasis] = mapped_column(
        Enum(VatAccountingBasis, name="vat_accounting_basis"), default=VatAccountingBasis.invoice_based
    )
    input_vat_pro_rata_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    # ---- Phase 22: company setup wizard ----
    # RSIN only exists for entities with legal personality (BV/NV/stichting/
    # vereniging/cooperatie); eenmanszaak/VOF/maatschap have none.
    rsin: Mapped[str | None] = mapped_column(String(9), nullable=True)
    # Explicit answers, never inferred from the legal form: a company can be
    # VAT-exempt (e.g. medical) or use the KOR small-business scheme, and
    # both change what the VAT module should expect. Defaults match every
    # pre-existing row's effective behaviour (VAT-registered, no KOR).
    vat_registered: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    kor_participant: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    business_activity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="companies")
    users: Mapped[list["User"]] = relationship(
        secondary=user_companies, back_populates="companies"
    )
    financial_years: Mapped[list["FinancialYear"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    customers: Mapped[list["Customer"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class CompanySetupDraft(Base):
    """Phase 22: one row per in-progress company setup wizard. `data` holds
    the wizard's answers verbatim (validated on completion, not on every
    keystroke), so a user can close the browser mid-setup and resume on
    another device. Completion is idempotent: `created_company_id` is set
    inside the same transaction that creates the Company and the row is
    locked FOR UPDATE while completing, so a double-submit or a retried
    request can never create a second company from one draft."""

    __tablename__ = "company_setup_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    current_step: Mapped[int] = mapped_column(default=0)
    created_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
