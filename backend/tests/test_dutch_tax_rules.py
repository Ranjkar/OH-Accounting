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


def test_unknown_tax_year_raises_rather_than_falling_back():
    import pytest

    with pytest.raises(ValueError):
        tax.get_rule_set(1999)
