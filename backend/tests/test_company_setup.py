"""Phase 22: company setup wizard -- drafts, validation, idempotent completion."""
import threading

from app.core.dutch_identifiers import is_valid_btw, is_valid_iban, is_valid_kvk, is_valid_rsin
from app.core.security import hash_password
from app.models.company import Company, CompanySetupDraft
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User


def _user(db_session, email="owner@acme.nl", role=UserRole.owner, tenant_name="Acme"):
    tenant = Tenant(name=tenant_name)
    db_session.add(tenant)
    db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Owner", role=role)
    db_session.add(user)
    db_session.commit()
    return user


def _headers(client, email="owner@acme.nl"):
    token = client.post("/api/v1/auth/login", json={"email": email, "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


VALID = {
    "name": "Wizard B.V.", "legal_form_code": "bv", "kvk_number": "68750110", "rsin": "123456782",
    "vat_registered": True, "vat_number": "NL000099998B57", "vat_frequency": "quarterly",
    "vat_accounting_basis": "invoice_based", "kor_participant": False, "financial_year": 2026,
    "bank_iban": "NL91 ABNA 0417 1643 00", "bank_account_name": "Zakelijk",
}


def test_identifier_validators():
    assert is_valid_kvk("6875 0110") and not is_valid_kvk("123")
    assert is_valid_btw("NL000099998B57") and not is_valid_btw("NL000099998B58")
    assert is_valid_rsin("123456782") and not is_valid_rsin("123456783")
    assert is_valid_iban("NL91ABNA0417164300") and not is_valid_iban("NL91ABNA0417164301")


def test_draft_lifecycle_and_validation_messages(client, db_session):
    _user(db_session)
    h = _headers(client)
    draft = client.post("/api/v1/companies/setup-drafts", headers=h).json()
    assert draft["current_step"] == 0 and draft["created_company_id"] is None

    # Partial answers are saved as-is and resumable.
    r = client.patch(f"/api/v1/companies/setup-drafts/{draft['id']}", json={"data": {"name": "Wizard B.V.", "legal_form_code": "bv"}, "current_step": 1}, headers=h)
    assert r.status_code == 200 and r.json()["data"]["name"] == "Wizard B.V." and r.json()["current_step"] == 1
    assert [d["id"] for d in client.get("/api/v1/companies/setup-drafts", headers=h).json()] == [draft["id"]]

    # Validation names required + conditionally required fields.
    v = client.post(f"/api/v1/companies/setup-drafts/{draft['id']}/validate", headers=h).json()
    assert v["ok"] is False
    fields = {i["field"]: i["code"] for i in v["issues"]}
    assert fields["kvk_number"] == "required" and fields["vat_registered"] == "required" and fields["financial_year"] == "required"
    assert any(w["field"] == "rsin" for w in v["warnings"])  # BV: RSIN expected but not blocking

    # Completion with an incomplete draft is refused, nothing created.
    r = client.post(f"/api/v1/companies/setup-drafts/{draft['id']}/complete", headers=h)
    assert r.status_code == 422 and db_session.query(Company).count() == 0

    # Bad checksums are rejected explicitly.
    bad = {**VALID, "vat_number": "NL000099998B58", "rsin": "123456789", "bank_iban": "NL91ABNA0417164301"}
    v = client.post(f"/api/v1/companies/setup-drafts/{draft['id']}/validate", json={"data": bad, "current_step": 3}, headers=h).json()
    assert {i["field"] for i in v["issues"] if i["code"] == "invalid"} == {"vat_number", "rsin", "bank_iban"}

    # Non-VAT-registered company must not need a btw-id, but cannot claim KOR.
    v = client.post(f"/api/v1/companies/setup-drafts/{draft['id']}/validate", json={"data": {**VALID, "vat_registered": False, "vat_number": None, "kor_participant": True}, "current_step": 3}, headers=h).json()
    assert {i["field"] for i in v["issues"]} == {"kor_participant"}


def test_complete_creates_company_year_bank_and_is_idempotent(client, db_session):
    _user(db_session)
    h = _headers(client)
    draft_id = client.post("/api/v1/companies/setup-drafts", headers=h).json()["id"]
    client.patch(f"/api/v1/companies/setup-drafts/{draft_id}", json={"data": VALID, "current_step": 4}, headers=h)

    first = client.post(f"/api/v1/companies/setup-drafts/{draft_id}/complete", headers=h)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["already_completed"] is False
    assert body["company"]["kvk_number"] == "68750110" and body["company"]["rsin"] == "123456782"
    assert body["company"]["vat_registered"] is True and body["company"]["kor_participant"] is False
    assert body["financial_year_id"] and body["bank_account_id"]

    # Retry / double submit: same company, no second row.
    second = client.post(f"/api/v1/companies/setup-drafts/{draft_id}/complete", headers=h)
    assert second.status_code == 200 and second.json()["already_completed"] is True
    assert second.json()["company"]["id"] == body["company"]["id"]
    assert db_session.query(Company).count() == 1

    # Legal form history + VAT periods + bank account exist.
    years = client.get(f"/api/v1/companies/{body['company']['id']}/financial-years", headers=h).json()
    assert [p["label"] for p in years[0]["vat_periods"]] == ["Q1", "Q2", "Q3", "Q4"]
    current = client.get(f"/api/v1/company-legal-forms/current?company_id={body['company']['id']}", headers=h).json()
    assert current["legal_form_code"] == "BV"
    accounts = client.get(f"/api/v1/bank-accounts?company_id={body['company']['id']}", headers=h).json()
    assert accounts[0]["iban"] == "NL91ABNA0417164300"

    # A completed draft can no longer be edited or deleted, and no longer lists as open.
    assert client.patch(f"/api/v1/companies/setup-drafts/{draft_id}", json={"data": VALID, "current_step": 1}, headers=h).status_code == 409
    assert client.delete(f"/api/v1/companies/setup-drafts/{draft_id}", headers=h).status_code == 409
    assert client.get("/api/v1/companies/setup-drafts", headers=h).json() == []


def test_duplicate_company_is_refused(client, db_session):
    _user(db_session)
    h = _headers(client)
    client.post("/api/v1/companies", json={"name": "Existing B.V.", "kvk_number": "68750110"}, headers=h)
    draft_id = client.post("/api/v1/companies/setup-drafts", headers=h).json()["id"]
    v = client.post(f"/api/v1/companies/setup-drafts/{draft_id}/validate", json={"data": {**VALID, "name": "existing b.v."}, "current_step": 4}, headers=h).json()
    codes = {(i["field"], i["code"]) for i in v["issues"]}
    assert ("kvk_number", "duplicate") in codes and ("name", "duplicate") in codes


def test_drafts_are_tenant_isolated_and_admin_only(client, db_session):
    _user(db_session)
    other = _user(db_session, email="other@b.nl", tenant_name="B")
    viewer = User(tenant_id=other.tenant_id, email="viewer@b.nl", hashed_password=hash_password("secret123"), full_name="V", role=UserRole.viewer)
    db_session.add(viewer)
    db_session.commit()
    h_a = _headers(client)
    h_b = _headers(client, "other@b.nl")
    draft_id = client.post("/api/v1/companies/setup-drafts", headers=h_a).json()["id"]
    assert client.get(f"/api/v1/companies/setup-drafts/{draft_id}", headers=h_b).status_code == 404
    assert client.post(f"/api/v1/companies/setup-drafts/{draft_id}/complete", headers=h_b).status_code == 404
    assert client.post("/api/v1/companies/setup-drafts", headers=_headers(client, "viewer@b.nl")).status_code == 403


def test_email_format_is_enforced_server_side(client, db_session):
    _user(db_session)
    h = _headers(client)
    draft_id = client.post("/api/v1/companies/setup-drafts", headers=h).json()["id"]

    v = client.post(f"/api/v1/companies/setup-drafts/{draft_id}/validate", json={"data": {**VALID, "email": "info@"}, "current_step": 3}, headers=h).json()
    assert {i["field"]: i["code"] for i in v["issues"]}.get("email") == "invalid"

    v = client.post(f"/api/v1/companies/setup-drafts/{draft_id}/validate", json={"data": {**VALID, "email": "info@voorbeeld.nl"}, "current_step": 3}, headers=h).json()
    assert not any(i["field"] == "email" for i in v["issues"])

    # Direct company creation rejects a malformed address at the schema level.
    r = client.post("/api/v1/companies", json={"name": "Email Format B.V.", "email": "not-an-email"}, headers=h)
    assert r.status_code == 422
    r = client.post("/api/v1/companies", json={"name": "Email Format B.V.", "email": "boekhouder@voorbeeld.nl"}, headers=h)
    assert r.status_code == 201
