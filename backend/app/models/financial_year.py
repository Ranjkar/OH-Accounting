from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import VatPeriodStatus


class FinancialYear(Base):
    """Locking a financial year blocks new ledger postings and corrections
    dated within it (see ledger_service.py) -- it never retroactively edits
    or removes transactions already posted. Unlocking is a deliberate,
    audit-logged action (see app/api/v1/companies.py), never automatic."""

    __tablename__ = "financial_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    year: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    company: Mapped["Company"] = relationship(back_populates="financial_years")
    vat_periods: Mapped[list["VatPeriod"]] = relationship(
        back_populates="financial_year", cascade="all, delete-orphan"
    )


class VatPeriod(Base):
    __tablename__ = "vat_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    financial_year_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id"))
    label: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    filing_deadline: Mapped[date] = mapped_column(Date)
    payment_deadline: Mapped[date] = mapped_column(Date)
    status: Mapped[VatPeriodStatus] = mapped_column(
        Enum(VatPeriodStatus, name="vat_period_status"), default=VatPeriodStatus.open
    )

    financial_year: Mapped["FinancialYear"] = relationship(back_populates="vat_periods")
