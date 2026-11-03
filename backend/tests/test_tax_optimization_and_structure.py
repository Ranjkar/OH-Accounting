from decimal import Decimal

from app.accounting import structure_comparator, tax_optimization


def test_zelfstandigenaftrek_opportunity_shows_savings_when_not_yet_applied():
    opportunities = tax_optimization.find_opportunities(
        legal_form_code="EENMANSZAAK", annual_profit=Decimal("50000"), annual_revenue=Decimal("60000"),
        hours_criterion_met=False, is_starter=False,
    )
    zza = next(o for o in opportunities if "Zelfstandigenaftrek" in o.recommendation)
    assert zza.potential_savings > 0
    assert zza.accountant_approval_required is True
    assert zza.confidence == "requires_hours_log_confirmation"


def test_kor_opportunity_reflects_eligibility():
    below = tax_optimization.find_opportunities(legal_form_code="EENMANSZAAK", annual_profit=None, annual_revenue=Decimal("15000"))
    above = tax_optimization.find_opportunities(legal_form_code="EENMANSZAAK", annual_profit=None, annual_revenue=Decimal("50000"))
    kor_below = next(o for o in below if "KOR" in o.recommendation)
    kor_above = next(o for o in above if "KOR" in o.recommendation)
    assert kor_below.confidence == "computed_from_recorded_data"
    assert kor_above.confidence == "not_eligible_at_current_revenue"


def test_catalogue_entries_never_fabricate_a_savings_figure():
    opportunities = tax_optimization.find_opportunities(legal_form_code="BV", annual_profit=Decimal("100000"), annual_revenue=Decimal("150000"))
    kia = next(o for o in opportunities if "KIA" in o.recommendation)
    assert kia.estimated_tax_before is None
    assert kia.estimated_tax_after is None
    assert kia.potential_savings is None
    assert kia.confidence == "requires_data_not_tracked"


def test_bv_comparison_only_offered_for_bv_nv():
    eenmanszaak_opps = tax_optimization.find_opportunities(legal_form_code="EENMANSZAAK", annual_profit=Decimal("50000"), annual_revenue=Decimal("60000"))
    bv_opps = tax_optimization.find_opportunities(legal_form_code="BV", annual_profit=Decimal("50000"), annual_revenue=Decimal("60000"))
    assert not any("BV vs. eenmanszaak" in o.recommendation for o in eenmanszaak_opps)
    assert any("BV vs. eenmanszaak" in o.recommendation for o in bv_opps)


# ---- Structure comparator ----


def test_structure_comparison_runs_all_three_structures():
    assumptions = structure_comparator.StructureAssumptions(
        annual_revenue=Decimal("200000"), annual_operating_expenses=Decimal("50000"),
    )
    result = structure_comparator.compare_structures(assumptions)
    assert result["eenmanszaak"]["total_tax"] > 0
    assert result["vof"]["total_tax"] > 0
    assert result["bv"]["total_tax"] > 0
    assert result["lowest_total_tax_option"] in ("eenmanszaak", "vof", "bv")
    assert result["requires_accountant_confirmation"] is True


def test_structure_comparison_never_claims_one_option_is_always_best():
    assumptions = structure_comparator.StructureAssumptions(annual_revenue=Decimal("50000"), annual_operating_expenses=Decimal("10000"))
    result = structure_comparator.compare_structures(assumptions)
    assert "never" in result["disclaimer"].lower() or "not" in result["disclaimer"].lower()


def test_vof_profit_split_matches_custom_shares():
    assumptions = structure_comparator.StructureAssumptions(
        annual_revenue=Decimal("200000"), annual_operating_expenses=Decimal("0"), num_partners=2,
        partner_profit_shares=[Decimal("70"), Decimal("30")],
    )
    result = structure_comparator.compare_structures(assumptions)
    per_partner = result["vof"]["per_partner"]
    assert per_partner[0]["allocated_profit"] == Decimal("140000.00")
    assert per_partner[1]["allocated_profit"] == Decimal("60000.00")


def test_bv_uses_norm_salary_by_default_and_flags_shortfall_if_underpaid():
    assumptions = structure_comparator.StructureAssumptions(
        annual_revenue=Decimal("200000"), annual_operating_expenses=Decimal("0"), dga_salary=Decimal("30000"),
    )
    result = structure_comparator.compare_structures(assumptions)
    assert result["bv"]["dga_salary_check"]["compliant"] is False
    assert result["bv"]["dga_salary_check"]["required_minimum"] == Decimal("56000")
