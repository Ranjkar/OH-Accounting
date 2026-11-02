from io import BytesIO

import fitz
import openpyxl

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


def _create_company(client, headers, name="Test B.V.") -> int:
    return client.post("/api/v1/companies", json={"name": name}, headers=headers).json()["id"]


def _sample_pdf_bytes(text: str = "Invoice INV-001\nTotal: 121.00 EUR") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    content = doc.tobytes()
    doc.close()
    return content


def _sample_png_bytes() -> bytes:
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (100, 100), color="white").save(buf, format="PNG")
    return buf.getvalue()


def _sample_xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["description", "net_amount", "vat_rate", "vat_amount", "gross_amount"])
    ws.append(["Office supplies", 40, 21, 8.4, 48.4])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _sample_csv_bytes() -> bytes:
    return b"description,net_amount,vat_rate,vat_amount,gross_amount\nConsulting,100,21,21,121\n"


def test_upload_pdf_is_extracted_via_ai_provider(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)

    response = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("invoice.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 201
    document_id = response.json()["id"]
    assert len(fake_ai_provider.calls) == 1

    detail = client.get(f"/api/v1/documents/{document_id}", headers=headers).json()
    assert detail["status"] == "extracted"
    assert detail["fields"]["invoice_number"] == "INV-001"
    assert detail["fields"]["gross_amount"] == 121.0


def test_upload_png_runs_ocr_then_ai(client, db_session, fake_ai_provider, fake_ocr_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)

    response = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("scan.png", _sample_png_bytes(), "image/png")},
        headers=headers,
    )
    assert response.status_code == 201
    assert fake_ocr_provider.calls == 1
    assert len(fake_ai_provider.calls) == 1


def test_upload_xlsx_parses_rows_without_ai_call(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)

    response = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={
            "file": (
                "rows.xlsx",
                _sample_xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=headers,
    )
    assert response.status_code == 201
    document_id = response.json()["id"]
    assert fake_ai_provider.calls == []  # structured data skips the AI call entirely

    detail = client.get(f"/api/v1/documents/{document_id}", headers=headers).json()
    assert detail["status"] == "extracted"
    assert len(detail["line_items"]) == 1
    assert detail["line_items"][0]["description"] == "Office supplies"


def test_upload_csv_parses_rows(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)

    response = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("rows.csv", _sample_csv_bytes(), "text/csv")},
        headers=headers,
    )
    assert response.status_code == 201
    detail = client.get(f"/api/v1/documents/{response.json()['id']}", headers=headers).json()
    assert len(detail["line_items"]) == 1


def test_invalid_file_content_rejected(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)

    response = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("fake.pdf", b"not actually a pdf", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 422


def test_duplicate_upload_is_flagged_needs_review(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)
    content = _sample_pdf_bytes()

    first = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("invoice.pdf", content, "application/pdf")},
        headers=headers,
    ).json()

    second = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("invoice-copy.pdf", content, "application/pdf")},
        headers=headers,
    ).json()

    assert second["is_duplicate"] is True
    assert second["duplicate_of_document_id"] == first["id"]
    detail = client.get(f"/api/v1/documents/{second['id']}", headers=headers).json()
    assert detail["status"] == "needs_review"
    assert any(v["rule_code"] == "DUPLICATE_DOCUMENT" for v in detail["validation_results"])


def test_cross_tenant_access_is_blocked(client, db_session, fake_ai_provider):
    _create_user(db_session, tenant_name="Tenant A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a = _create_company(client, headers_a, name="Company A")
    doc = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_a},
        files={"file": ("invoice.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers_a,
    ).json()

    _create_user(db_session, tenant_name="Tenant B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")

    response = client.get(f"/api/v1/documents/{doc['id']}", headers=headers_b)
    assert response.status_code == 404

    file_response = client.get(f"/api/v1/documents/{doc['id']}/file", headers=headers_b)
    assert file_response.status_code == 404

    listing = client.get("/api/v1/documents", headers=headers_b).json()
    assert doc["id"] not in [d["id"] for d in listing]


def test_viewer_cannot_upload_or_approve(client, db_session, fake_ai_provider):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers_admin)

    viewer = User(
        tenant_id=admin.tenant_id,
        email="viewer@acme.nl",
        hashed_password=hash_password("secret123"),
        full_name="Viewer",
        role=UserRole.viewer,
    )
    db_session.add(viewer)
    db_session.commit()
    headers_viewer = _login(client, "viewer@acme.nl")

    response = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("invoice.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers_viewer,
    )
    assert response.status_code == 403


