"""Versioned Dutch VAT rules: rates and the declaration-box mapping.

This is the single source of truth for which box a transaction line lands
in. Nothing elsewhere in the codebase should hardcode a box number or a
rate -- when the rates change (as the Belastingdienst does from time to
time), add a new RuleSet version here rather than editing call sites.

Box reference (current Belastingdienst OB-aangifte structure):
  1a/1b/1c  domestic sales by rate (high/low/other)
  1d        private-use correction
  1e        domestic zero-rated or exempt sales
  2a        domestic reverse-charge received (you are the recipient)
  3a/3b/3c  export (non-EU) / EU supply / EU distance sale
  4a/4b     import (non-EU) / EU acquisition
  5a        total VAT payable (sum of the VAT-due boxes above)
  5b        total deductible input VAT

Note: the official form does not currently have a literal "5g" box; the
instructions that produced this module asked for one, so `net_payable`
(5a - 5b) is exposed as that final total rather than inventing a box that
doesn't exist on the real form.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import InputVatEligibility, LedgerSide, VatTreatment

EU_COUNTRY_CODES = frozenset(
    {
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR",
        "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
        "SE", "SI", "SK",
    }
)


@dataclass(frozen=True)
class VatRuleSet:
    version: str
    standard_rate: Decimal
    low_rate: Decimal


RULE_VERSIONS: dict[str, VatRuleSet] = {
    "nl-2024": VatRuleSet(version="nl-2024", standard_rate=Decimal("21"), low_rate=Decimal("9")),
}
CURRENT_RULE_VERSION = "nl-2024"


def get_rule_set(version: str | None = None) -> VatRuleSet:
    return RULE_VERSIONS[version or CURRENT_RULE_VERSION]


# (ledger_side, vat_treatment) -> box code, or None when the treatment does not
# contribute to a sales/acquisition box at all (ordinary domestic purchases only
# ever contribute to box 5b, handled separately in the engine).
BOX_MAP: dict[tuple[LedgerSide, VatTreatment], str | None] = {
    (LedgerSide.sales, VatTreatment.domestic_standard): "1a",
    (LedgerSide.sales, VatTreatment.domestic_low): "1b",
    (LedgerSide.sales, VatTreatment.domestic_other): "1c",
    (LedgerSide.sales, VatTreatment.private_use): "1d",
    (LedgerSide.sales, VatTreatment.domestic_zero_or_exempt): "1e",
    (LedgerSide.sales, VatTreatment.exempt): "1e",
    (LedgerSide.sales, VatTreatment.export_non_eu): "3a",
    (LedgerSide.sales, VatTreatment.eu_supply): "3b",
    (LedgerSide.sales, VatTreatment.eu_distance_sale): "3c",
    (LedgerSide.purchases, VatTreatment.domestic_standard): None,
    (LedgerSide.purchases, VatTreatment.domestic_low): None,
    (LedgerSide.purchases, VatTreatment.domestic_other): None,
    (LedgerSide.purchases, VatTreatment.domestic_zero_or_exempt): None,
    (LedgerSide.purchases, VatTreatment.exempt): None,
    (LedgerSide.purchases, VatTreatment.domestic_reverse_charge_received): "2a",
    (LedgerSide.purchases, VatTreatment.import_non_eu): "4a",
    (LedgerSide.purchases, VatTreatment.eu_acquisition): "4b",
}

# Boxes whose VAT amount counts toward box 5a (total VAT payable).
VAT_DUE_BOXES = {"1a", "1b", "1c", "1d", "2a", "4a", "4b"}


def box_for_line(ledger_side: LedgerSide, treatment: VatTreatment) -> str | None:
    key = (ledger_side, treatment)
    if key not in BOX_MAP:
        raise ValueError(f"VAT treatment {treatment.value} is not valid on the {ledger_side.value} side")
    return BOX_MAP[key]


def is_self_assessed_purchase_treatment(treatment: VatTreatment) -> bool:
    """Reverse-charge/import/EU-acquisition purchases: you self-assess the VAT
    (it counts toward 5a) and, if eligible, deduct the same amount in 5b."""
    return treatment in (
        VatTreatment.domestic_reverse_charge_received,
        VatTreatment.import_non_eu,
        VatTreatment.eu_acquisition,
    )


def classify_default_treatment(
    ledger_side: LedgerSide,
    vat_rate: Decimal | None,
    counterparty_vat_number: str | None,
    rules: VatRuleSet | None = None,
) -> VatTreatment:
    """Deterministic default classification from already-extracted, approved
    fields. Never guesses reverse-charge/export/import -- those require explicit
    accountant confirmation and default to the plain rate-based treatment or,
    when the rate is 0/absent, the conservative zero-or-exempt bucket."""
    rules = rules or get_rule_set()

    if vat_rate is not None:
        if vat_rate == rules.standard_rate:
            return VatTreatment.domestic_standard
        if vat_rate == rules.low_rate:
            return VatTreatment.domestic_low
        if vat_rate != 0:
            return VatTreatment.domestic_other

    counterparty_country = country_from_vat_number(counterparty_vat_number)
    if counterparty_country and counterparty_country != "NL" and counterparty_country in EU_COUNTRY_CODES:
        return VatTreatment.eu_supply if ledger_side == LedgerSide.sales else VatTreatment.eu_acquisition

    return VatTreatment.domestic_zero_or_exempt


def country_from_vat_number(vat_number: str | None) -> str | None:
    if not vat_number or len(vat_number) < 2:
        return None
    prefix = vat_number[:2].upper()
    return prefix if prefix.isalpha() else None


def default_input_vat_eligibility(
    vat_amount: Decimal, invoice_number: str | None, supplier_vat_number: str | None
) -> InputVatEligibility:
    """Conservative default: only auto-approve as ELIGIBLE when the purchase
    has the hallmarks of a valid deductible invoice. Never auto-assigns
    INELIGIBLE or PARTIALLY_ELIGIBLE -- those require accountant judgment."""
    if vat_amount == 0:
        return InputVatEligibility.eligible
    if invoice_number and supplier_vat_number:
        return InputVatEligibility.eligible
    return InputVatEligibility.requires_review


def compute_deductible_vat(
    vat_amount: Decimal, eligibility: InputVatEligibility | None, pro_rata_percentage: Decimal | None
) -> Decimal:
    """Never assume full deductibility: ELIGIBLE deducts in full, PARTIALLY_ELIGIBLE
    applies the company's pro-rata percentage (0 if none is configured -- we do not
    guess a fraction), everything else deducts nothing until an accountant resolves it."""
    if eligibility == InputVatEligibility.eligible:
        return vat_amount
    if eligibility == InputVatEligibility.partially_eligible:
        if pro_rata_percentage is None:
            return Decimal("0")
        return (vat_amount * pro_rata_percentage / Decimal("100")).quantize(Decimal("0.01"))
    return Decimal("0")
