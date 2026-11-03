"""Evidence-based Dutch tax optimization catalogue. Every entry states its
legal basis, eligibility conditions, and required evidence. Only entries
backed by data this system actually has (profit, hours criterion, revenue)
get a computed before/after figure; everything else is returned as a
catalogue entry with estimated_tax_before/after left as None and a
confidence of "requires_data_not_tracked" -- never a fabricated number.

Never recommends anything resembling false invoices, concealed income,
fabricated hours, or artificial transactions -- every entry here is a
legitimate, named statutory facility."""

from dataclasses import dataclass, field
from decimal import Decimal

from app.accounting import dutch_tax_rules as tax
from app.accounting import entity_tax

ZERO = Decimal("0")


@dataclass
class TaxOpportunity:
    recommendation: str
    legal_basis: str
    tax_year: int
    eligibility_conditions: list[str]
    required_evidence: list[str]
    estimated_tax_before: Decimal | None
    estimated_tax_after: Decimal | None
    potential_savings: Decimal | None
    additional_costs: str
    risk: str
    confidence: str
    deadline: str
    accountant_approval_required: bool
    official_source: str
    is_deferred_not_saved: bool = False
    notes: list[str] = field(default_factory=list)


def _zelfstandigenaftrek_opportunity(annual_profit: Decimal, hours_criterion_met: bool, is_starter: bool, rules: tax.DutchTaxRuleSet) -> TaxOpportunity:
    without = entity_tax.estimate_sole_proprietor_income_tax(annual_profit, hours_criterion_met=False, is_starter=False, rules=rules)
    with_deduction = entity_tax.estimate_sole_proprietor_income_tax(annual_profit, hours_criterion_met=True, is_starter=is_starter, rules=rules)
    already_applied = hours_criterion_met
    return TaxOpportunity(
        recommendation="Zelfstandigenaftrek" + (" + startersaftrek" if is_starter else ""),
        legal_basis="Wet IB 2001, art. 3.76",
        tax_year=rules.year,
        eligibility_conditions=[f"Meet the urencriterium ({rules.urencriterium_hours} hours/year spent on the business)", "Be recognized as an entrepreneur for income tax purposes"],
        required_evidence=["Entrepreneur hours log (see Entrepreneur Hours module) covering the full tax year"],
        estimated_tax_before=without["net_income_tax"],
        estimated_tax_after=with_deduction["net_income_tax"],
        potential_savings=without["net_income_tax"] - with_deduction["net_income_tax"],
        additional_costs="None beyond keeping an hours log",
        risk="LOW" if already_applied else "MEDIUM",
        confidence="computed_from_recorded_data" if already_applied else "requires_hours_log_confirmation",
        deadline=f"Claimed on the {rules.year} income tax return",
        accountant_approval_required=not already_applied,
        official_source="Belastingdienst 'Zelfstandigenaftrek 2025'",
        notes=["Already assumed met for this estimate." if already_applied else "Not yet confirmed met -- the hours log must show at least the required hours before this is claimed."],
    )


def _kor_opportunity(annual_revenue: Decimal, rules: tax.DutchTaxRuleSet) -> TaxOpportunity:
    eligible = tax.check_kor_eligible(annual_revenue, rules)
    return TaxOpportunity(
        recommendation="Kleineondernemersregeling (KOR) -- VAT exemption",
        legal_basis="Wet OB 1968, art. 25",
        tax_year=rules.year,
        eligibility_conditions=[f"Annual revenue at or below EUR {rules.kor_revenue_threshold}", "Established in the Netherlands"],
        required_evidence=["Revenue total for the calendar year and the prior calendar year"],
        estimated_tax_before=None,
        estimated_tax_after=None,
        potential_savings=None,
        additional_costs="Cannot reclaim input VAT while using KOR -- only worthwhile if input VAT is low relative to turnover",
        risk="LOW",
        confidence="computed_from_recorded_data" if eligible else "not_eligible_at_current_revenue",
        deadline="Register at least 4 weeks before the VAT period it should take effect",
        accountant_approval_required=True,
        official_source="KVK/Belastingdienst KOR 2025 overview",
        notes=[f"Revenue EUR {annual_revenue} is {'within' if eligible else 'above'} the EUR {rules.kor_revenue_threshold} threshold."],
    )


def _mkb_winstvrijstelling_note(rules: tax.DutchTaxRuleSet) -> TaxOpportunity:
    return TaxOpportunity(
        recommendation="MKB-winstvrijstelling",
        legal_basis="Wet IB 2001, art. 3.79a",
        tax_year=rules.year,
        eligibility_conditions=["Automatic for anyone with box-1 business profit -- not elective"],
        required_evidence=[],
        estimated_tax_before=None, estimated_tax_after=None, potential_savings=None,
        additional_costs="None", risk="LOW", confidence="computed_from_recorded_data",
        deadline="Applied automatically on the income tax return",
        accountant_approval_required=False,
        official_source="Rendement.nl citing the Belastingdienst 2025 rate (12.7%)",
        notes=["Already included in the profit_and_loss/entity_tax figures above -- listed here for transparency, not as a separate action."],
    )


