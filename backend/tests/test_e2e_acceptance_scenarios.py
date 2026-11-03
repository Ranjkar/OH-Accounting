"""Phase 10 acceptance scenarios A-C, E, F -- each test chains together a
realistic multi-step workflow across several subsystems (legal form, tax
engine, payroll, loonheffingen, financial reports), rather than testing
one endpoint in isolation. Scenario D (employee self-service, including
direct-API cross-employee access attempts) is covered in full in
test_employee_self_service_api.py; scenario G (bulk invoice upload,
approval, and ledger posting) is covered in full in test_batch_upload.py
-- neither is duplicated here."""

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


def _setup_company(client, headers, name="Test B.V."):
    return client.post("/api/v1/companies", json={"name": name}, headers=headers).json()["id"]


def test_scenario_a_eenmanszaak_legal_form_through_tax_optimization(client, db_session):
    """A: sole proprietor -- set legal form, confirm the urencriterium
    explicitly (never assumed), get an income tax estimate, and see the
    zelfstandigenaftrek opportunity reflect that confirmed status."""
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)

    legal_form = client.post(
        "/api/v1/company-legal-forms",
        json={"company_id": company_id, "legal_form_code": "EENMANSZAAK", "effective_from": "2025-01-01"},
        headers=headers,
    )
    assert legal_form.status_code == 201, legal_form.text

    overview = client.get("/api/v1/tax-centre/overview", params={"company_id": company_id}, headers=headers)
    assert overview.json()["current_legal_form"] == "EENMANSZAAK"

    estimate = client.get(
        "/api/v1/tax-centre/income-tax-estimate",
        params={"company_id": company_id, "annual_profit": "60000", "hours_criterion_met": True},
        headers=headers,
    )
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["hours_criterion_met"] is True
    assert estimate.json()["entrepreneur_deduction_applied"] != "0"

    opportunities = client.get(
        "/api/v1/tax-centre/tax-optimization",
        params={"company_id": company_id, "annual_profit": "60000", "annual_revenue": "70000", "hours_criterion_met": True},
        headers=headers,
    )
    zza = next(o for o in opportunities.json() if "Zelfstandigenaftrek" in o["recommendation"])
    assert zza["confidence"] == "computed_from_recorded_data"


def test_scenario_b_vof_partners_never_assumed_equally_eligible(client, db_session):
    """B: VOF with two partners who have DIFFERENT entrepreneur-hours
    eligibility -- the brief is explicit that this must never be assumed
    uniform, and the per-partner estimate must reflect each partner's own
    confirmed status."""
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    client.post(
        "/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "VOF", "effective_from": "2025-01-01"}, headers=headers,
    )

    client.post(
        "/api/v1/partners",
        json={"company_id": company_id, "name": "Alice", "profit_share_percentage": "60", "entrepreneur_hours_eligible": True, "effective_from": "2025-01-01"},
        headers=headers,
    )
    client.post(
        "/api/v1/partners",
        json={"company_id": company_id, "name": "Bob", "profit_share_percentage": "40", "entrepreneur_hours_eligible": False, "effective_from": "2025-01-01"},
        headers=headers,
    )

    estimate = client.get(
        "/api/v1/tax-centre/income-tax-estimate", params={"company_id": company_id, "annual_profit": "100000"}, headers=headers,
    )
    assert estimate.status_code == 200, estimate.text
    per_partner = {row["partner_name"]: row for row in estimate.json()["per_partner"]}
    assert per_partner["Alice"]["hours_criterion_met"] is True
    assert per_partner["Alice"]["entrepreneur_deduction_applied"] != "0"
    assert per_partner["Bob"]["hours_criterion_met"] is False
    assert per_partner["Bob"]["entrepreneur_deduction_applied"] == "0.00" or per_partner["Bob"]["entrepreneur_deduction_applied"] == "0"
    assert per_partner["Alice"]["allocated_profit"] == "60000.00"
    assert per_partner["Bob"]["allocated_profit"] == "40000.00"


