"""Phase 19 -- regression tests for the accounting-correctness fixes.

Four defects from docs/QWEN_TECHNICAL_AUDIT_REPORT.md, each verified in the
current source before fixing and each reproduced here:

  6.2  Cash-based VAT companies got permanently zero returns. The period is
       the one containing the PAYMENT date, which is unknown at posting time,
       so `determine_vat_period` correctly returned None -- and nothing ever
       came back to assign it. `app/api/v1/transactions.py` imported
       `determine_vat_period` and never called it.

  6.6  No DB-level guard against a document posting to the ledger twice. Two
       concurrent approvals both passed the SELECT-then-INSERT check.

  7.3  `previous_period()` counted DAYS, so the quarter before Q1 started on
       3 October, and an annual period spanning a leap year shifted by one.

  8.8  `PaymentCreate.amount` had no bound, so a zero or negative payment was
       accepted and fed into payment-status, aging and cash-flow maths.
"""

from datetime import date
from decimal import Decimal

import pytest
from dateutil.relativedelta import relativedelta
from sqlalchemy.exc import IntegrityError

from app.accounting import vat_engine
from app.accounting.financial_reports import (
    DateRange,
    ReportPeriod,
    previous_period,
    resolve_period,
)
from app.accounting.period_assignment import assign_vat_period_on_payment, determine_vat_period
from app.core.security import hash_password
from app.models.accounting import AccountingTransaction, TransactionLineItem
from app.models.company import Company
from app.models.enums import (
    LedgerSide,
    PaymentStatus,
    TransactionType,
    UserRole,
    VatAccountingBasis,
    VatTreatment,
)
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.accounting import PaymentCreate

PASSWORD = "secret123"


# --------------------------------------------------------------------------
# Fixtures / builders
# --------------------------------------------------------------------------


def _login_headers(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _world(db_session, basis=VatAccountingBasis.invoice_based, year=2026, quarterly=True):
    """One tenant, one admin, one company on the given VAT basis, one financial
    year, and its VAT periods."""
    tenant = Tenant(name=f"T-{basis.value}-{year}")
    db_session.add(tenant)
    db_session.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"admin-{basis.value}-{year}@t.nl",
        hashed_password=hash_password(PASSWORD),
        full_name="Admin",
        role=UserRole.admin,
    )
    db_session.add(user)
    company = Company(tenant_id=tenant.id, name="C", vat_accounting_basis=basis)
    db_session.add(company)
    db_session.flush()
    company.users.append(user)
    fy = FinancialYear(company_id=company.id, year=year, start_date=date(year, 1, 1), end_date=date(year, 12, 31))
    db_session.add(fy)
    db_session.flush()

    spans = [("Q1", 1, 3), ("Q2", 4, 6), ("Q3", 7, 9), ("Q4", 10, 12)] if quarterly else [("Year", 1, 12)]
    periods = []
    for label, m0, m1 in spans:
        period = VatPeriod(
            financial_year_id=fy.id,
            label=label,
            start_date=date(year, m0, 1),
            end_date=date(year, m1, 1) + relativedelta(months=1) - relativedelta(days=1),
            filing_deadline=date(year, m1, 1) + relativedelta(months=1, days=29),
            payment_deadline=date(year, m1, 1) + relativedelta(months=1, days=29),
        )
        db_session.add(period)
        periods.append(period)
    db_session.commit()
    return {"tenant": tenant, "user": user, "company": company, "fy": fy, "periods": periods}


