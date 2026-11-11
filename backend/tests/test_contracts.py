"""Phase 26: annual client agreements & electronic signatures."""

import hashlib
import threading
from datetime import date, datetime, timedelta, timezone

import fitz
import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.contract import Contract, ContractReminder, ContractSignature, ContractSigningInvitation, ContractVersion
from app.models.email_outbox import EmailOutbox
from app.models.enums import ContractStatus, SigningInvitationStatus, UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.services import contract_scheduler, contract_service as svc, email_provider, email_service
from app.services.email_provider import EmailSendError

pytestmark = pytest.mark.usefixtures("contracts_on")


@pytest.fixture()
def contracts_on(monkeypatch, test_session_local):
    monkeypatch.setattr(settings, "contracts_enabled", True)
    monkeypatch.setattr(settings, "contracts_email_automation_enabled", False)
    # The scheduler opens its own sessions (like document processing); point them at the test DB.
    monkeypatch.setattr(contract_scheduler, "SessionLocal", test_session_local)


@pytest.fixture()
def automation_on(monkeypatch):
    monkeypatch.setattr(settings, "contracts_email_automation_enabled", True)


class FlakyProvider:
    name = "fake"

    def __init__(self, fail_times=0, retryable=True):
        self.fail_times, self.retryable, self.calls, self.sent = fail_times, retryable, 0, []

    def send(self, message):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise EmailSendError("boom", retryable=self.retryable)
        self.sent.append(message)
        return f"msg-{self.calls}"


@pytest.fixture()
def fake_email(monkeypatch, test_session_local):
    provider = FlakyProvider()
    monkeypatch.setattr(email_service, "SessionLocal", test_session_local)  # background delivery must hit the test DB
    monkeypatch.setattr(email_provider, "_provider", provider)
    monkeypatch.setattr(email_service, "get_email_provider", lambda: provider)
    monkeypatch.setattr(email_service, "is_configured", lambda: True)
    monkeypatch.setattr(settings, "email_retry_base_delay_seconds", 0.0)
    yield provider
    email_provider.reset_provider_cache()


def _setup(db_session, *, with_company=True):
    tenant = Tenant(name="Acme Accounting")
    db_session.add(tenant)
    db_session.flush()
    admin = User(tenant_id=tenant.id, email="admin@acme.nl", hashed_password=hash_password("secret123"), full_name="Admin Acme", role=UserRole.admin)
    accountant = User(tenant_id=tenant.id, email="acc@acme.nl", hashed_password=hash_password("secret123"), full_name="Acc", role=UserRole.accountant)
    viewer = User(tenant_id=tenant.id, email="viewer@acme.nl", hashed_password=hash_password("secret123"), full_name="Viewer", role=UserRole.viewer)
    db_session.add_all([admin, accountant, viewer])
    db_session.flush()
    company = None
    if with_company:
        company = Company(tenant_id=tenant.id, name="Client BV", kvk_number="12345678", vat_number="NL000099998B57", address="Keizersgracht 1, Amsterdam", email="owner@client.nl")
        db_session.add(company)
        db_session.flush()
        company.users.append(accountant)
    db_session.commit()
    return tenant, admin, accountant, viewer, company


def _other_tenant(db_session):
    tenant = Tenant(name="Other")
    db_session.add(tenant)
    db_session.flush()
    admin = User(tenant_id=tenant.id, email="admin@other.nl", hashed_password=hash_password("secret123"), full_name="Other", role=UserRole.owner)
    db_session.add(admin)
    db_session.commit()
    return admin