def test_scenario_c_bv_dga_payroll_through_loonheffingen_and_annual_statement(client, db_session):
    """C: BV with a DGA on payroll -- gebruikelijk-loon check, a full
    payroll run, the loonheffingen declaration lifecycle through to
    ACCEPTED, and the resulting annual statement, all chained together."""
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    client.post(
        "/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "BV", "effective_from": "2025-01-01"}, headers=headers,
    )

    dga_id = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id, "employee_number": "DGA1", "full_name": "Directeur Grootaandeelhouder",
            "employment_start_date": "2025-01-01", "employment_type": "PERMANENT",
            "salary_basis": "MONTHLY", "monthly_salary": "5000.00", "is_dga": True,
        },
        headers=headers,
    ).json()["id"]

    dga_position = client.get(
        "/api/v1/tax-centre/dga-position", params={"company_id": company_id, "proposed_dga_salary": "60000"}, headers=headers,
    )
    assert dga_position.status_code == 200
    assert dga_position.json()["salary_check"]["requires_accountant_confirmation"] is True

    run_id = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 1},
        headers=headers,
    ).json()["id"]
    client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": dga_id}, headers=headers)
    client.post(f"/api/v1/payroll-runs/{run_id}/approve", headers=headers)

    declaration_id = client.post(f"/api/v1/payroll-runs/{run_id}/loonheffingen-declaration", headers=headers).json()["id"]
    validated = client.post(f"/api/v1/loonheffingen-declarations/{declaration_id}/validate", headers=headers)
    assert validated.json()["status"] == "ACCOUNTANT_REVIEW"
    client.post(f"/api/v1/loonheffingen-declarations/{declaration_id}/approve", headers=headers)
    client.post(f"/api/v1/loonheffingen-declarations/{declaration_id}/mark-ready-for-submission", headers=headers)
    client.post(
        f"/api/v1/loonheffingen-declarations/{declaration_id}/record-submission",
        json={"submission_reference": "SBR-E2E-1"}, headers=headers,
    )
    accepted = client.post(
        f"/api/v1/loonheffingen-declarations/{declaration_id}/record-government-response",
        json={"accepted": True, "response_reference": "BD-E2E-1"}, headers=headers,
    )
    assert accepted.json()["status"] == "ACCEPTED"

    statement = client.get(f"/api/v1/employees/{dga_id}/annual-statement?tax_year=2025", headers=headers)
    assert statement.status_code == 200
    assert statement.json()["number_of_payslips"] == 1
    assert statement.json()["gross_salary"] == "5000.00"


def test_scenario_e_tax_optimization_mixes_computed_and_requires_data(client, db_session):
    """E: an eenmanszaak with real payroll (so WKR is computed from actual
    data) alongside facilities that genuinely have no underlying data
    (KIA) -- the catalogue must show both kinds honestly in one response,
    never inventing a savings figure for the latter."""
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    client.post(
        "/api/v1/company-legal-forms", json={"company_id": company_id, "legal_form_code": "EENMANSZAAK", "effective_from": "2025-01-01"}, headers=headers,
    )
    employee_id = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id, "employee_number": "E001", "full_name": "Staff Member",
            "employment_start_date": "2025-01-01", "employment_type": "PERMANENT",
            "salary_basis": "MONTHLY", "monthly_salary": "3000.00",
        },
        headers=headers,
    ).json()["id"]
    run_id = client.post(
        "/api/v1/payroll-runs", json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 1, "tax_year": 2025},
        headers=headers,
    ).json()["id"]
    client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_id}, headers=headers)

    opportunities = client.get(
        "/api/v1/tax-centre/tax-optimization",
        params={"company_id": company_id, "annual_profit": "50000", "annual_revenue": "60000", "hours_criterion_met": True, "tax_year": 2025},
        headers=headers,
    ).json()
    by_name = {o["recommendation"]: o for o in opportunities}
    wkr = next(v for k, v in by_name.items() if "Werkkostenregeling" in k)
    kia = next(v for k, v in by_name.items() if "KIA" in k)
    assert wkr["confidence"] == "computed_from_recorded_data"
    assert kia["confidence"] == "requires_data_not_tracked"
    assert kia["potential_savings"] is None


def test_scenario_f_financial_intelligence_manual_entries_through_reports_and_kpis(client, db_session):
    """F: manual ledger entries flowing through to P&L, balance sheet, and
    the KPI engine -- all reusing the existing Phase 8 financial reporting
    engine, not a separate calculation."""
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _setup_company(client, headers)
    fy_id = client.post("/api/v1/companies/{}/financial-years".format(company_id), json={"year": 2026}, headers=headers).json()["id"]

    sale = client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id, "financial_year_id": fy_id, "ledger_side": "SALES", "invoice_date": "2026-02-01",
            "line_items": [{"net_amount": "1000.00", "vat_rate": "21", "vat_amount": "210.00", "vat_treatment": "DOMESTIC_STANDARD"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    pnl = client.get(
        "/api/v1/financial-reports/profit-and-loss",
        params={"company_id": company_id, "period_type": "ANNUAL", "reference_date": "2026-06-01"},
        headers=headers,
    )
    assert pnl.status_code == 200, pnl.text
    assert pnl.json()["current"]["revenue"] == "1000.00"

    balance_sheet = client.get(
        "/api/v1/financial-reports/balance-sheet", params={"company_id": company_id, "as_of_date": "2026-06-01"}, headers=headers,
    )
    assert balance_sheet.status_code == 200, balance_sheet.text

    kpis = client.get(
        "/api/v1/financial-reports/kpis",
        params={"company_id": company_id, "period_type": "ANNUAL", "reference_date": "2026-06-01"},
        headers=headers,
    )
    assert kpis.status_code == 200, kpis.text
