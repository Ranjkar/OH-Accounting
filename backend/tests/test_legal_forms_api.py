from app.core.security import hash_password
from app.models.enums import UserRole
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


def _setup_company(client, headers):
    return client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]


def test_list_legal_form_definitions(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    response = client.get("/api/v1/legal-form-definitions", headers=headers)
    assert response.status_code == 200
    codes = {row["code"] for row in response.json()}
    assert "EENMANSZAAK" in codes
    assert "BV" in codes
    assert "STICHTING" in codes
    bv = next(row for row in response.json() if row["code"] == "BV")
    assert bv["subject_to_corporate_income_tax"] is True
    assert bv["subject_to_income_tax"] is False


def test_set_and_get_current_company_legal_form(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)

    response = client.post(
        "/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "EENMANSZAAK", "effective_from": "2025-01-01"},
        headers=headers,
    )
    assert response.status_code == 201, response.text

    current = client.get("/api/v1/company-legal-forms/current", params={"company_id": company_id}, headers=headers)
    assert current.status_code == 200
    assert current.json()["legal_form_code"] == "EENMANSZAAK"


def test_changing_legal_form_closes_previous_row(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)

    client.post("/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "EENMANSZAAK", "effective_from": "2025-01-01"}, headers=headers)
    client.post("/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "BV", "effective_from": "2026-01-01"}, headers=headers)

    history = client.get("/api/v1/company-legal-forms", params={"company_id": company_id}, headers=headers).json()
    assert len(history) == 2
    eenmanszaak_row = next(r for r in history if r["legal_form_code"] == "EENMANSZAAK")
    assert eenmanszaak_row["effective_to"] == "2026-01-01"

    as_of_2025 = client.get("/api/v1/company-legal-forms/current", params={"company_id": company_id, "as_of_date": "2025-06-01"}, headers=headers)
    assert as_of_2025.json()["legal_form_code"] == "EENMANSZAAK"
    as_of_2026 = client.get("/api/v1/company-legal-forms/current", params={"company_id": company_id, "as_of_date": "2026-06-01"}, headers=headers)
    assert as_of_2026.json()["legal_form_code"] == "BV"


def test_create_partners_with_unequal_shares_and_hours_eligibility(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)

    alice = client.post(
        "/api/v1/partners", json={"company_id": company_id, "name": "Alice", "profit_share_percentage": "60", "effective_from": "2025-01-01"},
        headers=headers,
    ).json()
    client.post(
        "/api/v1/partners", json={"company_id": company_id, "name": "Bob", "profit_share_percentage": "40", "effective_from": "2025-01-01"},
        headers=headers,
    )

    partners = client.get("/api/v1/partners", params={"company_id": company_id}, headers=headers).json()
    assert len(partners) == 2
    assert all(p["entrepreneur_hours_eligible"] is False for p in partners)

    updated = client.patch(f"/api/v1/partners/{alice['id']}/entrepreneur-hours-eligibility", params={"eligible": "true"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["entrepreneur_hours_eligible"] is True


def test_viewer_cannot_create_legal_form_or_partner(client, db_session):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers_admin)

    viewer = User(tenant_id=admin.tenant_id, email="viewer@acme.nl", hashed_password=hash_password("secret123"), full_name="Viewer", role=UserRole.viewer)
    db_session.add(viewer)
    db_session.commit()
    from app.models.user import user_companies
    db_session.execute(user_companies.insert().values(user_id=viewer.id, company_id=company_id))
    db_session.commit()
    headers_viewer = _login(client, "viewer@acme.nl")

    response = client.post(
        "/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "BV", "effective_from": "2025-01-01"},
        headers=headers_viewer,
    )
    assert response.status_code == 403


def test_cross_tenant_cannot_access_legal_form(client, db_session):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a = _setup_company(client, headers_a)
    client.post("/api/v1/company-legal-forms", json={"company_id": company_a, "legal_form_code": "EENMANSZAAK", "effective_from": "2025-01-01"}, headers=headers_a)

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get("/api/v1/company-legal-forms/current", params={"company_id": company_a}, headers=headers_b)
    assert response.status_code == 404
