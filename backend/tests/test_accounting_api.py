from datetime import date

import fitz

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
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _setup_company_with_fy(client, headers, year=2026):
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(
        f"/api/v1/companies/{company_id}/financial-years", json={"year": year}, headers=headers
    ).json()
    return company_id, fy


def _sample_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    content = doc.tobytes()
    doc.close()
    return content


def _approve_document_from_upload(client, headers, company_id, fy_id, fake_ai_provider, extraction_result):
    fake_ai_provider.result = extraction_result
    doc = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id, "financial_year_id": fy_id},
        files={"file": ("invoice.pdf", _sample_pdf_bytes("Invoice"), "application/pdf")},
        headers=headers,
    ).json()
    approve = client.post(f"/api/v1/documents/{doc['id']}/approve", headers=headers)
    assert approve.status_code == 200, approve.text
    return doc


def test_approving_purchase_invoice_posts_a_transaction(client, db_session, fake_ai_provider):
    from app.schemas.extraction import InvoiceExtraction

    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    _approve_document_from_upload(
        client, headers, company_id, fy["id"], fake_ai_provider,
        InvoiceExtraction(
            document_type="PURCHASE_INVOICE",
            classification_confidence=0.95,
            invoice_number="INV-9",
            invoice_date="2026-02-01",
            supplier_name="Acme",
            supplier_vat_number="NL123456789B01",
            net_amount=100.0,
            vat_rate=21.0,
            vat_amount=21.0,
            gross_amount=121.0,
        ),
    )

    transactions = client.get("/api/v1/transactions", params={"company_id": company_id}, headers=headers).json()
    assert len(transactions) == 1
    assert transactions[0]["net_amount"] == "100.00"
    assert transactions[0]["vat_amount"] == "21.00"
    assert transactions[0]["ledger_side"] == "PURCHASES"


def test_cross_tenant_access_blocked_on_transactions(client, db_session, fake_ai_provider):
    from app.schemas.extraction import InvoiceExtraction

    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a, fy_a = _setup_company_with_fy(client, headers_a)
    _approve_document_from_upload(
        client, headers_a, company_a, fy_a["id"], fake_ai_provider,
        InvoiceExtraction(document_type="PURCHASE_INVOICE", classification_confidence=0.95, net_amount=10.0, vat_rate=21.0, vat_amount=2.1, gross_amount=12.1, invoice_number="X", supplier_vat_number="NL1"),
    )
    transaction_id = client.get("/api/v1/transactions", params={"company_id": company_a}, headers=headers_a).json()[0]["id"]

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get(f"/api/v1/transactions/{transaction_id}", headers=headers_b)
    assert response.status_code == 404


def test_manual_entry_requires_valid_treatment_for_side(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id,
            "financial_year_id": fy["id"],
            "ledger_side": "SALES",
            "invoice_date": "2026-02-01",
            "line_items": [
                {
                    "net_amount": "100.00",
                    "vat_rate": "21",
                    "vat_amount": "21.00",
                    "vat_treatment": "DOMESTIC_REVERSE_CHARGE_RECEIVED",  # invalid on sales side
                }
            ],
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_manual_entry_and_payment_recording(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    created = client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id,
            "financial_year_id": fy["id"],
            "ledger_side": "SALES",
            "invoice_date": "2026-02-01",
            "due_date": "2027-06-01",
            "line_items": [
                {"net_amount": "100.00", "vat_rate": "21", "vat_amount": "21.00", "vat_treatment": "DOMESTIC_STANDARD"}
            ],
        },
        headers=headers,
    ).json()
    assert created["gross_amount"] == "121.00"
    assert created["payment_status"] == "UNPAID"

    paid = client.post(
        f"/api/v1/transactions/{created['id']}/payments",
        json={"amount": "50.00", "payment_date": "2026-02-15"},
        headers=headers,
    ).json()
    assert paid["payment_status"] == "PARTIALLY_PAID"
    assert paid["amount_paid"] == "50.00"
    assert paid["remaining_balance"] == "71.00"

    paid_fully = client.post(
        f"/api/v1/transactions/{created['id']}/payments",
        json={"amount": "71.00", "payment_date": "2026-02-20"},
        headers=headers,
    ).json()
    assert paid_fully["payment_status"] == "PAID"
    assert paid_fully["remaining_balance"] == "0.00"


