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


def _create_sale(db_session, company_id, fy_id, tenant_id, user_id, net=Decimal("1000"), invoice_date=date(2027, 6, 1)):
    tx = AccountingTransaction(
        tenant_id=tenant_id, company_id=company_id, financial_year_id=fy_id,
        transaction_type=TransactionType.sales_invoice, ledger_side=LedgerSide.sales,
        counterparty_name="Customer A", invoice_date=invoice_date, due_date=invoice_date,
        net_amount=net, vat_amount=Decimal("0"), gross_amount=net, created_by_user_id=user_id,
    )
    db_session.add(tx)
    db_session.commit()
    return tx


def test_accountant_dashboard_portfolio(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id)

    response = client.get("/api/v1/dashboard/accountant", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["portfolio"]) == 1
    assert body["portfolio"][0]["company_id"] == company_id


def test_business_owner_dashboard(client, db_session):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers_admin)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id)

    owner = User(tenant_id=admin.tenant_id, email="owner@acme.nl", hashed_password=hash_password("secret123"), full_name="Owner", role=UserRole.customer)
    db_session.add(owner)
    db_session.commit()
    from app.models.user import user_companies
    db_session.execute(user_companies.insert().values(user_id=owner.id, company_id=company_id))
    db_session.commit()
    headers_owner = _login(client, "owner@acme.nl")

    response = client.get(
        "/api/v1/dashboard/business-owner", params={"company_id": company_id, "reference_date": "2027-06-15"}, headers=headers_owner
    )
    assert response.status_code == 200
    body = response.json()
    assert body["revenue"] == "1000.00"
    assert "forecast_summary" in body


def test_business_owner_dashboard_blocked_for_other_company(client, db_session):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a, _ = _setup_company_with_fy(client, headers_a)

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get("/api/v1/dashboard/business-owner", params={"company_id": company_a}, headers=headers_b)
    assert response.status_code == 404


def test_financial_question_endpoint_uses_fake_provider(client, db_session, fake_assistant_provider):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id)

    response = client.post(
        "/api/v1/assistant/financial-question",
        json={"company_id": company_id, "question": "How profitable was my business this quarter?",
              "period_type": "ANNUAL", "reference_date": "2027-06-01"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == fake_assistant_provider.answer
    assert body["facts"]["profit_and_loss_current_period"]["revenue"] == "1000.00"
    assert fake_assistant_provider.calls[-1][1] == "How profitable was my business this quarter?"


def test_financial_question_with_scenario_assumptions(client, db_session, fake_assistant_provider):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id)

    response = client.post(
        "/api/v1/assistant/financial-question",
        json={"company_id": company_id, "question": "What happens if revenue falls by 15%?",
              "period_type": "ANNUAL", "reference_date": "2027-06-01",
              "scenario_assumptions": {"revenue_change_pct": "-15"}},
        headers=headers,
    )
    assert response.status_code == 200
    assert "requested_scenario" in response.json()["facts"]
    assert response.json()["facts"]["requested_scenario"]["never_modifies_ledger"] is True