def test_correction_updates_fields_and_writes_audit_log(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)
    doc = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("invoice.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers,
    ).json()

    response = client.patch(
        f"/api/v1/documents/{doc['id']}/fields",
        json={"invoice_number": "CORRECTED-001", "net_amount": 200.0},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["fields"]["invoice_number"] == "CORRECTED-001"

    from app.models.audit_log import AuditLog

    logs = db_session.query(AuditLog).filter(AuditLog.action == "correct").all()
    assert len(logs) == 1
    assert logs[0].after["invoice_number"] == "CORRECTED-001"


def test_approval_workflow_and_reprocess_blocked_after_approval(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)
    fy = client.post(
        f"/api/v1/companies/{company_id}/financial-years", json={"year": 2026}, headers=headers
    ).json()
    doc = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id, "financial_year_id": fy["id"]},
        files={"file": ("invoice.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers,
    ).json()

    approve = client.post(f"/api/v1/documents/{doc['id']}/approve", headers=headers)
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    reprocess = client.post(f"/api/v1/documents/{doc['id']}/reprocess", headers=headers)
    assert reprocess.status_code == 409


def test_approving_postable_document_without_financial_year_is_rejected(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)
    doc = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("invoice.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers,
    ).json()

    response = client.post(f"/api/v1/documents/{doc['id']}/approve", headers=headers)
    assert response.status_code == 409
    assert "financial year" in response.json()["detail"].lower()


def test_reject_requires_reason_and_sets_status(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)
    doc = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("invoice.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers,
    ).json()

    response = client.post(
        f"/api/v1/documents/{doc['id']}/reject",
        json={"reason": "Wrong company"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_low_confidence_classification_goes_to_needs_review(client, db_session, fake_ai_provider):
    from app.schemas.extraction import InvoiceExtraction

    fake_ai_provider.result = InvoiceExtraction(
        document_type="OTHER", classification_confidence=0.2, invoice_number="X"
    )
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)
    doc = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("invoice.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers,
    ).json()

    detail = client.get(f"/api/v1/documents/{doc['id']}", headers=headers).json()
    assert detail["status"] == "needs_review"


def test_ai_extraction_failure_marks_document_failed_then_reprocess_recovers(
    client, db_session, fake_ai_provider
):
    fake_ai_provider.raise_exc = RuntimeError("provider timeout")
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = _create_company(client, headers)
    doc = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_id},
        files={"file": ("invoice.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers,
    ).json()

    detail = client.get(f"/api/v1/documents/{doc['id']}", headers=headers).json()
    assert detail["status"] == "failed"
    assert "provider timeout" in detail["error_message"]

    fake_ai_provider.raise_exc = None
    reprocess = client.post(f"/api/v1/documents/{doc['id']}/reprocess", headers=headers)
    assert reprocess.status_code == 200

    detail = client.get(f"/api/v1/documents/{doc['id']}", headers=headers).json()
    assert detail["status"] == "extracted"


def test_reassign_document_to_another_company(client, db_session, fake_ai_provider):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_a = _create_company(client, headers, name="Company A")
    company_b = _create_company(client, headers, name="Company B")
    doc = client.post(
        "/api/v1/documents/upload",
        params={"company_id": company_a},
        files={"file": ("invoice.pdf", _sample_pdf_bytes(), "application/pdf")},
        headers=headers,
    ).json()

    response = client.patch(
        f"/api/v1/documents/{doc['id']}/assignment",
        json={"company_id": company_b},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["company_id"] == company_b
