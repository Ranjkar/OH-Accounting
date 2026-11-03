from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, LargeBinary, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import EmploymentType, SalaryBasis


class Employee(Base):
    """BSN is stored only as bsn_encrypted (app.core.crypto, Fernet) --
    never in plaintext, never passed to an AI prompt, never logged. Decrypt
    only at the point of display to an authorised payroll user."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    employee_number: Mapped[str] = mapped_column(String(50))
    full_name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bsn_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    employment_start_date: Mapped[date] = mapped_column(Date)
    employment_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    employment_type: Mapped[EmploymentType] = mapped_column(Enum(EmploymentType, name="employment_type"))
    contract_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)

    contracted_hours_per_week: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    salary_basis: Mapped[SalaryBasis] = mapped_column(Enum(SalaryBasis, name="salary_basis"))
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    monthly_salary: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    holiday_allowance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("8.00"))
    pension_scheme: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_dga: Mapped[bool] = mapped_column(Boolean, default=False)
    linked_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    company: Mapped["Company"] = relationship()
