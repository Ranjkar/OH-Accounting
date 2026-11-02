from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import RecurringFrequency, RecurringStatus


class RecurringPattern(Base):
    """A detected recurring payment (supplier invoice, subscription, rent,
    utility, ...). Detection only -- nothing here ever creates or pays an
    invoice automatically."""

    __tablename__ = "recurring_patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    counterparty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    description_sample: Mapped[str | None] = mapped_column(String(255), nullable=True)

    frequency: Mapped[RecurringFrequency] = mapped_column(Enum(RecurringFrequency, name="recurring_frequency"))
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    amount_tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("10"))

    last_transaction_date: Mapped[date] = mapped_column(Date)
    next_expected_date: Mapped[date] = mapped_column(Date)
    status: Mapped[RecurringStatus] = mapped_column(Enum(RecurringStatus, name="recurring_status"), default=RecurringStatus.active)

    occurrence_count: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company: Mapped["Company"] = relationship()
