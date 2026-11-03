"""Versioned Dutch personal/corporate tax rules, mirroring the pattern in
vat_rules.py: nothing elsewhere hardcodes a bracket, percentage, or
threshold -- add a new DutchTaxRuleSet per tax year here instead.

Every figure below was looked up against public Belastingdienst-sourced
material during this session (via web search, not from training-data
memory alone) and is tagged with the source used. These are still
general-purpose figures, not a substitute for an accountant's own
confirmation for a specific taxpayer -- every function that uses them
returns `requires_accountant_confirmation: True` in its result, per this
phase's own instruction to mark anything not independently re-verified by
a licensed professional as requiring confirmation. Figures for a tax year
that has not yet closed (such as the current and next calendar year) are
also subject to final legislation and should be re-checked before relying
on them for an actual filing.

2025 sources (checked this session):
- Box 1 brackets: MKB Servicedesk / Belastingdienst box 1 overview
- Zelfstandigenaftrek + startersaftrek: Belastingdienst "Zelfstandigenaftrek 2025"
- MKB-winstvrijstelling: Rendement.nl citing the 2025 rate change to 12.7%
- Vpb (corporate tax) brackets: MKB Servicedesk / Belastingdienst Vpb 2025 changes
- KOR threshold: Qredits / KVK KOR 2025 overview
- DGA gebruikelijk loon norm: SRA / Belastingdienst normbedragen loonheffingen 2025
- Box 2 (aanmerkelijk belang): MKB Servicedesk / Belastingdienst box 2 overview
- Urencriterium: Belastingdienst "Voorwaarden urencriterium"
- Algemene heffingskorting / arbeidskorting: Belastingdienst "Tabel arbeidskorting 2025"
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class TaxBracket:
    upper_bound: Decimal | None  # None = no upper bound (top bracket)
    rate: Decimal  # e.g. Decimal("0.3582") for 35.82%


def _progressive_tax(amount: Decimal, brackets: list[TaxBracket]) -> Decimal:
    if amount <= 0:
        return ZERO
    tax = ZERO
    lower = ZERO
    for bracket in brackets:
        upper = bracket.upper_bound if bracket.upper_bound is not None else amount
        slice_amount = min(amount, upper) - lower
        if slice_amount > 0:
            tax += slice_amount * bracket.rate
        lower = upper
        if bracket.upper_bound is not None and amount <= bracket.upper_bound:
            break
    return tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DutchTaxRuleSet:
    year: int
    box1_brackets: list[TaxBracket]
    box2_brackets: list[TaxBracket]
    corporate_tax_brackets: list[TaxBracket]

    zelfstandigenaftrek: Decimal
    startersaftrek: Decimal
    mkb_winstvrijstelling_pct: Decimal

    kor_revenue_threshold: Decimal
    dga_gebruikelijk_loon_norm: Decimal

    algemene_heffingskorting_max: Decimal
    algemene_heffingskorting_phaseout_start: Decimal
    algemene_heffingskorting_phaseout_end: Decimal

    arbeidskorting_max: Decimal
    arbeidskorting_brackets: list[tuple[Decimal, Decimal, Decimal]]  # (lower_bound, base_amount, rate) per bracket

    urencriterium_hours: int

    sources: list[str] = field(default_factory=list)


RULES_2025 = DutchTaxRuleSet(
    year=2025,
    box1_brackets=[
        TaxBracket(Decimal("38441"), Decimal("0.3582")),
        TaxBracket(Decimal("76817"), Decimal("0.3748")),
        TaxBracket(None, Decimal("0.4950")),
    ],
    box2_brackets=[
        TaxBracket(Decimal("67804"), Decimal("0.245")),
        TaxBracket(None, Decimal("0.31")),
    ],
    corporate_tax_brackets=[
        TaxBracket(Decimal("200000"), Decimal("0.19")),
        TaxBracket(None, Decimal("0.258")),
    ],
    zelfstandigenaftrek=Decimal("2470"),
    startersaftrek=Decimal("2123"),
    mkb_winstvrijstelling_pct=Decimal("0.127"),
    kor_revenue_threshold=Decimal("20000"),
    dga_gebruikelijk_loon_norm=Decimal("56000"),
    algemene_heffingskorting_max=Decimal("3068"),
    algemene_heffingskorting_phaseout_start=Decimal("28406"),
    algemene_heffingskorting_phaseout_end=Decimal("76817"),
    arbeidskorting_max=Decimal("5599"),
    arbeidskorting_brackets=[
        (Decimal("0"), Decimal("0"), Decimal("0.08053")),
        (Decimal("12169"), Decimal("980"), Decimal("0.30030")),
        (Decimal("26288"), Decimal("5220"), Decimal("0.02258")),
        (Decimal("43071"), Decimal("5599"), Decimal("-0.06510")),
    ],
    urencriterium_hours=1225,
    sources=[
        "Belastingdienst box 1 tarieven 2025 (via MKB Servicedesk overview)",
        "Belastingdienst 'Zelfstandigenaftrek 2025'",
        "Rendement.nl: mkb-winstvrijstelling 12,7% in 2025",
        "Belastingdienst Vpb-tarieven 2025 (19% / 25,8%, drempel EUR 200.000)",
        "KVK/Qredits KOR 2025 overview (EUR 20.000 omzetgrens)",
        "SRA normbedragen loonheffingen 2025 (gebruikelijk loon DGA EUR 56.000)",
        "Belastingdienst box 2 tarieven 2025 (24,5% / 31%)",
        "Belastingdienst 'Voorwaarden urencriterium' (1.225 uur)",
        "Belastingdienst 'Tabel arbeidskorting 2025' / algemene heffingskorting 2025",
    ],
)

_RULE_SETS: dict[int, DutchTaxRuleSet] = {2025: RULES_2025}
CURRENT_TAX_YEAR = 2025


def get_rule_set(year: int | None = None) -> DutchTaxRuleSet:
    year = year or CURRENT_TAX_YEAR
    if year not in _RULE_SETS:
        raise ValueError(
            f"No Dutch tax rule set recorded for {year} -- add one to dutch_tax_rules.py "
            f"with a verified source before using it, rather than falling back to another year's rates."
        )
    return _RULE_SETS[year]


def calculate_box1_tax(taxable_income: Decimal, rules: DutchTaxRuleSet) -> Decimal:
    return _progressive_tax(taxable_income, rules.box1_brackets)


def calculate_box2_tax(income: Decimal, rules: DutchTaxRuleSet) -> Decimal:
    return _progressive_tax(income, rules.box2_brackets)


def calculate_corporate_tax(taxable_profit: Decimal, rules: DutchTaxRuleSet) -> Decimal:
    return _progressive_tax(taxable_profit, rules.corporate_tax_brackets)


def algemene_heffingskorting(verzamelinkomen: Decimal, rules: DutchTaxRuleSet) -> Decimal:
    """Linear phase-out between phaseout_start and phaseout_end -- the
    actual Belastingdienst formula is piecewise-linear with these two
    anchor points, not a flat cliff."""
    if verzamelinkomen <= rules.algemene_heffingskorting_phaseout_start:
        return rules.algemene_heffingskorting_max
    if verzamelinkomen >= rules.algemene_heffingskorting_phaseout_end:
        return ZERO
    span = rules.algemene_heffingskorting_phaseout_end - rules.algemene_heffingskorting_phaseout_start
    reduction_fraction = (verzamelinkomen - rules.algemene_heffingskorting_phaseout_start) / span
    return (rules.algemene_heffingskorting_max * (1 - reduction_fraction)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def arbeidskorting(arbeidsinkomen: Decimal, rules: DutchTaxRuleSet) -> Decimal:
    """Labor tax credit, piecewise-linear over 4 brackets (under-AOW-age
    table). Clamped at 0 -- the last bracket's negative rate phases the
    credit down to nothing at high income, it must never go negative."""
    if arbeidsinkomen <= 0:
        return ZERO
    bracket = rules.arbeidskorting_brackets[0]
    for candidate in rules.arbeidskorting_brackets:
        if arbeidsinkomen >= candidate[0]:
            bracket = candidate
        else:
            break
    lower_bound, base_amount, rate = bracket
    credit = base_amount + (arbeidsinkomen - lower_bound) * rate
    return max(min(credit, rules.arbeidskorting_max), ZERO).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def zelfstandigenaftrek_amount(rules: DutchTaxRuleSet, is_starter: bool) -> Decimal:
    amount = rules.zelfstandigenaftrek
    if is_starter:
        amount += rules.startersaftrek
    return amount


def mkb_winstvrijstelling(profit_after_entrepreneur_deductions: Decimal, rules: DutchTaxRuleSet) -> Decimal:
    if profit_after_entrepreneur_deductions <= 0:
        return ZERO
    return (profit_after_entrepreneur_deductions * rules.mkb_winstvrijstelling_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def check_kor_eligible(annual_revenue_eur: Decimal, rules: DutchTaxRuleSet) -> bool:
    return annual_revenue_eur <= rules.kor_revenue_threshold


def check_dga_customary_salary(
    proposed_salary: Decimal,
    comparable_role_salary: Decimal | None,
    highest_employee_salary: Decimal | None,
    rules: DutchTaxRuleSet,
) -> dict:
    """The required minimum is the HIGHEST of: the norm amount, the
    highest-paid employee's salary, and the comparable-role salary (when
    known) -- never just the flat norm amount, which is only a floor."""
    candidates = [rules.dga_gebruikelijk_loon_norm]
    if comparable_role_salary is not None:
        candidates.append(comparable_role_salary)
    if highest_employee_salary is not None:
        candidates.append(highest_employee_salary)
    required_minimum = max(candidates)
    compliant = proposed_salary >= required_minimum
    return {
        "proposed_salary": proposed_salary,
        "required_minimum": required_minimum,
        "norm_amount": rules.dga_gebruikelijk_loon_norm,
        "compliant": compliant,
        "shortfall": ZERO if compliant else (required_minimum - proposed_salary),
        "explanation": (
            "Gebruikelijk loon must be at least the highest of: the published norm amount, the "
            "highest salary paid to another employee of the BV, or the salary for the most comparable "
            "role elsewhere. A lower salary is only legally defensible with documented special "
            "circumstances and accountant sign-off -- this engine never reduces it automatically."
        ),
        "requires_accountant_confirmation": True,
    }
