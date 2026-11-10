from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import TimesheetEntryType, TimesheetStatus


class EmployeeTimesheetEntry(Base):
    """An employee's recorded hours for one day. Approval creates an audit
    trail (approved_by_user_id/approved_at); nothing here is ever silently
    recalculated once approved -- a correction is a new entry plus a note,
    same pattern as the rest of this codebase."""

    __tablename__ = "employee_timesheet_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))

    entry_date: Mapped[date] = mapped_column(Date)
    entry_type: Mapped[TimesheetEntryType] = mapped_column(Enum(TimesheetEntryType, name="timesheet_entry_type"))
    hours: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[TimesheetStatus] = mapped_column(Enum(TimesheetStatus, name="timesheet_status"), default=TimesheetStatus.draft)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    employee: Mapped["Employee"] = relationship()


class EntrepreneurHoursEntry(Base):
    """Hours an entrepreneur/partner spent on their business, for the
    1,225-hour urencriterium. partner_id is nullable -- a sole proprietor
    (eenmanszaak) with no Partner row logs hours directly against the
    company. Entering a total never automatically grants a deduction; see
    app.accounting.tax_optimization for the eligibility check, which is
    always presented as a recommendation requiring confirmation."""

    __tablename__ = "entrepreneur_hours_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"), nullable=True)

    entry_date: Mapped[date] = mapped_column(Date)
    activity_category: Mapped[str] = mapped_column(String(50))  # business_activity/training/administration/business_development/travel/other
    duration_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
