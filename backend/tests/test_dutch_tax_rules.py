from decimal import Decimal

from app.accounting import dutch_tax_rules as tax


def test_box1_tax_single_bracket():
    rules = tax.get_rule_set(2025)
    result = tax.calculate_box1_tax(Decimal("10000"), rules)
    assert result == Decimal("10000") * Decimal("0.3582")


def test_box1_tax_crosses_two_brackets():
    rules = tax.get_rule_set(2025)
    income = Decimal("50000")
    expected = Decimal("38441") * Decimal("0.3582") + (income - Decimal("38441")) * Decimal("0.3748")
    result = tax.calculate_box1_tax(income, rules)
    assert result == expected.quantize(Decimal("0.01"))


def test_box1_tax_crosses_all_three_brackets():
    rules = tax.get_rule_set(2025)
    income = Decimal("100000")
    expected = (
        Decimal("38441") * Decimal("0.3582")
        + (Decimal("76817") - Decimal("38441")) * Decimal("0.3748")
        + (income - Decimal("76817")) * Decimal("0.4950")
    )
    result = tax.calculate_box1_tax(income, rules)
    assert result == expected.quantize(Decimal("0.01"))


def test_box1_tax_zero_or_negative_income():
    rules = tax.get_rule_set(2025)
    assert tax.calculate_box1_tax(Decimal("0"), rules) == Decimal("0")
    assert tax.calculate_box1_tax(Decimal("-500"), rules) == Decimal("0")


def test_corporate_tax_brackets():
    rules = tax.get_rule_set(2025)
    assert tax.calculate_corporate_tax(Decimal("100000"), rules) == Decimal("19000.00")
    expected_300k = Decimal("200000") * Decimal("0.19") + Decimal("100000") * Decimal("0.258")
    assert tax.calculate_corporate_tax(Decimal("300000"), rules) == expected_300k.quantize(Decimal("0.01"))


def test_box2_tax_brackets():
    rules = tax.get_rule_set(2025)
    assert tax.calculate_box2_tax(Decimal("50000"), rules) == (Decimal("50000") * Decimal("0.245")).quantize(Decimal("0.01"))


def test_algemene_heffingskorting_full_below_threshold():
    rules = tax.get_rule_set(2025)
    assert tax.algemene_heffingskorting(Decimal("20000"), rules) == rules.algemene_heffingskorting_max


def test_algemene_heffingskorting_zero_above_threshold():
    rules = tax.get_rule_set(2025)
    assert tax.algemene_heffingskorting(Decimal("100000"), rules) == Decimal("0")


def test_algemene_heffingskorting_midpoint_phaseout():
    rules = tax.get_rule_set(2025)
    midpoint = (rules.algemene_heffingskorting_phaseout_start + rules.algemene_heffingskorting_phaseout_end) / 2
    result = tax.algemene_heffingskorting(midpoint, rules)
    expected = (rules.algemene_heffingskorting_max / 2).quantize(Decimal("0.01"))
    assert result == expected


def test_zelfstandigenaftrek_starter_vs_non_starter():
    rules = tax.get_rule_set(2025)
    assert tax.zelfstandigenaftrek_amount(rules, is_starter=False) == rules.zelfstandigenaftrek
    assert tax.zelfstandigenaftrek_amount(rules, is_starter=True) == rules.zelfstandigenaftrek + rules.startersaftrek


def test_mkb_winstvrijstelling_percentage():
    rules = tax.get_rule_set(2025)
    assert tax.mkb_winstvrijstelling(Decimal("10000"), rules) == Decimal("1270.00")
    assert tax.mkb_winstvrijstelling(Decimal("-500"), rules) == Decimal("0")


def test_kor_eligibility_threshold():
    rules = tax.get_rule_set(2025)
    assert tax.check_kor_eligible(Decimal("20000"), rules) is True
    assert tax.check_kor_eligible(Decimal("20000.01"), rules) is False


def test_dga_customary_salary_uses_highest_of_three():
    rules = tax.get_rule_set(2025)
    result = tax.check_dga_customary_salary(Decimal("56000"), Decimal("70000"), Decimal("60000"), rules)
    assert result["required_minimum"] == Decimal("70000")
    assert result["compliant"] is False
    assert result["shortfall"] == Decimal("14000")
    assert result["requires_accountant_confirmation"] is True


def test_dga_customary_salary_compliant():
    rules = tax.get_rule_set(2025)
    result = tax.check_dga_customary_salary(Decimal("60000"), None, None, rules)
    assert result["required_minimum"] == rules.dga_gebruikelijk_loon_norm
    assert result["compliant"] is True
    assert result["shortfall"] == Decimal("0")


