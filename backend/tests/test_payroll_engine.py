from decimal import Decimal

import pytest

from app.accounting import payroll_engine
from app.models.enums import PayrollPeriodType, SalaryBasis


def test_monthly_salaried_employee_basic():
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    assert result["base_pay"] == Decimal("4000.00")
    assert result["gross_salary"] == Decimal("4000.00")
    assert result["net_salary"] < result["gross_salary"]
    assert result["requires_accountant_confirmation"] is True


def test_hourly_employee_requires_rate_and_hours():
    with pytest.raises(ValueError):
        payroll_engine.calculate_payslip(
            period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.hourly,
            monthly_salary=None, hourly_rate=None, paid_hours=None,
            pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
        )


def test_hourly_employee_gross_pay():
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.hourly,
        monthly_salary=None, hourly_rate=Decimal("25.00"), paid_hours=Decimal("160"),
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    assert result["base_pay"] == Decimal("4000.00")


def test_overtime_adds_to_gross():
    base = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.hourly,
        monthly_salary=None, hourly_rate=Decimal("20.00"), paid_hours=Decimal("160"),
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    with_overtime = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.hourly,
        monthly_salary=None, hourly_rate=Decimal("20.00"), paid_hours=Decimal("160"),
        overtime_hours=Decimal("10"), overtime_rate_multiplier=Decimal("1.5"),
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    assert with_overtime["overtime_amount"] == Decimal("300.00")  # 20 * 10 * 1.5
    assert with_overtime["gross_salary"] == base["gross_salary"] + Decimal("300.00")


def test_overtime_without_hourly_rate_is_zero_and_noted():
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        overtime_hours=Decimal("5"),
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    assert result["overtime_amount"] == Decimal("0.00")
    assert "overtime" in result["calculation_notes"].lower()


def test_holiday_allowance_applied_only_when_flagged():
    without = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    with_allowance = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=True, holiday_allowance_pct=Decimal("8.00"),
    )
    assert without["holiday_allowance"] == Decimal("0")
    assert with_allowance["holiday_allowance"] == Decimal("320.00")  # 4000 * 8%
    assert with_allowance["gross_salary"] == without["gross_salary"] + Decimal("320.00")


def test_four_weekly_prorates_monthly_salary():
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.four_weekly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("5200"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    assert result["base_pay"] == Decimal("4800.00")  # 5200 * 12 / 13


def test_higher_gross_salary_means_higher_period_withholding():
    low = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("2500"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    high = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("10000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    assert high["wage_tax_and_national_insurance"] > low["wage_tax_and_national_insurance"]


def test_pension_deduction_reduces_net_salary():
    without = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"), pension_deduction_pct=Decimal("0"),
    )
    with_pension = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"), pension_deduction_pct=Decimal("5"),
    )
    assert with_pension["pension_deduction"] == Decimal("200.00")
    assert with_pension["net_salary"] == without["net_salary"] - Decimal("200.00")


def test_expense_reimbursement_added_back_untaxed():
    without = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    with_reimbursement = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
        expense_reimbursement=Decimal("50"),
    )
    # Reimbursement doesn't change taxable gross, only adds straight to net.
    assert with_reimbursement["gross_salary"] == without["gross_salary"]
    assert with_reimbursement["net_salary"] == without["net_salary"] + Decimal("50")
