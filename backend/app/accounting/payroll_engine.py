"""Deterministic Dutch payroll calculation. Decimal arithmetic throughout;
never calls an LLM for any monetary figure.

Regular wage (base pay + overtime) is taxed by annualizing the period's
gross pay through the same box-1 brackets and credits that
app.accounting.dutch_tax_rules already uses for personal income tax --
methodologically how the official loonbelastingtabel is itself derived,
but the published table includes additional rounding/edge-case rules not
reproduced here.

Special remuneration (bijzondere beloningen -- holiday allowance paid as a
lump sum, bonuses, gratifications) is taxed separately via the exact
official "tabel bijzondere beloningen" combined rate (standaardtarief +
verrekeningspercentage loonheffingskorting, app.accounting.dutch_tax_rules.
calculate_special_remuneration_tax), NOT blended into the regular-wage
annualization the way Phase 9 did -- that was a real methodological bug,
fixed in Phase 10, and the official table (fetched and read directly, not
paraphrased) is now reproduced rather than approximated for this part of
the calculation. It still only covers the "jonger dan AOW-leeftijd, met
loonheffingskorting" case; the table's other columns (AOW-age employees,
no/reduced loonheffingskorting) are not yet selected between, and that
remaining gap is stated in calculation_notes on every result, not hidden.

Employer AWf/Aof/Whk/Zvw premiums are all calculated (Phase 9 only had a
placeholder Zvw figure), each capped at the annual max_premieloon via a
running per-employee cumulative total the caller supplies. Whk uses a
nationwide average (the real rate is an individual employer/sector
assessment this system cannot look up) and is_small_employer defaults to
True with an explicit note -- neither is silently presented as verified
fact.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.accounting import dutch_tax_rules as tax
from app.models.enums import PayrollPeriodType, SalaryBasis

ZERO = Decimal("0")

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
    has_permanent_contract: bool = True,
    is_small_employer: bool = True,
    cumulative_wage_this_year_before_this_period: Decimal = ZERO,
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

    # ---- Regular wage: annualize/divide approximation of the periodic table ----
    regular_wage = _q(base_pay + overtime_amount)
    annualized_regular_wage = regular_wage * periods_per_year

    # Pension premium is withheld pre-tax in NL: it reduces the wage base for
    # loonbelasting/premies volksverzekeringen before that base is annualized.
    # No AOW-franchise (threshold) is modelled -- the percentage is taken on
    # the full base pay, which is stated below rather than hidden.
    pension_deduction = _q(base_pay * pension_deduction_pct / 100)
    taxable_regular_wage = max(regular_wage - pension_deduction, ZERO)
    annualized_taxable_regular_wage = taxable_regular_wage * periods_per_year
    annual_gross_tax = tax.calculate_box1_tax(annualized_taxable_regular_wage, rules)
    annual_general_credit = tax.algemene_heffingskorting(annualized_taxable_regular_wage, rules)
    annual_labor_credit = tax.arbeidskorting(annualized_taxable_regular_wage, rules)
    annual_withholding = max(annual_gross_tax - annual_general_credit - annual_labor_credit, ZERO)
    regular_wage_tax = _q(annual_withholding / periods_per_year)
    if pension_deduction > 0:
        notes.append(
            "Pension premium is deducted pre-tax: the regular-wage tax base is the annualized regular wage minus "
            "the pension deduction. No AOW-franchise (threshold below which no pension premium is due) is applied "
            "-- the configured percentage is taken on the full base pay."
        )

    # ---- Special remuneration: exact official tabel bijzondere beloningen rate, taxed separately ----
    special_remuneration = _q(holiday_allowance + bonus_amount)
    special_remuneration_tax = tax.calculate_special_remuneration_tax(special_remuneration, annualized_taxable_regular_wage, rules)
    if special_remuneration > 0:
        notes.append(
            "Special remuneration (holiday allowance/bonus) is taxed using the exact official 'tabel bijzondere "
            "beloningen' combined rate (standaardtarief + verrekeningspercentage loonheffingskorting) for the "
            "employee's annualized regular wage -- this reproduces the real published table rather than "
            "approximating it, for the under-AOW-age / standard loonheffingskorting case. The table's AOW-age and "
            "no/reduced-loonheffingskorting columns are not yet selected between."
        )

    gross_salary = _q(regular_wage + special_remuneration)
    total_employee_withholding = _q(regular_wage_tax + special_remuneration_tax)

    net_salary = _q(gross_salary - total_employee_withholding - pension_deduction - other_deductions + expense_reimbursement)

    employer = tax.employer_social_insurance_premiums(
        gross_salary, cumulative_wage_this_year_before_this_period,
        has_permanent_contract=has_permanent_contract, is_small_employer=is_small_employer, rules=rules,
    )
    employer_costs_total = _q(gross_salary + employer["total_employer_premiums"])
    if pension_deduction > 0:
        notes.append(
            "Employer social insurance premiums are calculated on the full gross salary, not reduced by the "
            "pension deduction -- in practice premieloon is also reduced by an employee pension contribution, "
            "which is not yet modelled here."
        )

    notes.append(
        "Regular-wage withholding is approximated by annualizing this period's gross pay through the same box-1 "
        "brackets and heffingskortingen used for personal income tax, then dividing back by the number of periods "
        "-- this is how the official loonbelastingtabel is itself derived, but the published table includes "
        "additional rounding/edge-case rules not reproduced here."
    )
    notes.append(
        f"Employer premiums: AWf {employer['awf_rate_used'] * 100}% ({'permanent' if has_permanent_contract else 'flexible'} "
        f"contract rate), Aof {employer['aof_rate_used'] * 100}% ({'small' if is_small_employer else 'medium/large'} "
        f"employer rate, assumed -- confirm against the employer's actual 2023 payroll total), Whk "
        f"{employer['whk_rate_used'] * 100}% (nationwide average, not this employer's individually-assessed rate), "
        f"Zvw {employer['zvw_rate_used'] * 100}%, all capped at EUR {employer['max_premieloon']} cumulative wage for the year."
    )

    return {
        "tax_year": rules.year,
        "period_type": period_type.value,
        "base_pay": _q(base_pay),
        "overtime_hours": overtime_hours,
        "overtime_amount": _q(overtime_amount),
        "holiday_allowance": holiday_allowance,
        "bonus_amount": bonus_amount,
        "special_remuneration": special_remuneration,
        "expense_reimbursement": expense_reimbursement,
        "gross_salary": gross_salary,
        "taxable_wage": gross_salary,
        "annualized_regular_wage": annualized_regular_wage,
        "annualized_taxable_regular_wage": annualized_taxable_regular_wage,
        "annual_general_tax_credit": annual_general_credit,
        "annual_labor_tax_credit": annual_labor_credit,
        "regular_wage_tax": regular_wage_tax,
        "special_remuneration_tax": special_remuneration_tax,
        "wage_tax_and_national_insurance": total_employee_withholding,
        "general_tax_credit_applied": _q(annual_general_credit / periods_per_year),
        "labor_tax_credit_applied": _q(annual_labor_credit / periods_per_year),
        "pension_deduction": pension_deduction,
        "other_deductions": other_deductions,
        "net_salary": net_salary,
        "employer_premium_awf": employer["awf_premium"],
        "employer_premium_aof": employer["aof_premium"],
        "employer_premium_whk": employer["whk_premium"],
        "employer_levy_zvw": employer["zvw_premium"],
        "employer_premiums_total": employer["total_employer_premiums"],
        "employer_costs_total": employer_costs_total,
        "calculation_notes": " | ".join(notes),
        "requires_accountant_confirmation": True,
    }