def test_arbeidskorting_first_bracket():
    rules = tax.get_rule_set(2025)
    result = tax.arbeidskorting(Decimal("10000"), rules)
    assert result == (Decimal("10000") * Decimal("0.08053")).quantize(Decimal("0.01"))


def test_arbeidskorting_never_negative_at_high_income():
    rules = tax.get_rule_set(2025)
    result = tax.arbeidskorting(Decimal("500000"), rules)
    assert result >= Decimal("0")


def test_arbeidskorting_zero_income():
    rules = tax.get_rule_set(2025)
    assert tax.arbeidskorting(Decimal("0"), rules) == Decimal("0")


def test_special_remuneration_rate_picks_correct_bracket():
    rules = tax.get_rule_set(2025)
    # Reference points straight from the official "Witte tabel bijzondere beloning
    # Nederland, Standaard (uitgave januari 2025)" PDF (jonger dan AOW-leeftijd, met
    # loonheffingskorting: standaardtarief + verrekeningspercentage combined). The
    # combined rate is deliberately non-monotonic at low incomes -- e.g. 20,000 sits in
    # the 13,144 bracket (35.82% - 30.03% = 5.79%), well below the 0-11,050 rate of
    # 35.82% -- this is the real table's behavior, not a bug.
    assert tax.special_remuneration_rate(Decimal("0"), rules) == Decimal("0.3582")
    assert tax.special_remuneration_rate(Decimal("20000"), rules) == Decimal("0.0579")
    assert tax.special_remuneration_rate(Decimal("30000"), rules) == Decimal("0.3990")
    assert tax.special_remuneration_rate(Decimal("100000"), rules) == Decimal("0.5601")
    assert tax.special_remuneration_rate(Decimal("200000"), rules) == Decimal("0.4950")


def test_special_remuneration_tax_matches_official_worked_example():
    """Reference case: EUR 2,560 holiday allowance at an annual wage level in the
    EUR 28,407-36,661 bracket -> 35.82% + 4.08% = 39.90% combined rate, EUR 1,021.44
    withheld. This specific combination is independently cited by a third-party source
    (MKB Servicedesk) as well as derivable directly from the official PDF table."""
    rules = tax.get_rule_set(2025)
    result = tax.calculate_special_remuneration_tax(Decimal("2560"), Decimal("30000"), rules)
    assert result == Decimal("1021.44")


def test_employer_premiums_use_low_rates_for_permanent_small_employer():
    rules = tax.get_rule_set(2025)
    result = tax.employer_social_insurance_premiums(
        Decimal("4000"), Decimal("0"), has_permanent_contract=True, is_small_employer=True, rules=rules,
    )
    assert result["awf_rate_used"] == rules.awf_low_rate
    assert result["aof_rate_used"] == rules.aof_low_rate
    assert result["premium_base"] == Decimal("4000")
    assert result["zvw_premium"] == (Decimal("4000") * rules.zvw_employer_rate).quantize(Decimal("0.01"))


def test_employer_premiums_use_high_rates_for_flexible_large_employer():
    rules = tax.get_rule_set(2025)
    result = tax.employer_social_insurance_premiums(
        Decimal("4000"), Decimal("0"), has_permanent_contract=False, is_small_employer=False, rules=rules,
    )
    assert result["awf_rate_used"] == rules.awf_high_rate
    assert result["aof_rate_used"] == rules.aof_high_rate


def test_employer_premiums_respect_annual_cap():
    rules = tax.get_rule_set(2025)
    # Already earned EUR 74,000 this year; cap is EUR 75,864 -- only EUR 1,864 of
    # this period's EUR 4,000 gross wage should be subject to premiums.
    result = tax.employer_social_insurance_premiums(
        Decimal("4000"), Decimal("74000"), has_permanent_contract=True, is_small_employer=True, rules=rules,
    )
    assert result["premium_base"] == Decimal("1864")


def test_employer_premiums_zero_once_cap_fully_reached():
    rules = tax.get_rule_set(2025)
    result = tax.employer_social_insurance_premiums(
        Decimal("4000"), Decimal("80000"), has_permanent_contract=True, is_small_employer=True, rules=rules,
    )
    assert result["premium_base"] == Decimal("0")
    assert result["total_employer_premiums"] == Decimal("0.00")


def test_unknown_tax_year_raises_rather_than_falling_back():
    import pytest

    with pytest.raises(ValueError):
        tax.get_rule_set(1999)
