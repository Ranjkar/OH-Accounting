from datetime import date
from decimal import Decimal

from app.core.security import hash_password
from app.models.accounting import AccountingTransaction
from app.models.enums import LedgerSide, TransactionType, UserRole
from app.models.tenant import Tenant
from app.models.user import User


def _create_user(db_session, tenant_name="Acme Accounting", email="admin@acme.nl", role=UserRole.admin):
    tenant = db_session.query(Tenant).filter(Tenant.name == tenant_name).first()
    if tenant is None:
        tenant = Tenant(name=tenant_name)
        db_session.add(tenant)
        db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Test", role=role)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, email, password="secret123") -> dict:
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _setup_company_with_fy(client, headers, year=2027):
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": year}, headers=headers).json()
    return company_id, fy


def _create_sale(db_session, company_id, fy_id, tenant_id, user_id, net=Decimal("1000"), invoice_date=date(2027, 2, 1)):
    tx = AccountingTransaction(
        tenant_id=tenant_id, company_id=company_id, financial_year_id=fy_id,
        transaction_type=TransactionType.sales_invoice, ledger_side=LedgerSide.sales,
        counterparty_name="Customer A", invoice_date=invoice_date, due_date=invoice_date,
        net_amount=net, vat_amount=Decimal("0"), gross_amount=net, created_by_user_id=user_id,
    )
    db_session.add(tx)
    db_session.commit()
    return tx


# ---- Profit & loss / balance sheet / reports ----


