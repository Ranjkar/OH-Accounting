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
    """Pension is withheld pre-tax (see test_pension_deduction_reduces_tax_base_not_just_net_salary),
    so net salary drops by less than the raw pension_deduction amount -- the tax saved on the
    now-smaller wage base partially offsets it. Net salary must still strictly decrease."""
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
    tax_saved = without["regular_wage_tax"] - with_pension["regular_wage_tax"]
    assert tax_saved > 0
    assert with_pension["net_salary"] == without["net_salary"] - Decimal("200.00") + tax_saved


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


# ---- Phase 10: special remuneration taxed separately from regular wage ----


def test_holiday_allowance_taxed_as_special_remuneration_not_blended_into_regular_wage():
    from app.accounting import dutch_tax_rules as tax

    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=True, holiday_allowance_pct=Decimal("8.00"),
    )
    rules = tax.get_rule_set()
    expected_special_tax = tax.calculate_special_remuneration_tax(result["special_remuneration"], result["annualized_regular_wage"], rules)
    assert result["special_remuneration_tax"] == expected_special_tax
    assert result["special_remuneration"] == Decimal("320.00")
    # The regular-wage tax must be computed on regular wage ALONE (annualized_regular_wage
    # excludes the holiday allowance), not on gross_salary including it.
    assert result["annualized_regular_wage"] == Decimal("4000.00") * 12


def test_bonus_and_holiday_allowance_both_count_as_special_remuneration():
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=True, holiday_allowance_pct=Decimal("8.00"),
        bonus_amount=Decimal("1000"),
    )
    assert result["special_remuneration"] == Decimal("1320.00")


def test_wage_tax_total_is_sum_of_regular_and_special():
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=True, holiday_allowance_pct=Decimal("8.00"),
        bonus_amount=Decimal("500"),
    )
    assert result["wage_tax_and_national_insurance"] == result["regular_wage_tax"] + result["special_remuneration_tax"]


# ---- Phase 10: employer social insurance premiums ----


def test_employer_premiums_present_for_permanent_small_employer():
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
        has_permanent_contract=True, is_small_employer=True,
    )
    assert result["employer_premium_awf"] > 0
    assert result["employer_premium_aof"] > 0
    assert result["employer_premium_whk"] > 0
    assert result["employer_levy_zvw"] > 0
    assert result["employer_premiums_total"] == (
        result["employer_premium_awf"] + result["employer_premium_aof"] + result["employer_premium_whk"] + result["employer_levy_zvw"]
    )
    assert result["employer_costs_total"] == result["gross_salary"] + result["employer_premiums_total"]


def test_flexible_contract_has_higher_awf_premium_than_permanent():
    permanent = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
        has_permanent_contract=True,
    )
    flexible = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
        has_permanent_contract=False,
    )
    assert flexible["employer_premium_awf"] > permanent["employer_premium_awf"]


def test_employer_premiums_respect_cumulative_annual_cap():
    near_cap = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
        cumulative_wage_this_year_before_this_period=Decimal("74000"),
    )
    well_under_cap = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
        cumulative_wage_this_year_before_this_period=Decimal("0"),
    )
    assert near_cap["employer_premiums_total"] < well_under_cap["employer_premiums_total"]


def test_pension_deduction_reduces_tax_base_not_just_net_salary():
    """Pension premium is withheld pre-tax in NL -- it must lower the wage base
    that regular_wage_tax is computed on, not just be subtracted from net_salary
    after tax is already calculated on the full gross wage."""
    no_pension = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    with_pension = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
        pension_deduction_pct=Decimal("5.00"),
    )
    assert with_pension["pension_deduction"] == Decimal("200.00")
    assert with_pension["annualized_taxable_regular_wage"] == no_pension["annualized_taxable_regular_wage"] - Decimal("200.00") * 12
    assert with_pension["regular_wage_tax"] < no_pension["regular_wage_tax"]
    # gross_salary itself is unaffected -- pension is a deduction from net, computed on a reduced tax base.
    assert with_pension["gross_salary"] == no_pension["gross_salary"]
