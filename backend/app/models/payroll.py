from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import PayrollPeriodType, PayrollRunStatus


class PayrollRun(Base):
    """One payroll period for a company. Approving a run never edits a
    Payslip in place afterward -- a correction creates a new Payslip linked
    via corrects_payslip_id, same immutable-correction pattern used
    throughout this codebase.

    Phase 12: unique on (company_id, period_type, period_year,
    period_number) -- a double-click or retried request on "create
    payroll run" must not silently create two runs (and therefore double
    payroll) for the same period. Enforced at the DB level, not just in
    application code, so it holds even under concurrent requests."""

    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "period_type", "period_year", "period_number", name="uq_payroll_run_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    period_type: Mapped[PayrollPeriodType] = mapped_column(Enum(PayrollPeriodType, name="payroll_period_type"))
    period_year: Mapped[int] = mapped_column(Integer)
    period_number: Mapped[int] = mapped_column(Integer)  # month 1-12, or four-week period 1-13
    tax_year: Mapped[int] = mapped_column(Integer)  # which DutchTaxRuleSet year this run used

    status: Mapped[PayrollRunStatus] = mapped_column(Enum(PayrollRunStatus, name="payroll_run_status"), default=PayrollRunStatus.draft)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship()
    payslips: Mapped[list["Payslip"]] = relationship(back_populates="payroll_run", cascade="all, delete-orphan")


class Payslip(Base):
    """One employee's payslip for one payroll run. Figures are Decimal and
    never recalculated silently after issue -- voided + a new corrected
    Payslip is the only way to change one, mirroring Payment.voided."""

    __tablename__ = "payslips"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    payroll_run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    corrects_payslip_id: Mapped[int | None] = mapped_column(ForeignKey("payslips.id"), nullable=True)

    contracted_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    paid_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    overtime_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    holiday_allowance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    expense_reimbursement: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))

    gross_salary: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    taxable_wage: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    wage_tax_and_national_insurance: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    general_tax_credit_applied: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    labor_tax_credit_applied: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    pension_deduction: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    other_deductions: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    net_salary: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    employer_levy_zvw: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    employer_costs_total: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Text, not a bounded VARCHAR -- Phase 10's calculation notes are deliberately
    # detailed (every employer-premium rate used, every simplification stated) and
    # must never be silently truncated, which would hide a compliance caveat.
    calculation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    payroll_run: Mapped["PayrollRun"] = relationship(back_populates="payslips")
    employee: Mapped["Employee"] = relationship()
