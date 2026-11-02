from datetime import date
from decimal import Decimal

import pytest

from app.accounting import budget_service
from app.core.security import hash_password
from app.models.accounting import AccountingTransaction
from app.models.company import Company
from app.models.enums import BudgetStatus, LedgerSide, TransactionType, UserRole
from app.models.financial_year import FinancialYear
from app.models.tenant import Tenant
from app.models.user import User
from app.services import ai_budget_provider


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


def test_create_budget_and_compute_variance(db_session):
    tenant, company, fy, user = _setup(db_session)
    tx = AccountingTransaction(
        tenant_id=tenant.id, company_id=company.id, financial_year_id=fy.id,
        transaction_type=TransactionType.sales_invoice, ledger_side=LedgerSide.sales,
        invoice_date=date(2027, 2, 1), due_date=date(2027, 2, 1),
        net_amount=Decimal("1200"), vat_amount=Decimal("0"), gross_amount=Decimal("1200"),
        created_by_user_id=user.id,
    )
    db_session.add(tx)
    db_session.commit()

    budget = budget_service.create_budget(
        db_session, tenant_id=tenant.id, company_id=company.id, financial_year_id=fy.id, name="2027 Budget",
        lines=[{"category": "Revenue", "month": 2, "amount": "1000.00"}], created_by_user_id=user.id,
    )
    db_session.commit()

    result = budget_service.budget_vs_actual(db_session, budget)
    assert result["lines"][0]["budgeted"] == Decimal("1000.00")
    assert result["lines"][0]["actual"] == Decimal("1200")
    assert result["lines"][0]["variance"] == Decimal("200")
    assert result["lines"][0]["variance_pct"] == Decimal("20.0")


def test_budget_approval_workflow(db_session):
    tenant, company, fy, user = _setup(db_session)
    budget = budget_service.create_budget(
        db_session, tenant_id=tenant.id, company_id=company.id, financial_year_id=fy.id, name="B", lines=[], created_by_user_id=user.id,
    )
    db_session.commit()
    assert budget.status == BudgetStatus.draft

    with pytest.raises(budget_service.BudgetError):
        budget_service.approve_budget(db_session, budget, user.id)

    budget_service.submit_budget(db_session, budget)
    db_session.commit()
    assert budget.status == BudgetStatus.submitted

    budget_service.approve_budget(db_session, budget, user.id)
    db_session.commit()
    assert budget.status == BudgetStatus.approved
    assert budget.approved_by_user_id == user.id


def test_revision_creates_new_immutable_version(db_session):
    tenant, company, fy, user = _setup(db_session)
    original = budget_service.create_budget(
        db_session, tenant_id=tenant.id, company_id=company.id, financial_year_id=fy.id, name="B",
        lines=[{"category": "Revenue", "month": 1, "amount": "1000"}], created_by_user_id=user.id,
    )
    budget_service.submit_budget(db_session, original)
    budget_service.approve_budget(db_session, original, user.id)
    db_session.commit()
    original_amount = original.lines[0].amount

    revision = budget_service.revise_budget(
        db_session, original, lines=[{"category": "Revenue", "month": 1, "amount": "1500"}], created_by_user_id=user.id,
    )
    db_session.commit()

    assert revision.version == 2
    assert revision.supersedes_budget_id == original.id
    assert revision.status == BudgetStatus.draft
    # Original is untouched
    db_session.refresh(original)
    assert original.status == BudgetStatus.approved
    assert original.lines[0].amount == original_amount


def test_budget_history_returns_full_chain(db_session):
    tenant, company, fy, user = _setup(db_session)
    v1 = budget_service.create_budget(
        db_session, tenant_id=tenant.id, company_id=company.id, financial_year_id=fy.id, name="B", lines=[], created_by_user_id=user.id,
    )
    db_session.commit()
    v2 = budget_service.revise_budget(db_session, v1, lines=[], created_by_user_id=user.id)
    db_session.commit()
    v3 = budget_service.revise_budget(db_session, v2, lines=[], created_by_user_id=user.id)
    db_session.commit()

    history = budget_service.budget_history(db_session, v2)
    versions = [b.version for b in history]
    assert versions == [1, 2, 3]


def test_suggest_lines_from_history_uses_prior_year_average(db_session):
    tenant, company, fy, user = _setup(db_session)
    prior_fy = FinancialYear(company_id=company.id, year=2026, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db_session.add(prior_fy)
    db_session.flush()
    tx = AccountingTransaction(
        tenant_id=tenant.id, company_id=company.id, financial_year_id=prior_fy.id,
        transaction_type=TransactionType.purchase_invoice, ledger_side=LedgerSide.purchases,
        invoice_date=date(2026, 6, 1), due_date=date(2026, 6, 1),
        net_amount=Decimal("1200.00"), vat_amount=Decimal("0"), gross_amount=Decimal("1200.00"),
        expense_category="Rent", created_by_user_id=user.id,
    )
    db_session.add(tx)
    db_session.commit()

    lines = budget_service.suggest_lines_from_history(db_session, company.id, fy, ["Rent"])
    assert len(lines) == 12
    assert lines[0]["amount"] == Decimal("100.00")  # 1200 / 12 months


# ---- AI budget provider ----


def test_stub_budget_provider_carries_baseline_forward(monkeypatch):
    ai_budget_provider.reset_provider_cache()
    monkeypatch.setattr("app.core.config.settings.anthropic_api_key", None)
    provider = ai_budget_provider.get_budget_provider()
    result = provider.suggest_budget([{"category": "Rent", "average_monthly_amount": "500.00"}])
    assert result.suggestions[0].suggested_monthly_amount == "500.00"
    assert result.requires_accountant_review is True
    ai_budget_provider.reset_provider_cache()