def _sales_invoice(db_session, w, *, invoice_date, vat_period_id=None, net="1000.00", vat_rate="21",
                   treatment=VatTreatment.domestic_standard, source_document_id=None):
    net_amount = Decimal(net)
    vat_amount = (net_amount * Decimal(vat_rate) / Decimal("100")).quantize(Decimal("0.01"))
    gross = net_amount + vat_amount
    tx = AccountingTransaction(
        tenant_id=w["tenant"].id,
        company_id=w["company"].id,
        financial_year_id=w["fy"].id,
        vat_period_id=vat_period_id,
        source_document_id=source_document_id,
        transaction_type=TransactionType.sales_invoice,
        ledger_side=LedgerSide.sales,
        invoice_date=invoice_date,
        currency="EUR",
        fx_rate_to_eur=Decimal("1"),
        net_amount=net_amount,
        vat_amount=vat_amount,
        gross_amount=gross,
        net_amount_eur=net_amount,
        vat_amount_eur=vat_amount,
        gross_amount_eur=gross,
        created_by_user_id=w["user"].id,
    )
    db_session.add(tx)
    db_session.flush()
    db_session.add(
        TransactionLineItem(
            transaction_id=tx.id,
            line_number=1,
            description="Test line",
            net_amount=net_amount,
            vat_rate=Decimal(vat_rate),
            vat_amount=vat_amount,
            gross_amount=gross,
            vat_treatment=treatment,
            input_vat_eligibility=None,
            deductible_vat_amount=None,
        )
    )
    db_session.commit()
    return tx


# --------------------------------------------------------------------------
# 7.3 -- previous_period() calendar arithmetic
# --------------------------------------------------------------------------


def test_previous_period_of_q1_is_exactly_q4_of_the_prior_year():
    """The original bug: Q1 2026 is 90 days, so `start - 91 days` landed on
    3 October 2025 and silently dropped 1-2 October from every quarterly
    comparison."""
    result = previous_period(DateRange(date(2026, 1, 1), date(2026, 3, 31)))
    assert result.start == date(2025, 10, 1)
    assert result.end == date(2025, 12, 31)


@pytest.mark.parametrize(
    "current,expected",
    [
        (DateRange(date(2026, 1, 1), date(2026, 3, 31)), DateRange(date(2025, 10, 1), date(2025, 12, 31))),
        (DateRange(date(2026, 4, 1), date(2026, 6, 30)), DateRange(date(2026, 1, 1), date(2026, 3, 31))),
        (DateRange(date(2026, 7, 1), date(2026, 9, 30)), DateRange(date(2026, 4, 1), date(2026, 6, 30))),
        (DateRange(date(2026, 10, 1), date(2026, 12, 31)), DateRange(date(2026, 7, 1), date(2026, 9, 30))),
    ],
)
def test_every_quarter_steps_back_to_the_exact_previous_quarter(current, expected):
    assert previous_period(current) == expected


@pytest.mark.parametrize(
    "current,expected",
    [
        (DateRange(date(2026, 3, 1), date(2026, 3, 31)), DateRange(date(2026, 2, 1), date(2026, 2, 28))),
        (DateRange(date(2024, 3, 1), date(2024, 3, 31)), DateRange(date(2024, 2, 1), date(2024, 2, 29))),
        (DateRange(date(2026, 5, 1), date(2026, 5, 31)), DateRange(date(2026, 4, 1), date(2026, 4, 30))),
        (DateRange(date(2026, 1, 1), date(2026, 1, 31)), DateRange(date(2025, 12, 1), date(2025, 12, 31))),
    ],
)
def test_every_month_steps_back_to_the_exact_previous_month(current, expected):
    """February is the case day arithmetic gets wrong in both leap and
    non-leap years."""
    assert previous_period(current) == expected


def test_annual_period_spanning_a_leap_year_steps_back_to_the_exact_prior_year():
    """2024 has 366 days, so the old `start - 366` produced
    31 Dec 2022 - 31 Dec 2023 instead of 1 Jan 2023 - 31 Dec 2023."""
    result = previous_period(DateRange(date(2024, 1, 1), date(2024, 12, 31)))
    assert result.start == date(2023, 1, 1)
    assert result.end == date(2023, 12, 31)

    result = previous_period(DateRange(date(2026, 1, 1), date(2026, 12, 31)))
    assert result.start == date(2025, 1, 1)
    assert result.end == date(2025, 12, 31)


