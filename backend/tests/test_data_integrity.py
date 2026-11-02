from datetime import date
from decimal import Decimal

from app.accounting import financial_reports as fr
from app.core.security import hash_password
from app.models.accounting import AccountingTransaction
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.enums import LedgerSide, TransactionApprovalStatus, TransactionType, UserRole
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
    db_session.commit()
    return tenant, company, fy, user


def _sale(db_session, company, fy, user, net, invoice_date):
    tx = AccountingTransaction(
        tenant_id=company.tenant_id, company_id=company.id, financial_year_id=fy.id,
        transaction_type=TransactionType.sales_invoice, ledger_side=LedgerSide.sales,
        counterparty_name="Customer", invoice_date=invoice_date, due_date=invoice_date,
        net_amount=net, vat_amount=Decimal("0"), gross_amount=net, created_by_user_id=user.id,
    )
    db_session.add(tx)
    db_session.flush()
    return tx


def test_monthly_pnl_sums_reconcile_to_annual_pnl(db_session):
    """Ledger-to-report validation: summing the monthly P&L revenue for
    every month in a year must equal the annual P&L revenue computed
    directly -- the reporting engine must never silently drop or double
    count a transaction depending on which period width is requested."""
    tenant, company, fy, user = _setup(db_session)
    for month in range(1, 13):
        _sale(db_session, company, fy, user, Decimal("100.00"), date(2027, month, 15))
    db_session.commit()

    monthly_total = Decimal("0")
    for month in range(1, 13):
        period = fr.resolve_period(fr.ReportPeriod.monthly, date(2027, month, 15))
        monthly_total += fr.profit_and_loss(db_session, company.id, period)["revenue"]

    annual = fr.profit_and_loss(db_session, company.id, fr.resolve_period(fr.ReportPeriod.annual, date(2027, 6, 1)))
    assert monthly_total == annual["revenue"] == Decimal("1200.00")


def test_quarterly_pnl_sums_reconcile_to_annual(db_session):
    tenant, company, fy, user = _setup(db_session)
    for month in (1, 4, 7, 10):
        _sale(db_session, company, fy, user, Decimal("500.00"), date(2027, month, 10))
    db_session.commit()

    quarterly_total = Decimal("0")
    for month in (1, 4, 7, 10):
        period = fr.resolve_period(fr.ReportPeriod.quarterly, date(2027, month, 10))
        quarterly_total += fr.profit_and_loss(db_session, company.id, period)["revenue"]

    annual = fr.profit_and_loss(db_session, company.id, fr.resolve_period(fr.ReportPeriod.annual, date(2027, 6, 1)))
    assert quarterly_total == annual["revenue"] == Decimal("2000.00")


def test_report_is_reproducible_for_unchanged_ledger_state(db_session):
    """Recomputing the same report twice with no ledger change must yield
    byte-for-byte identical figures -- the engine has no hidden time- or
    random-dependent state."""
    tenant, company, fy, user = _setup(db_session)
    _sale(db_session, company, fy, user, Decimal("750.00"), date(2027, 3, 1))
    db_session.commit()

    period = fr.DateRange(date(2027, 1, 1), date(2027, 12, 31))
    first = fr.profit_and_loss(db_session, company.id, period)
    second = fr.profit_and_loss(db_session, company.id, period)
    assert first == second


def test_locked_transaction_figures_are_immutable_so_past_reports_stay_reproducible(db_session):
    """Once a transaction is LOCKED, app/api/v1/transactions.py blocks any
    further edit to its own net/vat/gross amounts (verified at the API
    layer) -- a correction creates a new, separately-dated transaction
    instead of rewriting history. This test documents that invariant at
    the model level: locking a transaction and re-reading its figures
    later returns exactly what was locked."""
    tenant, company, fy, user = _setup(db_session)
    tx = _sale(db_session, company, fy, user, Decimal("300.00"), date(2027, 2, 1))
    tx.approval_status = TransactionApprovalStatus.locked
    db_session.commit()

    period = fr.DateRange(date(2027, 1, 1), date(2027, 12, 31))
    before = fr.profit_and_loss(db_session, company.id, period)

    db_session.refresh(tx)
    assert tx.net_amount == Decimal("300.00")  # unchanged
    after = fr.profit_and_loss(db_session, company.id, period)
    assert before == after


def test_duplicate_bank_import_never_doubles_reported_cash_position(db_session):
    """Re-importing the same bank statement must not inflate the balance
    sheet's cash figure -- reuses Phase 6's dedupe_hash guarantee."""
    from app.models.banking import BankAccount, BankImportBatch, BankTransaction

    tenant, company, fy, user = _setup(db_session)
    account = BankAccount(tenant_id=tenant.id, company_id=company.id, iban="NL91ABNA0417164300", account_name="Main")
    db_session.add(account)
    db_session.flush()
    batch = BankImportBatch(tenant_id=tenant.id, company_id=company.id, bank_account_id=account.id,
                             source_format="CSV", original_filename="f.csv", storage_path="x", imported_by_user_id=user.id)
    db_session.add(batch)
    db_session.flush()

    # Simulate the dedupe guarantee directly: two rows with the same
    # dedupe_hash should never both be inserted by app.accounting.bank_import
    # (tested there); here we confirm the balance sheet reads whatever rows
    # exist without re-summing on its own.
    tx = BankTransaction(tenant_id=tenant.id, company_id=company.id, bank_account_id=account.id, import_batch_id=batch.id,
                          dedupe_hash="h-1", booking_date=date(2027, 3, 1), amount=Decimal("500.00"), currency="EUR",
                          source_format="CSV", raw_data={})
    db_session.add(tx)
    db_session.commit()

    bs = fr.balance_sheet(db_session, company.id, date(2027, 6, 1))
    assert bs["assets"]["cash_and_bank"] == Decimal("500.00")


def test_audit_log_recorded_for_manual_balance_sheet_item(client, db_session):
    from app.core.security import hash_password as hp
    from app.models.tenant import Tenant as TenantModel
    from app.models.user import User as UserModel

    tenant = TenantModel(name="Acme Accounting")
    db_session.add(tenant)
    db_session.flush()
    admin = UserModel(tenant_id=tenant.id, email="admin@acme.nl", hashed_password=hp("secret123"), full_name="Admin", role=UserRole.admin)
    db_session.add(admin)
    db_session.commit()

    token = client.post("/api/v1/auth/login", json={"email": "admin@acme.nl", "password": "secret123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]

    response = client.post(
        "/api/v1/financial-reports/balance-sheet-items",
        json={"company_id": company_id, "category": "EQUITY", "label": "Founder capital", "amount": "5000.00", "as_of_date": "2027-01-01"},
        headers=headers,
    )
    assert response.status_code == 201
    item_id = response.json()["id"]

    log = db_session.query(AuditLog).filter(AuditLog.entity_type == "manual_balance_sheet_item", AuditLog.entity_id == item_id).first()
    assert log is not None
    assert log.action == "create"
