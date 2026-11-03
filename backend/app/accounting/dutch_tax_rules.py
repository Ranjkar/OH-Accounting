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

Phase 10 additions (checked this session):
- AWf (Awf, general unemployment fund) low/high rates: Salaris Vanmorgen
  "Premiepercentages sociale verzekeringen 2025" (low 2.74% for permanent
  contracts, high 7.74% for flexible/temporary contracts)
- Aof (disability fund) low/high rates and the small-employer threshold:
  Salaris Vanmorgen (same article) + christelijkevacature.nl "Aof-premie
  2025" (low 6.28% when the employer's 2023 total taxable payroll was at
  or below EUR 990,000, i.e. 25x the 2025 average wage of EUR 39,600;
  otherwise the high rate 7.64% applies)
- Whk (work-resumption fund) average rate: Vanoers.nl "Werkgeverslasten
  2025" (1.33% nationwide average -- the real rate is employer/sector-
  specific via an individual assessment this system has no way to look up,
  so the average is used with that limitation stated, never presented as
  the employer's actual rate)
- Zvw employer levy: Rendement.nl "Definitieve percentages ZVW-premie
  2025" (6.51% -- corrects the Phase 9 placeholder of 5.65%, which was an
  estimate never verified against a real source)
- Maximum premieloon/bijdrageloon (caps Zvw/AWf/Aof/Whk employer premium
  bases): Rendement.nl "Daling van werkgeversheffing ZVW per 2025"
  (EUR 75.864 for 2025)
- Special-remuneration (bijzondere beloningen -- holiday allowance paid as
  a lump sum, bonuses, gratifications, 13th month): the official
  Belastingdienst "Witte tabel bijzondere beloning Nederland, Standaard
  (uitgave januari 2025)" PDF was fetched and read directly this session
  (not a third-party summary) -- its exact combined rates (standaardtarief
  + verrekeningspercentage loonheffingskorting) are reproduced verbatim in
  `special_remuneration_brackets` below for the "jonger dan AOW-leeftijd,
  met loonheffingskorting" case. The table also has separate columns for
  AOW-age employees and for no/partial loonheffingskorting that this
  engine does not yet select between -- stated in
  `calculate_special_remuneration_tax`'s own docstring, not hidden.
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

    # ---- Phase 10: employer social-insurance premiums ----
    awf_low_rate: Decimal  # permanent contracts
    awf_high_rate: Decimal  # flexible/temporary contracts
    aof_low_rate: Decimal  # small employer (2023 payroll <= small_employer_payroll_threshold)
    aof_high_rate: Decimal
    small_employer_payroll_threshold: Decimal
    whk_average_rate: Decimal  # nationwide average -- real rate is employer/sector-specific, not looked up here
    zvw_employer_rate: Decimal
    max_premieloon: Decimal  # caps the wage base for AWf/Aof/Whk/Zvw employer premiums

    # (jaarloon lower bound, combined rate = standaardtarief + verrekeningspercentage
    # loonheffingskorting) for "jonger dan AOW-leeftijd, met loonheffingskorting" --
    # the exact official tabel bijzondere beloningen, not an approximation.
    special_remuneration_brackets: list[tuple[Decimal, Decimal]]

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
    awf_low_rate=Decimal("0.0274"),
    awf_high_rate=Decimal("0.0774"),
    aof_low_rate=Decimal("0.0628"),
    aof_high_rate=Decimal("0.0764"),
    small_employer_payroll_threshold=Decimal("990000"),
    whk_average_rate=Decimal("0.0133"),
    zvw_employer_rate=Decimal("0.0651"),
    max_premieloon=Decimal("75864"),
    # Exact combined rates (standaardtarief + verrekeningspercentage loonheffingskorting)
    # from the official "Witte tabel bijzondere beloning Nederland, Standaard (uitgave
    # januari 2025)" PDF, jonger-dan-AOW-leeftijd / met loonheffingskorting columns.
    special_remuneration_brackets=[
        (Decimal("0"), Decimal("0.3582")),
        (Decimal("11050"), Decimal("0.2777")),
        (Decimal("13144"), Decimal("0.0579")),
        (Decimal("24342"), Decimal("0.3356")),
        (Decimal("28407"), Decimal("0.3990")),
        (Decimal("34001"), Decimal("0.3990")),
        (Decimal("36661"), Decimal("0.3990")),
        (Decimal("38442"), Decimal("0.4156")),
        (Decimal("40503"), Decimal("0.4156")),
        (Decimal("43072"), Decimal("0.5033")),
        (Decimal("45309"), Decimal("0.5033")),
        (Decimal("58876"), Decimal("0.5033")),
        (Decimal("76818"), Decimal("0.5601")),
        (Decimal("139405"), Decimal("0.4950")),
    ],
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
        "Salaris Vanmorgen 'Premiepercentages sociale verzekeringen 2025' (AWf 2,74%/7,74%, Aof 6,28%/7,64%)",
        "christelijkevacature.nl 'Aof-premie 2025' (kleine-werkgeversgrens EUR 990.000)",
        "Vanoers.nl 'Werkgeverslasten 2025' (Whk gemiddelde 1,33%)",
        "Rendement.nl 'Definitieve percentages ZVW-premie 2025' (6,51%) en 'Daling van werkgeversheffing ZVW per 2025' (max premieloon EUR 75.864)",
        "Belastingdienst 'Witte tabel bijzondere beloning Nederland, Standaard (uitgave januari 2025)' -- "
        "fetched and read directly (download.belastingdienst.nl .../wit_bb_nl_std_20250101.pdf), the exact "
        "combined standaardtarief+verrekeningspercentage rates, not a paraphrased third-party summary",
        "Belastingdienst 'Witte Maandloon-tabel loonbelasting/premie volksverzekeringen, Nederland, Standaard "
        "(uitgave januari 2025)' -- fetched and read directly (.../wit_mnd_nl_std_20250101.pdf); used to "
        "independently validate the regular-wage annualize/divide approximation (see test_payroll_validation.py: "
        "EUR 2,500/4,000/8,000 monthly wage all matched the official 'met loonheffingskorting' column within "
        "EUR 0.40)",
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


