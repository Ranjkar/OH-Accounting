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


def test_overview_warns_when_no_legal_form_set(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)

    response = client.get("/api/v1/tax-centre/overview", params={"company_id": company_id}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["current_legal_form"] is None
    assert body["legal_form_warning"] is not None
    assert "NOT_CONFIGURED" in body["sbr_digipoort_integration_status"]
    assert body["government_integration"]["status"] == "NOT_CONFIGURED"
    assert "ACCEPTED" in body["government_integration"]["possible_statuses"]
    assert body["payroll_tax"]["status"] == "NOT_FILED"


def test_overview_reflects_registered_legal_form(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    client.post("/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "EENMANSZAAK", "effective_from": "2025-01-01"}, headers=headers)

    response = client.get("/api/v1/tax-centre/overview", params={"company_id": company_id}, headers=headers)
    assert response.json()["current_legal_form"] == "EENMANSZAAK"
    assert response.json()["legal_form_warning"] is None


def test_overview_shows_real_loonheffingen_declaration_status(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    employee_id = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id, "employee_number": "E001", "full_name": "Jan Jansen",
            "employment_start_date": "2025-01-01", "employment_type": "PERMANENT",
            "salary_basis": "MONTHLY", "monthly_salary": "4000.00",
        },
        headers=headers,
    ).json()["id"]
    run_id = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 1},
        headers=headers,
    ).json()["id"]
    client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_id}, headers=headers)
    client.post(f"/api/v1/payroll-runs/{run_id}/approve", headers=headers)
    declaration_id = client.post(f"/api/v1/payroll-runs/{run_id}/loonheffingen-declaration", headers=headers).json()["id"]

    response = client.get("/api/v1/tax-centre/overview", params={"company_id": company_id}, headers=headers)
    assert response.status_code == 200
    payroll_tax_rows = response.json()["payroll_tax"]
    assert isinstance(payroll_tax_rows, list)
    assert payroll_tax_rows[0]["declaration_id"] == declaration_id
    assert payroll_tax_rows[0]["status"] == "DRAFT"


def test_income_tax_estimate_for_eenmanszaak(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    client.post("/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "EENMANSZAAK", "effective_from": "2025-01-01"}, headers=headers)

    response = client.get(
        "/api/v1/tax-centre/income-tax-estimate",
        params={"company_id": company_id, "annual_profit": "50000", "hours_criterion_met": "true"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["requires_accountant_confirmation"] is True


def test_income_tax_estimate_rejected_for_bv(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    client.post("/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "BV", "effective_from": "2025-01-01"}, headers=headers)

    response = client.get(
        "/api/v1/tax-centre/income-tax-estimate", params={"company_id": company_id, "annual_profit": "50000"}, headers=headers,
    )
    assert response.status_code == 400


def test_income_tax_estimate_splits_across_partners(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    client.post("/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "VOF", "effective_from": "2025-01-01"}, headers=headers)
    client.post("/api/v1/partners", json={"company_id": company_id, "name": "Alice", "profit_share_percentage": "60", "effective_from": "2025-01-01"}, headers=headers)
    client.post("/api/v1/partners", json={"company_id": company_id, "name": "Bob", "profit_share_percentage": "40", "effective_from": "2025-01-01"}, headers=headers)

    response = client.get(
        "/api/v1/tax-centre/income-tax-estimate", params={"company_id": company_id, "annual_profit": "100000"}, headers=headers,
    )
    assert response.status_code == 200
    per_partner = response.json()["per_partner"]
    assert len(per_partner) == 2
    assert {p["partner_name"] for p in per_partner} == {"Alice", "Bob"}


def test_dga_position_endpoint(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)

    response = client.get(
        "/api/v1/tax-centre/dga-position", params={"company_id": company_id, "proposed_dga_salary": "40000"}, headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["salary_check"]["compliant"] is False


def test_dga_position_auto_fills_highest_employee_salary(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id, "employee_number": "E001", "full_name": "Senior Engineer",
            "employment_start_date": "2025-01-01", "employment_type": "PERMANENT",
            "salary_basis": "MONTHLY", "monthly_salary": "6000.00",
        },
        headers=headers,
    )

    response = client.get(
        "/api/v1/tax-centre/dga-position", params={"company_id": company_id, "proposed_dga_salary": "40000"}, headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["highest_employee_salary_auto_filled"] is True
    # 6000/month annualized = 72,000, higher than the flat norm amount -- must become the required minimum.
    assert body["salary_check"]["required_minimum"] == "72000.00"
    assert "note_on_highest_employee_salary" in body["salary_check"]


def test_dga_position_explicit_highest_employee_salary_overrides_auto_fill(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id, "employee_number": "E001", "full_name": "Senior Engineer",
            "employment_start_date": "2025-01-01", "employment_type": "PERMANENT",
            "salary_basis": "MONTHLY", "monthly_salary": "6000.00",
        },
        headers=headers,
    )

    response = client.get(
        "/api/v1/tax-centre/dga-position",
        params={"company_id": company_id, "proposed_dga_salary": "80000", "highest_employee_salary": "65000"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["highest_employee_salary_auto_filled"] is False
    # Overridden to 65,000 -- must win over both the norm amount and the (ignored) auto-fill value of 72,000.
    assert body["salary_check"]["required_minimum"] == "65000"


def test_tax_optimization_wkr_uses_real_payroll_wage_data(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    employee_id = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id, "employee_number": "E001", "full_name": "Jan Jansen",
            "employment_start_date": "2025-01-01", "employment_type": "PERMANENT",
            "salary_basis": "MONTHLY", "monthly_salary": "4000.00",
        },
        headers=headers,
    ).json()["id"]
    run_id = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 1, "tax_year": 2025},
        headers=headers,
    ).json()["id"]
    client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_id}, headers=headers)

    response = client.get(
        "/api/v1/tax-centre/tax-optimization", params={"company_id": company_id, "tax_year": 2025}, headers=headers,
    )
    assert response.status_code == 200
    opportunities = response.json()
    wkr = next(o for o in opportunities if "Werkkostenregeling" in o["recommendation"])
    assert wkr["confidence"] == "computed_from_recorded_data"
    assert "EUR 4000.00" in wkr["notes"][0]


def test_tax_optimization_endpoint_returns_catalogue(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    client.post("/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "EENMANSZAAK", "effective_from": "2025-01-01"}, headers=headers)

    response = client.get(
        "/api/v1/tax-centre/tax-optimization",
        params={"company_id": company_id, "annual_profit": "50000", "annual_revenue": "60000"},
        headers=headers,
    )
    assert response.status_code == 200
    names = [o["recommendation"] for o in response.json()]
    assert any("Zelfstandigenaftrek" in n for n in names)
    assert any("KOR" in n for n in names)


def test_structure_comparison_endpoint(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)

    response = client.get(
        "/api/v1/tax-centre/structure-comparison",
        params={"company_id": company_id, "annual_revenue": "200000", "annual_operating_expenses": "50000"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert "eenmanszaak" in body
    assert "vof" in body
    assert "bv" in body
    assert body["lowest_total_tax_option"] in ("eenmanszaak", "vof", "bv")


def test_cross_tenant_cannot_access_tax_centre(client, db_session):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a = _setup_company(client, headers_a)

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get("/api/v1/tax-centre/overview", params={"company_id": company_a}, headers=headers_b)
    assert response.status_code == 404
