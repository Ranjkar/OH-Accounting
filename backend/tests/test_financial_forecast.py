from datetime import date
from decimal import Decimal

from app.accounting import financial_forecast, scenario_engine
from app.core.security import hash_password
from app.models.accounting import AccountingTransaction
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


def test_revenue_forecast_averages_last_three_months(db_session):
    tenant, company, fy, user = _setup(db_session)
    reference = date(2027, 7, 1)
    _sale(db_session, company, fy, user, Decimal("1000"), date(2027, 4, 15))
    _sale(db_session, company, fy, user, Decimal("2000"), date(2027, 5, 15))
    _sale(db_session, company, fy, user, Decimal("3000"), date(2027, 6, 15))
    db_session.commit()

    result = financial_forecast.revenue_expense_profit_forecast(db_session, company.id, horizon_months=2, reference_date=reference)
    assert result["monthly_forecast"][0]["forecast_revenue"] == Decimal("2000.00")
    assert len(result["monthly_forecast"]) == 2
    assert result["is_estimate"] is True
    assert "assumptions" in result and len(result["assumptions"]) > 0


def test_outstanding_invoice_forecast_is_not_an_estimate(db_session):
    tenant, company, fy, user = _setup(db_session)
    _sale(db_session, company, fy, user, Decimal("500"), date(2027, 2, 1))
    db_session.commit()

    result = financial_forecast.outstanding_invoice_forecast(db_session, company.id, date(2027, 6, 1))
    assert result["confirmed_receivables_outstanding"] == Decimal("500")
    assert result["is_estimate"] is False


def test_tax_liability_forecast_never_fabricates_corporate_tax(db_session):
    tenant, company, fy, user = _setup(db_session)
    result = financial_forecast.tax_liability_forecast(db_session, company.id)
    assert result["corporate_income_tax_estimate"] is None
    assert "not calculated" in result["note"]


def test_full_forecast_reuses_phase6_cash_flow_module(db_session):
    tenant, company, fy, user = _setup(db_session)
    result = financial_forecast.full_forecast(db_session, company.id, horizon_months=2, reference_date=date(2027, 7, 1))
    assert "cash_flow" in result
    assert "net_bank_transaction_movement_disclaimer" in result["cash_flow"]
    assert "revenue_expense_profit" in result
    assert "outstanding_invoices" in result
    assert "vat_payments" in result
    assert "tax_liability" in result


# ---- Scenario engine ----


def test_scenario_never_touches_ledger(db_session):
    tenant, company, fy, user = _setup(db_session)
    _sale(db_session, company, fy, user, Decimal("1000"), date(2027, 6, 1))
    db_session.commit()
    tx_count_before = db_session.query(AccountingTransaction).count()

    scenario_engine.apply_scenario(db_session, company.id, {"revenue_change_pct": "10"}, horizon_months=1, reference_date=date(2027, 7, 1))
    db_session.flush()

    tx_count_after = db_session.query(AccountingTransaction).count()
    assert tx_count_before == tx_count_after


def test_optimistic_scenario_increases_profit_vs_conservative(db_session):
    tenant, company, fy, user = _setup(db_session)
    _sale(db_session, company, fy, user, Decimal("1000"), date(2027, 6, 1))
    db_session.commit()

    optimistic = scenario_engine.apply_scenario(db_session, company.id, {"revenue_change_pct": "10"}, horizon_months=1, reference_date=date(2027, 7, 1))
    conservative = scenario_engine.apply_scenario(db_session, company.id, {"revenue_change_pct": "-15"}, horizon_months=1, reference_date=date(2027, 7, 1))

    assert optimistic["revenue_expense_profit"]["total_forecast_profit"] > conservative["revenue_expense_profit"]["total_forecast_profit"]


def test_new_hire_cost_reduces_profit(db_session):
    tenant, company, fy, user = _setup(db_session)
    _sale(db_session, company, fy, user, Decimal("1000"), date(2027, 6, 1))
    db_session.commit()

    base = scenario_engine.apply_scenario(db_session, company.id, {}, horizon_months=1, reference_date=date(2027, 7, 1))
    with_hire = scenario_engine.apply_scenario(db_session, company.id, {"new_hire_monthly_cost": "3000"}, horizon_months=1, reference_date=date(2027, 7, 1))

    assert with_hire["revenue_expense_profit"]["total_forecast_profit"] < base["revenue_expense_profit"]["total_forecast_profit"]
    diff = base["revenue_expense_profit"]["total_forecast_profit"] - with_hire["revenue_expense_profit"]["total_forecast_profit"]
    assert diff == Decimal("3000.00")


def test_compare_scenarios(db_session):
    tenant, company, fy, user = _setup(db_session)
    _sale(db_session, company, fy, user, Decimal("1000"), date(2027, 6, 1))
    db_session.commit()

    result = scenario_engine.compare_scenarios(
        db_session, company.id,
        [{"name": "Optimistic", "assumptions": {"revenue_change_pct": "10"}}, {"name": "Conservative", "assumptions": {"revenue_change_pct": "-15"}}],
        horizon_months=1, reference_date=date(2027, 7, 1),
    )
    assert len(result["comparison"]) == 2
    names = {c["name"] for c in result["comparison"]}
    assert names == {"Optimistic", "Conservative"}
