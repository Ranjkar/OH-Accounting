import fitz

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.extraction import InvoiceExtraction


def _create_user(db_session, tenant_name="Acme Accounting", email="admin@acme.nl", role=UserRole.admin):
    tenant = db_session.query(Tenant).filter(Tenant.name == tenant_name).first()
    if tenant is None:
        tenant = Tenant(name=tenant_name)
        db_session.add(tenant)
        db_session.flush()
    user = User(
        tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Test User", role=role
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


def _pdf(text: str = "Invoice") -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    content = doc.tobytes()
    doc.close()
    return content


def _file_tuple(name: str, content: bytes, content_type: str = "application/pdf"):
    return ("files", (name, content, content_type))


def test_upload_multiple_sales_invoices_in_one_batch(client, db_session, fake_ai_provider):
    fake_ai_provider.result = InvoiceExtraction(
        document_type="SALES_INVOICE", classification_confidence=0.9, invoice_number="S-1",
        invoice_date="2026-02-01", net_amount=100.0, vat_rate=21.0, vat_amount=21.0, gross_amount=121.0,
    )
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[_file_tuple(f"sales-{i}.pdf", _pdf(f"Sales {i}")) for i in range(3)],
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["batch"]["category"] == "SALES"
    assert len(body["documents"]) == 3
    assert all(d["upload_category"] == "SALES" for d in body["documents"])
    assert len(fake_ai_provider.calls) == 3

    detail = client.get(f"/api/v1/batches/{body['batch']['id']}", headers=headers).json()
    assert detail["counts"]["total"] == 3
    assert detail["counts"]["extracted"] == 3


def test_upload_multiple_purchase_invoices_separate_from_sales(client, db_session, fake_ai_provider):
    fake_ai_provider.result = InvoiceExtraction(
        document_type="PURCHASE_INVOICE", classification_confidence=0.9, invoice_number="P-1",
        invoice_date="2026-02-01", net_amount=50.0, vat_rate=9.0, vat_amount=4.5, gross_amount=54.5,
        supplier_vat_number="NL123456789B01",
    )
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "PURCHASES"},
        files=[_file_tuple(f"purchase-{i}.pdf", _pdf(f"Purchase {i}")) for i in range(2)],
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["batch"]["category"] == "PURCHASES"
    assert all(d["upload_category"] == "PURCHASES" for d in body["documents"])

    # Separate filters: a sales-only query must not return this purchase batch.
    sales_batches = client.get("/api/v1/batches", params={"company_id": company_id, "category": "SALES"}, headers=headers).json()
    assert body["batch"]["id"] not in [b["id"] for b in sales_batches]
    purchase_batches = client.get("/api/v1/batches", params={"company_id": company_id, "category": "PURCHASES"}, headers=headers).json()
    assert body["batch"]["id"] in [b["id"] for b in purchase_batches]


def test_mixed_file_formats_in_one_batch(client, db_session, fake_ai_provider):
    import openpyxl
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["description", "net_amount", "vat_rate", "vat_amount", "gross_amount"])
    ws.append(["Supplies", 10, 21, 2.1, 12.1])
    buf = BytesIO()
    wb.save(buf)

    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "PURCHASES"},
        files=[
            _file_tuple("invoice.pdf", _pdf("PDF invoice")),
            (
                "files",
                ("rows.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ),
        ],
        headers=headers,
    )
    assert response.status_code == 201
    assert len(response.json()["documents"]) == 2


def test_partial_failure_does_not_block_rest_of_batch(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[
            _file_tuple("good.pdf", _pdf("Good invoice")),
            ("files", ("bad.pdf", b"not a real pdf", "application/pdf")),
            _file_tuple("good2.pdf", _pdf("Good invoice 2")),
        ],
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["documents"]) == 2
    assert len(body["rejected_files"]) == 1
    assert body["rejected_files"][0]["filename"] == "bad.pdf"


def test_batch_size_limit_enforced(client, db_session, fake_ai_provider, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "batch_max_files", 2)
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[_file_tuple(f"f{i}.pdf", _pdf(str(i))) for i in range(3)],
        headers=headers,
    )
    assert response.status_code == 422


