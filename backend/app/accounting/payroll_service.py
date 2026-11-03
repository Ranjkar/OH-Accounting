"""Payroll run / payslip orchestration. Issued payslips are never edited
in place -- a correction voids the original (voided=True, same pattern as
Payment) and creates a new Payslip linked via corrects_payslip_id."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounting import dutch_tax_rules as tax
from app.accounting import payroll_engine
from app.models.employee import Employee
from app.models.enums import EmploymentType, PayrollRunStatus
from app.models.payroll import PayrollRun, Payslip


class PayrollError(Exception):
    pass


def create_payroll_run(db: Session, *, tenant_id: int, company_id: int, period_type, period_year: int,
                        period_number: int, created_by_user_id: int, tax_year: int | None = None) -> PayrollRun:
    tax_year = tax_year or tax.CURRENT_TAX_YEAR
    tax.get_rule_set(tax_year)  # raises if no rule set exists for this year -- fail fast, not silently
    run = PayrollRun(
        tenant_id=tenant_id, company_id=company_id, period_type=period_type, period_year=period_year,
        period_number=period_number, tax_year=tax_year, created_by_user_id=created_by_user_id,
    )
    db.add(run)
    db.flush()
    return run


def add_payslip(
    db: Session, run: PayrollRun, employee: Employee, *, paid_hours: Decimal | None = None,
    overtime_hours: Decimal = Decimal("0"), overtime_rate_multiplier: Decimal = Decimal("1.5"),
    bonus_amount: Decimal = Decimal("0"), expense_reimbursement: Decimal = Decimal("0"),
    pay_holiday_allowance_this_period: bool = False, pension_deduction_pct: Decimal = Decimal("0"),
    other_deductions: Decimal = Decimal("0"),
) -> Payslip:
    if run.status != PayrollRunStatus.draft:
        raise PayrollError(f"Payroll run is {run.status.value}, not DRAFT -- cannot add a payslip to it")

    rules = tax.get_rule_set(run.tax_year)
    cumulative_wage_this_year_before_this_period = db.scalar(
        select(func.coalesce(func.sum(Payslip.gross_salary), Decimal("0")))
        .join(PayrollRun, Payslip.payroll_run_id == PayrollRun.id)
        .where(
            Payslip.employee_id == employee.id,
            Payslip.voided.is_(False),
            PayrollRun.period_year == run.period_year,
            PayrollRun.period_number < run.period_number,
        )
    ) or Decimal("0")
    result = payroll_engine.calculate_payslip(
        period_type=run.period_type, salary_basis=employee.salary_basis, monthly_salary=employee.monthly_salary,
        hourly_rate=employee.hourly_rate, paid_hours=paid_hours, overtime_hours=overtime_hours,
        overtime_rate_multiplier=overtime_rate_multiplier, bonus_amount=bonus_amount,
        expense_reimbursement=expense_reimbursement, pay_holiday_allowance_this_period=pay_holiday_allowance_this_period,
        holiday_allowance_pct=employee.holiday_allowance_pct, pension_deduction_pct=pension_deduction_pct,
        other_deductions=other_deductions, has_permanent_contract=employee.employment_type == EmploymentType.permanent,
        cumulative_wage_this_year_before_this_period=cumulative_wage_this_year_before_this_period, rules=rules,
    )
    payslip = Payslip(
        tenant_id=run.tenant_id, company_id=run.company_id, payroll_run_id=run.id, employee_id=employee.id,
        contracted_hours=employee.contracted_hours_per_week, paid_hours=paid_hours, overtime_hours=overtime_hours,
        overtime_amount=result["overtime_amount"], holiday_allowance=result["holiday_allowance"],
        bonus_amount=bonus_amount, expense_reimbursement=expense_reimbursement,
        gross_salary=result["gross_salary"], taxable_wage=result["taxable_wage"],
        wage_tax_and_national_insurance=result["wage_tax_and_national_insurance"],
        general_tax_credit_applied=result["general_tax_credit_applied"],
        labor_tax_credit_applied=result["labor_tax_credit_applied"],
        pension_deduction=result["pension_deduction"], other_deductions=other_deductions,
        net_salary=result["net_salary"], employer_levy_zvw=result["employer_levy_zvw"],
        employer_costs_total=result["employer_costs_total"], calculation_notes=result["calculation_notes"],
    )
    db.add(payslip)
    db.flush()
    return payslip


def approve_payroll_run(db: Session, run: PayrollRun, user_id: int) -> None:
    if run.status != PayrollRunStatus.draft:
        raise PayrollError(f"Payroll run is {run.status.value}, not DRAFT")
    if not run.payslips:
        raise PayrollError("Cannot approve a payroll run with no payslips")
    run.status = PayrollRunStatus.approved
    run.approved_by_user_id = user_id
    run.approved_at = datetime.now(timezone.utc)
    db.flush()


def mark_paid(db: Session, run: PayrollRun) -> None:
    if run.status != PayrollRunStatus.approved:
        raise PayrollError(f"Payroll run is {run.status.value}, not APPROVED")
    run.status = PayrollRunStatus.paid
    db.flush()


def build_annual_statement(db: Session, employee: Employee, tax_year: int) -> dict:
    """Jaaropgaaf: sums every non-voided payslip issued to this employee under
    payroll runs for the given tax_year. This is a deterministic aggregation of
    figures already calculated and stored on each Payslip -- it never
    recomputes or re-derives tax, it only totals what was actually withheld."""
    payslips = (
        db.query(Payslip)
        .join(PayrollRun, Payslip.payroll_run_id == PayrollRun.id)
        .filter(
            Payslip.employee_id == employee.id,
            Payslip.voided.is_(False),
            PayrollRun.tax_year == tax_year,
        )
        .order_by(PayrollRun.period_number)
        .all()
    )

    zero = Decimal("0.00")
    totals = {
        "gross_salary": zero, "taxable_wage": zero, "wage_tax_and_national_insurance": zero,
        "general_tax_credit_applied": zero, "labor_tax_credit_applied": zero, "pension_deduction": zero,
        "other_deductions": zero, "net_salary": zero, "employer_levy_zvw": zero, "employer_costs_total": zero,
    }
    for payslip in payslips:
        for field in totals:
            totals[field] += getattr(payslip, field)

    return {
        "employee_id": employee.id, "tax_year": tax_year, "number_of_payslips": len(payslips),
        **totals,
        "requires_accountant_confirmation": True,
        "note": (
            "This annual statement is a sum of figures already calculated and stored on this "
            "employee's payslips for the tax year -- it does not independently verify completeness "
            "(e.g. that a payslip exists for every period the employee was employed this year)."
        ),
    }


def correct_payslip(db: Session, original: Payslip, *, reason: str, **override_kwargs) -> Payslip:
    """Void the original (keeping it as a permanent audit record) and
    create a new Payslip for the same employee/run with corrected inputs."""
    if original.voided:
        raise PayrollError("This payslip has already been corrected")
    run = db.get(PayrollRun, original.payroll_run_id)
    employee = db.get(Employee, original.employee_id)

    original.voided = True
    original.void_reason = reason

    kwargs = {
        "paid_hours": original.paid_hours,
        "overtime_hours": original.overtime_hours,
        "bonus_amount": original.bonus_amount,
        "expense_reimbursement": original.expense_reimbursement,
        "pay_holiday_allowance_this_period": original.holiday_allowance > 0,
        "pension_deduction_pct": Decimal("0"),
        "other_deductions": original.other_deductions,
    }
    kwargs.update(override_kwargs)

    was_draft = run.status == PayrollRunStatus.draft
    if not was_draft:
        run.status = PayrollRunStatus.draft  # temporarily reopen to reuse add_payslip's validation
    try:
        correction = add_payslip(db, run, employee, **kwargs)
    finally:
        if not was_draft:
            run.status = PayrollRunStatus.corrected
    correction.corrects_payslip_id = original.id
    db.flush()
    return correction
