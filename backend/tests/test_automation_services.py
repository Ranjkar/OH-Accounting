from datetime import date, timedelta
from decimal import Decimal

from app.accounting import anomaly_detection, categorization, cash_flow, recurring_detection
from app.core.security import hash_password
from app.models.accounting import AccountingTransaction, Payment
from app.models.banking import BankAccount, BankImportBatch, BankTransaction
from app.models.categorization import CategorizationRule
from app.models.company import Company
from app.models.enums import (
    AnomalyStatus,
    CategorizationRuleType,
    CategorySource,
    LedgerSide,
    PaymentStatus,
    ReconciliationStatus,
    RecurringStatus,
    TransactionType,
    UserRole,
)
from app.models.financial_year import FinancialYear
from app.models.tenant import Tenant
from app.models.user import User


def _setup(db_session):
    tenant = Tenant(name="T")
    db_session.add(tenant)
    db_session.flush()
    company = Company(tenant_id=tenant.id, name="C")
    db_session.add(company)
    db_session.flush()
    user = User(tenant_id=tenant.id, email="u@t.nl", hashed_password=hash_password("x"), full_name="U", role=UserRole.admin)
    db_session.add(user)
    db_session.flush()
    fy = FinancialYear(company_id=company.id, year=2027, start_date=date(2027, 1, 1), end_date=date(2027, 12, 31))
    db_session.add(fy)
    db_session.flush()
    bank_account = BankAccount(tenant_id=tenant.id, company_id=company.id, iban="NL91ABNA0417164300", account_name="Main")
    db_session.add(bank_account)
    db_session.flush()
    batch = BankImportBatch(
        tenant_id=tenant.id, company_id=company.id, bank_account_id=bank_account.id,
        source_format="CSV", original_filename="f.csv", storage_path="x", imported_by_user_id=user.id,
    )
    db_session.add(batch)
    db_session.flush()
    db_session.commit()
    return tenant, company, fy, user, bank_account, batch


def _invoice(db_session, company, fy, user, *, invoice_number="INV-1", gross=Decimal("121.00"), net=Decimal("100.00"),
             counterparty="Klant Retail B.V.", iban=None, invoice_date=date(2027, 2, 1), due_date=date(2027, 6, 1),
             ledger_side=LedgerSide.purchases):
    tx = AccountingTransaction(
        tenant_id=company.tenant_id, company_id=company.id, financial_year_id=fy.id,
        transaction_type=TransactionType.purchase_invoice if ledger_side == LedgerSide.purchases else TransactionType.sales_invoice,
        ledger_side=ledger_side,
        invoice_number=invoice_number, counterparty_name=counterparty, counterparty_iban=iban,
        invoice_date=invoice_date, due_date=due_date,
        net_amount=net, vat_amount=gross - net, gross_amount=gross,
        created_by_user_id=user.id,
    )
    db_session.add(tx)
    db_session.flush()
    return tx


def _bank_tx(db_session, company, bank_account, batch, *, amount, booking_date=date(2027, 3, 1), counterparty_name=None,
             counterparty_iban=None, status=ReconciliationStatus.unmatched):
    tx = BankTransaction(
        tenant_id=company.tenant_id, company_id=company.id, bank_account_id=bank_account.id, import_batch_id=batch.id,
        dedupe_hash=f"hash-{amount}-{booking_date}-{counterparty_name}", booking_date=booking_date, amount=amount, currency="EUR",
        counterparty_name=counterparty_name, counterparty_iban=counterparty_iban,
        source_format="CSV", raw_data={}, reconciliation_status=status,
    )
    db_session.add(tx)
    db_session.flush()
    return tx


# ---- categorization ----