def test_duplicate_file_within_batch_is_flagged(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    content = _pdf("Same invoice")

    response = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[_file_tuple("a.pdf", content), _file_tuple("b.pdf", content)],
        headers=headers,
    )
    body = response.json()
    docs = {d["original_filename"]: d for d in body["documents"]}
    assert docs["a.pdf"]["is_duplicate"] is False
    assert docs["b.pdf"]["is_duplicate"] is True
    assert docs["b.pdf"]["duplicate_of_document_id"] == docs["a.pdf"]["id"]


def test_category_mismatch_flags_for_review_not_silent_posting(client, db_session, fake_ai_provider):
    # Uploaded via the SALES screen, but Claude reads it as a purchase invoice.
    fake_ai_provider.result = InvoiceExtraction(
        document_type="PURCHASE_INVOICE", classification_confidence=0.95, invoice_number="X-1",
        invoice_date="2026-02-01", net_amount=10.0, vat_rate=21.0, vat_amount=2.1, gross_amount=12.1,
        supplier_vat_number="NL999999999B01",
    )
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[_file_tuple("mismatch.pdf", _pdf("Mismatch"))],
        headers=headers,
    )
    document_id = response.json()["documents"][0]["id"]
    detail = client.get(f"/api/v1/documents/{document_id}", headers=headers).json()
    assert detail["status"] == "needs_review"
    assert any(v["rule_code"] == "UPLOAD_CATEGORY_MISMATCH" for v in detail["validation_results"])


def test_business_duplicate_flagged_as_warning_across_two_documents(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    fake_ai_provider.result = InvoiceExtraction(
        document_type="SALES_INVOICE", classification_confidence=0.9, invoice_number="DUP-1",
        invoice_date="2026-02-01", net_amount=100.0, vat_rate=21.0, vat_amount=21.0, gross_amount=121.0,
        customer_vat_number="NL111111111B01",
    )
    first = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"]},
        files={"file": ("first.pdf", _pdf("first content unique"), "application/pdf")},
        headers=headers,
    ).json()

    # Different file bytes (different SHA-256) but same business facts.
    second = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"]},
        files={"file": ("second.pdf", _pdf("second content also unique but longer text"), "application/pdf")},
        headers=headers,
    ).json()

    detail = client.get(f"/api/v1/documents/{second['id']}", headers=headers).json()
    assert detail["is_duplicate"] is False  # not a byte-for-byte duplicate
    assert any(v["rule_code"] == "POTENTIAL_BUSINESS_DUPLICATE" for v in detail["validation_results"])


def test_bulk_approve_posts_to_ledger_and_handles_one_failure_gracefully(client, db_session, fake_ai_provider):
    fake_ai_provider.result = InvoiceExtraction(
        document_type="SALES_INVOICE", classification_confidence=0.9, invoice_number="S-1",
        invoice_date="2026-02-01", net_amount=100.0, vat_rate=21.0, vat_amount=21.0, gross_amount=121.0,
    )
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    upload = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[_file_tuple("a.pdf", _pdf("a")), _file_tuple("b.pdf", _pdf("b"))],
        headers=headers,
    ).json()
    batch_id = upload["batch"]["id"]
    doc_ids = [d["id"] for d in upload["documents"]]

    # Approve one document directly first so the bulk call hits a conflict for it.
    client.post(f"/api/v1/documents/{doc_ids[0]}/approve", headers=headers)

    bulk = client.post(
        f"/api/v1/batches/{batch_id}/approve", json={"document_ids": doc_ids}, headers=headers
    ).json()
    results_by_id = {r["document_id"]: r for r in bulk["results"]}
    assert results_by_id[doc_ids[1]]["success"] is True
    # Already-approved document fails gracefully, doesn't blow up the whole call.
    assert results_by_id[doc_ids[0]]["success"] is False

    transactions = client.get("/api/v1/transactions", params={"company_id": company_id}, headers=headers).json()
    # One transaction per approved document (doc_ids[0] from the pre-approval, doc_ids[1] from
    # the bulk call) -- never double-posted for the same document.
    assert len(transactions) == 2
    assert len({t["source_document_id"] for t in transactions}) == 2


def test_bulk_reject(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    upload = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[_file_tuple("a.pdf", _pdf("a")), _file_tuple("b.pdf", _pdf("b"))],
        headers=headers,
    ).json()
    doc_ids = [d["id"] for d in upload["documents"]]

    bulk = client.post(
        f"/api/v1/batches/{upload['batch']['id']}/reject",
        json={"document_ids": doc_ids, "reason": "Not relevant"},
        headers=headers,
    ).json()
    assert all(r["success"] for r in bulk["results"])

    for doc_id in doc_ids:
        detail = client.get(f"/api/v1/documents/{doc_id}", headers=headers).json()
        assert detail["status"] == "rejected"


