from app.core.security import hash_password
from app.models.company import Company
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User


def _create_admin(db_session) -> User:
    tenant = Tenant(name="Acme Accounting")
    db_session.add(tenant)
    db_session.flush()
    admin = User(
        tenant_id=tenant.id,
        email="admin@acme.nl",
        hashed_password=hash_password("secret123"),
        full_name="Admin",
        role=UserRole.admin,
    )
    db_session.add(admin)
    db_session.commit()
    return admin


def _login(client, email="admin@acme.nl", password="secret123") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login_rejects_wrong_password(client, db_session):
    _create_admin(db_session)
    response = client.post(
        "/api/v1/auth/login", json={"email": "admin@acme.nl", "password": "wrong"}
    )
    assert response.status_code == 401


def test_create_company_and_financial_year_generates_quarterly_vat_periods(client, db_session):
    _create_admin(db_session)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/api/v1/companies",
        json={"name": "Test B.V.", "vat_frequency": "quarterly"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    company_id = create_resp.json()["id"]

    fy_resp = client.post(
        f"/api/v1/companies/{company_id}/financial-years",
        json={"year": 2026},
        headers=headers,
    )
    assert fy_resp.status_code == 201
    periods = fy_resp.json()["vat_periods"]
    assert [p["label"] for p in periods] == ["Q1", "Q2", "Q3", "Q4"]

    duplicate_resp = client.post(
        f"/api/v1/companies/{company_id}/financial-years",
        json={"year": 2026},
        headers=headers,
    )
    assert duplicate_resp.status_code == 409


def test_dashboard_reflects_open_vat_periods(client, db_session):
    _create_admin(db_session)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    company_id = client.post(
        "/api/v1/companies", json={"name": "Test B.V."}, headers=headers
    ).json()["id"]
    client.post(
        f"/api/v1/companies/{company_id}/financial-years",
        json={"year": 2026},
        headers=headers,
    )

    dashboard = client.get("/api/v1/dashboard", headers=headers).json()
    assert dashboard["company_count"] == 1
    assert dashboard["open_vat_periods"] == 4


def test_non_admin_cannot_create_company(client, db_session):
    tenant = Tenant(name="Acme Accounting")
    db_session.add(tenant)
    db_session.flush()
    viewer = User(
        tenant_id=tenant.id,
        email="viewer@acme.nl",
        hashed_password=hash_password("secret123"),
        full_name="Viewer",
        role=UserRole.viewer,
    )
    db_session.add(viewer)
    db_session.commit()

    token = _login(client, email="viewer@acme.nl")
    response = client.post(
        "/api/v1/companies",
        json={"name": "Nope B.V."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_viewer_cannot_create_financial_year(client, db_session):
    admin = _create_admin(db_session)
    admin_token = _login(client)
    company_id = client.post(
        "/api/v1/companies",
        json={"name": "Test B.V."},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()["id"]

    viewer = User(
        tenant_id=admin.tenant_id,
        email="viewer@acme.nl",
        hashed_password=hash_password("secret123"),
        full_name="Viewer",
        role=UserRole.viewer,
    )
    db_session.add(viewer)
    db_session.flush()
    company = db_session.get(Company, company_id)
    viewer.companies.append(company)
    db_session.commit()

    viewer_token = _login(client, email="viewer@acme.nl")
    response = client.post(
        f"/api/v1/companies/{company_id}/financial-years",
        json={"year": 2026},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert response.status_code == 403
