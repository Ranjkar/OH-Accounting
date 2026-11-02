from datetime import date, timedelta
from decimal import Decimal

from app.accounting import financial_reports as fr
from app.core.security import hash_password
from app.models.accounting import AccountingTransaction, Payment
from app.models.balance_sheet import ManualBalanceSheetItem
from app.models.banking import BankAccount, BankImportBatch, BankTransaction
from app.models.company import Company
from app.models.enums import (
    BalanceSheetItemCategory,
    LedgerSide,
    TransactionType,
    UserRole,
    VatPeriodStatus,
    VatReturnStatus,
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
    user = User(tenant_id=tenant.id, email="u@t.nl", hashed_password=hash_password("x"), full_name="U", role=UserRole.admin)
    db_session.add(user)
    db_session.flush()
    fy = FinancialYear(company_id=company.id, year=2027, start_date=date(2027, 1, 1), end_date=date(2027, 12, 31))
    db_session.add(fy)
    db_session.flush()
    db_session.commit()
    return tenant, company, fy, user


def _tx(db_session, company, fy, user, *, ledger_side, net=Decimal("100.00"), vat=Decimal("21.00"),
        invoice_date=date(2027, 2, 1), due_date=date(2027, 3, 1), counterparty="Acme",
        expense_category=None, invoice_number=None):
    tx = AccountingTransaction(
        tenant_id=company.tenant_id, company_id=company.id, financial_year_id=fy.id,
        transaction_type=TransactionType.sales_invoice if ledger_side == LedgerSide.sales else TransactionType.purchase_invoice,
        ledger_side=ledger_side, invoice_number=invoice_number, counterparty_name=counterparty,
        invoice_date=invoice_date, due_date=due_date,
        net_amount=net, vat_amount=vat, gross_amount=net + vat,
        expense_category=expense_category, created_by_user_id=user.id,
    )
    db_session.add(tx)
    db_session.flush()
    return tx


def _pay(db_session, company, tx, amount, payment_date, user_id=None):
    p = Payment(tenant_id=company.tenant_id, company_id=company.id, transaction_id=tx.id, amount=amount, payment_date=payment_date, created_by_user_id=user_id or tx.created_by_user_id)
    db_session.add(p)
    db_session.flush()
    return p


def _bank_setup(db_session, company, user):
    account = BankAccount(tenant_id=company.tenant_id, company_id=company.id, iban="NL91ABNA0417164300", account_name="Main")
    db_session.add(account)
    db_session.flush()
    batch = BankImportBatch(tenant_id=company.tenant_id, company_id=company.id, bank_account_id=account.id,
                             source_format="CSV", original_filename="f.csv", storage_path="x", imported_by_user_id=user.id)
    db_session.add(batch)
    db_session.flush()
    return account, batch


def _bank_tx(db_session, company, account, batch, amount, booking_date):
    tx = BankTransaction(tenant_id=company.tenant_id, company_id=company.id, bank_account_id=account.id, import_batch_id=batch.id,
                          dedupe_hash=f"h-{amount}-{booking_date}", booking_date=booking_date, amount=amount, currency="EUR",
                          source_format="CSV", raw_data={})
    db_session.add(tx)
    db_session.flush()
    return tx


# ---- Profit and Loss ----


def test_pnl_classifies_categories_into_correct_buckets(db_session):
    tenant, company, fy, user = _setup(db_session)
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("1000.00"), counterparty="Customer A")
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.purchases, net=Decimal("400.00"), expense_category="Cost of goods sold")
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.purchases, net=Decimal("100.00"), expense_category="Personnel expenses")
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.purchases, net=Decimal("50.00"), expense_category="Depreciation")
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.purchases, net=Decimal("20.00"), expense_category="Interest expense")
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.purchases, net=Decimal("60.00"), expense_category="Office expenses")
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.purchases, net=Decimal("30.00"), expense_category=None)
    db_session.commit()

    period = fr.DateRange(date(2027, 1, 1), date(2027, 12, 31))
    pnl = fr.profit_and_loss(db_session, company.id, period)

    assert pnl["revenue"] == Decimal("1000.00")
    assert pnl["cost_of_sales"] == Decimal("400.00")
    assert pnl["gross_profit"] == Decimal("600.00")
    assert pnl["personnel_expenses"] == Decimal("100.00")
    assert pnl["depreciation"] == Decimal("50.00")
    assert pnl["interest_expense"] == Decimal("20.00")
    assert pnl["operating_expenses"] == Decimal("60.00")
    assert pnl["uncategorized_expenses"] == Decimal("30.00")
    # ebitda = gross_profit - opex - personnel - uncategorized = 600 - 60 - 100 - 30 = 410
    assert pnl["ebitda"] == Decimal("410.00")
    # ebit = ebitda - depreciation = 360
    assert pnl["ebit"] == Decimal("360.00")
    # profit_before_tax = ebit - interest = 340
    assert pnl["profit_before_tax"] == Decimal("340.00")
    assert pnl["tax_expense"] == Decimal("0")
    assert pnl["net_profit"] == Decimal("340.00")


