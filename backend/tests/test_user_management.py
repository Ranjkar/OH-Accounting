"""Phase 15: tenant user management -- list/invite/accept/role-change/
activate/deactivate/revoke-sessions, plus the authorization rules that
make this safe (self-escalation prevention, owner-only owner/admin
grants, last-owner protection, tenant isolation)."""

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User


def _tenant(db_session, name="Acme Accounting"):
    tenant = db_session.query(Tenant).filter(Tenant.name == name).first()
    if tenant is None:
        tenant = Tenant(name=name)
        db_session.add(tenant)
        db_session.flush()
    return tenant


def _user(db_session, tenant, email, role, is_active=True):
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name=email.split("@")[0], role=role, is_active=is_active)
    db_session.add(user)
    db_session.flush()
    return user


def _login(client, email, password="secret123") -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _setup(db_session):
    tenant = _tenant(db_session)
    owner = _user(db_session, tenant, "owner@acme.nl", UserRole.owner)
    admin = _user(db_session, tenant, "admin@acme.nl", UserRole.admin)
    accountant = _user(db_session, tenant, "accountant@acme.nl", UserRole.accountant)
    viewer = _user(db_session, tenant, "viewer@acme.nl", UserRole.viewer)
    db_session.commit()
    return tenant, owner, admin, accountant, viewer


# ---- listing / access control ----


def test_list_users_requires_admin_or_owner(client, db_session):
    _setup(db_session)
    owner_resp = client.get("/api/v1/users", headers=_login(client, "owner@acme.nl"))
    assert owner_resp.status_code == 200
    emails = {u["email"] for u in owner_resp.json()}
    assert emails == {"owner@acme.nl", "admin@acme.nl", "accountant@acme.nl", "viewer@acme.nl"}

    admin_resp = client.get("/api/v1/users", headers=_login(client, "admin@acme.nl"))
    assert admin_resp.status_code == 200

    accountant_resp = client.get("/api/v1/users", headers=_login(client, "accountant@acme.nl"))
    assert accountant_resp.status_code == 403

    viewer_resp = client.get("/api/v1/users", headers=_login(client, "viewer@acme.nl"))
    assert viewer_resp.status_code == 403


def test_users_are_tenant_isolated(client, db_session):
    tenant, owner, *_ = _setup(db_session)
    other_tenant = _tenant(db_session, "Other Co")
    _user(db_session, other_tenant, "owner@other.nl", UserRole.owner)
    db_session.commit()

    resp = client.get("/api/v1/users", headers=_login(client, "owner@acme.nl"))
    emails = {u["email"] for u in resp.json()}
    assert "owner@other.nl" not in emails


def test_cannot_fetch_another_tenants_user_by_id(client, db_session):
    tenant, owner, *_ = _setup(db_session)
    other_tenant = _tenant(db_session, "Other Co")
    outsider = _user(db_session, other_tenant, "owner@other.nl", UserRole.owner)
    db_session.commit()

    resp = client.get(f"/api/v1/users/{outsider.id}", headers=_login(client, "owner@acme.nl"))
    assert resp.status_code == 404


# ---- role changes: escalation rules ----


def test_cannot_change_own_role(client, db_session):
    _, owner, *_ = _setup(db_session)
    resp = client.patch(
        f"/api/v1/users/{owner.id}/role", json={"role": "admin"}, headers=_login(client, "owner@acme.nl")
    )
    assert resp.status_code == 403
    assert "own role" in resp.json()["detail"]


