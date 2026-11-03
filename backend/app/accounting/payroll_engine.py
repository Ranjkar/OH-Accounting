"""Deterministic Dutch payroll calculation. Decimal arithmetic throughout;
never calls an LLM for any monetary figure. Withholding is approximated by
annualizing the period's gross pay through the same box-1 brackets and
credits that app.accounting.dutch_tax_rules already uses for personal
income tax -- this is methodologically how the official loonbelastingtabel
is itself derived (the published tables are a precomputed version of this
same annualize-divide-by-periods approach), but the published tables
contain additional rounding and edge-case rules this engine does not
reproduce. Every result is marked accordingly and must be verified against
the official tabel before being relied on for an actual filing.

Employer-side national-insurance premiums (WW, WIA, Aof, sector fund) are
genuinely sector- and employer-specific percentages published separately
each year; only the employer Zvw contribution is estimated here, using a
placeholder rate explicitly flagged as requiring confirmation. This is the
"implement the architecture, label the rate as pending" approach the
engineering brief calls for when an official source can't be fully
reproduced in this session.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.accounting import dutch_tax_rules as tax
from app.models.enums import PayrollPeriodType, SalaryBasis

ZERO = Decimal("0")

# Placeholder -- the real employer Zvw contribution percentage is published
# yearly by the Belastingdienst and must be confirmed before this is used
# for an actual payroll filing.
EMPLOYER_ZVW_RATE_PLACEHOLDER = Decimal("0.0565")

PERIODS_PER_YEAR = {
    PayrollPeriodType.monthly: 12,
    PayrollPeriodType.four_weekly: 13,
}


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_payslip(
    *,
    period_type: PayrollPeriodType,
    salary_basis: SalaryBasis,
    monthly_salary: Decimal | None,
    hourly_rate: Decimal | None,
    paid_hours: Decimal | None,
    overtime_hours: Decimal = ZERO,
    overtime_rate_multiplier: Decimal = Decimal("1.5"),
    bonus_amount: Decimal = ZERO,
    expense_reimbursement: Decimal = ZERO,
    pay_holiday_allowance_this_period: bool,
    holiday_allowance_pct: Decimal,
    pension_deduction_pct: Decimal = ZERO,
    other_deductions: Decimal = ZERO,
    rules: tax.DutchTaxRuleSet | None = None,
) -> dict:
    rules = rules or tax.get_rule_set()
    periods_per_year = PERIODS_PER_YEAR[period_type]
    notes: list[str] = []

    if salary_basis == SalaryBasis.hourly:
        if hourly_rate is None or paid_hours is None:
            raise ValueError("Hourly employees require both hourly_rate and paid_hours")
        base_pay = hourly_rate * paid_hours
    else:
        if monthly_salary is None:
            raise ValueError("Monthly-salary employees require monthly_salary")
        base_pay = monthly_salary if period_type == PayrollPeriodType.monthly else (monthly_salary * 12 / 13)
        if period_type == PayrollPeriodType.four_weekly:
            notes.append("Four-weekly base pay is the monthly salary pro-rated by 12/13, not a separately-entered four-weekly rate.")

    overtime_amount = ZERO
    if overtime_hours > 0:
        if hourly_rate is not None:
            overtime_amount = hourly_rate * overtime_hours * overtime_rate_multiplier
        else:
            notes.append("Overtime hours were given but no hourly_rate is on file -- overtime amount could not be calculated and was left at 0.")

    holiday_allowance = _q(base_pay * holiday_allowance_pct / 100) if pay_holiday_allowance_this_period else ZERO

    gross_salary = _q(base_pay + overtime_amount + holiday_allowance + bonus_amount)

    annualized_taxable = gross_salary * periods_per_year
    annual_gross_tax = tax.calculate_box1_tax(annualized_taxable, rules)
    annual_general_credit = tax.algemene_heffingskorting(annualized_taxable, rules)
    annual_labor_credit = tax.arbeidskorting(annualized_taxable, rules)
    annual_withholding = max(annual_gross_tax - annual_general_credit - annual_labor_credit, ZERO)
    period_withholding = _q(annual_withholding / periods_per_year)

    pension_deduction = _q(base_pay * pension_deduction_pct / 100)

    net_salary = _q(gross_salary - period_withholding - pension_deduction - other_deductions + expense_reimbursement)

    employer_levy_zvw = _q(gross_salary * EMPLOYER_ZVW_RATE_PLACEHOLDER)
    notes.append(
        f"Employer Zvw levy uses a placeholder rate ({EMPLOYER_ZVW_RATE_PLACEHOLDER * 100}%) -- confirm against the "
        "published year's rate before relying on employer_costs_total. Employer WW/WIA/Aof/sector-fund premiums are "
        "not included at all (they are employer- and sector-specific); employer_costs_total therefore understates "
        "true employer cost and must not be treated as final."
    )
    employer_costs_total = _q(gross_salary + employer_levy_zvw)

    notes.append(
        "Wage tax/national insurance withholding is approximated by annualizing this period's gross pay through "
        "the same box-1 brackets and heffingskortingen used for personal income tax, then dividing back by the "
        "number of periods -- this is how the official loonbelastingtabel is itself derived, but the published "
        "table includes additional rounding/edge-case rules not reproduced here. Verify against the official "
        "tabel before relying on this for an actual filing."
    )

    return {
        "tax_year": rules.year,
        "period_type": period_type.value,
        "base_pay": _q(base_pay),
        "overtime_hours": overtime_hours,
        "overtime_amount": _q(overtime_amount),
        "holiday_allowance": holiday_allowance,
        "bonus_amount": bonus_amount,
        "expense_reimbursement": expense_reimbursement,
        "gross_salary": gross_salary,
        "taxable_wage": gross_salary,
        "annualized_taxable_income": annualized_taxable,
        "annual_general_tax_credit": annual_general_credit,
        "annual_labor_tax_credit": annual_labor_credit,
        "wage_tax_and_national_insurance": period_withholding,
        "general_tax_credit_applied": _q(annual_general_credit / periods_per_year),
        "labor_tax_credit_applied": _q(annual_labor_credit / periods_per_year),
        "pension_deduction": pension_deduction,
        "other_deductions": other_deductions,
        "net_salary": net_salary,
        "employer_levy_zvw": employer_levy_zvw,
        "employer_costs_total": employer_costs_total,
        "calculation_notes": " | ".join(notes),
        "requires_accountant_confirmation": True,
    }
