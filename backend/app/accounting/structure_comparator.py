"""Interactive eenmanszaak vs VOF vs BV comparison. Pure what-if
computation over app.accounting.entity_tax/dutch_tax_rules -- never reads
or writes actual ledger/company records, so a comparison can never be
confused with real accounting data."""

from dataclasses import dataclass
from decimal import Decimal

from app.accounting import dutch_tax_rules as tax
from app.accounting import entity_tax

ZERO = Decimal("0")


@dataclass
class StructureAssumptions:
    annual_revenue: Decimal
    annual_operating_expenses: Decimal
    hours_criterion_met: bool = True
    is_starter: bool = False
    num_partners: int = 1
    partner_profit_shares: list[Decimal] | None = None  # VOF only; defaults to equal split
    dga_salary: Decimal | None = None  # BV only; defaults to the gebruikelijk-loon norm
    dividend_declared: Decimal = ZERO  # BV only


def _profit(assumptions: StructureAssumptions) -> Decimal:
    return max(assumptions.annual_revenue - assumptions.annual_operating_expenses, ZERO)


def compare_structures(assumptions: StructureAssumptions, rules: tax.DutchTaxRuleSet | None = None) -> dict:
    rules = rules or tax.get_rule_set()
    profit = _profit(assumptions)

    eenmanszaak = entity_tax.estimate_sole_proprietor_income_tax(profit, assumptions.hours_criterion_met, assumptions.is_starter, rules)

    shares = assumptions.partner_profit_shares or [Decimal(100) / assumptions.num_partners] * assumptions.num_partners
    vof_partners = [
        {"name": f"Partner {i + 1}", "profit_share_percentage": share, "hours_criterion_met": assumptions.hours_criterion_met, "is_starter": assumptions.is_starter}
        for i, share in enumerate(shares)
    ]
    vof_results = entity_tax.allocate_vof_profit(profit, vof_partners)
    vof_total_tax = sum((r["net_income_tax"] for r in vof_results), ZERO)

    dga_salary = assumptions.dga_salary if assumptions.dga_salary is not None else rules.dga_gebruikelijk_loon_norm
    corporate_taxable_profit = max(profit - dga_salary, ZERO)
    corporate = entity_tax.estimate_bv_corporate_tax(corporate_taxable_profit, rules)
    dga = entity_tax.estimate_dga_position(dga_salary, None, None, assumptions.dividend_declared, rules)
    bv_total_tax = corporate["corporate_tax"] + dga["total_estimated_personal_tax"]

    return {
        "tax_year": rules.year,
        "assumptions": {
            "annual_revenue": assumptions.annual_revenue,
            "annual_operating_expenses": assumptions.annual_operating_expenses,
            "profit_before_tax": profit,
            "hours_criterion_met": assumptions.hours_criterion_met,
            "num_partners": assumptions.num_partners,
        },
        "eenmanszaak": {
            "total_tax": eenmanszaak["net_income_tax"],
            "net_result": eenmanszaak["estimated_net_result"],
            "detail": eenmanszaak,
        },
        "vof": {
            "total_tax": vof_total_tax,
            "net_result": profit - vof_total_tax,
            "per_partner": vof_results,
        },
        "bv": {
            "total_tax": bv_total_tax,
            "net_result": profit - bv_total_tax,
            "corporate_tax": corporate["corporate_tax"],
            "retained_profit_after_corporate_tax": corporate["retained_profit_after_tax"],
            "dga_personal_tax": dga["total_estimated_personal_tax"],
            "dga_salary_used": dga_salary,
            "dga_salary_check": dga["salary_check"],
        },
        "lowest_total_tax_option": min(
            [("eenmanszaak", eenmanszaak["net_income_tax"]), ("vof", vof_total_tax), ("bv", bv_total_tax)],
            key=lambda pair: pair[1],
        )[0],
        "disclaimer": (
            "This compares estimated tax under simplified assumptions for one tax year only. It never claims one "
            "legal structure is always best -- a BV's retained profit stays inside the company (not personally "
            "available without further dividend tax), conversion costs and administrative burden are not "
            "quantified here, and personal circumstances (other income, mortgage, benefits) are not included. "
            "This is a planning aid, not a recommendation, and never writes to any actual company or ledger record."
        ),
        "requires_accountant_confirmation": True,
    }
