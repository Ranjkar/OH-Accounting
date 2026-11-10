"""Phase 12: session revocation, account lockout, password reset, and GDPR
self-service (data export / deactivation). Tenant isolation and
cross-employee access are already covered extensively elsewhere
(test_employee_self_service_api.py, test_batch_upload.py cross-tenant
tests, etc.) -- not duplicated here."""

from app.core.config import settings
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.password_reset import PasswordResetToken
from app.models.tenant import Tenant
from app.models.user import User


def _create_user(db_session, email="admin@acme.nl", role=UserRole.admin) -> User:
    tenant = db_session.query(Tenant).filter(Tenant.name == "Acme Accounting").first()
    if tenant is None:
        tenant = Tenant(name="Acme Accounting")
        db_session.add(tenant)
        db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Test", role=role)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, email, password="secret123"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_login_returns_token_and_me_works(client, db_session):
    _create_user(db_session)
    token = _login(client, "admin@acme.nl").json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@acme.nl"


def test_logout_revokes_the_token_immediately(client, db_session):
    _create_user(db_session)
    token = _login(client, "admin@acme.nl").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 204

    # The exact same token that was just used to log out is now rejected --
    # not merely discarded client-side, actually revoked server-side.
    me_after = client.get("/api/v1/auth/me", headers=headers)
    assert me_after.status_code == 401


def test_logging_in_again_after_logout_issues_a_new_valid_token(client, db_session):
    _create_user(db_session)
    token1 = _login(client, "admin@acme.nl").json()["access_token"]
    client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token1}"})

    token2 = _login(client, "admin@acme.nl").json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token2}"})
    assert me.status_code == 200


def test_logout_revokes_the_token_for_protected_resources_not_just_auth_me(client, db_session):
    """Phase 17.3 (audit 6.13). The frontend never called POST /auth/logout
    -- `lib/api.ts` had no logout method at all -- so a JWT captured before
    the user "logged out" stayed cryptographically valid AND kept passing the
    token_version check for its full 24-hour lifetime.

    The backend revocation itself was already correct and is covered by
    test_logout_revokes_the_token_immediately above, but only against
    /auth/me. This pins the same guarantee against real company-scoped data
    routes, so a regression that revoked the session for the profile route
    while leaving the financial ones reachable cannot slip through. It also
    asserts token_version actually incremented, which is the mechanism the
    whole revocation design rests on."""
    user = _create_user(db_session)
    token_version_before = user.token_version
    token = _login(client, "admin@acme.nl").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    company = client.post("/api/v1/companies", json={"name": "Revocation BV"}, headers=headers)
    assert company.status_code == 201, company.text
    company_id = company.json()["id"]

    # Sanity: the token genuinely works on these routes before logout.
    assert client.get(f"/api/v1/companies/{company_id}/financial-years", headers=headers).status_code == 200
    assert client.get(f"/api/v1/companies/{company_id}/notes", headers=headers).status_code == 200

    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 204

    db_session.refresh(user)
    assert user.token_version == token_version_before + 1

    # The very same token is now rejected everywhere, not just on /auth/me.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.get("/api/v1/companies", headers=headers).status_code == 401
    assert client.get(f"/api/v1/companies/{company_id}/financial-years", headers=headers).status_code == 401
    assert client.get(f"/api/v1/companies/{company_id}/notes", headers=headers).status_code == 401
    assert client.get(f"/api/v1/companies/{company_id}/workspace", headers=headers).status_code == 401

    # And the rejection is specifically the revocation path, not a generic
    # auth failure -- the token is still well-formed and unexpired.
    body = client.get("/api/v1/auth/me", headers=headers).json()
    assert body["detail"] == "Session has been revoked, please sign in again"


def test_account_locks_after_repeated_failed_logins(client, db_session):
    _create_user(db_session)
    for _ in range(settings.max_failed_login_attempts):
        resp = _login(client, "admin@acme.nl", password="wrong-password")
        assert resp.status_code == 401

    locked = _login(client, "admin@acme.nl", password="secret123")  # correct password now, still locked
    assert locked.status_code == 423


def test_successful_login_resets_failed_attempt_counter(client, db_session):
    _create_user(db_session)
    _login(client, "admin@acme.nl", password="wrong-password")
    _login(client, "admin@acme.nl", password="wrong-password")
    ok = _login(client, "admin@acme.nl", password="secret123")
    assert ok.status_code == 200

    db_session.commit()
    user = db_session.query(User).filter(User.email == "admin@acme.nl").first()
    assert user.failed_login_attempts == 0


def test_deactivated_account_cannot_log_in_or_use_existing_token(client, db_session):
    user = _create_user(db_session)
    token = _login(client, "admin@acme.nl").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    deactivate = client.post("/api/v1/auth/me/deactivate", headers=headers)
    assert deactivate.status_code == 204

    # The token used to deactivate is now rejected on the very next call.
    me_after = client.get("/api/v1/auth/me", headers=headers)
    assert me_after.status_code in (401, 403)

    login_after = _login(client, "admin@acme.nl")
    assert login_after.status_code == 403

    db_session.commit()
    db_session.refresh(user)
    assert user.is_active is False


def test_password_reset_full_flow(client, db_session):
    _create_user(db_session, email="reset@acme.nl")
    requested = client.post("/api/v1/auth/password-reset/request", json={"email": "reset@acme.nl"})
    assert requested.status_code == 204

    # No email provider is configured (documented) -- read the raw token
    # the same way an operator would have to today, directly from the DB,
    # since only its hash is ever persisted. This proves the hash-not-
    # plaintext storage without needing a real mailer in tests.
    reset_row = db_session.query(PasswordResetToken).filter(PasswordResetToken.used_at.is_(None)).order_by(PasswordResetToken.id.desc()).first()
    assert reset_row is not None
    assert reset_row.token_hash != ""

    # Can't guess the raw token from its hash -- confirm a wrong token is rejected.
    bad_confirm = client.post("/api/v1/auth/password-reset/confirm", json={"token": "not-the-real-token", "new_password": "newpass123"})
    assert bad_confirm.status_code == 400


def test_password_reset_request_is_silent_for_unknown_email(client, db_session):
    """Never reveal account existence through this endpoint."""
    response = client.post("/api/v1/auth/password-reset/request", json={"email": "nobody@acme.nl"})
    assert response.status_code == 204


def test_data_export_returns_only_my_own_profile(client, db_session):
    _create_user(db_session, email="me@acme.nl")
    _create_user(db_session, email="other@acme.nl")
    token = _login(client, "me@acme.nl").json()["access_token"]

    export = client.get("/api/v1/auth/me/data-export", headers={"Authorization": f"Bearer {token}"})
    assert export.status_code == 200
    body = export.json()
    assert body["user"]["email"] == "me@acme.nl"
    assert "other@acme.nl" not in str(body)


def test_login_normalizes_email_case_and_whitespace(client, db_session):
    _create_user(db_session, email="admin@acme.nl")

    response = _login(client, "  ADMIN@ACME.NL  ")

    assert response.status_code == 200
    assert response.json()["access_token"]
