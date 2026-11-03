from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import LegalFormCode, LiabilityType, PartnerType


class LegalFormDefinition(Base):
    """Reference registry of Dutch (and a few foreign) legal forms. Seeded
    once via migration data, not derived or guessed -- every tax-obligation
    flag here is a starting point an accountant must confirm for a specific
    entity, never treated as automatically authoritative."""

    __tablename__ = "legal_form_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[LegalFormCode] = mapped_column(Enum(LegalFormCode, name="legal_form_code"), unique=True)
    name_nl: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str] = mapped_column(String(100))

    has_legal_personality: Mapped[bool] = mapped_column(Boolean)
    liability: Mapped[LiabilityType] = mapped_column(Enum(LiabilityType, name="liability_type"))
    min_partners: Mapped[int] = mapped_column(Integer, default=1)
    max_partners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_kvk_registration: Mapped[bool] = mapped_column(Boolean, default=True)

    subject_to_income_tax: Mapped[bool] = mapped_column(Boolean)  # pass-through to owner(s)/partner(s)
    subject_to_corporate_income_tax: Mapped[bool] = mapped_column(Boolean)
    subject_to_vat_by_default: Mapped[bool] = mapped_column(Boolean, default=True)
    payroll_tax_applies_if_employees: Mapped[bool] = mapped_column(Boolean, default=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CompanyLegalForm(Base):
    """A company's legal form over time. Changing form (e.g. eenmanszaak
    converting to a BV) closes the old row (effective_to) and opens a new
    one -- the history is never overwritten, matching Phase 8's immutable-
    correction pattern."""

    __tablename__ = "company_legal_forms"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    legal_form_code: Mapped[LegalFormCode] = mapped_column(Enum(LegalFormCode, name="legal_form_code", create_type=False))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    company: Mapped["Company"] = relationship()


class Partner(Base):
    """A partner in a VOF/Maatschap/CV. entrepreneur_hours_eligible is
    never assumed true -- it must be explicitly assessed per partner, since
    not every partner automatically meets the urencriterium or qualifies
    for entrepreneur deductions."""

    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(255))
    partner_type: Mapped[PartnerType] = mapped_column(Enum(PartnerType, name="partner_type"), default=PartnerType.general)
    profit_share_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    entrepreneur_hours_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    linked_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    company: Mapped["Company"] = relationship()


class Shareholder(Base):
    """A shareholder/director of a BV or NV. is_dga marks a director-
    shareholder subject to the gebruikelijk-loon rules -- never inferred,
    only set explicitly."""

    __tablename__ = "shareholders"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(255))
    ownership_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    is_director: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dga: Mapped[bool] = mapped_column(Boolean, default=False)
    linked_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    company: Mapped["Company"] = relationship()