def test_twelve_monthly_previous_periods_tile_the_prior_twelve_months_with_no_gaps_or_overlaps():
    """The strongest form of the invariant: stepping back from each month of
    2026 must cover Dec 2025 - Nov 2026 exactly once, contiguous, with no gap
    and no overlap."""
    covered = []
    for month in range(1, 13):
        current = DateRange(date(2026, month, 1), date(2026, month, 1) + relativedelta(months=1) - relativedelta(days=1))
        prev = previous_period(current)
        covered.append((prev.start, prev.end))
        # Each previous period must end exactly one day before the current one starts.
        assert prev.end == current.start - relativedelta(days=1)

    covered.sort()
    assert covered[0][0] == date(2025, 12, 1)
    assert covered[-1][1] == date(2026, 11, 30)
    total_days = sum((end - start).days + 1 for start, end in covered)
    for (_, prev_end), (next_start, _) in zip(covered, covered[1:]):
        assert next_start == prev_end + relativedelta(days=1), "gap or overlap between consecutive periods"
    assert total_days == (date(2026, 11, 30) - date(2025, 12, 1)).days + 1


def test_previous_period_of_a_non_calendar_range_falls_back_to_day_count():
    """An arbitrary range has no calendar shape to preserve, so the day count
    is the best available answer -- and the old behaviour is retained for it."""
    result = previous_period(DateRange(date(2026, 3, 10), date(2026, 4, 20)))
    assert result.end == date(2026, 3, 9)
    assert (result.end - result.start).days == (date(2026, 4, 20) - date(2026, 3, 10)).days


def test_previous_period_agrees_with_resolve_period_for_every_quarter():
    """Cross-check against the other independent implementation: resolving
    "the quarter before" via resolve_period must equal previous_period()."""
    for month in (1, 4, 7, 10):
        current = resolve_period(ReportPeriod.quarterly, date(2026, month, 15))
        prior_reference = current.start - relativedelta(days=1)
        expected = resolve_period(ReportPeriod.quarterly, prior_reference)
        assert previous_period(current) == expected, f"mismatch for quarter starting {current.start}"


# --------------------------------------------------------------------------
# 8.8 -- payment amount validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [Decimal("0"), Decimal("-0.01"), Decimal("-1210.00")])
def test_payment_schema_rejects_zero_and_negative_amounts(bad):
    with pytest.raises(Exception):
        PaymentCreate(amount=bad, payment_date=date(2026, 3, 15))


def test_payment_schema_accepts_a_positive_amount():
    payment = PaymentCreate(amount=Decimal("1210.00"), payment_date=date(2026, 3, 15))
    assert payment.amount == Decimal("1210.00")


def test_api_rejects_a_negative_payment_and_leaves_the_ledger_untouched(client, db_session):
    """End-to-end: a negative payment must be refused with 422 and must not
    create a Payment row or change payment_status."""
    w = _world(db_session)
    headers = _login_headers(client, w["user"].email)
    tx = _sales_invoice(db_session, w, invoice_date=date(2026, 2, 1), vat_period_id=w["periods"][0].id)

    from app.models.accounting import Payment

    payments_before = db_session.query(Payment).count()

    response = client.post(
        f"/api/v1/transactions/{tx.id}/payments",
        headers=headers,
        json={"amount": "-1210.00", "payment_date": "2026-03-15"},
    )
    assert response.status_code == 422, response.text
    assert db_session.query(Payment).count() == payments_before

    db_session.refresh(tx)
    assert tx.payment_status == PaymentStatus.unpaid

    # And a legitimate payment still works (the endpoint is declared 201).
    good = client.post(
        f"/api/v1/transactions/{tx.id}/payments",
        headers=headers,
        json={"amount": "1210.00", "payment_date": "2026-03-15"},
    )
    assert good.status_code == 201, good.text
    assert db_session.query(Payment).count() == payments_before + 1


# --------------------------------------------------------------------------
# 6.2 -- cash-based VAT period assignment
# --------------------------------------------------------------------------


def test_determine_vat_period_returns_none_for_an_unpaid_cash_based_transaction(db_session):
    """The pre-existing, correct behaviour that the missing follow-up call
    relied on."""
    w = _world(db_session, basis=VatAccountingBasis.cash_based)
    assert determine_vat_period(
        db_session, w["company"], w["fy"].id, LedgerSide.sales, date(2026, 2, 1), None
    ) is None


def test_cash_based_transaction_is_unassigned_until_a_payment_is_recorded(db_session):
    w = _world(db_session, basis=VatAccountingBasis.cash_based)
    tx = _sales_invoice(db_session, w, invoice_date=date(2026, 2, 1))
    assert tx.vat_period_id is None

    assign_vat_period_on_payment(db_session, tx, date(2026, 5, 20))
    db_session.commit()

    db_session.refresh(tx)
    assert tx.vat_period_id == w["periods"][1].id, "must land in Q2, the period containing the payment date"