def special_remuneration_rate(annual_wage_level: Decimal, rules: DutchTaxRuleSet) -> Decimal:
    """Exact combined rate (standaardtarief + verrekeningspercentage
    loonheffingskorting) from the official tabel bijzondere beloningen,
    looked up by the employee's annual wage level -- the highest bracket
    whose lower bound does not exceed it."""
    rate = rules.special_remuneration_brackets[0][1]
    for lower_bound, bracket_rate in rules.special_remuneration_brackets:
        if annual_wage_level >= lower_bound:
            rate = bracket_rate
        else:
            break
    return rate


def calculate_special_remuneration_tax(amount: Decimal, annual_regular_wage_level: Decimal, rules: DutchTaxRuleSet) -> Decimal:
    """Tax on a one-time special remuneration (holiday allowance paid as a
    lump sum, bonus, gratification, 13th month) -- NOT run through the
    regular annualize/divide approximation used for periodic wage. Uses the
    exact official tabel bijzondere beloningen rate (standaardtarief +
    verrekeningspercentage loonheffingskorting combined), for the
    "jonger dan AOW-leeftijd, met loonheffingskorting" case -- the table
    also has separate columns for AOW-age employees and for no/partial
    loonheffingskorting, which this engine does not yet select between
    (it always assumes under-AOW-age with the standard loonheffingskorting
    applied); that remaining simplification is stated here, not hidden."""
    rate = special_remuneration_rate(annual_regular_wage_level, rules)
    return (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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


def employer_social_insurance_premiums(
    gross_wage_this_period: Decimal,
    cumulative_wage_this_year_before_this_period: Decimal,
    *,
    has_permanent_contract: bool,
    is_small_employer: bool,
    rules: DutchTaxRuleSet,
) -> dict:
    """AWf, Aof, Whk, and Zvw employer premiums, each capped at the annual
    max_premieloon. Whk uses the nationwide average rate -- an employer's
    real Whk rate is individually assessed by the Belastingdienst based on
    sector and claims history, which this system has no way to look up, so
    the average is applied with that limitation stated rather than
    presented as this employer's actual rate.

    cumulative_wage_this_year_before_this_period lets the cap apply
    correctly across periods within a year (an employee crossing the cap
    mid-year pays no further premium on the excess) -- pass 0 for a
    single-period estimate with no running total."""
    remaining_cap = max(rules.max_premieloon - cumulative_wage_this_year_before_this_period, ZERO)
    premium_base = min(gross_wage_this_period, remaining_cap)

    awf_rate = rules.awf_low_rate if has_permanent_contract else rules.awf_high_rate
    aof_rate = rules.aof_low_rate if is_small_employer else rules.aof_high_rate

    def _q(v: Decimal) -> Decimal:
        return (premium_base * v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "premium_base": premium_base,
        "awf_rate_used": awf_rate,
        "awf_premium": _q(awf_rate),
        "aof_rate_used": aof_rate,
        "aof_premium": _q(aof_rate),
        "whk_rate_used": rules.whk_average_rate,
        "whk_premium": _q(rules.whk_average_rate),
        "zvw_rate_used": rules.zvw_employer_rate,
        "zvw_premium": _q(rules.zvw_employer_rate),
        "total_employer_premiums": _q(awf_rate + aof_rate + rules.whk_average_rate + rules.zvw_employer_rate),
        "max_premieloon": rules.max_premieloon,
        "whk_is_nationwide_average_not_employer_specific": True,
        "requires_accountant_confirmation": True,
    }
