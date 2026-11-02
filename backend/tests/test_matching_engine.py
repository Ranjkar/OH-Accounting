from datetime import date
from decimal import Decimal

import pytest

from app.accounting import matching_engine, reconciliation_service
from app.core.security import hash_password
from app.models.accounting import AccountingTransaction
from app.models.banking import BankAccount, BankImportBatch, BankTransaction
from app.models.company import Company
from app.models.enums import (
    LedgerSide,
    PaymentStatus,
    ReconciliationStatus,
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
    fy = FinancialYear(company_id=company.id, year=2026, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
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


def _invoice(db_session, company, fy, user, *, invoice_number="INV-1", gross=Decimal("121.00"), counterparty="Klant Retail B.V.", iban=None, due_date=date(2027, 6, 1)):
    tx = AccountingTransaction(
        tenant_id=company.tenant_id, company_id=company.id, financial_year_id=fy.id,
        transaction_type=TransactionType.sales_invoice, ledger_side=LedgerSide.sales,
        invoice_number=invoice_number, counterparty_name=counterparty, counterparty_iban=iban,
        invoice_date=date(2026, 2, 1), due_date=due_date,
        net_amount=Decimal("100.00"), vat_amount=Decimal("21.00"), gross_amount=gross,
        created_by_user_id=user.id,
    )
    db_session.add(tx)
    db_session.flush()
    return tx


def _bank_tx(db_session, company, bank_account, batch, *, amount, booking_date=date(2026, 3, 1), reference=None, description=None, counterparty_name=None, counterparty_iban=None):
    tx = BankTransaction(
        tenant_id=company.tenant_id, company_id=company.id, bank_account_id=bank_account.id, import_batch_id=batch.id,
        dedupe_hash=f"hash-{amount}-{booking_date}-{reference}", booking_date=booking_date, amount=amount, currency="EUR",
        counterparty_name=counterparty_name, counterparty_iban=counterparty_iban,
        payment_reference=reference, description=description, source_format="CSV", raw_data={},
    )
    db_session.add(tx)
    db_session.flush()
    return tx


# ---- Matching engine: scoring ----


def test_exact_amount_and_invoice_number_is_high_confidence(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    invoice = _invoice(db_session, company, fy, user)
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("121.00"), reference="INV-1")

    candidates = matching_engine.find_single_matches(db_session, bank_tx)
    assert candidates[0].accounting_transaction_id == invoice.id
    assert candidates[0].confidence == "HIGH"
    assert candidates[0].signals["exact_amount"] is True
    assert candidates[0].signals["invoice_number_found_in_reference"] is True


def test_iban_match_contributes_to_score(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    invoice = _invoice(db_session, company, fy, user, iban="NL80RABO0123456789")
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("121.00"), counterparty_iban="NL80RABO0123456789")

    candidates = matching_engine.find_single_matches(db_session, bank_tx)
    assert candidates[0].signals["iban_match"] is True


def test_partial_payment_scores_lower_than_exact(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _invoice(db_session, company, fy, user)
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("60.50"))  # half of 121.00

    candidates = matching_engine.find_single_matches(db_session, bank_tx)
    assert candidates[0].confidence in ("LOW", "MEDIUM")
    assert "partial_amount_coverage" in candidates[0].signals


def test_unrelated_transaction_has_no_match(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _invoice(db_session, company, fy, user)
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("9999.99"))

    candidates = matching_engine.find_single_matches(db_session, bank_tx)
    assert all(c.confidence not in ("HIGH", "MEDIUM") for c in candidates)


def test_combined_payment_matches_two_invoices_from_same_counterparty(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    inv_a = _invoice(db_session, company, fy, user, invoice_number="INV-A", gross=Decimal("100.00"))
    inv_b = _invoice(db_session, company, fy, user, invoice_number="INV-B", gross=Decimal("50.00"))
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("150.00"), counterparty_name="Klant Retail B.V.")

    combined = matching_engine.find_combined_match(db_session, bank_tx)
    assert combined is not None
    matched_ids = {c.accounting_transaction_id for c in combined}
    assert matched_ids == {inv_a.id, inv_b.id}
    assert sum(c.suggested_allocation for c in combined) == Decimal("150.00")


def test_overpayment_is_flagged_not_silently_matched(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _invoice(db_session, company, fy, user, gross=Decimal("100.00"))
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("150.00"))

    candidates = matching_engine.find_single_matches(db_session, bank_tx)
    top = candidates[0]
    assert top.signals.get("amount_exceeds_remaining_balance") is True
    assert top.confidence != "HIGH"  # never silently treated as an exact match


# ---- Reconciliation service: suggest / approve / reject / reverse ----


def test_generate_suggestions_is_idempotent(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _invoice(db_session, company, fy, user)
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("121.00"), reference="INV-1")

    first = reconciliation_service.generate_suggestions(db_session, bank_tx)
    second = reconciliation_service.generate_suggestions(db_session, bank_tx)
    assert len(first) == len(second) == 1
    assert bank_tx.reconciliation_status == ReconciliationStatus.suggested_match


def test_approve_match_creates_payment_and_updates_statuses(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    invoice = _invoice(db_session, company, fy, user)
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("121.00"), reference="INV-1")
    matches = reconciliation_service.generate_suggestions(db_session, bank_tx)
    db_session.commit()

    payment = reconciliation_service.approve_match(db_session, matches[0], user.id)
    db_session.commit()

    assert payment.amount == Decimal("121.00")
    assert payment.bank_transaction_id == bank_tx.id
    db_session.refresh(invoice)
    assert invoice.payment_status == PaymentStatus.paid
    db_session.refresh(bank_tx)
    assert bank_tx.reconciliation_status == ReconciliationStatus.matched


def test_cannot_approve_the_same_match_twice(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _invoice(db_session, company, fy, user)
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("121.00"), reference="INV-1")
    matches = reconciliation_service.generate_suggestions(db_session, bank_tx)
    db_session.commit()

    reconciliation_service.approve_match(db_session, matches[0], user.id)
    db_session.commit()
    with pytest.raises(reconciliation_service.ReconciliationError):
        reconciliation_service.approve_match(db_session, matches[0], user.id)


def test_reject_match_does_not_create_payment(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    _invoice(db_session, company, fy, user)
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("121.00"), reference="INV-1")
    matches = reconciliation_service.generate_suggestions(db_session, bank_tx)
    db_session.commit()

    reconciliation_service.reject_match(db_session, matches[0])
    db_session.commit()
    assert matches[0].status == "REJECTED"
    assert matches[0].payment_id is None


def test_reverse_match_voids_payment_without_deleting_it(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    invoice = _invoice(db_session, company, fy, user)
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("121.00"), reference="INV-1")
    matches = reconciliation_service.generate_suggestions(db_session, bank_tx)
    db_session.commit()
    payment = reconciliation_service.approve_match(db_session, matches[0], user.id)
    db_session.commit()
    payment_id = payment.id

    reconciliation_service.reverse_match(db_session, matches[0], user.id, "Wrong allocation")
    db_session.commit()

    from app.models.accounting import Payment

    reloaded_payment = db_session.get(Payment, payment_id)
    assert reloaded_payment is not None  # never deleted
    assert reloaded_payment.voided is True
    assert reloaded_payment.void_reason == "Wrong allocation"
    db_session.refresh(invoice)
    assert invoice.payment_status == PaymentStatus.unpaid
    db_session.refresh(bank_tx)
    assert bank_tx.reconciliation_status == ReconciliationStatus.unmatched


def test_partial_payment_allocation_then_second_payment_completes_invoice(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    invoice = _invoice(db_session, company, fy, user, gross=Decimal("121.00"))

    first_bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("60.00"), reference="INV-1")
    first_matches = reconciliation_service.generate_suggestions(db_session, first_bank_tx)
    db_session.commit()
    reconciliation_service.approve_match(db_session, first_matches[0], user.id)
    db_session.commit()
    db_session.refresh(invoice)
    assert invoice.payment_status == PaymentStatus.partially_paid

    second_bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("61.00"), reference="INV-1", booking_date=date(2026, 3, 5))
    second_matches = reconciliation_service.generate_suggestions(db_session, second_bank_tx)
    db_session.commit()
    reconciliation_service.approve_match(db_session, second_matches[0], user.id)
    db_session.commit()
    db_session.refresh(invoice)
    assert invoice.payment_status == PaymentStatus.paid


def test_exclude_transaction_sets_excluded_status(db_session):
    tenant, company, fy, user, bank_account, batch = _setup(db_session)
    bank_tx = _bank_tx(db_session, company, bank_account, batch, amount=Decimal("-5.00"), description="Bank fee")
    reconciliation_service.exclude_transaction(db_session, bank_tx)
    db_session.commit()
    assert bank_tx.reconciliation_status == ReconciliationStatus.excluded