def test_apply_rules_matches_supplier_name(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    rule = CategorizationRule(
        tenant_id=tenant.id, company_id=company.id, rule_type=CategorizationRuleType.supplier_name,
        match_value="Klant Retail", category="Office expenses", created_by_user_id=user.id,
    )
    db_session.add(rule)
    db_session.flush()
    tx = _invoice(db_session, company, fy, user, counterparty="Klant Retail B.V.")

    matched = categorization.apply_rules(db_session, tx)
    assert matched is True
    assert tx.expense_category == "Office expenses"
    assert tx.category_source == CategorySource.rule


def test_apply_rules_never_crosses_company_boundary(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    other_company = Company(tenant_id=tenant.id, name="Other")
    db_session.add(other_company)
    db_session.flush()
    rule = CategorizationRule(
        tenant_id=tenant.id, company_id=other_company.id, rule_type=CategorizationRuleType.supplier_name,
        match_value="Klant Retail", category="Office expenses", created_by_user_id=user.id,
    )
    db_session.add(rule)
    db_session.flush()
    tx = _invoice(db_session, company, fy, user, counterparty="Klant Retail B.V.")

    matched = categorization.apply_rules(db_session, tx)
    assert matched is False
    assert tx.expense_category is None


def test_create_rule_from_correction_then_future_transactions_match(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    tx = _invoice(db_session, company, fy, user, counterparty="Acme Supplies")

    rule = categorization.create_rule_from_correction(db_session, tx, "Equipment", user.id)
    db_session.commit()
    assert rule is not None

    tx2 = _invoice(db_session, company, fy, user, counterparty="Acme Supplies", invoice_number="INV-2")
    matched = categorization.apply_rules(db_session, tx2)
    assert matched is True
    assert tx2.expense_category == "Equipment"


# ---- recurring detection ----


def test_detect_recurring_monthly_pattern(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    base = date(2027, 1, 5)
    for i in range(4):
        _bank_tx(
            db_session, company, bank_account, batch, amount=Decimal("-50.00"),
            booking_date=base + timedelta(days=30 * i), counterparty_name="Telco B.V.",
        )
    db_session.commit()

    patterns = recurring_detection.detect_recurring_patterns(db_session, company.id, tenant.id)
    db_session.commit()
    assert len(patterns) == 1
    assert patterns[0].counterparty_name == "Telco B.V."
    assert patterns[0].occurrence_count == 4


def test_detect_recurring_ignores_too_few_occurrences(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _bank_tx(db_session, company, bank_account, batch, amount=Decimal("-50.00"), booking_date=date(2027, 1, 5), counterparty_name="Rare Vendor")
    _bank_tx(db_session, company, bank_account, batch, amount=Decimal("-50.00"), booking_date=date(2027, 2, 4), counterparty_name="Rare Vendor")
    db_session.commit()

    patterns = recurring_detection.detect_recurring_patterns(db_session, company.id, tenant.id)
    assert patterns == []


def test_detect_recurring_is_idempotent_and_updates_existing_row(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    base = date(2027, 1, 5)
    for i in range(4):
        _bank_tx(db_session, company, bank_account, batch, amount=Decimal("-50.00"), booking_date=base + timedelta(days=30 * i), counterparty_name="Telco B.V.")
    db_session.commit()

    first = recurring_detection.detect_recurring_patterns(db_session, company.id, tenant.id)
    db_session.commit()
    second = recurring_detection.detect_recurring_patterns(db_session, company.id, tenant.id)
    db_session.commit()

    assert len(first) == 1
    assert len(second) == 1
    assert first[0].id == second[0].id


# ---- anomaly detection ----


def test_detect_duplicate_payments(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    tx_a = _invoice(db_session, company, fy, user, invoice_number="INV-A")
    tx_b = _invoice(db_session, company, fy, user, invoice_number="INV-B")
    pay_date = date(2027, 3, 1)
    db_session.add(Payment(tenant_id=tenant.id, company_id=company.id, transaction_id=tx_a.id, amount=Decimal("121.00"), payment_date=pay_date, created_by_user_id=user.id))
    db_session.add(Payment(tenant_id=tenant.id, company_id=company.id, transaction_id=tx_b.id, amount=Decimal("121.00"), payment_date=pay_date, created_by_user_id=user.id))
    db_session.commit()

    flags = anomaly_detection.detect_duplicate_payments(db_session, company.id, tenant.id)
    db_session.commit()
    assert len(flags) == 1
    assert flags[0].rule_code == "DUPLICATE_PAYMENT"
    assert flags[0].status == AnomalyStatus.open


def test_detect_duplicate_payments_is_idempotent(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    tx_a = _invoice(db_session, company, fy, user, invoice_number="INV-A")
    tx_b = _invoice(db_session, company, fy, user, invoice_number="INV-B")
    pay_date = date(2027, 3, 1)
    db_session.add(Payment(tenant_id=tenant.id, company_id=company.id, transaction_id=tx_a.id, amount=Decimal("121.00"), payment_date=pay_date, created_by_user_id=user.id))
    db_session.add(Payment(tenant_id=tenant.id, company_id=company.id, transaction_id=tx_b.id, amount=Decimal("121.00"), payment_date=pay_date, created_by_user_id=user.id))
    db_session.commit()

    anomaly_detection.detect_duplicate_payments(db_session, company.id, tenant.id)
    db_session.commit()
    second = anomaly_detection.detect_duplicate_payments(db_session, company.id, tenant.id)
    db_session.commit()
    assert len(second) == 1


def test_detect_supplier_bank_detail_change(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _invoice(db_session, company, fy, user, invoice_number="INV-1", counterparty="Acme Supplies", iban="NL80RABO0123456789", invoice_date=date(2027, 1, 1))
    _invoice(db_session, company, fy, user, invoice_number="INV-2", counterparty="Acme Supplies", iban="NL11INGB0987654321", invoice_date=date(2027, 2, 1))
    db_session.commit()

    flags = anomaly_detection.detect_supplier_bank_detail_changes(db_session, company.id, tenant.id)
    assert len(flags) == 1
    assert flags[0].rule_code == "SUPPLIER_BANK_DETAILS_CHANGED"
    assert flags[0].evidence["new_iban"] == "NL11INGB0987654321"


def test_detect_unexpected_expense_increase(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _invoice(db_session, company, fy, user, invoice_number="INV-1", counterparty="Acme Supplies", net=Decimal("100.00"), invoice_date=date(2027, 1, 1))
    _invoice(db_session, company, fy, user, invoice_number="INV-2", counterparty="Acme Supplies", net=Decimal("100.00"), invoice_date=date(2027, 2, 1))
    _invoice(db_session, company, fy, user, invoice_number="INV-3", counterparty="Acme Supplies", net=Decimal("500.00"), invoice_date=date(2027, 3, 1))
    db_session.commit()

    flags = anomaly_detection.detect_unexpected_expense_increases(db_session, company.id, tenant.id)
    assert len(flags) == 1
    assert flags[0].rule_code == "UNEXPECTED_EXPENSE_INCREASE"


def test_detect_aging_unmatched_payments(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    stale_date = date.today() - timedelta(days=30)
    _bank_tx(db_session, company, bank_account, batch, amount=Decimal("100.00"), booking_date=stale_date)
    db_session.commit()

    flags = anomaly_detection.detect_aging_unmatched_payments(db_session, company.id, tenant.id)
    assert len(flags) == 1
    assert flags[0].rule_code == "UNMATCHED_PAYMENT_AGING"


def test_run_all_rules_never_marks_fraudulent(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _invoice(db_session, company, fy, user, invoice_number="INV-1", counterparty="Acme Supplies", iban="NL80RABO0123456789", invoice_date=date(2027, 1, 1))
    _invoice(db_session, company, fy, user, invoice_number="INV-2", counterparty="Acme Supplies", iban="NL11INGB0987654321", invoice_date=date(2027, 2, 1))
    db_session.commit()

    flags = anomaly_detection.run_all_rules(db_session, company.id, tenant.id)
    for flag in flags:
        assert "fraud" not in flag.message.lower()


# ---- cash flow ----


def test_cash_flow_forecast_distinguishes_actual_and_estimate(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _bank_tx(db_session, company, bank_account, batch, amount=Decimal("500.00"), booking_date=date(2027, 1, 10))
    _invoice(
        db_session, company, fy, user, invoice_number="INV-1", ledger_side=LedgerSide.sales,
        gross=Decimal("242.00"), net=Decimal("200.00"), due_date=date.today() + timedelta(days=15),
    )
    db_session.commit()

    forecast = cash_flow.build_cash_flow_forecast(db_session, company.id, months_ahead=2)

    assert forecast["net_bank_transaction_movement"] == "500.00"
    assert "not a live bank balance" in forecast["net_bank_transaction_movement_disclaimer"]
    assert forecast["outstanding_sales_invoice_count"] == 1
    assert all(month["is_estimate"] is True for month in forecast["monthly_projection"])
