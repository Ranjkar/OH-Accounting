from datetime import date
from decimal import Decimal

from app.accounting import vat_engine
from app.accounting.vat_rules import CURRENT_RULE_VERSION
from app.core.security import hash_password
from app.models.accounting import AccountingTransaction, TransactionLineItem
from app.models.company import Company
from app.models.enums import (
    InputVatEligibility,
    LedgerSide,
    TransactionType,
    UserRole,
    VatTreatment,
)
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.tenant import Tenant
from app.models.user import User


def _setup(db_session):
    tenant = Tenant(name="T")
    db_session.add(tenant)
    db_session.flush()
    company = Company(tenant_id=tenant.id, name="C")
    db_session.add(company)
    db_session.flush()
    user = User(
        tenant_id=tenant.id,
        email="u@t.nl",
        hashed_password=hash_password("x"),
        full_name="U",
        role=UserRole.admin,
    )
    db_session.add(user)
    db_session.flush()
    fy = FinancialYear(company_id=company.id, year=2026, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db_session.add(fy)
    db_session.flush()
    period = VatPeriod(
        financial_year_id=fy.id,
        label="Q1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        filing_deadline=date(2026, 4, 30),
        payment_deadline=date(2026, 4, 30),
    )
    db_session.add(period)
    db_session.commit()
    return tenant, company, fy, period, user


def _add_transaction(
    db_session,
    tenant,
    company,
    fy,
    period,
    user,
    ledger_side,
    transaction_type,
    lines: list[dict],
    currency="EUR",
    fx_rate_to_eur=None,
) -> AccountingTransaction:
    net_total = sum((Decimal(str(l["net_amount"])) for l in lines), Decimal("0"))
    vat_total = sum((Decimal(str(l["vat_amount"])) for l in lines), Decimal("0"))
    gross_total = net_total + vat_total
    eur_fx = fx_rate_to_eur if currency != "EUR" else Decimal("1")

    transaction = AccountingTransaction(
        tenant_id=tenant.id,
        company_id=company.id,
        financial_year_id=fy.id,
        vat_period_id=period.id,
        transaction_type=transaction_type,
        ledger_side=ledger_side,
        invoice_date=date(2026, 2, 1),
        currency=currency,
        fx_rate_to_eur=eur_fx,
        net_amount=net_total,
        vat_amount=vat_total,
        gross_amount=gross_total,
        net_amount_eur=(net_total * eur_fx).quantize(Decimal("0.01")) if eur_fx is not None else None,
        vat_amount_eur=(vat_total * eur_fx).quantize(Decimal("0.01")) if eur_fx is not None else None,
        gross_amount_eur=(gross_total * eur_fx).quantize(Decimal("0.01")) if eur_fx is not None else None,
        created_by_user_id=user.id,
    )
    db_session.add(transaction)
    db_session.flush()
    for i, line in enumerate(lines, start=1):
        db_session.add(
            TransactionLineItem(
                transaction_id=transaction.id,
                line_number=i,
                net_amount=Decimal(str(line["net_amount"])),
                vat_rate=Decimal(str(line["vat_rate"])),
                vat_amount=Decimal(str(line["vat_amount"])),
                gross_amount=Decimal(str(line["net_amount"])) + Decimal(str(line["vat_amount"])),
                vat_treatment=line["vat_treatment"],
                input_vat_eligibility=line.get("input_vat_eligibility"),
                deductible_vat_amount=Decimal(str(line["deductible_vat_amount"])) if "deductible_vat_amount" in line else None,
            )
        )
    db_session.commit()
    return transaction


def test_single_21_percent_sale(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "100.00", "vat_rate": "21", "vat_amount": "21.00", "vat_treatment": VatTreatment.domestic_standard}],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_1a_net == Decimal("100.00")
    assert totals.box_1a_vat == Decimal("21.00")
    assert totals.box_5a_vat == Decimal("21.00")
    assert totals.box_5b_vat == Decimal("0")
    assert totals.net_payable == Decimal("21.00")


def test_single_9_percent_sale(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "200.00", "vat_rate": "9", "vat_amount": "18.00", "vat_treatment": VatTreatment.domestic_low}],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_1b_net == Decimal("200.00")
    assert totals.box_1b_vat == Decimal("18.00")
    assert totals.box_5a_vat == Decimal("18.00")