def test_cash_based_payment_lands_in_the_period_of_the_payment_not_the_invoice(db_session):
    """The whole point of cash-based accounting: a February invoice paid in
    October belongs to Q4."""
    w = _world(db_session, basis=VatAccountingBasis.cash_based)
    tx = _sales_invoice(db_session, w, invoice_date=date(2026, 2, 1))

    assign_vat_period_on_payment(db_session, tx, date(2026, 10, 5))
    db_session.commit()
    db_session.refresh(tx)
    assert tx.vat_period_id == w["periods"][3].id


def test_invoice_based_period_is_never_moved_by_a_later_payment(db_session):
    """Guard against the fix over-reaching: `determine_vat_period`'s own
    contract is that a payment date never moves an invoice-based transaction."""
    w = _world(db_session, basis=VatAccountingBasis.invoice_based)
    q1 = w["periods"][0]
    tx = _sales_invoice(db_session, w, invoice_date=date(2026, 2, 1), vat_period_id=q1.id)

    assign_vat_period_on_payment(db_session, tx, date(2026, 11, 30))
    db_session.commit()
    db_session.refresh(tx)
    assert tx.vat_period_id == q1.id


def test_already_assigned_cash_based_transaction_is_not_reassigned(db_session):
    w = _world(db_session, basis=VatAccountingBasis.cash_based)
    tx = _sales_invoice(db_session, w, invoice_date=date(2026, 2, 1), vat_period_id=w["periods"][1].id)

    assign_vat_period_on_payment(db_session, tx, date(2026, 12, 1))
    db_session.commit()
    db_session.refresh(tx)
    assert tx.vat_period_id == w["periods"][1].id


def test_cash_based_vat_return_is_zero_before_payment_and_correct_after(db_session):
    """The end-to-end symptom of audit 6.2: calculate_vat_return filters on
    vat_period_id, so an unassigned transaction contributed nothing at all."""
    w = _world(db_session, basis=VatAccountingBasis.cash_based)
    q2 = w["periods"][1]
    _sales_invoice(db_session, w, invoice_date=date(2026, 2, 1), net="1000.00", vat_rate="21")

    before = vat_engine.calculate_vat_return(db_session, w["company"].id, q2.id)
    assert before.box_1a_net == Decimal("0"), "unpaid cash-based invoice must not appear yet"
    assert before.net_payable == Decimal("0")

    tx = db_session.query(AccountingTransaction).one()
    assign_vat_period_on_payment(db_session, tx, date(2026, 5, 20))
    db_session.commit()

    after = vat_engine.calculate_vat_return(db_session, w["company"].id, q2.id)
    assert after.box_1a_net == Decimal("1000.00")
    assert after.box_1a_vat == Decimal("210.00")
    assert after.net_payable == Decimal("210.00")


def test_recording_a_payment_through_the_api_assigns_the_period(client, db_session):
    """The API path, which is what the dead import in transactions.py was for."""
    w = _world(db_session, basis=VatAccountingBasis.cash_based)
    headers = _login_headers(client, w["user"].email)
    tx = _sales_invoice(db_session, w, invoice_date=date(2026, 2, 1), net="1000.00")
    assert tx.vat_period_id is None

    response = client.post(
        f"/api/v1/transactions/{tx.id}/payments",
        headers=headers,
        json={"amount": "1210.00", "payment_date": "2026-05-20"},
    )
    assert response.status_code == 201, response.text
    # Visible in the response too: the transaction now carries a period.
    assert response.json()["vat_period_id"] == w["periods"][1].id

    db_session.refresh(tx)
    assert tx.vat_period_id == w["periods"][1].id

    totals = vat_engine.calculate_vat_return(db_session, w["company"].id, w["periods"][1].id)
    assert totals.box_1a_net == Decimal("1000.00")
    assert totals.net_payable == Decimal("210.00")


