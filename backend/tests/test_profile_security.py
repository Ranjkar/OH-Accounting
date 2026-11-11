"""Phase 22: my profile, password change, verified email change, sessions."""
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.models.email_outbox import EmailOutbox
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User


def _user(db_session, email="me@acme.nl", role=UserRole.accountant):
    tenant = Tenant(name="Acme")
    db_session.add(tenant)
    db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Me Myself", role=role)
    db_session.add(user)
    db_session.commit()
    return user


def _token(client, email="me@acme.nl", password="secret123"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]


def test_profile_update_keeps_full_name_in_sync_and_never_touches_role(client, db_session):
    _user(db_session)
    h = {"Authorization": f"Bearer {_token(client)}"}
    r = client.patch("/api/v1/auth/me/profile", json={"first_name": "Sam", "last_name": "Jansen", "phone": "+31 6 1234", "country": "nl", "role": "owner"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_name"] == "Sam Jansen" and body["country"] == "NL" and body["role"] == "accountant"
    r = client.patch("/api/v1/auth/me/profile", json={"display_name": "Sammy"}, headers=h)
    assert r.json()["full_name"] == "Sammy"


def test_password_change_requires_current_enforces_policy_and_rotates_sessions(client, db_session):
    _user(db_session)
    old_token = _token(client)
    h = {"Authorization": f"Bearer {old_token}"}
    assert client.post("/api/v1/auth/me/password", json={"current_password": "wrong", "new_password": "longer-pass-1", "confirm_password": "longer-pass-1"}, headers=h).status_code == 400
    assert client.post("/api/v1/auth/me/password", json={"current_password": "secret123", "new_password": "short1", "confirm_password": "short1"}, headers=h).status_code == 400
    assert client.post("/api/v1/auth/me/password", json={"current_password": "secret123", "new_password": "onlyletterslong", "confirm_password": "onlyletterslong"}, headers=h).status_code == 400
    assert client.post("/api/v1/auth/me/password", json={"current_password": "secret123", "new_password": "longer-pass-1", "confirm_password": "different-1x"}, headers=h).status_code == 400
    r = client.post("/api/v1/auth/me/password", json={"current_password": "secret123", "new_password": "longer-pass-1", "confirm_password": "longer-pass-1"}, headers=h)
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    # Old session revoked, new one works, new password logs in.
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "me@acme.nl", "password": "longer-pass-1"}).status_code == 200
    # A security notification was recorded (no provider -> failed, but logged, never silently dropped).
    row = db_session.query(EmailOutbox).filter(EmailOutbox.template == "security_notification").first()
    assert row is not None and row.to_email == "me@acme.nl" and row.status == "failed" and "No email provider" in row.last_error


def test_email_change_is_two_step_and_verified(client, db_session, monkeypatch):
    from app.api.v1 import auth as auth_api

    _user(db_session)
    other = User(tenant_id=1, email="taken@acme.nl", hashed_password=hash_password("secret123"), full_name="T", role=UserRole.viewer)
    other.tenant_id = db_session.query(User).first().tenant_id
    db_session.add(other)
    db_session.commit()
    h = {"Authorization": f"Bearer {_token(client)}"}

    captured = {}
    real = auth_api.generate_password_reset_token

    def capture():
        raw, hashed = real()
        captured["raw"] = raw
        return raw, hashed

    monkeypatch.setattr(auth_api, "generate_password_reset_token", capture)

    assert client.post("/api/v1/auth/me/email/request-change", json={"new_email": "new@acme.nl", "current_password": "nope"}, headers=h).status_code == 400
    assert client.post("/api/v1/auth/me/email/request-change", json={"new_email": "taken@acme.nl", "current_password": "secret123"}, headers=h).status_code == 409
    r = client.post("/api/v1/auth/me/email/request-change", json={"new_email": "New@Acme.nl", "current_password": "secret123"}, headers=h)
    assert r.status_code == 200 and r.json()["pending_email"] == "new@acme.nl" and r.json()["email"] == "me@acme.nl"
    outbox = db_session.query(EmailOutbox).filter(EmailOutbox.template == "email_verification").one()
    assert outbox.to_email == "new@acme.nl"

    # Wrong token -> nothing changes.
    assert client.post("/api/v1/auth/email/confirm-change", json={"token": "bogus"}).status_code == 400
    # Right token -> email swapped, old sessions revoked, old address notified.
    assert client.post("/api/v1/auth/email/confirm-change", json={"token": captured["raw"]}).status_code == 204
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "new@acme.nl", "password": "secret123"}).status_code == 200
    notice = db_session.query(EmailOutbox).filter(EmailOutbox.template == "security_notification").one()
    assert notice.to_email == "me@acme.nl"
    # Token is single-use.
    assert client.post("/api/v1/auth/email/confirm-change", json={"token": captured["raw"]}).status_code == 400


def test_expired_email_change_token_is_rejected(client, db_session):
    user = _user(db_session)
    from app.core.security import generate_password_reset_token
    raw, hashed = generate_password_reset_token()
    user.pending_email = "late@acme.nl"
    user.email_change_token_hash = hashed
    user.email_change_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    assert client.post("/api/v1/auth/email/confirm-change", json={"token": raw}).status_code == 400


def test_revoke_other_sessions_keeps_this_device(client, db_session):
    _user(db_session)
    t1, t2 = _token(client), _token(client)
    r = client.post("/api/v1/auth/me/sessions/revoke-others", headers={"Authorization": f"Bearer {t1}"})
    assert r.status_code == 200
    fresh = r.json()["access_token"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


def test_password_reset_request_records_email_and_never_leaks_existence(client, db_session):
    _user(db_session)
    assert client.post("/api/v1/auth/password-reset/request", json={"email": "nobody@acme.nl"}).status_code == 204
    assert client.post("/api/v1/auth/password-reset/request", json={"email": "ME@acme.nl"}).status_code == 204
    rows = db_session.query(EmailOutbox).filter(EmailOutbox.template == "password_reset").all()
    assert [r.to_email for r in rows] == ["me@acme.nl"]