def test_multi_rate_invoice_splits_across_boxes(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [
            {"net_amount": "100.00", "vat_rate": "21", "vat_amount": "21.00", "vat_treatment": VatTreatment.domestic_standard},
            {"net_amount": "50.00", "vat_rate": "9", "vat_amount": "4.50", "vat_treatment": VatTreatment.domestic_low},
        ],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_1a_net == Decimal("100.00")
    assert totals.box_1a_vat == Decimal("21.00")
    assert totals.box_1b_net == Decimal("50.00")
    assert totals.box_1b_vat == Decimal("4.50")
    assert totals.box_5a_vat == Decimal("25.50")


def test_zero_rated_domestic_sale(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "500.00", "vat_rate": "0", "vat_amount": "0", "vat_treatment": VatTreatment.domestic_zero_or_exempt}],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_1e_net == Decimal("500.00")
    assert totals.box_5a_vat == Decimal("0")


def test_credit_note_against_sale_reduces_box_1a(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "100.00", "vat_rate": "21", "vat_amount": "21.00", "vat_treatment": VatTreatment.domestic_standard}],
    )
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.credit_note,
        [{"net_amount": "-50.00", "vat_rate": "21", "vat_amount": "-10.50", "vat_treatment": VatTreatment.domestic_standard}],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_1a_net == Decimal("50.00")
    assert totals.box_1a_vat == Decimal("10.50")


def test_export_and_eu_supply_sales_land_in_3a_and_3b(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "400.00", "vat_rate": "0", "vat_amount": "0", "vat_treatment": VatTreatment.export_non_eu}],
    )
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "250.00", "vat_rate": "0", "vat_amount": "0", "vat_treatment": VatTreatment.eu_supply}],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_3a_net == Decimal("400.00")
    assert totals.box_3b_net == Decimal("250.00")
    assert totals.box_5a_vat == Decimal("0")