def test_bank_match_approval_also_assigns_the_cash_based_period(db_session):
    """The second payment path. A bank-matched payment is just as much a
    payment as a manually recorded one."""
    from app.accounting import reconciliation_service
    from app.models.banking import BankAccount, BankImportBatch, BankTransaction, PaymentMatch
    from app.models.enums import BankSourceFormat, ReconciliationStatus

    w = _world(db_session, basis=VatAccountingBasis.cash_based)
    tx = _sales_invoice(db_session, w, invoice_date=date(2026, 2, 1), net="1000.00")

    account = BankAccount(
        tenant_id=w["tenant"].id, company_id=w["company"].id, iban="NL00BANK0000000001",
        account_name="Operating", currency="EUR",
    )
    db_session.add(account)
    db_session.flush()
    batch = BankImportBatch(
        tenant_id=w["tenant"].id, company_id=w["company"].id, bank_account_id=account.id,
        source_format=BankSourceFormat.csv, original_filename="s.csv", storage_path="s.csv",
        imported_by_user_id=w["user"].id,
    )
    db_session.add(batch)
    db_session.flush()
    bank_tx = BankTransaction(
        tenant_id=w["tenant"].id, company_id=w["company"].id, bank_account_id=account.id,
        import_batch_id=batch.id, dedupe_hash="h1", booking_date=date(2026, 8, 14),
        amount=Decimal("1210.00"), currency="EUR", source_format=BankSourceFormat.csv,
        raw_data={}, reconciliation_status=ReconciliationStatus.suggested_match,
    )
    db_session.add(bank_tx)
    db_session.flush()
    match = PaymentMatch(
        tenant_id=w["tenant"].id, company_id=w["company"].id, bank_transaction_id=bank_tx.id,
        accounting_transaction_id=tx.id, allocated_amount=Decimal("1210.00"),
        confidence_score=Decimal("95.00"), confidence_level="HIGH",
        match_signals={"exact_amount": True}, status="SUGGESTED",
    )
    db_session.add(match)
    db_session.commit()

    assert tx.vat_period_id is None
    reconciliation_service.approve_match(db_session, match, w["user"].id)
    db_session.commit()
    db_session.refresh(tx)

    assert tx.vat_period_id == w["periods"][2].id, "August booking date must land in Q3"


# --------------------------------------------------------------------------
# 6.6 -- one document may post to the ledger at most once
# --------------------------------------------------------------------------


def test_two_transactions_cannot_share_a_source_document(db_session):
    """The DB now enforces what post_document_to_ledger previously enforced
    only with a single-threaded SELECT-then-INSERT."""
    from app.models.document import Document

    w = _world(db_session)
    document = Document(
        tenant_id=w["tenant"].id,
        company_id=w["company"].id,
        uploaded_by_user_id=w["user"].id,
        original_filename="invoice.pdf",
        secure_filename="invoice.pdf",
        content_type="application/pdf",
        file_size=10,
        sha256_hash="a" * 64,
        storage_path="x/y.pdf",
    )
    db_session.add(document)
    db_session.commit()

    _sales_invoice(db_session, w, invoice_date=date(2026, 2, 1), source_document_id=document.id)

    with pytest.raises(IntegrityError):
        _sales_invoice(db_session, w, invoice_date=date(2026, 2, 2), source_document_id=document.id)
    db_session.rollback()


def test_many_transactions_may_have_no_source_document(db_session):
    """Manual entries and corrections both set source_document_id = NULL, and
    Postgres treats NULLs as distinct -- otherwise the constraint would make
    a second manual entry impossible."""
    w = _world(db_session)
    first = _sales_invoice(db_session, w, invoice_date=date(2026, 2, 1))
    second = _sales_invoice(db_session, w, invoice_date=date(2026, 2, 2))
    third = _sales_invoice(db_session, w, invoice_date=date(2026, 2, 3))

    assert first.source_document_id is None
    assert second.source_document_id is None
    assert third.source_document_id is None
    assert len({first.id, second.id, third.id}) == 3


def test_the_unique_constraint_is_declared_on_the_model():
    """Tests build the schema with create_all, so the constraint must be in the
    model metadata and not only in the migration -- otherwise the suite would
    never exercise it (audit 7.14)."""
    names = {
        getattr(c, "name", None)
        for c in AccountingTransaction.__table__.constraints
    }
    assert "uq_accounting_transaction_source_document" in names