def test_pnl_credit_note_reduces_revenue(db_session):
    tenant, company, fy, user = _setup(db_session)
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("1000.00"))
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("-200.00"))
    db_session.commit()

    pnl = fr.profit_and_loss(db_session, company.id, fr.DateRange(date(2027, 1, 1), date(2027, 12, 31)))
    assert pnl["revenue"] == Decimal("800.00")


def test_compare_periods_percentage_change(db_session):
    tenant, company, fy, user = _setup(db_session)
    current = fr.profit_and_loss(db_session, company.id, fr.DateRange(date(2027, 2, 1), date(2027, 2, 28)))
    # No data at all -> both periods zero; previous==0 means pct is None, never divide by zero
    comparison = fr.compare_periods(current, current)
    assert comparison["revenue"]["change_pct"] is None


def test_revenue_breakdown_percentages_sum_to_100(db_session):
    tenant, company, fy, user = _setup(db_session)
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("600.00"), counterparty="Customer A")
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("400.00"), counterparty="Customer B")
    db_session.commit()

    breakdown = fr.revenue_breakdown(db_session, company.id, fr.DateRange(date(2027, 1, 1), date(2027, 12, 31)))
    assert breakdown[0]["counterparty_name"] == "Customer A"
    assert breakdown[0]["pct_of_total"] == Decimal("60.0")
    assert breakdown[1]["pct_of_total"] == Decimal("40.0")


# ---- Debtors / creditors / aging ----


def test_debtors_aging_buckets(db_session):
    tenant, company, fy, user = _setup(db_session)
    today = date(2027, 6, 1)
    overdue_60 = _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("100"), vat=Decimal("0"),
                      invoice_date=date(2027, 3, 1), due_date=today - timedelta(days=45))
    current_tx = _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("50"), vat=Decimal("0"),
                      invoice_date=date(2027, 5, 20), due_date=today + timedelta(days=10))
    db_session.commit()

    result = fr.debtors(db_session, company.id, today)
    assert result["total_outstanding"] == Decimal("150")
    assert result["aging_summary"]["31-60"] == Decimal("100")
    assert result["aging_summary"]["current"] == Decimal("50")
    ids = {row["transaction_id"] for row in result["items"]}
    assert ids == {overdue_60.id, current_tx.id}


def test_debtors_excludes_fully_paid_invoices(db_session):
    tenant, company, fy, user = _setup(db_session)
    tx = _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("100"), vat=Decimal("21"))
    _pay(db_session, company, tx, Decimal("121.00"), date(2027, 2, 15))
    db_session.commit()

    result = fr.debtors(db_session, company.id, date(2027, 6, 1))
    assert result["total_outstanding"] == Decimal("0")
    assert result["items"] == []


def test_remaining_balance_as_of_excludes_future_payments(db_session):
    tenant, company, fy, user = _setup(db_session)
    tx = _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("100"), vat=Decimal("21"))
    _pay(db_session, company, tx, Decimal("121.00"), date(2027, 8, 1))
    db_session.commit()

    # as_of a date before the payment was made -- should still show as outstanding
    result = fr.debtors(db_session, company.id, date(2027, 6, 1))
    assert result["total_outstanding"] == Decimal("121.00")


# ---- Balance sheet ----


def test_balance_sheet_flags_missing_manual_items(db_session):
    tenant, company, fy, user = _setup(db_session)
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("100"), vat=Decimal("0"))
    db_session.commit()

    bs = fr.balance_sheet(db_session, company.id, date(2027, 6, 1))
    assert bs["missing_opening_balance_warning"] is not None
    assert bs["assets"]["fixed_assets"] == Decimal("0")