def test_viewer_cannot_create_manual_entry_or_record_payment(client, db_session):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers_admin)

    viewer = User(
        tenant_id=admin.tenant_id, email="viewer@acme.nl", hashed_password=hash_password("secret123"),
        full_name="Viewer", role=UserRole.viewer,
    )
    db_session.add(viewer)
    db_session.commit()
    headers_viewer = _login(client, "viewer@acme.nl")

    response = client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id,
            "financial_year_id": fy["id"],
            "ledger_side": "SALES",
            "invoice_date": "2026-02-01",
            "line_items": [{"net_amount": "1", "vat_rate": "21", "vat_amount": "0.21", "vat_treatment": "DOMESTIC_STANDARD"}],
        },
        headers=headers_viewer,
    )
    assert response.status_code == 403


def test_approve_transaction_then_direct_edit_blocked_requires_correction(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    created = client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id,
            "financial_year_id": fy["id"],
            "ledger_side": "SALES",
            "invoice_date": "2026-02-01",
            "line_items": [{"net_amount": "100.00", "vat_rate": "21", "vat_amount": "21.00", "vat_treatment": "DOMESTIC_STANDARD"}],
        },
        headers=headers,
    ).json()

    approve = client.post(f"/api/v1/transactions/{created['id']}/approve", headers=headers)
    assert approve.status_code == 200
    assert approve.json()["approval_status"] == "APPROVED"

    blocked = client.patch(
        f"/api/v1/transactions/{created['id']}", json={"accounting_classification": "hack"}, headers=headers
    )
    assert blocked.status_code == 409

    correction = client.post(
        f"/api/v1/transactions/{created['id']}/corrections",
        json={
            "financial_year_id": fy["id"],
            "line_items": [{"net_amount": "-10.00", "vat_rate": "21", "vat_amount": "-2.10", "vat_treatment": "DOMESTIC_STANDARD"}],
        },
        headers=headers,
    )
    assert correction.status_code == 201
    assert correction.json()["corrects_transaction_id"] == created["id"]


def test_vat_return_reconciliation_and_approval_workflow(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    vat_period_id = fy["vat_periods"][0]["id"]  # Q1

    client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id,
            "financial_year_id": fy["id"],
            "ledger_side": "SALES",
            "invoice_date": "2026-02-01",
            "line_items": [{"net_amount": "1000.00", "vat_rate": "21", "vat_amount": "210.00", "vat_treatment": "DOMESTIC_STANDARD"}],
        },
        headers=headers,
    )

    vat_return = client.get(
        "/api/v1/vat-returns", params={"company_id": company_id, "vat_period_id": vat_period_id}, headers=headers
    ).json()
    assert vat_return["box_1a_vat"] == "210.00"
    assert vat_return["net_payable"] == "210.00"
    assert vat_return["status"] == "draft"

    reconciliation = client.get(f"/api/v1/vat-returns/{vat_return['id']}/reconciliation", headers=headers).json()
    assert reconciliation["sales_total_net"] == "1000.00"

    submit = client.post(f"/api/v1/vat-returns/{vat_return['id']}/submit-for-approval", headers=headers)
    assert submit.status_code == 200
    assert submit.json()["status"] == "ready_for_approval"

    approve = client.post(f"/api/v1/vat-returns/{vat_return['id']}/approve", headers=headers)
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    # Approved returns can no longer be freely recalculated.
    recalc = client.post(f"/api/v1/vat-returns/{vat_return['id']}/recalculate", headers=headers)
    assert recalc.status_code == 409

    lock = client.post(f"/api/v1/vat-returns/{vat_return['id']}/lock", headers=headers)
    assert lock.status_code == 200
    assert lock.json()["status"] == "locked"


def test_vat_return_approve_requires_ready_for_approval_state(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    vat_period_id = fy["vat_periods"][0]["id"]

    vat_return = client.get(
        "/api/v1/vat-returns", params={"company_id": company_id, "vat_period_id": vat_period_id}, headers=headers
    ).json()

    response = client.post(f"/api/v1/vat-returns/{vat_return['id']}/approve", headers=headers)
    assert response.status_code == 409
