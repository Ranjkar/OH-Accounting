from decimal import Decimal

from app.accounting import entity_tax


def test_sole_proprietor_no_entrepreneur_deduction_without_hours_criterion():
    """Zelfstandigenaftrek requires the urencriterium; mkb-winstvrijstelling
    does not -- it applies to any IB-taxed business profit regardless."""
    result = entity_tax.estimate_sole_proprietor_income_tax(Decimal("50000"), hours_criterion_met=False, is_starter=False)
    assert result["entrepreneur_deduction_applied"] == Decimal("0")
    assert result["mkb_winstvrijstelling_applied"] == (Decimal("50000") * Decimal("0.127")).quantize(Decimal("0.01"))
    assert result["requires_accountant_confirmation"] is True


def test_sole_proprietor_with_hours_criterion_and_starter():
    result = entity_tax.estimate_sole_proprietor_income_tax(Decimal("50000"), hours_criterion_met=True, is_starter=True)
    assert result["entrepreneur_deduction_applied"] == Decimal("2470") + Decimal("2123")
    assert result["mkb_winstvrijstelling_applied"] > 0
    assert result["taxable_profit"] < Decimal("50000")
    assert result["net_income_tax"] > 0


def test_vof_profit_allocation_unequal_shares_and_eligibility():
    partners = [
        {"name": "Alice", "profit_share_percentage": "60", "hours_criterion_met": True, "is_starter": False},
        {"name": "Bob", "profit_share_percentage": "40", "hours_criterion_met": False, "is_starter": False},
    ]
    results = entity_tax.allocate_vof_profit(Decimal("100000"), partners)
    alice, bob = results[0], results[1]
    assert alice["allocated_profit"] == Decimal("60000.00")
    assert bob["allocated_profit"] == Decimal("40000.00")
    # Alice gets the entrepreneur deduction (hours criterion met); Bob never does, even
    # though he's a partner in the same VOF -- eligibility is per partner, never shared.
    assert alice["entrepreneur_deduction_applied"] > 0
    assert bob["entrepreneur_deduction_applied"] == Decimal("0")


def test_bv_corporate_tax_two_brackets():
    result = entity_tax.estimate_bv_corporate_tax(Decimal("300000"))
    expected = Decimal("200000") * Decimal("0.19") + Decimal("100000") * Decimal("0.258")
    assert result["corporate_tax"] == expected.quantize(Decimal("0.01"))
    assert result["retained_profit_after_tax"] == Decimal("300000") - result["corporate_tax"]


def test_dga_position_flags_below_minimum_salary():
    result = entity_tax.estimate_dga_position(
        proposed_dga_salary=Decimal("40000"), comparable_role_salary=None, highest_employee_salary=None,
        dividend_declared=Decimal("0"),
    )
    assert result["salary_check"]["compliant"] is False
    assert result["salary_check"]["required_minimum"] == Decimal("56000")


def test_dga_position_includes_box2_on_dividend():
    result = entity_tax.estimate_dga_position(
        proposed_dga_salary=Decimal("56000"), comparable_role_salary=None, highest_employee_salary=None,
        dividend_declared=Decimal("30000"),
    )
    assert result["box2_tax_on_dividend"] == (Decimal("30000") * Decimal("0.245")).quantize(Decimal("0.01"))
    assert result["total_estimated_personal_tax"] == result["box1_net_tax_on_salary"] + result["box2_tax_on_dividend"]


def test_foundation_never_guesses_tax_applicability():
    result = entity_tax.foundation_or_association_obligations_note("Stichting")
    assert result["corporate_income_tax_applicable"] is None
    assert result["vat_applicable"] is None
    assert result["requires_accountant_confirmation"] is True
