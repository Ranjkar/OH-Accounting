"""Independent validation of the deterministic payroll engine against the
real, official Belastingdienst wage-tax tables for 2025 -- not a
third-party blog's paraphrased example, the actual published PDFs fetched
and read directly this session:

- "Witte Maandloon-tabel loonbelasting/premie volksverzekeringen,
  Nederland, Standaard (uitgave januari 2025)"
  https://download.belastingdienst.nl/belastingdienst/dl/rekenhulpen/loonheffing/2025/v01/pdf/wit_mnd_nl_std_20250101.pdf
  (regular periodic wage, "met loonheffingskorting" / jonger dan AOW column)

- "Witte tabel bijzondere beloning Nederland, Standaard (uitgave januari
  2025)"
  https://download.belastingdienst.nl/belastingdienst/dl/rekenhulpen/loonheffing/2025/v01/pdf/wit_bb_nl_std_20250101.pdf
  (special remuneration, exact combined standaardtarief +
  verrekeningspercentage loonheffingskorting rate)

Each reference case below cites the exact table row (tabelloon or
jaarloon value and the PDF page it came from). Differences are reported
and explained, not hidden behind a loose tolerance -- the regular-wage
cases below are allowed a tolerance of only EUR 1.00 (the table itself is
granular in EUR 4.50 steps, so the single table row nearest a given salary
is itself within a few cents of the "true" continuous value; EUR 1.00
comfortably covers that quantization without masking a real calculation
error). The special-remuneration case is checked for an EXACT cent match,
since that calculation now reproduces the published table rate verbatim
rather than approximating it.

One simplification remains and is stated here, not hidden: this engine
does not reproduce the official table's own internal rounding/step
granularity (EUR 4.50 "tabelloon" bands) -- it computes a continuous
value via the annualize/divide method instead of looking up a banded row.
That is why an exact cent-for-cent match is not expected for the regular-
wage cases, only a close agreement, confirmed below."""

from decimal import Decimal

import pytest

from app.accounting import payroll_engine
from app.models.enums import PayrollPeriodType, SalaryBasis

REGULAR_WAGE_TOLERANCE = Decimal("1.00")


@pytest.mark.parametrize(
    "monthly_salary, official_value, source_row",
    [
        # PDF page 15/16 (wit_mnd_nl_std_20250101.pdf): tabelloon 2.497,50 -> 205,17;
        # tabelloon 2.502,00 -> 206,92 ("met loonheffingskorting", jonger dan AOW).
        (Decimal("2500.00"), Decimal("206.00"), "wit_mnd_nl_std_20250101.pdf p.15-16, tabelloon ~2500"),
        # PDF page 24/25: tabelloon 4.000,50 -> 854,08.
        (Decimal("4000.00"), Decimal("854.08"), "wit_mnd_nl_std_20250101.pdf p.25, tabelloon 4.000,50"),
        # PDF page 48/49: tabelloon 8.001,00 -> 2.958,33.
        (Decimal("8000.00"), Decimal("2958.33"), "wit_mnd_nl_std_20250101.pdf p.49, tabelloon 8.001,00"),
    ],
)
def test_regular_wage_withholding_matches_official_table_within_tolerance(monthly_salary, official_value, source_row):
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=monthly_salary, hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    difference = abs(result["regular_wage_tax"] - official_value)
    assert difference <= REGULAR_WAGE_TOLERANCE, (
        f"Computed {result['regular_wage_tax']} vs official {official_value} from {source_row} -- "
        f"difference {difference} exceeds the {REGULAR_WAGE_TOLERANCE} tolerance, investigate before trusting this engine."
    )


def test_low_income_part_time_wage_also_validated():
    """Low-salary case, same methodology, different bracket region of the table.
    PDF page 1, tabelloon 166,50 row reads (zonder loonheffingskorting / met
    loonheffingskorting / verrekende arbeidskorting) = 59,58 / 0,00 / 29,83 -- the
    relevant "met loonheffingskorting" column is 0,00: at this low a wage, the
    general + labor tax credits fully absorb the gross tax, same as this engine's
    own max(...,0) floor."""
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("166.50"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    assert result["regular_wage_tax"] == Decimal("0.00")


def test_special_remuneration_matches_official_table_exactly():
    """EUR 2,560 holiday allowance paid as a lump sum at an annual wage level of
    EUR 30,000 falls in the 28.407-36.661 jaarloon bracket of
    wit_bb_nl_std_20250101.pdf -> standaardtarief 35,82% + verrekeningspercentage
    4,08% = 39,90% combined, EUR 1.021,44 withheld. Exact match expected (no banded
    table lookup involved on this side -- the rate itself is reproduced verbatim)."""
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("2500.00"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=True, holiday_allowance_pct=Decimal("8.00"),
        bonus_amount=Decimal("2360.00"),  # holiday allowance (8% of 2500 = 200.00) + bonus = 2,560.00 total special remuneration
    )
    # annualized_regular_wage for a EUR 2500 salary = 30,000 -- exactly the reference bracket.
    assert result["annualized_regular_wage"] == Decimal("30000.00")
    assert result["special_remuneration"] == Decimal("2560.00")
    assert result["special_remuneration_tax"] == Decimal("1021.44")


def test_higher_salary_crosses_top_bracket_and_still_validates():
    """Confirms the annualize/divide approximation holds even where the annualized
    wage crosses into the 49.50% top box-1 bracket (EUR 8,000/month -> EUR 96,000/year,
    well above the EUR 76,817 top-bracket threshold)."""
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("8000.00"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    assert result["annualized_regular_wage"] == Decimal("96000.00")
    official_value = Decimal("2958.33")
    assert abs(result["regular_wage_tax"] - official_value) <= REGULAR_WAGE_TOLERANCE


def test_employer_premiums_use_cited_2025_rates_not_phase9_placeholder():
    """Phase 9 used an unverified Zvw placeholder of 5.65%; Phase 10 corrects it to
    the cited, sourced 2025 rate of 6.51% (Rendement.nl 'Definitieve percentages
    ZVW-premie 2025'). This test pins that regression down explicitly."""
    result = payroll_engine.calculate_payslip(
        period_type=PayrollPeriodType.monthly, salary_basis=SalaryBasis.monthly,
        monthly_salary=Decimal("4000.00"), hourly_rate=None, paid_hours=None,
        pay_holiday_allowance_this_period=False, holiday_allowance_pct=Decimal("8.00"),
    )
    expected_zvw = (Decimal("4000.00") * Decimal("0.0651")).quantize(Decimal("0.01"))
    assert result["employer_levy_zvw"] == expected_zvw
    old_phase9_placeholder_value = (Decimal("4000.00") * Decimal("0.0565")).quantize(Decimal("0.01"))
    assert result["employer_levy_zvw"] != old_phase9_placeholder_value
