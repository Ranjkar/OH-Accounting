from datetime import date, timedelta

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
    user = User(
        tenant_id=tenant.id,
        email=email,
        hashed_password=hash_password("secret123"),
        full_name="Test User",
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, email, password="secret123") -> dict:
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _setup_company_with_fy(client, headers, year=2026):
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": year}, headers=headers).json()
    return company_id, fy


def _post_sales_transaction(client, headers, company_id, fy, net="1000.00", vat="210.00", invoice_date="2026-02-01"):
    return client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id,
            "financial_year_id": fy["id"],
            "ledger_side": "SALES",
            "invoice_date": invoice_date,
            "line_items": [{"net_amount": net, "vat_rate": "21", "vat_amount": vat, "vat_treatment": "DOMESTIC_STANDARD"}],
        },
        headers=headers,
    ).json()


# ---- Notes ----


def test_create_list_and_resolve_note(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    created = client.post(
        f"/api/v1/companies/{company_id}/notes",
        json={"note_type": "CUSTOMER_QUESTION", "body": "Please send the January bank statement."},
        headers=headers,
    )
    assert created.status_code == 201
    note = created.json()
    assert note["status"] == "OPEN"

    listed = client.get(f"/api/v1/companies/{company_id}/notes", headers=headers).json()
    assert len(listed) == 1

    resolved = client.patch(f"/api/v1/notes/{note['id']}/status", json={"status": "RESOLVED"}, headers=headers)
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolved_at"] is not None


def test_notes_are_tenant_isolated(client, db_session):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a, _ = _setup_company_with_fy(client, headers_a)
    note = client.post(
        f"/api/v1/companies/{company_a}/notes", json={"note_type": "INTERNAL", "body": "secret"}, headers=headers_a
    ).json()

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.patch(f"/api/v1/notes/{note['id']}/status", json={"status": "RESOLVED"}, headers=headers_b)
    assert response.status_code == 404


def test_viewer_cannot_create_notes(client, db_session):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id, _ = _setup_company_with_fy(client, headers_admin)

    viewer = User(
        tenant_id=admin.tenant_id, email="viewer@acme.nl", hashed_password=hash_password("secret123"),
        full_name="Viewer", role=UserRole.viewer,
    )
    db_session.add(viewer)
    db_session.commit()
    headers_viewer = _login(client, "viewer@acme.nl")

    response = client.post(
        f"/api/v1/companies/{company_id}/notes", json={"note_type": "INTERNAL", "body": "x"}, headers=headers_viewer
    )
    assert response.status_code == 403


# ---- Workspace / completeness ----


def test_workspace_reports_incomplete_without_evidence(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    workspace = client.get(f"/api/v1/companies/{company_id}/workspace", headers=headers).json()
    assert workspace["sales_invoice_count"] == 0
    period = workspace["period_completeness"][0]
    sales_row = next(r for r in period["rows"] if r["requirement"] == "Sales invoices")
    assert sales_row["complete"] is False  # no evidence -> not silently marked complete


def test_workspace_marks_sales_complete_once_posted(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _post_sales_transaction(client, headers, company_id, fy)

    workspace = client.get(f"/api/v1/companies/{company_id}/workspace", headers=headers).json()
    assert workspace["sales_invoice_count"] == 0  # MANUAL_ENTRY, not SALES_INVOICE transaction_type
    period = next(p for p in workspace["period_completeness"] if p["label"] == "2026 Q1")
    sales_row = next(r for r in period["rows"] if r["requirement"] == "Sales invoices")
    assert sales_row["complete"] is True  # completeness counts any sales-side transaction


# ---- Tax calendar ----


def test_tax_calendar_marks_overdue_period(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers, year=2020)  # safely in the past

    entries = client.get("/api/v1/tax-calendar", params={"company_id": company_id}, headers=headers).json()
    q1 = next(e for e in entries if e["period_label"] == "Q1")
    assert q1["calendar_status"] == "overdue"


def test_tax_calendar_marks_future_period_upcoming(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers, year=date.today().year + 5)

    entries = client.get("/api/v1/tax-calendar", params={"company_id": company_id}, headers=headers).json()
    q1 = next(e for e in entries if e["period_label"] == "Q1")
    assert q1["calendar_status"] == "upcoming"


# ---- Dashboard ----


def test_dashboard_counts_documents_awaiting_approval(client, db_session, fake_ai_provider):
    import fitz

    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    doc = fitz.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"]},
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )

    dashboard = client.get("/api/v1/dashboard", params={"company_id": company_id}, headers=headers).json()
    assert dashboard["documents_awaiting_approval"] >= 1
    assert dashboard["company_count"] == 1
    assert "generated_at" in dashboard


def test_dashboard_flags_company_with_overdue_vat_return(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers, year=2020)

    dashboard = client.get("/api/v1/dashboard", params={"company_id": company_id}, headers=headers).json()
    assert dashboard["overdue_vat_returns"] >= 1
    flagged = [c for c in dashboard["companies_requiring_attention"] if c["company_id"] == company_id]
    assert flagged
    # Reason text is locale-dependent (see app/core/messages_i18n.py) --
    # the overdue count itself, never translated, is the stable thing
    # to assert on here.
    assert any(str(dashboard["overdue_vat_returns"]) in r for r in flagged[0]["reasons"])


# ---- Assistant ----


def test_assistant_company_summary_uses_real_facts_not_ai_numbers(client, db_session, fake_assistant_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _post_sales_transaction(client, headers, company_id, fy)

    response = client.get("/api/v1/assistant/company-summary", params={"company_id": company_id}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["facts"]["total_sales_transactions"] == 1
    assert body["facts"]["total_sales_net"] == "1000.00"
    assert body["answer"] == "This is a fake assistant answer."
    assert "not a verified accounting fact" in body["disclaimer"]
    # The provider only ever receives deterministic facts, never DB access.
    assert fake_assistant_provider.calls[0][0]["total_sales_net"] == "1000.00"


def test_assistant_vat_return_explanation(client, db_session, fake_assistant_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _post_sales_transaction(client, headers, company_id, fy)
    vat_period_id = fy["vat_periods"][0]["id"]
    vat_return = client.get(
        "/api/v1/vat-returns", params={"company_id": company_id, "vat_period_id": vat_period_id}, headers=headers
    ).json()

    response = client.get(f"/api/v1/assistant/vat-return-explanation/{vat_return['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["facts"]["box_5a_total_vat_payable"] == "210.00"


def test_assistant_cross_tenant_blocked(client, db_session, fake_assistant_provider):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a, _ = _setup_company_with_fy(client, headers_a)

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get("/api/v1/assistant/company-summary", params={"company_id": company_a}, headers=headers_b)
    assert response.status_code == 404


# ---- Reports ----


def test_vat_return_report_pdf_xlsx_csv(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _post_sales_transaction(client, headers, company_id, fy)
    vat_period_id = fy["vat_periods"][0]["id"]
    vat_return = client.get(
        "/api/v1/vat-returns", params={"company_id": company_id, "vat_period_id": vat_period_id}, headers=headers
    ).json()

    pdf = client.get(f"/api/v1/reports/vat-return/{vat_return['id']}", params={"format": "pdf"}, headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"

    xlsx = client.get(f"/api/v1/reports/vat-return/{vat_return['id']}", params={"format": "xlsx"}, headers=headers)
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"  # xlsx is a zip container

    csv_resp = client.get(f"/api/v1/reports/vat-return/{vat_return['id']}", params={"format": "csv"}, headers=headers)
    assert csv_resp.status_code == 200
    assert b"box,description,net,vat" in csv_resp.content
    assert b"210.00" in csv_resp.content


def test_financial_overview_report_and_period_comparison(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _post_sales_transaction(client, headers, company_id, fy)

    pdf = client.get(
        "/api/v1/reports/financial-overview",
        params={"company_id": company_id, "financial_year_id": fy["id"], "format": "pdf"},
        headers=headers,
    )
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    comparison = client.get(
        "/api/v1/reports/period-comparison", params={"company_id": company_id, "financial_year_id": fy["id"]}, headers=headers
    ).json()
    assert comparison["total_sales_net"] == "1000.00"
    q1 = next(p for p in comparison["periods"] if p["label"] == "Q1")
    assert q1["sales_net"] == "1000.00"


def test_report_cross_tenant_blocked(client, db_session):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a, fy_a = _setup_company_with_fy(client, headers_a)
    _post_sales_transaction(client, headers_a, company_a, fy_a)
    vat_period_id = fy_a["vat_periods"][0]["id"]
    vat_return = client.get(
        "/api/v1/vat-returns", params={"company_id": company_a, "vat_period_id": vat_period_id}, headers=headers_a
    ).json()

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get(f"/api/v1/reports/vat-return/{vat_return['id']}", headers=headers_b)
    assert response.status_code == 404