def _headers(client, email="admin@acme.nl"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "secret123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


TERMS = {"signer_name": "Jan de Vries", "signer_email": "jan@client.nl", "monthly_fee": "250.00", "payment_terms_days": 14, "notice_period_days": 30}


def _ready_contract(client, h, company_id, **overrides):
    """Create -> complete terms -> approve. Returns the detail payload."""
    created = client.post("/api/v1/contracts", headers=h, json={"company_id": company_id, **overrides.pop("create", {})})
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    patched = client.patch(f"/api/v1/contracts/{cid}", headers=h, json={**TERMS, **overrides})
    assert patched.status_code == 200, patched.text
    approved = client.post(f"/api/v1/contracts/{cid}/approve", headers=h)
    assert approved.status_code == 200, approved.text
    return approved.json()


def _token_from(body, provider=None) -> str:
    """The raw token is only ever in the admin response (when email could not
    be sent) or in the delivered email itself -- never in any stored row."""
    if body.get("signing_link"):
        return body["signing_link"].rsplit("/sign/", 1)[1]
    import re
    return re.search(r"/sign/(\S+)", provider.sent[-1].text_body).group(1)


def _sent_contract(client, h, company_id, provider=None, **overrides):
    detail = _ready_contract(client, h, company_id, **overrides)
    sent = client.post(f"/api/v1/contracts/{detail['id']}/send", headers=h)
    assert sent.status_code == 200, sent.text
    body = sent.json()
    return detail["id"], _token_from(body, provider), body


# ---- feature flag ----


def test_feature_flag_hides_every_endpoint(client, db_session, monkeypatch):
    _, admin, _, _, company = _setup(db_session)
    h = _headers(client)
    monkeypatch.setattr(settings, "contracts_enabled", False)
    assert client.get("/api/v1/contracts", headers=h).status_code == 404
    assert client.get("/api/v1/contracts/sign/whatever").status_code == 404
    # Company creation still works and creates NO draft while disabled.
    created = client.post("/api/v1/companies", headers=h, json={"name": "Dark BV"})
    assert created.status_code == 201
    assert db_session.query(Contract).count() == 0


# ---- automatic creation ----


def test_quick_company_create_produces_draft_agreement(client, db_session):
    _setup(db_session, with_company=False)
    h = _headers(client)
    created = client.post("/api/v1/companies", headers=h, json={"name": "Nieuw BV", "kvk_number": "87654321", "email": "baas@nieuw.nl"})
    assert created.status_code == 201, created.text
    contracts = client.get("/api/v1/contracts", headers=h, params={"company_id": created.json()["id"]}).json()
    assert len(contracts) == 1
    c = contracts[0]
    assert c["status"] == "DRAFT" and c["created_source"] == "company_created"
    assert c["signer_email"] == "baas@nieuw.nl" and c["term_months"] == 12
    assert c["reference"].startswith("OHA-")
    assert (date.fromisoformat(c["end_date"]) - date.fromisoformat(c["start_date"])).days in (364, 365)
    assert c["monthly_fee"] is None  # never invented


def test_wizard_company_create_produces_draft_agreement(client, db_session):
    _setup(db_session, with_company=False)
    h = _headers(client)
    draft = client.post("/api/v1/companies/setup-drafts", headers=h).json()
    client.patch(f"/api/v1/companies/setup-drafts/{draft['id']}", headers=h, json={"current_step": 5, "data": {
        "name": "Wizard BV", "legal_form_code": "vve", "vat_registered": False, "financial_year": 2026, "bank_skipped": True, "email": "info@wizard.nl",
    }})
    done = client.post(f"/api/v1/companies/setup-drafts/{draft['id']}/complete", headers=h)
    assert done.status_code == 200, done.text
    contracts = client.get("/api/v1/contracts", headers=h, params={"company_id": done.json()["company"]["id"]}).json()
    assert len(contracts) == 1 and contracts[0]["created_source"] == "company_created"


def test_auto_create_respects_tenant_setting_and_never_breaks_onboarding(client, db_session, monkeypatch):
    _setup(db_session, with_company=False)
    h = _headers(client)
    assert client.put("/api/v1/contracts/settings", headers=h, json={"auto_create_on_company_create": False}).status_code == 200
    created = client.post("/api/v1/companies", headers=h, json={"name": "Quiet BV"})
    assert created.status_code == 201 and db_session.query(Contract).count() == 0

    client.put("/api/v1/contracts/settings", headers=h, json={"auto_create_on_company_create": True})
    monkeypatch.setattr(svc, "create_draft", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    created = client.post("/api/v1/companies", headers=h, json={"name": "Resilient BV"})
    assert created.status_code == 201, created.text
    assert db_session.query(Company).filter(Company.name == "Resilient BV").count() == 1


# ---- manual creation, approval, sending ----


def test_manual_create_requires_complete_terms_before_approval(client, db_session):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    created = client.post("/api/v1/contracts", headers=h, json={"company_id": company.id, "language": "en", "start_date": "2027-01-01"})
    assert created.status_code == 201
    body = created.json()
    assert body["language"] == "en" and body["end_date"] == "2027-12-31"
    assert set(body["approval_missing"]) >= {"signer_name", "monthly_fee", "payment_terms_days"}
    refused = client.post(f"/api/v1/contracts/{body['id']}/approve", headers=h)
    assert refused.status_code == 422 and "signer_name" in refused.json()["detail"]
    assert client.post(f"/api/v1/contracts/{body['id']}/send", headers=h).status_code == 409


def test_approval_freezes_an_immutable_version_with_hashes(client, db_session, tmp_storage):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    detail = _ready_contract(client, h, company.id)
    assert detail["status"] == "READY_TO_SEND" and len(detail["versions"]) == 1
    version = detail["versions"][0]
    assert version["kind"] == "APPROVED" and len(version["pdf_sha256"]) == 64

    pdf = client.get(f"/api/v1/contracts/{detail['id']}/versions/{version['id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert hashlib.sha256(pdf.content).hexdigest() == version["pdf_sha256"]
    text = "".join(page.get_text() for page in fitz.open(stream=pdf.content, filetype="pdf"))
    assert "Overeenkomst administratieve dienstverlening" in text and "Client BV" in text and "EUR 250,00" in text

    verify = client.get(f"/api/v1/contracts/{detail['id']}/versions/{version['id']}/verify", headers=h).json()
    assert verify["valid"] is True
    # Editing after approval is refused; terms are frozen.
    assert client.patch(f"/api/v1/contracts/{detail['id']}", headers=h, json={"monthly_fee": "1.00"}).status_code == 409
    assert db_session.query(AuditLog).filter(AuditLog.entity_type == "contract", AuditLog.action == "approve").count() == 1


def test_send_creates_invitation_with_hashed_token_and_outbox_row(client, db_session):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    cid, token, body = _sent_contract(client, h, company.id)
    assert body["email_sent"] is False  # EMAIL_PROVIDER=none -> link returned to admin, like company invitations
    assert body["contract"]["status"] == "SENT" and body["contract"]["signing_status"] == "awaiting"
    inv = db_session.query(ContractSigningInvitation).one()
    assert inv.token_hash != token and len(inv.token_hash) == 64 and token not in inv.token_hash
    assert db_session.query(EmailOutbox).filter(EmailOutbox.template == "contract_invitation").count() == 1
    # Tokens never appear in events or audit rows.
    for event in db_session.get(Contract, cid).events:
        assert token not in str(event.data)
    for row in db_session.query(AuditLog).all():
        assert token not in str(row.after)


def test_viewer_cannot_create_accountant_cannot_approve_or_send(client, db_session):
    _, _, _, _, company = _setup(db_session)
    assert client.post("/api/v1/contracts", headers=_headers(client, "viewer@acme.nl"), json={"company_id": company.id}).status_code == 403
    acc = _headers(client, "acc@acme.nl")
    created = client.post("/api/v1/contracts", headers=acc, json={"company_id": company.id})
    assert created.status_code == 201
    cid = created.json()["id"]
    client.patch(f"/api/v1/contracts/{cid}", headers=acc, json=TERMS)
    assert client.post(f"/api/v1/contracts/{cid}/submit", headers=acc).status_code == 200
    assert client.post(f"/api/v1/contracts/{cid}/approve", headers=acc).status_code == 403
    assert client.post(f"/api/v1/contracts/{cid}/send", headers=acc).status_code == 403
    assert client.post(f"/api/v1/contracts/{cid}/approve", headers=_headers(client)).status_code == 200


# ---- signing ----


def test_full_signing_flow_records_evidence_and_final_pdf(client, db_session, tmp_storage):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    cid, token, _ = _sent_contract(client, h, company.id)

    page = client.get(f"/api/v1/contracts/sign/{token}")
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["status"] == "VIEWED" and body["already_signed"] is False
    assert body["signer_name"] == "Jan de Vries" and body["signer_email_hint"] == "ja***@client.nl"
    assert "Jan de Vries" in body["consent_text"] and "gewone elektronische handtekening" in body["consent_text"]
    assert "geen gekwalificeerde" in body["assurance_notice"]
    assert body["content"]["clauses"][0]["body"].startswith("Deze overeenkomst wordt gesloten tussen OnHolland Accounting")
    assert "{" not in body["content"]["clauses"][0]["body"]

    # Consent and identity are enforced.
    assert client.post(f"/api/v1/contracts/sign/{token}", json={"full_name": "Jan de Vries", "email": "jan@client.nl", "consent": False}).status_code == 422
    assert client.post(f"/api/v1/contracts/sign/{token}", json={"full_name": "Jan de Vries", "email": "someone@else.nl", "consent": True}).status_code == 403
    assert client.post(f"/api/v1/contracts/sign/{token}", json={"full_name": "Piet", "email": "jan@client.nl", "consent": True}).status_code == 422

    signed = client.post(f"/api/v1/contracts/sign/{token}", json={"full_name": "  jan DE vries ", "email": "Jan@Client.nl", "consent": True}, headers={"user-agent": "pytest"})
    assert signed.status_code == 200, signed.text
    assert signed.json()["already_signed"] is True and signed.json()["status"] == "ACTIVE"  # start date today -> active immediately

    contract = db_session.get(Contract, cid)
    db_session.refresh(contract)
    sig = db_session.query(ContractSignature).one()
    approved_version = db_session.query(ContractVersion).filter(ContractVersion.id == sig.contract_version_id).one()
    signed_version = db_session.query(ContractVersion).filter(ContractVersion.id == sig.signed_version_id).one()
    assert sig.signing_method == "simple_electronic_typed_name" and sig.provider_name == "internal"
    assert sig.document_sha256 == approved_version.pdf_sha256 and signed_version.kind.value == "SIGNED"
    assert sig.user_agent == "pytest" and sig.consent_given_at is not None
    assert "{name}" not in sig.consent_text and "jan DE vries" in sig.consent_text
    assert signed_version.content["signature"]["document_sha256"] == approved_version.pdf_sha256

    # Final PDF carries the evidence page and its own verifiable hash.
    pdf = client.get(f"/api/v1/contracts/sign/{token}/pdf")
    assert pdf.status_code == 200 and hashlib.sha256(pdf.content).hexdigest() == signed_version.pdf_sha256
    text = "".join(p.get_text() for p in fitz.open(stream=pdf.content, filetype="pdf"))
    assert "Bewijs van elektronische ondertekening" in text and approved_version.pdf_sha256 in text and "jan DE vries" in text

    detail = client.get(f"/api/v1/contracts/{cid}", headers=h).json()
    assert detail["signing_status"] == "signed" and detail["signature"]["signer_email"] == "jan@client.nl"
    assert [e["event_type"] for e in detail["events"]][:6] == ["created", "terms_updated", "approved", "sent", "viewed", "signed"]
    assert any(e["event_type"] == "notification_skipped" for e in detail["events"])  # automation flag off
    assert db_session.query(AuditLog).filter(AuditLog.action == "sign").count() == 1


def test_signed_contract_is_immutable_and_replay_is_refused(client, db_session, tmp_storage):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    cid, token, _ = _sent_contract(client, h, company.id)
    assert client.post(f"/api/v1/contracts/sign/{token}", json={"full_name": "Jan de Vries", "email": "jan@client.nl", "consent": True}).status_code == 200
    replay = client.post(f"/api/v1/contracts/sign/{token}", json={"full_name": "Jan de Vries", "email": "jan@client.nl", "consent": True})
    assert replay.status_code == 409
    assert db_session.query(ContractSignature).count() == 1 and db_session.query(ContractVersion).count() == 2
    assert client.patch(f"/api/v1/contracts/{cid}", headers=h, json={"monthly_fee": "9999"}).status_code == 409
    assert client.post(f"/api/v1/contracts/{cid}/cancel", headers=h).status_code == 409  # signed: terminate, not cancel
    assert client.post(f"/api/v1/contracts/{cid}/resend", headers=h).status_code == 409
    # The signer may still open the signed state through the used link.
    page = client.get(f"/api/v1/contracts/sign/{token}")
    assert page.status_code == 200 and page.json()["already_signed"] is True
    # Stored bytes untouched -> both hashes still verify.
    for v in db_session.query(ContractVersion).all():
        assert svc.verify_version(v)["valid"] is True


def test_invalid_expired_and_revoked_links(client, db_session):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    assert client.get("/api/v1/contracts/sign/not-a-real-token").status_code == 404
    assert client.get("/api/v1/contracts/sign/" + "x" * 300).status_code == 404

    cid, token, _ = _sent_contract(client, h, company.id)
    inv = db_session.query(ContractSigningInvitation).one()
    inv.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get(f"/api/v1/contracts/sign/{token}").status_code == 410
    assert client.post(f"/api/v1/contracts/sign/{token}", json={"full_name": "Jan de Vries", "email": "jan@client.nl", "consent": True}).status_code == 410
    db_session.refresh(inv)
    assert inv.status == SigningInvitationStatus.expired
    assert client.get(f"/api/v1/contracts/{cid}", headers=h).json()["signing_status"] == "expired"

    # Resend issues a fresh link; the old one is revoked, the new one works.
    resent = client.post(f"/api/v1/contracts/{cid}/resend", headers=h)
    assert resent.status_code == 200
    new_token = resent.json()["signing_link"].rsplit("/sign/", 1)[1]
    assert client.get(f"/api/v1/contracts/sign/{new_token}").status_code == 200
    assert client.get(f"/api/v1/contracts/sign/{token}").status_code == 410

    # Cancellation withdraws the agreement from the signer.
    assert client.post(f"/api/v1/contracts/{cid}/cancel", headers=h, json={"reason": "client withdrew"}).status_code == 200
    assert client.get(f"/api/v1/contracts/sign/{new_token}").status_code == 410
    assert client.post(f"/api/v1/contracts/sign/{new_token}", json={"full_name": "Jan de Vries", "email": "jan@client.nl", "consent": True}).status_code in (409, 410)


def test_concurrent_sign_requests_yield_exactly_one_signature(client, db_session, test_session_local, tmp_storage):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    cid, token, _ = _sent_contract(client, h, company.id)
    barrier = threading.Barrier(2)
    results: list = []

    def attempt():
        session = test_session_local()
        try:
            barrier.wait(timeout=10)
            svc.sign(session, None, token, typed_name="Jan de Vries", typed_email="jan@client.nl", consent=True, ip_address="127.0.0.1", user_agent="t")
            results.append("ok")
        except svc.ContractError as exc:
            session.rollback()
            results.append(exc.status_code)
        finally:
            session.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(results, key=str) == [409, "ok"], results
    assert db_session.query(ContractSignature).count() == 1


# ---- tenant isolation ----


def test_cross_tenant_access_is_denied_everywhere(client, db_session, tmp_storage):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    cid, token, _ = _sent_contract(client, h, company.id)
    version_id = client.get(f"/api/v1/contracts/{cid}", headers=h).json()["versions"][0]["id"]
    _other_tenant(db_session)
    other = _headers(client, "admin@other.nl")
    assert client.get("/api/v1/contracts", headers=other).json() == []
    assert client.get(f"/api/v1/contracts/{cid}", headers=other).status_code == 404
    assert client.get("/api/v1/contracts", headers=other, params={"company_id": company.id}).status_code == 404
    assert client.post("/api/v1/contracts", headers=other, json={"company_id": company.id}).status_code == 404
    for action in ("approve", "send", "resend", "cancel", "terminate", "renewal", "submit"):
        assert client.post(f"/api/v1/contracts/{cid}/{action}", headers=other).status_code == 404, action
    assert client.patch(f"/api/v1/contracts/{cid}", headers=other, json={"monthly_fee": "1"}).status_code == 404
    assert client.get(f"/api/v1/contracts/{cid}/versions/{version_id}/pdf", headers=other).status_code == 404
    assert client.get(f"/api/v1/contracts/{cid}/preview.pdf", headers=other).status_code == 404
    template_id = client.get("/api/v1/contracts/templates", headers=h).json()[0]["id"]
    assert client.post(f"/api/v1/contracts/templates/{template_id}/approve", headers=other).status_code == 404
    # Nothing changed for the victim.
    assert db_session.get(Contract, cid).status == ContractStatus.sent
    # A same-tenant non-member accountant is refused with 403, not 404.
    other_company = Company(tenant_id=company.tenant_id, name="Not mine BV")
    db_session.add(other_company)
    db_session.commit()
    created = client.post("/api/v1/contracts", headers=h, json={"company_id": other_company.id}).json()
    assert client.get(f"/api/v1/contracts/{created['id']}", headers=_headers(client, "acc@acme.nl")).status_code == 403
    assert all(c["company_id"] == company.id for c in client.get("/api/v1/contracts", headers=_headers(client, "acc@acme.nl")).json())


# ---- renewals & scheduler ----


def _signed_active(client, db_session, h, company_id, start, provider=None, **overrides):
    cid, token, _ = _sent_contract(client, h, company_id, provider=provider, create={"start_date": start.isoformat()}, **overrides)
    assert client.post(f"/api/v1/contracts/sign/{token}", json={"full_name": "Jan de Vries", "email": "jan@client.nl", "consent": True}).status_code == 200
    return db_session.get(Contract, cid)


def test_scheduler_activates_prepares_renewal_once_and_dedupes_reminders(client, db_session, tmp_storage):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    start = date.today() - timedelta(days=320)  # ends in ~45 days
    contract = _signed_active(client, db_session, h, company.id, start)
    db_session.refresh(contract)
    assert contract.status == ContractStatus.active and contract.renewal_disabled is False

    first = contract_scheduler.run_once(db_session)
    assert first["renewals_created"] == 1 and first["renewal_reminders"] == 1
    second = contract_scheduler.run_once(db_session)
    assert second["renewals_created"] == 0 and second["renewal_reminders"] == 0  # idempotent tick

    db_session.refresh(contract)
    assert contract.status == ContractStatus.renewal_due
    renewal = svc.existing_renewal(db_session, contract)
    assert renewal is not None and renewal.status == ContractStatus.draft and renewal.created_source == "renewal"
    assert renewal.start_date == contract.end_date + timedelta(days=1) and renewal.term_months == 12
    assert renewal.monthly_fee == contract.monthly_fee and renewal.signer_email == contract.signer_email  # terms carried over, not altered
    assert db_session.query(Contract).filter(Contract.renews_contract_id == contract.id).count() == 1
    reminders = {r.kind: r.status for r in db_session.query(ContractReminder).filter(ContractReminder.contract_id == contract.id)}
    assert reminders == {"renewal_60": "skipped_disabled"}  # 45 days left: only the 60-day threshold crossed; email automation off
    assert db_session.query(EmailOutbox).filter(EmailOutbox.template == "contract_renewal_upcoming").count() == 0

    # Admin-triggered renewal creation on the same contract returns the existing draft.
    again = client.post(f"/api/v1/contracts/{contract.id}/renewal", headers=h)
    assert again.status_code == 200 and again.json()["created"] is False and again.json()["contract"]["id"] == renewal.id

    # Crossing the next threshold sends exactly one more reminder.
    later = contract_scheduler.run_once(db_session, today=contract.end_date - timedelta(days=20))
    assert later["renewal_reminders"] == 1
    assert contract_scheduler.run_once(db_session, today=contract.end_date - timedelta(days=20))["renewal_reminders"] == 0
    kinds = sorted(r.kind for r in db_session.query(ContractReminder).filter(ContractReminder.contract_id == contract.id))
    assert kinds == ["renewal_30", "renewal_60"]

    # Expiry: an unsigned renewal is never treated as accepted.
    expired = contract_scheduler.run_once(db_session, today=contract.end_date + timedelta(days=1))
    assert expired["expired"] == 1
    db_session.refresh(contract)
    db_session.refresh(renewal)
    assert contract.status == ContractStatus.expired and renewal.status == ContractStatus.draft
    detail = client.get(f"/api/v1/contracts/{contract.id}", headers=h).json()
    assert detail["renewal_contract_id"] == renewal.id and detail["renewal_reference"] == renewal.reference
    assert client.get(f"/api/v1/contracts/{renewal.id}", headers=h).json()["renews_reference"] == contract.reference


def test_scheduler_emails_when_automation_enabled_and_renewal_signing_invitation(client, db_session, tmp_storage, fake_email, automation_on):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    contract = _signed_active(client, db_session, h, company.id, date.today() - timedelta(days=340), provider=fake_email)
    assert fake_email.sent  # signed notifications went out (automation on)
    fake_email.sent.clear()
    result = contract_scheduler.run_once(db_session)
    assert result["renewals_created"] == 1 and result["renewal_reminders"] == 1
    assert [m.to_email for m in fake_email.sent] == ["jan@client.nl"]
    assert "loopt af" in fake_email.sent[0].subject
    # ~24 days left: the 60-day threshold is marked superseded, the 30-day one is the single email sent.
    statuses = {r.kind: r.status for r in db_session.query(ContractReminder).filter(ContractReminder.contract_id == contract.id)}
    assert statuses == {"renewal_60": "skipped_superseded", "renewal_30": "sent"}
    assert db_session.query(ContractReminder).filter(ContractReminder.kind == "renewal_30").one().email_outbox_id is not None

    # Admin approves + sends the renewal: the signer receives a renewal signing request.
    renewal = svc.existing_renewal(db_session, contract)
    assert client.post(f"/api/v1/contracts/{renewal.id}/approve", headers=h).status_code == 200
    sent = client.post(f"/api/v1/contracts/{renewal.id}/send", headers=h)
    assert sent.status_code == 200 and sent.json()["email_sent"] is True and sent.json()["signing_link"] is None
    assert sent.json()["invitation"]["is_renewal"] is True
    assert "Verlengingsovereenkomst" in fake_email.sent[-1].subject
    assert db_session.query(EmailOutbox).filter(EmailOutbox.template == "contract_renewal_signing", EmailOutbox.status == "sent").count() == 1

    # Expiry notice goes out once.
    contract_scheduler.run_once(db_session, today=contract.end_date + timedelta(days=1))
    contract_scheduler.run_once(db_session, today=contract.end_date + timedelta(days=2))
    assert db_session.query(EmailOutbox).filter(EmailOutbox.template == "contract_expired").count() == 1


def test_non_renewal_and_termination(client, db_session, tmp_storage):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    contract = _signed_active(client, db_session, h, company.id, date.today() - timedelta(days=330))
    assert client.post(f"/api/v1/contracts/{contract.id}/non-renewal", headers=h, json={"disabled": True, "reason": "client moving abroad"}).status_code == 200
    assert contract_scheduler.run_once(db_session)["renewals_created"] == 0
    assert svc.existing_renewal(db_session, contract) is None

    terminated = client.post(f"/api/v1/contracts/{contract.id}/terminate", headers=h, json={"reason": "non-payment", "effective_date": date.today().isoformat()})
    assert terminated.status_code == 200
    body = terminated.json()
    assert body["status"] == "TERMINATED" and body["closure_reason"] == "non-payment" and body["termination_effective_date"] == date.today().isoformat()
    assert client.post(f"/api/v1/contracts/{contract.id}/terminate", headers=h).status_code == 409
    assert client.post(f"/api/v1/contracts/{contract.id}/renewal", headers=h).status_code == 409
    # Signed documents are preserved and still verify after termination.
    for v in db_session.query(ContractVersion).filter(ContractVersion.contract_id == contract.id):
        assert svc.verify_version(v)["valid"]
    assert db_session.query(AuditLog).filter(AuditLog.action == "terminate").count() == 1


def test_signing_reminder_reissues_link_once(client, db_session, tmp_storage, fake_email, automation_on):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    cid, token, _ = _sent_contract(client, h, company.id, provider=fake_email)
    inv = db_session.query(ContractSigningInvitation).one()
    inv.created_at = datetime.now(timezone.utc) - timedelta(days=8)
    db_session.commit()
    fake_email.sent.clear()
    assert contract_scheduler.run_once(db_session)["signing_reminders"] == 1
    assert contract_scheduler.run_once(db_session)["signing_reminders"] == 0
    assert len(fake_email.sent) == 1 and "Herinnering" in fake_email.sent[0].subject
    assert client.get(f"/api/v1/contracts/sign/{token}").status_code == 410  # old link replaced
    assert db_session.query(ContractSigningInvitation).filter(ContractSigningInvitation.status == SigningInvitationStatus.pending).count() == 1


def test_scheduler_advisory_lock_skips_concurrent_tick(client, db_session, test_session_local):
    _setup(db_session)
    holder = test_session_local()
    from sqlalchemy import text
    assert holder.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": contract_scheduler.ADVISORY_LOCK_KEY}).scalar() is True
    try:
        assert contract_scheduler.run_with_lock(test_session_local) is None
        assert client.post("/api/v1/contracts/scheduler/run", headers=_headers(client)).status_code == 409
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": contract_scheduler.ADVISORY_LOCK_KEY})
        holder.commit()
        holder.close()
    assert isinstance(contract_scheduler.run_with_lock(test_session_local), dict)


# ---- email delivery failures & retries ----


def test_email_retry_then_success_and_permanent_failure_visible(client, db_session, tmp_storage, fake_email):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    fake_email.fail_times = 2
    cid, token, body = _sent_contract(client, h, company.id, provider=fake_email)
    assert body["email_sent"] is True and body["signing_link"] is None
    row = db_session.query(EmailOutbox).filter(EmailOutbox.template == "contract_invitation").one()
    assert row.status == "sent" and row.attempts == 3  # two transient failures, then delivered

    fake_email.calls, fake_email.fail_times, fake_email.retryable = 0, 99, False
    detail = _ready_contract(client, h, company.id)
    sent = client.post(f"/api/v1/contracts/{detail['id']}/send", headers=h).json()
    assert sent["email_sent"] is True  # attempted...
    failed = db_session.query(EmailOutbox).filter(EmailOutbox.template == "contract_invitation", EmailOutbox.status == "failed").one()
    assert failed.attempts == 1  # ...non-retryable -> no retries
    assert client.get(f"/api/v1/contracts/{detail['id']}", headers=h).json()["invitations"][0]["email_status"] == "failed"
    # Recovery path: resend issues a new token and a new delivery attempt; no second contract or signature was created.
    fake_email.fail_times = 0
    resent = client.post(f"/api/v1/contracts/{detail['id']}/resend", headers=h).json()
    assert resent["email_sent"] is True
    assert db_session.query(Contract).count() == 2 and db_session.query(ContractSignature).count() == 0


# ---- templates, settings, localisation ----


def test_templates_settings_and_english_rendering(client, db_session, tmp_storage):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    versions = client.get("/api/v1/contracts/templates", headers=h).json()
    assert len(versions) == 1 and versions[0]["status"] == "DRAFT" and versions[0]["default_monthly_fee"] is None
    content = versions[0]["content"]
    content["en"]["clauses"][3]["body"] = "The fee amounts to {fee}, payable within {payment_terms_days} days. CUSTOM-EN"
    content["nl"]["clauses"][3]["body"] = "De vergoeding bedraagt {fee}. AANGEPAST-NL"
    created = client.post("/api/v1/contracts/templates", headers=h, json={"content": content, "default_services": versions[0]["default_services"], "default_payment_terms_days": 30, "default_notice_period_days": 60, "change_note": "reviewed by counsel"})
    assert created.status_code == 201 and created.json()["version_no"] == 2
    bad = client.post("/api/v1/contracts/templates", headers=h, json={"content": {"nl": content["nl"]}})
    assert bad.status_code == 422
    assert client.post(f"/api/v1/contracts/templates/{created.json()['id']}/approve", headers=h).status_code == 200
    statuses = {v["version_no"]: v["status"] for v in client.get("/api/v1/contracts/templates", headers=h).json()}
    assert statuses == {1: "DRAFT", 2: "APPROVED"}

    conf = client.put("/api/v1/contracts/settings", headers=h, json={"reminder_days": [14, 90, 30], "default_language": "en", "signing_link_expire_days": 7}).json()
    assert conf["reminder_days"] == [90, 30, 14] and conf["default_language"] == "en" and conf["feature_enabled"] is True and conf["email_automation_enabled"] is False
    assert client.put("/api/v1/contracts/settings", headers=h, json={"default_language": "fr"}).status_code == 422
    assert client.get("/api/v1/contracts/settings", headers=_headers(client, "acc@acme.nl")).status_code == 403

    # A new contract picks up the approved template, its defaults and the tenant language.
    approved_id = next(v["id"] for v in client.get("/api/v1/contracts/templates", headers=h).json() if v["status"] == "APPROVED")
    created = client.post("/api/v1/contracts", headers=h, json={"company_id": company.id}).json()
    assert created["language"] == "en" and created["payment_terms_days"] == 30 and created["notice_period_days"] == 60 and created["template_version_id"] == approved_id
    client.patch(f"/api/v1/contracts/{created['id']}", headers=h, json={"signer_name": "Jan de Vries", "signer_email": "jan@client.nl", "monthly_fee": "300"})
    approved = client.post(f"/api/v1/contracts/{created['id']}/approve", headers=h).json()
    version = approved["versions"][0]
    pdf = client.get(f"/api/v1/contracts/{created['id']}/versions/{version['id']}/pdf", headers=h).content
    text = "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))
    assert "Accounting Services Agreement" in text and "CUSTOM-EN" in text and "EUR 300.00 per month" in text and "AANGEPAST-NL" not in text
    sent = client.post(f"/api/v1/contracts/{created['id']}/send", headers=h).json()
    token = sent["signing_link"].rsplit("/sign/", 1)[1]
    page = client.get(f"/api/v1/contracts/sign/{token}").json()
    assert page["language"] == "en" and page["consent_text"].startswith("I, Jan de Vries") and "not a qualified" in page["assurance_notice"]
    inv = db_session.query(ContractSigningInvitation).filter(ContractSigningInvitation.contract_id == created["id"]).one()
    assert round((inv.expires_at - inv.created_at).total_seconds() / 86400) == 7
    outbox = db_session.query(EmailOutbox).filter(EmailOutbox.template == "contract_invitation").order_by(EmailOutbox.id.desc()).first()
    assert outbox.locale == "en" and outbox.subject.startswith("Agreement to sign")


def test_list_filters(client, db_session, tmp_storage):
    _, _, _, _, company = _setup(db_session)
    h = _headers(client)
    draft = client.post("/api/v1/contracts", headers=h, json={"company_id": company.id}).json()
    cid, token, _ = _sent_contract(client, h, company.id, create={"start_date": "2030-01-01"})
    rows = client.get("/api/v1/contracts", headers=h).json()
    assert {r["status"] for r in rows} == {"DRAFT", "SENT"} and rows[0]["company_name"] == "Client BV"
    assert [r["id"] for r in client.get("/api/v1/contracts", headers=h, params={"status": "SENT"}).json()] == [cid]
    assert [r["id"] for r in client.get("/api/v1/contracts", headers=h, params={"signing_status": "not_sent"}).json()] == [draft["id"]]
    assert client.get("/api/v1/contracts", headers=h, params={"expires_after": "2030-12-01"}).json()[0]["id"] == cid
    assert client.get("/api/v1/contracts", headers=h, params={"expires_before": "2029-01-01"}).json()[0]["id"] == draft["id"]
    assert client.get(f"/api/v1/contracts/{draft['id']}/preview.pdf", headers=h).headers["content-type"] == "application/pdf"
