from decimal import Decimal

import pytest

from app.accounting import vat_rules
from app.models.enums import InputVatEligibility, LedgerSide, VatTreatment


def test_classify_standard_and_low_rate_by_number():
    assert vat_rules.classify_default_treatment(LedgerSide.sales, Decimal("21"), None) == VatTreatment.domestic_standard
    assert vat_rules.classify_default_treatment(LedgerSide.sales, Decimal("9"), None) == VatTreatment.domestic_low


def test_classify_other_rate():
    assert vat_rules.classify_default_treatment(LedgerSide.sales, Decimal("5"), None) == VatTreatment.domestic_other


def test_classify_zero_rate_domestic_counterparty():
    # NL VAT number is explicitly excluded from the EU bucket -- it's domestic.
    assert (
        vat_rules.classify_default_treatment(LedgerSide.sales, Decimal("0"), "NL123456789B01")
        == VatTreatment.domestic_zero_or_exempt
    )


def test_classify_zero_rate_with_no_counterparty_info_is_conservative():
    assert (
        vat_rules.classify_default_treatment(LedgerSide.sales, Decimal("0"), None)
        == VatTreatment.domestic_zero_or_exempt
    )


def test_classify_zero_rate_eu_counterparty_sales_is_eu_supply():
    assert (
        vat_rules.classify_default_treatment(LedgerSide.sales, Decimal("0"), "DE123456789")
        == VatTreatment.eu_supply
    )


def test_classify_zero_rate_eu_counterparty_purchases_is_eu_acquisition():
    assert (
        vat_rules.classify_default_treatment(LedgerSide.purchases, Decimal("0"), "FR12345678901")
        == VatTreatment.eu_acquisition
    )


def test_classify_no_rate_at_all_falls_back_to_zero_or_exempt():
    assert vat_rules.classify_default_treatment(LedgerSide.sales, None, None) == VatTreatment.domestic_zero_or_exempt


def test_box_for_line_sales_rates():
    assert vat_rules.box_for_line(LedgerSide.sales, VatTreatment.domestic_standard) == "1a"
    assert vat_rules.box_for_line(LedgerSide.sales, VatTreatment.domestic_low) == "1b"
    assert vat_rules.box_for_line(LedgerSide.sales, VatTreatment.domestic_other) == "1c"
    assert vat_rules.box_for_line(LedgerSide.sales, VatTreatment.private_use) == "1d"
    assert vat_rules.box_for_line(LedgerSide.sales, VatTreatment.domestic_zero_or_exempt) == "1e"
    assert vat_rules.box_for_line(LedgerSide.sales, VatTreatment.export_non_eu) == "3a"
    assert vat_rules.box_for_line(LedgerSide.sales, VatTreatment.eu_supply) == "3b"
    assert vat_rules.box_for_line(LedgerSide.sales, VatTreatment.eu_distance_sale) == "3c"


def test_box_for_line_purchase_rates_are_not_boxed_in_sales_sections():
    # Ordinary domestic purchase VAT never lands in 1a/1b/1c -- only box 5b (via deductible_vat_amount).
    assert vat_rules.box_for_line(LedgerSide.purchases, VatTreatment.domestic_standard) is None
    assert vat_rules.box_for_line(LedgerSide.purchases, VatTreatment.domestic_low) is None


def test_box_for_line_self_assessed_purchase_treatments():
    assert vat_rules.box_for_line(LedgerSide.purchases, VatTreatment.domestic_reverse_charge_received) == "2a"
    assert vat_rules.box_for_line(LedgerSide.purchases, VatTreatment.import_non_eu) == "4a"
    assert vat_rules.box_for_line(LedgerSide.purchases, VatTreatment.eu_acquisition) == "4b"


def test_box_for_line_rejects_invalid_combinations():
    with pytest.raises(ValueError):
        vat_rules.box_for_line(LedgerSide.sales, VatTreatment.domestic_reverse_charge_received)
    with pytest.raises(ValueError):
        vat_rules.box_for_line(LedgerSide.purchases, VatTreatment.export_non_eu)


def test_default_input_vat_eligibility_valid_invoice():
    assert (
        vat_rules.default_input_vat_eligibility(Decimal("21.00"), "INV-1", "NL123456789B01")
        == InputVatEligibility.eligible
    )


def test_default_input_vat_eligibility_zero_vat_is_eligible_trivially():
    assert vat_rules.default_input_vat_eligibility(Decimal("0"), None, None) == InputVatEligibility.eligible


def test_default_input_vat_eligibility_missing_invoice_number_requires_review():
    assert (
        vat_rules.default_input_vat_eligibility(Decimal("21.00"), None, "NL123456789B01")
        == InputVatEligibility.requires_review
    )


def test_default_input_vat_eligibility_missing_supplier_vat_requires_review():
    assert (
        vat_rules.default_input_vat_eligibility(Decimal("21.00"), "INV-1", None)
        == InputVatEligibility.requires_review
    )


def test_compute_deductible_vat_eligible_is_full_amount():
    assert vat_rules.compute_deductible_vat(Decimal("21.00"), InputVatEligibility.eligible, None) == Decimal("21.00")


def test_compute_deductible_vat_partially_eligible_applies_pro_rata():
    result = vat_rules.compute_deductible_vat(Decimal("21.00"), InputVatEligibility.partially_eligible, Decimal("50"))
    assert result == Decimal("10.50")


def test_compute_deductible_vat_partially_eligible_without_pro_rata_deducts_nothing():
    result = vat_rules.compute_deductible_vat(Decimal("21.00"), InputVatEligibility.partially_eligible, None)
    assert result == Decimal("0")


def test_compute_deductible_vat_ineligible_and_requires_review_deduct_nothing():
    assert vat_rules.compute_deductible_vat(Decimal("21.00"), InputVatEligibility.ineligible, None) == Decimal("0")
    assert vat_rules.compute_deductible_vat(Decimal("21.00"), InputVatEligibility.requires_review, None) == Decimal("0")
