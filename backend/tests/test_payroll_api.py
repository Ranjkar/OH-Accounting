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


def _create_employee(client, headers, company_id):
    payload = {
        "company_id": company_id, "employee_number": "E001", "full_name": "Jan Jansen",
        "employment_start_date": "2025-01-01", "employment_type": "PERMANENT",
        "salary_basis": "MONTHLY", "monthly_salary": "4000.00",
    }
    return client.post("/api/v1/employees", json=payload, headers=headers).json()["id"]


def test_full_payroll_run_lifecycle(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    employee_id = _create_employee(client, headers, company_id)

    run = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 3},
        headers=headers,
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    assert run.json()["status"] == "DRAFT"

    payslip = client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_id}, headers=headers)
    assert payslip.status_code == 201, payslip.text
    assert payslip.json()["gross_salary"] == "4000.00"
    payslip_id = payslip.json()["id"]

    approve = client.post(f"/api/v1/payroll-runs/{run_id}/approve", headers=headers)
    assert approve.json()["status"] == "APPROVED"

    paid = client.post(f"/api/v1/payroll-runs/{run_id}/mark-paid", headers=headers)
    assert paid.json()["status"] == "PAID"

    pdf = client.get(f"/api/v1/payslips/{payslip_id}/pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


def test_cannot_approve_run_with_no_payslips_via_api(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)

    run = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 3},
        headers=headers,
    ).json()
    response = client.post(f"/api/v1/payroll-runs/{run['id']}/approve", headers=headers)
    assert response.status_code == 409


def test_correct_payslip_via_api_preserves_original(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    employee_id = _create_employee(client, headers, company_id)

    run_id = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 3},
        headers=headers,
    ).json()["id"]
    payslip = client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_id}, headers=headers).json()

    correction = client.post(
        f"/api/v1/payslips/{payslip['id']}/correct", json={"reason": "Forgot bonus", "bonus_amount": "500"}, headers=headers,
    )
    assert correction.status_code == 201, correction.text
    assert correction.json()["corrects_payslip_id"] == payslip["id"]
    assert correction.json()["gross_salary"] == "4500.00"

    original = client.get(f"/api/v1/payroll-runs/{run_id}/payslips", headers=headers).json()
    voided = next(p for p in original if p["id"] == payslip["id"])
    assert voided["voided"] is True
    assert voided["gross_salary"] == "4000.00"


def test_viewer_cannot_create_payroll_run(client, db_session):
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
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 3},
        headers=headers_viewer,
    )
    assert response.status_code == 403


def test_annual_statement_api_json_and_pdf(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    employee_id = _create_employee(client, headers, company_id)

    run_id = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 1, "tax_year": 2025},
        headers=headers,
    ).json()["id"]
    client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_id}, headers=headers)

    statement = client.get(f"/api/v1/employees/{employee_id}/annual-statement?tax_year=2025", headers=headers)
    assert statement.status_code == 200, statement.text
    body = statement.json()
    assert body["number_of_payslips"] == 1
    assert body["gross_salary"] == "4000.00"
    assert body["requires_accountant_confirmation"] is True

    pdf = client.get(f"/api/v1/employees/{employee_id}/annual-statement/pdf?tax_year=2025", headers=headers)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"