def test_admin_cannot_grant_admin_or_owner(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    headers = _login(client, "admin@acme.nl")

    to_admin = client.patch(f"/api/v1/users/{accountant.id}/role", json={"role": "admin"}, headers=headers)
    assert to_admin.status_code == 403

    to_owner = client.patch(f"/api/v1/users/{accountant.id}/role", json={"role": "owner"}, headers=headers)
    assert to_owner.status_code == 403


def test_admin_can_change_accountant_to_viewer(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    resp = client.patch(f"/api/v1/users/{accountant.id}/role", json={"role": "viewer"}, headers=_login(client, "admin@acme.nl"))
    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"


def test_owner_can_grant_admin(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    resp = client.patch(f"/api/v1/users/{accountant.id}/role", json={"role": "admin"}, headers=_login(client, "owner@acme.nl"))
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_owner_can_demote_another_owner_when_a_third_remains_as_actor(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    second_owner = _user(db_session, owner.tenant, "owner2@acme.nl", UserRole.owner)
    db_session.commit()

    resp = client.patch(f"/api/v1/users/{second_owner.id}/role", json={"role": "admin"}, headers=_login(client, "owner@acme.nl"))
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_admin_cannot_change_an_owners_role_even_downward(client, db_session):
    """An admin touching an owner's role at all -- even "just" demoting
    them to viewer -- is blocked, not only the upward-escalation case.
    Only an owner may change another owner's (or admin's) role."""
    _, owner, admin, accountant, viewer = _setup(db_session)
    resp = client.patch(f"/api/v1/users/{owner.id}/role", json={"role": "viewer"}, headers=_login(client, "admin@acme.nl"))
    assert resp.status_code == 403


def test_cannot_assign_legacy_roles_via_role_endpoint(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    resp = client.patch(f"/api/v1/users/{accountant.id}/role", json={"role": "customer"}, headers=_login(client, "owner@acme.nl"))
    assert resp.status_code == 400


# ---- activate / deactivate ----


def test_cannot_deactivate_self(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    resp = client.post(f"/api/v1/users/{admin.id}/deactivate", headers=_login(client, "admin@acme.nl"))
    assert resp.status_code == 400


def test_deactivate_revokes_sessions_and_blocks_login(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    viewer_headers = _login(client, "viewer@acme.nl")

    resp = client.post(f"/api/v1/users/{viewer.id}/deactivate", headers=_login(client, "owner@acme.nl"))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # The token issued before deactivation is now rejected (token_version bump).
    still_using_old_token = client.get("/api/v1/auth/me", headers=viewer_headers)
    assert still_using_old_token.status_code in (401, 403)

    # And a fresh login attempt is rejected outright.
    relogin = client.post("/api/v1/auth/login", json={"email": "viewer@acme.nl", "password": "secret123"})
    assert relogin.status_code == 403


def test_cannot_deactivate_the_last_active_owner(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    resp = client.post(f"/api/v1/users/{owner.id}/deactivate", headers=_login(client, "admin@acme.nl"))
    assert resp.status_code == 409


def test_activate_reactivates_a_deactivated_user(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    client.post(f"/api/v1/users/{viewer.id}/deactivate", headers=_login(client, "owner@acme.nl"))
    resp = client.post(f"/api/v1/users/{viewer.id}/activate", headers=_login(client, "owner@acme.nl"))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True
    relogin = client.post("/api/v1/auth/login", json={"email": "viewer@acme.nl", "password": "secret123"})
    assert relogin.status_code == 200


def test_revoke_sessions_without_deactivating(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    viewer_headers = _login(client, "viewer@acme.nl")

    resp = client.post(f"/api/v1/users/{viewer.id}/revoke-sessions", headers=_login(client, "admin@acme.nl"))
    assert resp.status_code == 204

    old_token_rejected = client.get("/api/v1/auth/me", headers=viewer_headers)
    assert old_token_rejected.status_code == 401

    # Still active -- a fresh login works fine.
    relogin = client.post("/api/v1/auth/login", json={"email": "viewer@acme.nl", "password": "secret123"})
    assert relogin.status_code == 200


def test_non_admin_cannot_activate_deactivate_or_change_roles(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    headers = _login(client, "accountant@acme.nl")
    assert client.post(f"/api/v1/users/{viewer.id}/deactivate", headers=headers).status_code == 403
    assert client.post(f"/api/v1/users/{viewer.id}/activate", headers=headers).status_code == 403
    assert client.patch(f"/api/v1/users/{viewer.id}/role", json={"role": "admin"}, headers=headers).status_code == 403
    assert client.post(f"/api/v1/users/{viewer.id}/revoke-sessions", headers=headers).status_code == 403


# ---- invitations: create / list / revoke / accept ----


def test_admin_can_invite_accountant_but_not_owner(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    headers = _login(client, "admin@acme.nl")

    ok = client.post("/api/v1/users/invitations", json={"invited_email": "new@acme.nl", "intended_role": "accountant"}, headers=headers)
    assert ok.status_code == 201
    assert ok.json()["invitation"]["status"] == "PENDING"

    blocked = client.post("/api/v1/users/invitations", json={"invited_email": "new-owner@acme.nl", "intended_role": "owner"}, headers=headers)
    assert blocked.status_code == 403


def test_owner_can_invite_admin(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    resp = client.post("/api/v1/users/invitations", json={"invited_email": "new-admin@acme.nl", "intended_role": "admin"}, headers=_login(client, "owner@acme.nl"))
    assert resp.status_code == 201


def test_invitation_accept_creates_account_and_logs_in(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    create = client.post(
        "/api/v1/users/invitations",
        json={"invited_email": "new@acme.nl", "intended_role": "accountant"},
        headers=_login(client, "owner@acme.nl"),
    )
    token = create.json()["raw_token"]

    accept = client.post(
        "/api/v1/users/invitations/accept",
        json={"token": token, "full_name": "New Person", "password": "brandnewpassword123"},
    )
    assert accept.status_code == 200, accept.text
    assert accept.json()["email"] == "new@acme.nl"
    assert accept.json()["role"] == "accountant"

    login = client.post("/api/v1/auth/login", json={"email": "new@acme.nl", "password": "brandnewpassword123"})
    assert login.status_code == 200


def test_invitation_cannot_be_accepted_twice(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    create = client.post(
        "/api/v1/users/invitations", json={"invited_email": "new@acme.nl", "intended_role": "viewer"}, headers=_login(client, "owner@acme.nl")
    )
    token = create.json()["raw_token"]
    client.post("/api/v1/users/invitations/accept", json={"token": token, "full_name": "A", "password": "firstpassword123"})

    second = client.post("/api/v1/users/invitations/accept", json={"token": token, "full_name": "B", "password": "secondpassword123"})
    assert second.status_code == 409


def test_revoked_invitation_cannot_be_accepted(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    create = client.post(
        "/api/v1/users/invitations", json={"invited_email": "new@acme.nl", "intended_role": "viewer"}, headers=_login(client, "owner@acme.nl")
    )
    invitation_id = create.json()["invitation"]["id"]
    token = create.json()["raw_token"]

    revoke = client.post(f"/api/v1/users/invitations/{invitation_id}/revoke", headers=_login(client, "owner@acme.nl"))
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "REVOKED"

    accept = client.post("/api/v1/users/invitations/accept", json={"token": token, "full_name": "A", "password": "somepassword123"})
    assert accept.status_code == 409


def test_cannot_invite_an_email_that_already_has_an_account(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    resp = client.post(
        "/api/v1/users/invitations", json={"invited_email": "viewer@acme.nl", "intended_role": "accountant"}, headers=_login(client, "owner@acme.nl")
    )
    assert resp.status_code == 409


def test_invitation_with_invalid_token_is_rejected(client, db_session):
    _setup(db_session)
    resp = client.post("/api/v1/users/invitations/accept", json={"token": "not-a-real-token", "full_name": "X", "password": "whatever12345"})
    assert resp.status_code == 404


def test_accountant_cannot_invite_users(client, db_session):
    _, owner, admin, accountant, viewer = _setup(db_session)
    resp = client.post(
        "/api/v1/users/invitations", json={"invited_email": "new@acme.nl", "intended_role": "viewer"}, headers=_login(client, "accountant@acme.nl")
    )
    assert resp.status_code == 403
