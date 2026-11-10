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


def test_loonheffingen_declaration_full_lifecycle_via_api(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    employee_id = _create_employee(client, headers, company_id)

    run_id = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 1},
        headers=headers,
    ).json()["id"]
    client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_id}, headers=headers)
    client.post(f"/api/v1/payroll-runs/{run_id}/approve", headers=headers)

    create = client.post(f"/api/v1/payroll-runs/{run_id}/loonheffingen-declaration", headers=headers)
    assert create.status_code == 201, create.text
    declaration_id = create.json()["id"]
    assert create.json()["status"] == "DRAFT"

    validated = client.post(f"/api/v1/loonheffingen-declarations/{declaration_id}/validate", headers=headers)
    assert validated.status_code == 200, validated.text
    assert validated.json()["status"] == "ACCOUNTANT_REVIEW"

    approved = client.post(f"/api/v1/loonheffingen-declarations/{declaration_id}/approve", headers=headers)
    assert approved.json()["status"] == "APPROVED"

    ready = client.post(f"/api/v1/loonheffingen-declarations/{declaration_id}/mark-ready-for-submission", headers=headers)
    assert ready.json()["status"] == "READY_FOR_SUBMISSION"

    # Cannot jump straight to accepted without a submission.
    bad_response = client.post(
        f"/api/v1/loonheffingen-declarations/{declaration_id}/record-government-response",
        json={"accepted": True, "response_reference": "X"}, headers=headers,
    )
    assert bad_response.status_code == 409

    submitted = client.post(
        f"/api/v1/loonheffingen-declarations/{declaration_id}/record-submission",
        json={"submission_reference": "SBR-KENMERK-123"}, headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    assert submitted.json()["submission_reference"] == "SBR-KENMERK-123"

    accepted = client.post(
        f"/api/v1/loonheffingen-declarations/{declaration_id}/record-government-response",
        json={"accepted": True, "response_reference": "BD-ACK-456"}, headers=headers,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACCEPTED"

    fetched = client.get(f"/api/v1/loonheffingen-declarations/{declaration_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "ACCEPTED"


def test_viewer_cannot_approve_declaration(client, db_session):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers_admin)
    employee_id = _create_employee(client, headers_admin, company_id)

    run_id = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 1},
        headers=headers_admin,
    ).json()["id"]
    client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_id}, headers=headers_admin)
    client.post(f"/api/v1/payroll-runs/{run_id}/approve", headers=headers_admin)
    declaration_id = client.post(f"/api/v1/payroll-runs/{run_id}/loonheffingen-declaration", headers=headers_admin).json()["id"]

    viewer = User(tenant_id=admin.tenant_id, email="viewer@acme.nl", hashed_password=hash_password("secret123"), full_name="Viewer", role=UserRole.viewer)
    db_session.add(viewer)
    db_session.commit()
    from app.models.user import user_companies
    db_session.execute(user_companies.insert().values(user_id=viewer.id, company_id=company_id))
    db_session.commit()
    headers_viewer = _login(client, "viewer@acme.nl")

    response = client.post(f"/api/v1/loonheffingen-declarations/{declaration_id}/validate", headers=headers_viewer)
    assert response.status_code == 403