def _catalogue_entry_requiring_data(name: str, legal_basis: str, conditions: list[str], evidence: list[str], source: str, risk: str, tax_year: int) -> TaxOpportunity:
    return TaxOpportunity(
        recommendation=name, legal_basis=legal_basis, tax_year=tax_year,
        eligibility_conditions=conditions, required_evidence=evidence,
        estimated_tax_before=None, estimated_tax_after=None, potential_savings=None,
        additional_costs="Varies -- see required evidence", risk=risk,
        confidence="requires_data_not_tracked", deadline="Varies by facility",
        accountant_approval_required=True, official_source=source,
        is_deferred_not_saved=False,
        notes=["This system does not track the underlying data (e.g. specific asset purchases, payroll "
               "structure, or pension arrangements) needed to assess eligibility -- an accountant must "
               "evaluate this directly with the business owner."],
    )


def find_opportunities(
    *, legal_form_code: str, annual_profit: Decimal | None, annual_revenue: Decimal | None,
    hours_criterion_met: bool = False, is_starter: bool = False, rules: tax.DutchTaxRuleSet | None = None,
) -> list[TaxOpportunity]:
    rules = rules or tax.get_rule_set()
    opportunities: list[TaxOpportunity] = []

    if legal_form_code in ("EENMANSZAAK", "VOF", "MAATSCHAP", "CV") and annual_profit is not None:
        opportunities.append(_zelfstandigenaftrek_opportunity(annual_profit, hours_criterion_met, is_starter, rules))
        opportunities.append(_mkb_winstvrijstelling_note(rules))

    if annual_revenue is not None:
        opportunities.append(_kor_opportunity(annual_revenue, rules))

    opportunities.append(_catalogue_entry_requiring_data(
        "Kleinschaligheidsinvesteringsaftrek (KIA)", "Wet IB 2001, art. 3.41",
        ["Qualifying business asset investments within the relevant investment bracket for the year"],
        ["Itemized list of qualifying investments and amounts for the tax year"],
        "Belastingdienst ondernemersfaciliteiten overview", "LOW", rules.year,
    ))
    opportunities.append(_catalogue_entry_requiring_data(
        "Energie-investeringsaftrek (EIA) / Milieu-investeringsaftrek (MIA) / Vamil", "Wet IB 2001, art. 3.42/3.42a",
        ["Investment must be on the officially published Energy/Environment list for the relevant year"],
        ["Asset specification matched against the current Energy-list/Milieulijst code"],
        "RVO.nl energy/environment investment lists", "MEDIUM", rules.year,
    ))
    opportunities.append(_catalogue_entry_requiring_data(
        "Werkkostenregeling (WKR) -- tax-free allowance budget", "Wet LB 1964, art. 31a",
        ["Employer with a payroll -- a free space (vrije ruimte) percentage of total taxable wage may be given tax-free"],
        ["Total fiscal wage sum for the year and a list of reimbursements/benefits already provided"],
        "Belastingdienst werkkostenregeling", "LOW", rules.year,
    ))
    opportunities.append(_catalogue_entry_requiring_data(
        "Pension arrangement (lijfrente / oudedagsreserve alternatives)", "Wet IB 2001, art. 3.126a",
        ["Sufficient 'jaarruimte' pension contribution space", "No existing employer pension scheme covering the same years"],
        ["Pension contribution history and current jaarruimte calculation from a pension provider"],
        "Belastingdienst lijfrente/pensioen voorwaarden", "MEDIUM", rules.year,
    ))
    opportunities.append(_catalogue_entry_requiring_data(
        "Loss utilization (verliesverrekening)", "Wet IB 2001 art. 3.150 / Wet Vpb 1969 art. 20",
        ["A recorded fiscal loss in a prior or current year available to carry back/forward"],
        ["Fiscal loss amount and the year(s) it arose in"],
        "Belastingdienst verliesverrekening", "LOW", rules.year,
    ))

    if legal_form_code in ("BV", "NV"):
        opportunities.append(_catalogue_entry_requiring_data(
            "BV vs. eenmanszaak structure comparison", "N/A -- structural choice, not a single statutory facility",
            ["Material enough profit that corporate tax + dividend tax may beat income tax, or vice versa"],
            ["Use the Legal Structure Comparator with real profit and salary assumptions"],
            "This application's own structure-comparator tool", "MEDIUM", rules.year,
        ))

    return opportunities
