"""Phase 13: optional per-user TOTP MFA (app.core.totp, app.core.mfa_crypto,
the /auth/mfa/* endpoints and the login flow's mfa_required branch)."""

from app.core.config import settings
from app.core.security import hash_password
from app.core.totp import totp_code
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User


def _create_user(db_session, email="mfa@acme.nl") -> User:
    tenant = db_session.query(Tenant).filter(Tenant.name == "Acme Accounting").first()
    if tenant is None:
        tenant = Tenant(name="Acme Accounting")
        db_session.add(tenant)
        db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Test", role=UserRole.admin)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, email, password="secret123", mfa_code=None):
    body = {"email": email, "password": password}
    if mfa_code is not None:
        body["mfa_code"] = mfa_code
    return client.post("/api/v1/auth/login", json=body)


def _token(client, email, password="secret123") -> str:
    return _login(client, email, password).json()["access_token"]


def test_login_has_no_mfa_requirement_by_default(client, db_session):
    _create_user(db_session)
    resp = _login(client, "mfa@acme.nl")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mfa_required"] is False
    assert body["access_token"]


def test_setup_then_enable_requires_a_valid_code(client, db_session):
    _create_user(db_session)
    token = _token(client, "mfa@acme.nl")
    headers = {"Authorization": f"Bearer {token}"}

    setup = client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert "otpauth://totp/" in setup.json()["provisioning_uri"]

    bad = client.post("/api/v1/auth/mfa/enable", headers=headers, json={"secret": secret, "code": "000000"})
    assert bad.status_code == 400

    good = client.post("/api/v1/auth/mfa/enable", headers=headers, json={"secret": secret, "code": totp_code(secret)})
    assert good.status_code == 204


def test_login_requires_code_once_mfa_is_enabled(client, db_session):
    user = _create_user(db_session)
    token = _token(client, "mfa@acme.nl")
    headers = {"Authorization": f"Bearer {token}"}
    secret = client.post("/api/v1/auth/mfa/setup", headers=headers).json()["secret"]
    client.post("/api/v1/auth/mfa/enable", headers=headers, json={"secret": secret, "code": totp_code(secret)})

    no_code = _login(client, "mfa@acme.nl")
    assert no_code.status_code == 200
    assert no_code.json()["mfa_required"] is True
    assert no_code.json()["access_token"] is None

    wrong_code = _login(client, "mfa@acme.nl", mfa_code="000000")
    assert wrong_code.status_code == 401

    db_session.refresh(user)
    right_code = _login(client, "mfa@acme.nl", mfa_code=totp_code(secret))
    assert right_code.status_code == 200
    assert right_code.json()["access_token"]


def test_disable_requires_a_valid_code_and_turns_mfa_off(client, db_session):
    _create_user(db_session)
    token = _token(client, "mfa@acme.nl")
    headers = {"Authorization": f"Bearer {token}"}
    secret = client.post("/api/v1/auth/mfa/setup", headers=headers).json()["secret"]
    client.post("/api/v1/auth/mfa/enable", headers=headers, json={"secret": secret, "code": totp_code(secret)})

    rejected = client.post("/api/v1/auth/mfa/disable", headers=headers, json={"code": "000000"})
    assert rejected.status_code == 401

    disabled = client.post("/api/v1/auth/mfa/disable", headers=headers, json={"code": totp_code(secret)})
    assert disabled.status_code == 204

    resp = _login(client, "mfa@acme.nl")
    assert resp.json()["mfa_required"] is False


def test_mfa_secret_is_encrypted_at_rest_not_stored_in_plaintext(client, db_session):
    _create_user(db_session)
    token = _token(client, "mfa@acme.nl")
    headers = {"Authorization": f"Bearer {token}"}
    secret = client.post("/api/v1/auth/mfa/setup", headers=headers).json()["secret"]
    client.post("/api/v1/auth/mfa/enable", headers=headers, json={"secret": secret, "code": totp_code(secret)})

    stored_user = db_session.query(User).filter(User.email == "mfa@acme.nl").first()
    assert stored_user.mfa_secret_encrypted is not None
    assert secret.encode() not in stored_user.mfa_secret_encrypted
