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


def test_profit_and_loss_report_all_formats(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id)

    for fmt, content_type in [("pdf", "application/pdf"), ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"), ("csv", "text/csv")]:
        response = client.get(
            "/api/v1/reports/profit-and-loss",
            params={"company_id": company_id, "period_type": "ANNUAL", "reference_date": "2027-06-01", "format": fmt},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith(content_type)
        assert len(response.content) > 0


def test_balance_sheet_report_pdf(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.get(
        "/api/v1/reports/balance-sheet", params={"company_id": company_id, "as_of_date": "2027-06-01", "format": "pdf"}, headers=headers
    )
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


def test_budget_vs_actual_report_csv(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id, net=Decimal("1200"), invoice_date=date(2027, 2, 1))

    budget = client.post(
        "/api/v1/budgets",
        json={"company_id": company_id, "financial_year_id": fy["id"], "name": "2027 Budget",
              "lines": [{"category": "Revenue", "month": 2, "amount": "1000"}]},
        headers=headers,
    ).json()

    response = client.get(f"/api/v1/reports/budget-vs-actual/{budget['id']}", params={"format": "csv"}, headers=headers)
    assert response.status_code == 200
    assert b"1200" in response.content


def test_scenario_comparison_report_csv(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_sale(db_session, company_id, fy["id"], admin.tenant_id, admin.id, invoice_date=date(2027, 6, 1))

    s1 = client.post(
        "/api/v1/scenarios",
        json={"company_id": company_id, "name": "Optimistic", "scenario_type": "OPTIMISTIC", "assumptions": {"revenue_change_pct": "10"}, "horizon_months": 1, "base_date": "2027-07-01"},
        headers=headers,
    ).json()
    s2 = client.post(
        "/api/v1/scenarios",
        json={"company_id": company_id, "name": "Conservative", "scenario_type": "CONSERVATIVE", "assumptions": {"revenue_change_pct": "-15"}, "horizon_months": 1, "base_date": "2027-07-01"},
        headers=headers,
    ).json()

    response = client.get(
        "/api/v1/reports/scenario-comparison",
        params={"company_id": company_id, "scenario_ids": f"{s1['id']},{s2['id']}", "format": "csv"},
        headers=headers,
    )
    assert response.status_code == 200
    assert b"Optimistic" in response.content
    assert b"Conservative" in response.content


def test_report_export_blocked_cross_tenant(client, db_session):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a, _ = _setup_company_with_fy(client, headers_a)

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get("/api/v1/reports/balance-sheet", params={"company_id": company_a, "format": "pdf"}, headers=headers_b)
    assert response.status_code == 404
