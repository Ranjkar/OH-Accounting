"""Phase 22: email provider abstraction, outbox log, retry, rate limit, admin page."""
import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.models.email_outbox import EmailOutbox
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.services import email_provider, email_service
from app.services.email_provider import EmailSendError, OutboundEmail


class FlakyProvider:
    name = "fake"

    def __init__(self, fail_times=0, retryable=True):
        self.fail_times, self.retryable, self.calls = fail_times, retryable, 0

    def send(self, message):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise EmailSendError("boom", retryable=self.retryable)
        return f"msg-{self.calls}"


@pytest.fixture()
def fake_provider(monkeypatch):
    provider = FlakyProvider()
    monkeypatch.setattr(email_provider, "_provider", provider)
    monkeypatch.setattr(email_service, "get_email_provider", lambda: provider)
    monkeypatch.setattr(email_service, "is_configured", lambda: True)
    monkeypatch.setattr(settings, "email_retry_base_delay_seconds", 0.0)
    yield provider
    email_provider.reset_provider_cache()


def _admin(db_session, platform=True):
    tenant = Tenant(name="Ops")
    db_session.add(tenant)
    db_session.flush()
    user = User(tenant_id=tenant.id, email="ops@acme.nl", hashed_password=hash_password("secret123"), full_name="Ops", role=UserRole.owner, is_platform_admin=platform)
    db_session.add(user)
    db_session.commit()
    return user


def _headers(client):
    token = client.post("/api/v1/auth/login", json={"email": "ops@acme.nl", "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_provider_factory_respects_setting(monkeypatch):
    email_provider.reset_provider_cache()
    monkeypatch.setattr(settings, "email_provider", "none")
    assert email_provider.get_email_provider().name == "none" and not email_provider.is_configured()
    email_provider.reset_provider_cache()
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example")
    assert email_provider.get_email_provider().name == "smtp" and email_provider.is_configured()
    email_provider.reset_provider_cache()
    monkeypatch.setattr(settings, "email_provider", "carrier-pigeon")
    with pytest.raises(RuntimeError):
        email_provider.get_email_provider()
    email_provider.reset_provider_cache()


def test_null_provider_logs_failed_row_without_raising(db_session):
    email_provider.reset_provider_cache()
    row, will_send = email_service.queue_email(db_session, None, to_email="a@b.nl", template="test", subject="s", html_body="<p>x</p>", text_body="x")
    db_session.commit()
    assert will_send is False and row.status == "failed" and "No email provider" in row.last_error


def test_retry_then_success_and_permanent_failure(db_session, fake_provider):
    fake_provider.fail_times = 2
    row, will_send = email_service.queue_email(db_session, None, to_email="a@b.nl", template="test", subject="s", html_body="<p>x</p>", text_body="x")
    assert will_send and row.status == "sent" and row.attempts == 3 and row.provider_message_id == "msg-3"

    row2 = EmailOutbox(to_email="c@d.nl", template="test", subject="s", locale="nl")
    db_session.add(row2)
    db_session.flush()
    fake_provider.fail_times, fake_provider.retryable, fake_provider.calls = 5, False, 0
    email_service.deliver(db_session, row2, OutboundEmail(to_email="c@d.nl", subject="s", html_body="x", text_body="x"))
    assert row2.status == "failed" and row2.attempts == 1  # no retry on a permanent error


def test_per_recipient_rate_limit(db_session, fake_provider, monkeypatch):
    monkeypatch.setattr(settings, "email_rate_limit_per_recipient_per_hour", 2)
    results = [email_service.queue_email(db_session, None, to_email="spam@b.nl", template="test", subject="s", html_body="x", text_body="x")[1] for _ in range(3)]
    assert results == [True, True, False]
    assert db_session.query(EmailOutbox).filter(EmailOutbox.status == "failed").one().last_error.startswith("Rate limit")


def test_admin_status_test_and_outbox_are_platform_admin_only(client, db_session, fake_provider):
    _admin(db_session)
    h = _headers(client)
    status_body = client.get("/api/v1/admin/email/status", headers=h).json()
    assert set(status_body) >= {"provider", "configured", "from_address", "dns", "last_24h"}
    assert "resend_api_key" not in str(status_body).lower() and "smtp_password" not in str(status_body).lower()
    r = client.post("/api/v1/admin/email/test", json={}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "sent" and r.json()["to_email"] == "ops@acme.nl"
    assert client.get("/api/v1/admin/email/outbox", headers=h).json()[0]["template"] == "test"

    # Tenant owner without platform flag: forbidden.
    other_tenant = Tenant(name="T2")
    db_session.add(other_tenant)
    db_session.flush()
    db_session.add(User(tenant_id=other_tenant.id, email="owner@t2.nl", hashed_password=hash_password("secret123"), full_name="O", role=UserRole.owner))
    db_session.commit()
    token = client.post("/api/v1/auth/login", json={"email": "owner@t2.nl", "password": "secret123"}).json()["access_token"]
    assert client.get("/api/v1/admin/email/status", headers={"Authorization": f"Bearer {token}"}).status_code == 403