def test_balance_sheet_unpaid_invoice_alone_balances_via_retained_earnings(db_session):
    """A plain unpaid invoice (no VAT) is Dr AR / Cr Revenue -- AR and
    retained earnings move together, so the balance sheet balances even
    though nothing has been paid or manually entered yet."""
    tenant, company, fy, user = _setup(db_session)
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("500"), vat=Decimal("0"))
    db_session.commit()

    bs = fr.balance_sheet(db_session, company.id, date(2027, 6, 1))
    assert bs["assets"]["accounts_receivable"] == Decimal("500")
    assert bs["equity"]["retained_earnings"] == Decimal("500")
    assert bs["is_balanced"] is True


def test_balance_sheet_flags_imbalance_from_vat_not_yet_booked(db_session):
    """AR includes the VAT (gross), but revenue only recognizes the net
    amount -- the VAT portion has nowhere to go until a VAT return is
    computed for the period, so it must show up as a real, flagged
    imbalance rather than being hidden or force-balanced."""
    tenant, company, fy, user = _setup(db_session)
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("500"), vat=Decimal("105.00"))
    db_session.commit()

    bs = fr.balance_sheet(db_session, company.id, date(2027, 6, 1))
    assert bs["assets"]["accounts_receivable"] == Decimal("605.00")
    assert bs["equity"]["retained_earnings"] == Decimal("500.00")
    assert bs["is_balanced"] is False
    assert bs["imbalance_amount"] == Decimal("105.00")


def test_balance_sheet_balances_with_manual_equity_matching_retained_earnings(db_session):
    tenant, company, fy, user = _setup(db_session)
    tx = _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("500"), vat=Decimal("0"))
    _pay(db_session, company, tx, Decimal("500"), date(2027, 2, 15))
    account, batch = _bank_setup(db_session, company, user)
    _bank_tx(db_session, company, account, batch, Decimal("500"), date(2027, 2, 15))
    db_session.commit()

    # Cash=500, AR=0, net_profit(retained earnings)=500 -> equity side already
    # matches assets with zero manual entries: Assets(cash 500) = Equity(RE 500).
    bs = fr.balance_sheet(db_session, company.id, date(2027, 6, 1))
    assert bs["assets"]["total"] == Decimal("500")
    assert bs["equity"]["retained_earnings"] == Decimal("500")
    assert bs["is_balanced"] is True
    assert bs["imbalance_amount"] == Decimal("0")


def test_balance_sheet_includes_manual_items_only_up_to_as_of_date(db_session):
    tenant, company, fy, user = _setup(db_session)
    db_session.add(ManualBalanceSheetItem(
        tenant_id=tenant.id, company_id=company.id, category=BalanceSheetItemCategory.fixed_assets,
        label="Van", amount=Decimal("10000"), as_of_date=date(2027, 9, 1), created_by_user_id=user.id,
    ))
    db_session.commit()

    before = fr.balance_sheet(db_session, company.id, date(2027, 6, 1))
    after = fr.balance_sheet(db_session, company.id, date(2027, 10, 1))
    assert before["assets"]["fixed_assets"] == Decimal("0")
    assert after["assets"]["fixed_assets"] == Decimal("10000")


# ---- VAT position on the balance sheet ----


def test_vat_payable_appears_as_liability_until_marked_paid(db_session):
    tenant, company, fy, user = _setup(db_session)
    period = VatPeriod(financial_year_id=fy.id, label="Q1", start_date=date(2027, 1, 1), end_date=date(2027, 3, 31),
                        filing_deadline=date(2027, 4, 30), payment_deadline=date(2027, 4, 30), status=VatPeriodStatus.open)
    db_session.add(period)
    db_session.flush()
    from app.models.accounting import VatReturn
    vat_return = VatReturn(tenant_id=tenant.id, company_id=company.id, vat_period_id=period.id,
                            status=VatReturnStatus.approved, rules_version="v1", net_payable=Decimal("210.00"))
    db_session.add(vat_return)
    db_session.commit()

    bs = fr.balance_sheet(db_session, company.id, date(2027, 6, 1))
    assert bs["liabilities"]["vat_payable"] == Decimal("210.00")

    period.status = VatPeriodStatus.paid
    db_session.commit()
    bs_after_payment = fr.balance_sheet(db_session, company.id, date(2027, 6, 1))
    assert bs_after_payment["liabilities"]["vat_payable"] == Decimal("0")