def test_profit_and_loss_endpoint(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id)

    response = client.get(
        "/api/v1/financial-reports/profit-and-loss",
        params={"company_id": company_id, "period_type": "ANNUAL", "reference_date": "2027-06-01"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current"]["revenue"] == "1000.00"


def test_profit_and_loss_with_previous_period_comparison(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id, invoice_date=date(2027, 3, 1))

    response = client.get(
        "/api/v1/financial-reports/profit-and-loss",
        params={"company_id": company_id, "period_type": "MONTHLY", "reference_date": "2027-03-15", "compare": "previous"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["previous"]["revenue"] == "0"
    assert body["comparison"]["revenue"]["change_pct"] is None


def test_balance_sheet_endpoint_flags_missing_items(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.get("/api/v1/financial-reports/balance-sheet", params={"company_id": company_id, "as_of_date": "2027-06-01"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["missing_opening_balance_warning"] is not None
    assert body["is_balanced"] is True  # nothing recorded at all -- trivially balanced at zero


def test_create_and_list_manual_balance_sheet_items(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.post(
        "/api/v1/financial-reports/balance-sheet-items",
        json={"company_id": company_id, "category": "FIXED_ASSETS", "label": "Van", "amount": "10000.00", "as_of_date": "2027-01-01"},
        headers=headers,
    )
    assert response.status_code == 201, response.text

    listed = client.get("/api/v1/financial-reports/balance-sheet-items", params={"company_id": company_id}, headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["amount"] == "10000.00"

    bs = client.get("/api/v1/financial-reports/balance-sheet", params={"company_id": company_id, "as_of_date": "2027-06-01"}, headers=headers).json()
    assert bs["assets"]["fixed_assets"] == "10000.00"


def test_debtors_and_creditors_endpoints(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id)

    response = client.get("/api/v1/financial-reports/debtors", params={"company_id": company_id, "as_of_date": "2027-06-01"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["total_outstanding"] == "1000.00"


def test_kpis_endpoint(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id)

    response = client.get(
        "/api/v1/financial-reports/kpis",
        params={"company_id": company_id, "period_type": "ANNUAL", "reference_date": "2027-06-01"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profitability"]["gross_margin_pct"]["value"] == "100.0"


def test_company_comparison_endpoint(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_a, fy_a = _setup_company_with_fy(client, headers)
    company_b, fy_b = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_a, fy_a["id"], admin.tenant_id, admin.id, net=Decimal("500"))
    _create_sale(db_session, company_b, fy_b["id"], admin.tenant_id, admin.id, net=Decimal("800"))

    response = client.get(
        "/api/v1/financial-reports/company-comparison",
        params={"company_ids": f"{company_a},{company_b}", "period_type": "ANNUAL", "reference_date": "2027-06-01"},
        headers=headers,
    )
    assert response.status_code == 200
    revenues = {row["company_id"]: row["profit_and_loss"]["revenue"] for row in response.json()["companies"]}
    assert revenues[company_a] == "500.00"
    assert revenues[company_b] == "800.00"


def test_working_capital_payment_delay_alerts(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    tx = AccountingTransaction(
        tenant_id=admin.tenant_id, company_id=company_id, financial_year_id=fy["id"],
        transaction_type=TransactionType.sales_invoice, ledger_side=LedgerSide.sales,
        counterparty_name="Late Payer", invoice_date=date(2027, 1, 1), due_date=date(2027, 1, 15),
        net_amount=Decimal("100"), vat_amount=Decimal("0"), gross_amount=Decimal("100"), created_by_user_id=admin.id,
    )
    db_session.add(tx)
    db_session.commit()

    response = client.get(
        "/api/v1/financial-reports/working-capital/payment-delay-alerts",
        params={"company_id": company_id, "as_of_date": "2027-06-01"},
        headers=headers,
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert "90 days" in response.json()[0]["alert_reason"]


# ---- Permissions / tenant isolation ----


def test_viewer_can_read_but_not_write_balance_sheet_items(client, db_session):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers_admin)

    viewer = User(tenant_id=admin.tenant_id, email="viewer@acme.nl", hashed_password=hash_password("secret123"), full_name="Viewer", role=UserRole.viewer)
    db_session.add(viewer)
    db_session.commit()

    from app.models.user import user_companies
    db_session.execute(user_companies.insert().values(user_id=viewer.id, company_id=company_id))
    db_session.commit()
    headers_viewer = _login(client, "viewer@acme.nl")

    read = client.get("/api/v1/financial-reports/balance-sheet", params={"company_id": company_id}, headers=headers_viewer)
    assert read.status_code == 200

    write = client.post(
        "/api/v1/financial-reports/balance-sheet-items",
        json={"company_id": company_id, "category": "EQUITY", "label": "Capital", "amount": "100", "as_of_date": "2027-01-01"},
        headers=headers_viewer,
    )
    assert write.status_code == 403


def test_cross_tenant_cannot_access_financial_reports(client, db_session):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a, _ = _setup_company_with_fy(client, headers_a)

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get("/api/v1/financial-reports/balance-sheet", params={"company_id": company_a}, headers=headers_b)
    assert response.status_code == 404


# ---- Budgets ----


def test_create_submit_approve_budget_and_variance(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id, net=Decimal("1200"), invoice_date=date(2027, 2, 1))

    create = client.post(
        "/api/v1/budgets",
        json={"company_id": company_id, "financial_year_id": fy["id"], "name": "2027 Budget",
              "lines": [{"category": "Revenue", "month": 2, "amount": "1000"}]},
        headers=headers,
    )
    assert create.status_code == 201, create.text
    budget_id = create.json()["id"]
    assert create.json()["status"] == "DRAFT"

    submit = client.post(f"/api/v1/budgets/{budget_id}/submit", headers=headers)
    assert submit.json()["status"] == "SUBMITTED"

    approve = client.post(f"/api/v1/budgets/{budget_id}/approve", headers=headers)
    assert approve.json()["status"] == "APPROVED"

    variance = client.get(f"/api/v1/budgets/{budget_id}/variance", headers=headers)
    assert variance.status_code == 200
    assert variance.json()["lines"][0]["actual"] == "1200.00"
    assert variance.json()["lines"][0]["variance"] == "200.00"


def test_business_owner_can_create_budget_but_not_approve(client, db_session):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers_admin)

    owner = User(tenant_id=admin.tenant_id, email="owner@acme.nl", hashed_password=hash_password("secret123"), full_name="Owner", role=UserRole.customer)
    db_session.add(owner)
    db_session.commit()
    from app.models.user import user_companies
    db_session.execute(user_companies.insert().values(user_id=owner.id, company_id=company_id))
    db_session.commit()
    headers_owner = _login(client, "owner@acme.nl")

    create = client.post(
        "/api/v1/budgets", json={"company_id": company_id, "financial_year_id": fy["id"], "name": "Owner Budget", "lines": []},
        headers=headers_owner,
    )
    assert create.status_code == 201
    budget_id = create.json()["id"]

    client.post(f"/api/v1/budgets/{budget_id}/submit", headers=headers_owner)
    approve = client.post(f"/api/v1/budgets/{budget_id}/approve", headers=headers_owner)
    assert approve.status_code == 403


def test_budget_suggestion_endpoint_uses_stub_without_api_key(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.get(
        "/api/v1/budgets/suggest",
        params={"company_id": company_id, "financial_year_id": fy["id"], "categories": "Revenue,Rent"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ai_suggestion"]["requires_accountant_review"] is True


# ---- Forecasts & scenarios ----


def test_full_forecast_endpoint(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.get("/api/v1/forecasts/full", params={"company_id": company_id, "horizon_months": 2}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "cash_flow" in body
    assert "revenue_expense_profit" in body


def test_create_and_compare_scenarios(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id, invoice_date=date(2027, 6, 1))

    optimistic = client.post(
        "/api/v1/scenarios",
        json={"company_id": company_id, "name": "Optimistic", "scenario_type": "OPTIMISTIC",
              "assumptions": {"revenue_change_pct": "10"}, "horizon_months": 1, "base_date": "2027-07-01"},
        headers=headers,
    ).json()
    conservative = client.post(
        "/api/v1/scenarios",
        json={"company_id": company_id, "name": "Conservative", "scenario_type": "CONSERVATIVE",
              "assumptions": {"revenue_change_pct": "-15"}, "horizon_months": 1, "base_date": "2027-07-01"},
        headers=headers,
    ).json()

    result = client.get(f"/api/v1/scenarios/{optimistic['id']}/result", headers=headers)
    assert result.status_code == 200
    assert result.json()["never_modifies_ledger"] is True

    comparison = client.get("/api/v1/scenarios/compare", params={"scenario_ids": f"{optimistic['id']},{conservative['id']}"}, headers=headers)
    assert comparison.status_code == 200
    assert len(comparison.json()["comparison"]) == 2


def test_duplicate_scenario(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    original = client.post(
        "/api/v1/scenarios",
        json={"company_id": company_id, "name": "Base", "scenario_type": "BASE", "assumptions": {}, "horizon_months": 3},
        headers=headers,
    ).json()
    duplicate = client.post(f"/api/v1/scenarios/{original['id']}/duplicate", params={"name": "Base copy"}, headers=headers)
    assert duplicate.status_code == 201
    assert duplicate.json()["assumptions"] == original["assumptions"]
    assert duplicate.json()["id"] != original["id"]
