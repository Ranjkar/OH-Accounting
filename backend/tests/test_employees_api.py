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


def _create_employee(client, headers, company_id, **overrides):
    payload = {
        "company_id": company_id, "employee_number": "E001", "full_name": "Jan Jansen",
        "bsn": "123456789", "employment_start_date": "2025-01-01", "employment_type": "PERMANENT",
        "salary_basis": "MONTHLY", "monthly_salary": "4000.00",
    }
    payload.update(overrides)
    return client.post("/api/v1/employees", json=payload, headers=headers)


def test_create_employee_never_exposes_plaintext_bsn(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)

    response = _create_employee(client, headers, company_id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert "bsn" not in body
    assert body["bsn_masked"] == "******789"

    from app.models.employee import Employee

    row = db_session.query(Employee).filter(Employee.id == body["id"]).first()
    assert row.bsn_encrypted is not None
    assert b"123456789" not in row.bsn_encrypted


def test_list_employees_shows_masked_bsn(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    _create_employee(client, headers, company_id)

    response = client.get("/api/v1/employees", params={"company_id": company_id}, headers=headers)
    assert response.status_code == 200
    assert response.json()[0]["bsn_masked"] == "******789"


def test_timesheet_submit_approve_via_api(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    employee_id = _create_employee(client, headers, company_id).json()["id"]

    entry = client.post(
        "/api/v1/timesheet-entries", json={"employee_id": employee_id, "entry_date": "2025-03-01", "entry_type": "WORKED", "hours": "8"},
        headers=headers,
    ).json()

    submit = client.post(f"/api/v1/timesheet-entries/{entry['id']}/submit", headers=headers)
    assert submit.json()["status"] == "SUBMITTED"
    approve = client.post(f"/api/v1/timesheet-entries/{entry['id']}/approve", headers=headers)
    assert approve.json()["status"] == "APPROVED"


def test_entrepreneur_hours_and_urencriterium_dashboard(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)

    for month in range(1, 4):
        client.post(
            "/api/v1/entrepreneur-hours-entries",
            json={"company_id": company_id, "entry_date": f"2025-0{month}-01", "activity_category": "business_activity", "duration_hours": "100"},
            headers=headers,
        )

    dashboard = client.get("/api/v1/companies/" + str(company_id) + "/urencriterium-dashboard", params={"year": 2025}, headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["total_recorded_hours"] == "300.00"
    assert dashboard.json()["threshold_met_by_recorded_hours_alone"] is False


def test_viewer_cannot_create_employee(client, db_session):
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

    response = _create_employee(client, headers_viewer, company_id)
    assert response.status_code == 403


def test_cross_tenant_cannot_access_employee(client, db_session):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a = _setup_company(client, headers_a)
    employee_id = _create_employee(client, headers_a, company_a).json()["id"]

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get(f"/api/v1/employees/{employee_id}", headers=headers_b)
    assert response.status_code == 404