# ---- Trial balance ----


def test_trial_balance_matches_balance_sheet_imbalance(db_session):
    tenant, company, fy, user = _setup(db_session)
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("500"), vat=Decimal("105.00"))
    db_session.commit()

    period = fr.DateRange(date(2027, 1, 1), date(2027, 6, 1))
    tb = fr.trial_balance(db_session, company.id, period)
    bs = fr.balance_sheet(db_session, company.id, period.end)
    assert tb["difference"] == bs["imbalance_amount"]
    assert tb["is_balanced"] == bs["is_balanced"]


def test_trial_balance_balances_when_nothing_outstanding(db_session):
    tenant, company, fy, user = _setup(db_session)
    tx = _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("500"), vat=Decimal("0"))
    _pay(db_session, company, tx, Decimal("500"), date(2027, 2, 15))
    account, batch = _bank_setup(db_session, company, user)
    _bank_tx(db_session, company, account, batch, Decimal("500.00"), date(2027, 2, 15))
    db_session.commit()

    period = fr.DateRange(date(2027, 1, 1), date(2027, 6, 1))
    tb = fr.trial_balance(db_session, company.id, period)
    assert tb["is_balanced"] is True
    assert tb["difference"] == Decimal("0")


# ---- Cash flow statement ----


def test_cash_flow_statement_operating_activities_from_bank_transactions(db_session):
    tenant, company, fy, user = _setup(db_session)
    account, batch = _bank_setup(db_session, company, user)
    _bank_tx(db_session, company, account, batch, Decimal("1000.00"), date(2027, 3, 10))
    _bank_tx(db_session, company, account, batch, Decimal("-400.00"), date(2027, 3, 15))
    db_session.commit()

    period = fr.DateRange(date(2027, 3, 1), date(2027, 3, 31))
    cf = fr.cash_flow_statement(db_session, company.id, period)
    assert cf["operating_activities"]["receipts"] == Decimal("1000.00")
    assert cf["operating_activities"]["payments"] == Decimal("-400.00")
    assert cf["operating_activities"]["net"] == Decimal("600.00")
    assert cf["net_change_in_cash"] == Decimal("600.00")


def test_cash_flow_distinguishes_accrual_from_cash(db_session):
    tenant, company, fy, user = _setup(db_session)
    # Invoiced in March but not yet paid -- accrual revenue exists, cash does not.
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("1000"), vat=Decimal("0"),
        invoice_date=date(2027, 3, 5))
    db_session.commit()

    period = fr.DateRange(date(2027, 3, 1), date(2027, 3, 31))
    cf = fr.cash_flow_statement(db_session, company.id, period)
    recon = cf["accrual_vs_cash_reconciliation"]
    assert recon["net_profit_accrual"] == Decimal("1000")
    assert recon["actual_operating_cash"] == Decimal("0")
    assert recon["increase_in_accounts_receivable"] == Decimal("1000")


# ---- Period resolution ----


def test_resolve_period_monthly_quarterly_annual():
    monthly = fr.resolve_period(fr.ReportPeriod.monthly, date(2027, 2, 15))
    assert monthly == fr.DateRange(date(2027, 2, 1), date(2027, 2, 28))

    quarterly = fr.resolve_period(fr.ReportPeriod.quarterly, date(2027, 5, 15))
    assert quarterly == fr.DateRange(date(2027, 4, 1), date(2027, 6, 30))

    annual = fr.resolve_period(fr.ReportPeriod.annual, date(2027, 7, 1))
    assert annual == fr.DateRange(date(2027, 1, 1), date(2027, 12, 31))


def test_year_on_year_period():
    period = fr.DateRange(date(2027, 1, 1), date(2027, 3, 31))
    yoy = fr.year_on_year_period(period)
    assert yoy == fr.DateRange(date(2026, 1, 1), date(2026, 3, 31))


def test_previous_period_same_length():
    period = fr.DateRange(date(2027, 2, 1), date(2027, 2, 28))
    prev = fr.previous_period(period)
    assert prev.end == date(2027, 1, 31)
    assert (prev.end - prev.start).days == (period.end - period.start).days