def test_remove_unprocessed_file(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    upload = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[_file_tuple("a.pdf", _pdf("a"))],
        headers=headers,
    ).json()
    doc_id = upload["documents"][0]["id"]

    response = client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert response.status_code == 204
    assert client.get(f"/api/v1/documents/{doc_id}", headers=headers).status_code == 404


def test_cannot_delete_approved_document(client, db_session, fake_ai_provider):
    fake_ai_provider.result = InvoiceExtraction(
        document_type="SALES_INVOICE", classification_confidence=0.9, invoice_number="S-1",
        invoice_date="2026-02-01", net_amount=10.0, vat_rate=21.0, vat_amount=2.1, gross_amount=12.1,
    )
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    doc = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"]},
        files={"file": ("a.pdf", _pdf("a"), "application/pdf")},
        headers=headers,
    ).json()
    client.post(f"/api/v1/documents/{doc['id']}/approve", headers=headers)

    response = client.delete(f"/api/v1/documents/{doc['id']}", headers=headers)
    assert response.status_code == 409


def test_export_batch_csv(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    upload = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[_file_tuple("a.pdf", _pdf("a"))],
        headers=headers,
    ).json()

    response = client.get(f"/api/v1/batches/{upload['batch']['id']}/export", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert b"a.pdf" in response.content
    assert response.content.startswith("﻿".encode("utf-8")), "CSV should start with a UTF-8 BOM for Excel compatibility"
    assert b"document_id,filename,category" in response.content  # stable, untranslated machine-readable header


def test_batch_cross_tenant_access_blocked(client, db_session, fake_ai_provider):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a, fy_a = _setup_company_with_fy(client, headers_a)
    upload = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_a, "financial_year_id": fy_a["id"], "category": "SALES"},
        files=[_file_tuple("a.pdf", _pdf("a"))],
        headers=headers_a,
    ).json()

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get(f"/api/v1/batches/{upload['batch']['id']}", headers=headers_b)
    assert response.status_code == 404


def test_viewer_cannot_upload_batch(client, db_session, fake_ai_provider):
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
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[_file_tuple("a.pdf", _pdf("a"))],
        headers=headers_viewer,
    )
    assert response.status_code == 403


def test_customer_can_upload_but_not_approve(client, db_session, fake_ai_provider):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers_admin)

    from app.models.company import Company

    customer = User(
        tenant_id=admin.tenant_id, email="customer@acme.nl", hashed_password=hash_password("secret123"),
        full_name="Customer", role=UserRole.customer,
    )
    db_session.add(customer)
    db_session.flush()
    company = db_session.get(Company, company_id)
    customer.companies.append(company)
    db_session.commit()

    headers_customer = _login(client, "customer@acme.nl")
    upload = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"], "category": "SALES"},
        files=[_file_tuple("a.pdf", _pdf("a"))],
        headers=headers_customer,
    )
    assert upload.status_code == 201
    doc_id = upload.json()["documents"][0]["id"]

    approve = client.post(f"/api/v1/documents/{doc_id}/approve", headers=headers_customer)
    assert approve.status_code == 403


def test_customer_cannot_access_other_companies_batches(client, db_session, fake_ai_provider):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_a, fy_a = _setup_company_with_fy(client, headers_admin, year=2026)
    company_b_id = client.post("/api/v1/companies", json={"name": "Other B.V."}, headers=headers_admin).json()["id"]

    from app.models.company import Company

    customer = User(
        tenant_id=admin.tenant_id, email="customer@acme.nl", hashed_password=hash_password("secret123"),
        full_name="Customer", role=UserRole.customer,
    )
    db_session.add(customer)
    db_session.flush()
    customer.companies.append(db_session.get(Company, company_a))
    db_session.commit()

    headers_customer = _login(client, "customer@acme.nl")
    response = client.post(
        "/api/v1/batches/upload",
        params={"company_id": company_b_id, "financial_year_id": fy_a["id"], "category": "SALES"},
        files=[_file_tuple("a.pdf", _pdf("a"))],
        headers=headers_customer,
    )
    assert response.status_code == 403