def test_domestic_reverse_charge_received_hits_2a_and_nets_zero_when_fully_deductible(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.purchases, TransactionType.purchase_invoice,
        [
            {
                "net_amount": "1000.00",
                "vat_rate": "21",
                "vat_amount": "210.00",
                "vat_treatment": VatTreatment.domestic_reverse_charge_received,
                "input_vat_eligibility": InputVatEligibility.eligible,
                "deductible_vat_amount": "210.00",
            }
        ],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_2a_net == Decimal("1000.00")
    assert totals.box_2a_vat == Decimal("210.00")
    assert totals.box_5a_vat == Decimal("210.00")
    assert totals.box_5b_vat == Decimal("210.00")
    assert totals.net_payable == Decimal("0.00")


def test_eu_acquisition_hits_4b(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.purchases, TransactionType.purchase_invoice,
        [
            {
                "net_amount": "300.00",
                "vat_rate": "21",
                "vat_amount": "63.00",
                "vat_treatment": VatTreatment.eu_acquisition,
                "input_vat_eligibility": InputVatEligibility.eligible,
                "deductible_vat_amount": "63.00",
            }
        ],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_4b_net == Decimal("300.00")
    assert totals.box_4b_vat == Decimal("63.00")
    assert totals.box_5a_vat == Decimal("63.00")
    assert totals.box_5b_vat == Decimal("63.00")


def test_ordinary_domestic_purchase_never_touches_sales_boxes_only_5b(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.purchases, TransactionType.purchase_invoice,
        [
            {
                "net_amount": "1000.00",
                "vat_rate": "21",
                "vat_amount": "210.00",
                "vat_treatment": VatTreatment.domestic_standard,
                "input_vat_eligibility": InputVatEligibility.eligible,
                "deductible_vat_amount": "210.00",
            }
        ],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_1a_net == Decimal("0")
    assert totals.box_1a_vat == Decimal("0")
    assert totals.box_5a_vat == Decimal("0")  # ordinary purchases never owe VAT
    assert totals.box_5b_vat == Decimal("210.00")
    assert totals.net_payable == Decimal("-210.00")  # refund due


def test_partially_eligible_purchase_deducts_pro_rata_only(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.purchases, TransactionType.purchase_invoice,
        [
            {
                "net_amount": "1000.00",
                "vat_rate": "21",
                "vat_amount": "210.00",
                "vat_treatment": VatTreatment.domestic_standard,
                "input_vat_eligibility": InputVatEligibility.partially_eligible,
                "deductible_vat_amount": "105.00",  # 50% pro rata, computed by vat_rules in real usage
            }
        ],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_5b_vat == Decimal("105.00")


def test_ineligible_purchase_deducts_nothing(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.purchases, TransactionType.purchase_invoice,
        [
            {
                "net_amount": "500.00",
                "vat_rate": "21",
                "vat_amount": "105.00",
                "vat_treatment": VatTreatment.domestic_standard,
                "input_vat_eligibility": InputVatEligibility.ineligible,
                "deductible_vat_amount": "0",
            }
        ],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_5b_vat == Decimal("0")


def test_combined_sales_and_purchases_net_payable(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    # Sales: 1000 net @ 21% = 210 VAT due
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "1000.00", "vat_rate": "21", "vat_amount": "210.00", "vat_treatment": VatTreatment.domestic_standard}],
    )
    # Purchases: 400 net @ 21% = 84 VAT, fully deductible
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.purchases, TransactionType.purchase_invoice,
        [
            {
                "net_amount": "400.00",
                "vat_rate": "21",
                "vat_amount": "84.00",
                "vat_treatment": VatTreatment.domestic_standard,
                "input_vat_eligibility": InputVatEligibility.eligible,
                "deductible_vat_amount": "84.00",
            }
        ],
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_5a_vat == Decimal("210.00")
    assert totals.box_5b_vat == Decimal("84.00")
    assert totals.net_payable == Decimal("126.00")


def test_foreign_currency_without_fx_rate_is_excluded_from_totals(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "100.00", "vat_rate": "21", "vat_amount": "21.00", "vat_treatment": VatTreatment.domestic_standard}],
        currency="USD",
        fx_rate_to_eur=None,
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_1a_net == Decimal("0")
    assert len(totals.excluded_transaction_ids) == 1


def test_foreign_currency_with_fx_rate_converts_to_eur(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "100.00", "vat_rate": "21", "vat_amount": "21.00", "vat_treatment": VatTreatment.domestic_standard}],
        currency="USD",
        fx_rate_to_eur=Decimal("0.90"),
    )
    totals = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals.box_1a_net == Decimal("90.00")
    assert totals.box_1a_vat == Decimal("18.90")
    assert totals.excluded_transaction_ids == []


def test_transactions_outside_the_period_are_not_included(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    other_period = VatPeriod(
        financial_year_id=fy.id,
        label="Q2",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 6, 30),
        filing_deadline=date(2026, 7, 31),
        payment_deadline=date(2026, 7, 31),
    )
    db_session.add(other_period)
    db_session.commit()
    tx = _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "100.00", "vat_rate": "21", "vat_amount": "21.00", "vat_treatment": VatTreatment.domestic_standard}],
    )
    tx.vat_period_id = other_period.id
    db_session.commit()

    totals_q1 = vat_engine.calculate_vat_return(db_session, company.id, period.id)
    assert totals_q1.box_1a_net == Decimal("0")
    totals_q2 = vat_engine.calculate_vat_return(db_session, company.id, other_period.id)
    assert totals_q2.box_1a_net == Decimal("100.00")


def test_recalculate_and_store_persists_and_rejects_when_approved(db_session):
    tenant, company, fy, period, user = _setup(db_session)
    _add_transaction(
        db_session, tenant, company, fy, period, user, LedgerSide.sales, TransactionType.sales_invoice,
        [{"net_amount": "100.00", "vat_rate": "21", "vat_amount": "21.00", "vat_treatment": VatTreatment.domestic_standard}],
    )
    vat_return = vat_engine.recalculate_and_store(db_session, company.id, tenant.id, period)
    db_session.commit()
    assert vat_return.box_1a_vat == Decimal("21.00")
    assert vat_return.rules_version == CURRENT_RULE_VERSION

    from app.models.enums import VatReturnStatus

    vat_return.status = VatReturnStatus.approved
    db_session.commit()

    import pytest

    with pytest.raises(ValueError):
        vat_engine.recalculate_and_store(db_session, company.id, tenant.id, period)
