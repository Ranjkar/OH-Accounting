from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import PayrollPeriodType, PayrollRunStatus


class PayrollRunCreate(BaseModel):
    company_id: int
    period_type: PayrollPeriodType
    period_year: int
    period_number: int
    tax_year: int | None = None


class PayrollRunOut(BaseModel):
    id: int
    company_id: int
    period_type: PayrollPeriodType
    period_year: int
    period_number: int
    tax_year: int
    status: PayrollRunStatus
    created_at: datetime
    approved_by_user_id: int | None
    approved_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PayslipCreate(BaseModel):
    employee_id: int
    paid_hours: Decimal | None = None
    overtime_hours: Decimal = Decimal("0")
    overtime_rate_multiplier: Decimal = Decimal("1.5")
    bonus_amount: Decimal = Decimal("0")
    expense_reimbursement: Decimal = Decimal("0")
    pay_holiday_allowance_this_period: bool = False
    pension_deduction_pct: Decimal = Decimal("0")
    other_deductions: Decimal = Decimal("0")


class PayslipOut(BaseModel):
    id: int
    payroll_run_id: int
    employee_id: int
    corrects_payslip_id: int | None
    gross_salary: Decimal
    taxable_wage: Decimal
    wage_tax_and_national_insurance: Decimal
    net_salary: Decimal
    employer_costs_total: Decimal
    voided: bool
    void_reason: str | None
    calculation_notes: str | None

    model_config = ConfigDict(from_attributes=True)


class AnnualStatementOut(BaseModel):
    employee_id: int
    tax_year: int
    number_of_payslips: int
    gross_salary: Decimal
    taxable_wage: Decimal
    wage_tax_and_national_insurance: Decimal
    general_tax_credit_applied: Decimal
    labor_tax_credit_applied: Decimal
    pension_deduction: Decimal
    other_deductions: Decimal
    net_salary: Decimal
    employer_levy_zvw: Decimal
    employer_costs_total: Decimal
    requires_accountant_confirmation: bool
    note: str


class PayslipCorrectRequest(BaseModel):
    reason: str
    paid_hours: Decimal | None = None
    overtime_hours: Decimal | None = None
    bonus_amount: Decimal | None = None
    expense_reimbursement: Decimal | None = None
    pay_holiday_allowance_this_period: bool | None = None
    other_deductions: Decimal | None = None
