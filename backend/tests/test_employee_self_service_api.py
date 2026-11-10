"""Employee self-service portal tests. Phase 10 explicitly requires testing
direct API access, not just frontend visibility -- every "blocked" test
here calls the API directly with a logged-in employee-role token and
checks the response code, never relying on a UI to hide a button."""

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


def _create_employee(client, headers, company_id, employee_number="E001", full_name="Jan Jansen"):
    payload = {
        "company_id": company_id, "employee_number": employee_number, "full_name": full_name,
        "employment_start_date": "2025-01-01", "employment_type": "PERMANENT",
        "salary_basis": "MONTHLY", "monthly_salary": "4000.00",
    }
    return client.post("/api/v1/employees", json=payload, headers=headers).json()["id"]


def _invite_self_service(client, admin_headers, employee_id, email, password="selfservice123"):
    response = client.post(
        f"/api/v1/employees/{employee_id}/invite-self-service", json={"email": email, "password": password}, headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_full_self_service_lifecycle(client, db_session):
    _create_user(db_session)
    admin_headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, admin_headers)
    employee_id = _create_employee(client, admin_headers, company_id)
    _invite_self_service(client, admin_headers, employee_id, "jan@employee.nl")

    run_id = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 1, "tax_year": 2025},
        headers=admin_headers,
    ).json()["id"]
    payslip_id = client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_id}, headers=admin_headers).json()["id"]

    employee_headers = _login(client, "jan@employee.nl", "selfservice123")

    profile = client.get("/api/v1/me/profile", headers=employee_headers)
    assert profile.status_code == 200
    assert profile.json()["employee_number"] == "E001"
    assert "bsn" not in profile.json() and "bsn_masked" not in profile.json()

    payslips = client.get("/api/v1/me/payslips", headers=employee_headers)
    assert payslips.status_code == 200
    assert len(payslips.json()) == 1
    assert payslips.json()[0]["id"] == payslip_id

    pdf = client.get(f"/api/v1/me/payslips/{payslip_id}/pdf", headers=employee_headers)
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    statement = client.get("/api/v1/me/annual-statement?tax_year=2025", headers=employee_headers)
    assert statement.status_code == 200
    assert statement.json()["number_of_payslips"] == 1

    entry = client.post(
        "/api/v1/me/timesheet-entries",
        json={"employee_id": employee_id, "entry_date": "2025-01-10", "entry_type": "WORKED", "hours": "8.00"},
        headers=employee_headers,
    )
    assert entry.status_code == 201
    submitted = client.post(f"/api/v1/me/timesheet-entries/{entry.json()['id']}/submit", headers=employee_headers)
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "SUBMITTED"

    summary = client.get("/api/v1/me/hours-summary?year=2025", headers=employee_headers)
    assert summary.status_code == 200
    assert summary.json()["total_entries"] == 1


def test_employee_cannot_access_another_employees_payslip_via_direct_api_call(client, db_session):
    _create_user(db_session)
    admin_headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, admin_headers)

    employee_a_id = _create_employee(client, admin_headers, company_id, "E001", "Employee A")
    employee_b_id = _create_employee(client, admin_headers, company_id, "E002", "Employee B")
    _invite_self_service(client, admin_headers, employee_a_id, "a@employee.nl")
    _invite_self_service(client, admin_headers, employee_b_id, "b@employee.nl")

    run_id = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 1},
        headers=admin_headers,
    ).json()["id"]
    payslip_b_id = client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_b_id}, headers=admin_headers).json()["id"]

    headers_a = _login(client, "a@employee.nl", "selfservice123")

    # Direct API call for B's payslip while authenticated as A -- must be rejected, not merely hidden in a UI.
    response = client.get(f"/api/v1/me/payslips/{payslip_b_id}/pdf", headers=headers_a)
    assert response.status_code == 404

    json_response = client.get("/api/v1/me/payslips", headers=headers_a)
    assert json_response.status_code == 200
    assert all(p["id"] != payslip_b_id for p in json_response.json())

    # A cannot submit a timesheet entry claiming to be B.
    forged = client.post(
        "/api/v1/me/timesheet-entries",
        json={"employee_id": employee_b_id, "entry_date": "2025-01-10", "entry_type": "WORKED", "hours": "8.00"},
        headers=headers_a,
    )
    assert forged.status_code == 403


def test_employee_role_cannot_reach_company_wide_endpoints(client, db_session):
    """An employee-role user is never added to user_companies -- every
    company-scoped endpoint (not just employee self-service) must reject it."""
    _create_user(db_session)
    admin_headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, admin_headers)
    employee_id = _create_employee(client, admin_headers, company_id)
    _invite_self_service(client, admin_headers, employee_id, "jan@employee.nl")
    employee_headers = _login(client, "jan@employee.nl", "selfservice123")

    assert client.get(f"/api/v1/employees?company_id={company_id}", headers=employee_headers).status_code == 403
    assert client.get(f"/api/v1/employees/{employee_id}", headers=employee_headers).status_code == 403
    assert client.get(f"/api/v1/companies/{company_id}/financial-years", headers=employee_headers).status_code == 403


def test_unlinked_user_gets_403_from_self_service(client, db_session):
    admin = _create_user(db_session)
    from app.models.enums import UserRole as Role
    unlinked = User(tenant_id=admin.tenant_id, email="nobody@employee.nl", hashed_password=hash_password("secret123"), full_name="Nobody", role=Role.employee)
    db_session.add(unlinked)
    db_session.commit()
    headers = _login(client, "nobody@employee.nl")

    response = client.get("/api/v1/me/profile", headers=headers)
    assert response.status_code == 403


def test_cannot_double_invite_same_employee(client, db_session):
    _create_user(db_session)
    admin_headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, admin_headers)
    employee_id = _create_employee(client, admin_headers, company_id)
    _invite_self_service(client, admin_headers, employee_id, "jan@employee.nl")

    second = client.post(
        f"/api/v1/employees/{employee_id}/invite-self-service", json={"email": "jan2@employee.nl", "password": "x"}, headers=admin_headers,
    )
    assert second.status_code == 409


def test_viewer_cannot_invite_self_service(client, db_session):
    admin = _create_user(db_session)
    admin_headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, admin_headers)
    employee_id = _create_employee(client, admin_headers, company_id)

    viewer = User(tenant_id=admin.tenant_id, email="viewer@acme.nl", hashed_password=hash_password("secret123"), full_name="Viewer", role=UserRole.viewer)
    db_session.add(viewer)
    db_session.commit()
    from app.models.user import user_companies
    db_session.execute(user_companies.insert().values(user_id=viewer.id, company_id=company_id))
    db_session.commit()
    headers_viewer = _login(client, "viewer@acme.nl")

    response = client.post(
        f"/api/v1/employees/{employee_id}/invite-self-service", json={"email": "x@employee.nl", "password": "x"}, headers=headers_viewer,
    )
    assert response.status_code == 403
