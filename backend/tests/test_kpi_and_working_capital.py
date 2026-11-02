from datetime import date, timedelta
from decimal import Decimal

from app.accounting import financial_reports as fr
from app.accounting import kpi_engine, working_capital
from app.core.security import hash_password
from app.models.accounting import AccountingTransaction, Payment
from app.models.company import Company
from app.models.enums import LedgerSide, TransactionType, UserRole
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


def _tx(db_session, company, fy, user, *, ledger_side, net, vat=Decimal("0"), invoice_date, due_date=None,
        counterparty="Acme", expense_category=None):
    tx = AccountingTransaction(
        tenant_id=company.tenant_id, company_id=company.id, financial_year_id=fy.id,
        transaction_type=TransactionType.sales_invoice if ledger_side == LedgerSide.sales else TransactionType.purchase_invoice,
        ledger_side=ledger_side, counterparty_name=counterparty, invoice_date=invoice_date, due_date=due_date or invoice_date,
        net_amount=net, vat_amount=vat, gross_amount=net + vat, expense_category=expense_category, created_by_user_id=user.id,
    )
    db_session.add(tx)
    db_session.flush()
    return tx


def _pay(db_session, company, tx, amount, payment_date):
    p = Payment(tenant_id=company.tenant_id, company_id=company.id, transaction_id=tx.id, amount=amount, payment_date=payment_date, created_by_user_id=tx.created_by_user_id)
    db_session.add(p)
    db_session.flush()
    return p


# ---- KPI engine ----


def test_profitability_kpis_formulas(db_session):
    tenant, company, fy, user = _setup(db_session)
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("1000"), invoice_date=date(2027, 2, 1))
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.purchases, net=Decimal("400"), invoice_date=date(2027, 2, 1), expense_category="Cost of goods sold")
    db_session.commit()

    period = fr.DateRange(date(2027, 1, 1), date(2027, 12, 31))
    kpis = kpi_engine.profitability_kpis(db_session, company.id, period)
    assert kpis["gross_margin_pct"]["value"] == Decimal("60.0")
    assert kpis["gross_margin_pct"]["missing_data"] is None


def test_kpi_missing_data_when_no_revenue(db_session):
    tenant, company, fy, user = _setup(db_session)
    period = fr.DateRange(date(2027, 1, 1), date(2027, 12, 31))
    kpis = kpi_engine.profitability_kpis(db_session, company.id, period)
    assert kpis["gross_margin_pct"]["value"] is None
    assert kpis["gross_margin_pct"]["missing_data"] is not None


def test_liquidity_ratio_undefined_with_no_liabilities(db_session):
    tenant, company, fy, user = _setup(db_session)
    kpis = kpi_engine.liquidity_kpis(db_session, company.id, date(2027, 6, 1))
    assert kpis["current_ratio"]["value"] is None
    assert "undefined" in kpis["current_ratio"]["missing_data"]


def test_inventory_turnover_always_reports_missing_data(db_session):
    tenant, company, fy, user = _setup(db_session)
    period = fr.DateRange(date(2027, 1, 1), date(2027, 12, 31))
    kpis = kpi_engine.efficiency_kpis(db_session, company.id, period)
    assert kpis["inventory_turnover"]["value"] is None
    assert kpis["inventory_turnover"]["missing_data"] is not None


def test_customer_concentration_top1_pct(db_session):
    tenant, company, fy, user = _setup(db_session)
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("800"), invoice_date=date(2027, 2, 1), counterparty="Big Co")
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("200"), invoice_date=date(2027, 2, 2), counterparty="Small Co")
    db_session.commit()

    period = fr.DateRange(date(2027, 1, 1), date(2027, 12, 31))
    kpis = kpi_engine.business_performance_kpis(db_session, company.id, period)
    assert kpis["customer_concentration_top1_pct"]["value"] == Decimal("80.0")


# ---- Working capital ----


def test_customer_payment_behavior_average_days(db_session):
    tenant, company, fy, user = _setup(db_session)
    tx = _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("100"), invoice_date=date(2027, 2, 1), counterparty="Fast Payer")
    _pay(db_session, company, tx, Decimal("100"), date(2027, 2, 11))
    db_session.commit()

    result = working_capital.customer_payment_behavior(db_session, company.id, fr.DateRange(date(2027, 1, 1), date(2027, 12, 31)))
    assert result[0]["counterparty_name"] == "Fast Payer"
    assert result[0]["average_days_to_pay"] == 10.0


def test_customer_payment_behavior_excludes_partial_payments(db_session):
    tenant, company, fy, user = _setup(db_session)
    tx = _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("100"), invoice_date=date(2027, 2, 1))
    _pay(db_session, company, tx, Decimal("50"), date(2027, 2, 11))
    db_session.commit()

    result = working_capital.customer_payment_behavior(db_session, company.id, fr.DateRange(date(2027, 1, 1), date(2027, 12, 31)))
    assert result == []


def test_payment_delay_alerts_flags_newly_overdue_and_severely_overdue(db_session):
    tenant, company, fy, user = _setup(db_session)
    today = date(2027, 6, 1)
    newly_overdue = _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("100"),
                        invoice_date=date(2027, 5, 1), due_date=today - timedelta(days=3), counterparty="Newly")
    severely_overdue = _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("100"),
                           invoice_date=date(2027, 1, 1), due_date=date(2027, 1, 15), counterparty="Severely")
    db_session.commit()

    alerts = working_capital.payment_delay_alerts(db_session, company.id, today)
    ids = {a["transaction_id"] for a in alerts}
    assert newly_overdue.id in ids
    assert severely_overdue.id in ids
    reasons = {a["transaction_id"]: a["alert_reason"] for a in alerts}
    assert "90 days" in reasons[severely_overdue.id]


def test_cash_conversion_cycle_reports_missing_inventory_data(db_session):
    tenant, company, fy, user = _setup(db_session)
    result = working_capital.cash_conversion_cycle(db_session, company.id, fr.DateRange(date(2027, 1, 1), date(2027, 12, 31)))
    assert result["days_inventory_outstanding"] is None
    assert result["cash_conversion_cycle_days"] is None
    assert result["missing_data"] is not None


def test_working_capital_trend_across_periods(db_session):
    tenant, company, fy, user = _setup(db_session)
    _tx(db_session, company, fy, user, ledger_side=LedgerSide.sales, net=Decimal("500"), invoice_date=date(2027, 2, 1))
    db_session.commit()

    periods = [fr.resolve_period(fr.ReportPeriod.monthly, date(2027, m, 15)) for m in (1, 2, 3)]
    trend = working_capital.working_capital_trend(db_session, company.id, periods)
    assert trend[0]["accounts_receivable"] == Decimal("0")
    assert trend[1]["accounts_receivable"] == Decimal("500")
