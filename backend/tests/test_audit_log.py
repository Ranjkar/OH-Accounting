"""Phase 15: the Audit Log read API -- pagination, filtering, tenant
isolation, access restriction to owner/admin, and that sensitive fields
never reach a persisted audit row."""

from app.core.audit_redaction import REDACTED, redact
from app.core.security import hash_password
from app.models.audit_log import AuditLog
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


def _user(db_session, tenant, email, role):
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name=email.split("@")[0], role=role)
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
    accountant = _user(db_session, tenant, "accountant@acme.nl", UserRole.accountant)
    db_session.commit()
    return tenant, owner, accountant


def test_audit_log_requires_admin_or_owner(client, db_session):
    _setup(db_session)
    owner_resp = client.get("/api/v1/audit-log", headers=_login(client, "owner@acme.nl"))
    assert owner_resp.status_code == 200

    accountant_resp = client.get("/api/v1/audit-log", headers=_login(client, "accountant@acme.nl"))
    assert accountant_resp.status_code == 403


def test_audit_log_is_tenant_isolated(client, db_session):
    tenant, owner, accountant = _setup(db_session)
    other_tenant = _tenant(db_session, "Other Co")
    other_owner = _user(db_session, other_tenant, "owner@other.nl", UserRole.owner)
    db_session.add_all([
        AuditLog(tenant_id=tenant.id, user_id=owner.id, action="test_event_a", entity_type="user", entity_id=owner.id),
        AuditLog(tenant_id=other_tenant.id, user_id=other_owner.id, action="test_event_b", entity_type="user", entity_id=other_owner.id),
    ])
    db_session.commit()

    resp = client.get("/api/v1/audit-log", headers=_login(client, "owner@acme.nl"))
    actions = {item["action"] for item in resp.json()["items"]}
    assert "test_event_a" in actions
    assert "test_event_b" not in actions


def test_audit_log_pagination(client, db_session):
    tenant, owner, accountant = _setup(db_session)
    db_session.add_all([
        AuditLog(tenant_id=tenant.id, user_id=owner.id, action=f"bulk_event_{i}", entity_type="user", entity_id=owner.id)
        for i in range(25)
    ])
    db_session.commit()
    headers = _login(client, "owner@acme.nl")

    page1 = client.get("/api/v1/audit-log", params={"skip": 0, "limit": 10}, headers=headers).json()
    assert len(page1["items"]) == 10
    assert page1["total"] >= 25

    page2 = client.get("/api/v1/audit-log", params={"skip": 10, "limit": 10}, headers=headers).json()
    assert len(page2["items"]) == 10
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})


def test_audit_log_limit_is_capped(client, db_session):
    _setup(db_session)
    resp = client.get("/api/v1/audit-log", params={"limit": 10000}, headers=_login(client, "owner@acme.nl"))
    assert resp.status_code == 422  # exceeds the server-enforced max


def test_audit_log_filters_by_action_entity_type_and_user(client, db_session):
    tenant, owner, accountant = _setup(db_session)
    db_session.add_all([
        AuditLog(tenant_id=tenant.id, user_id=owner.id, action="role_change", entity_type="user", entity_id=accountant.id),
        AuditLog(tenant_id=tenant.id, user_id=accountant.id, action="create", entity_type="bank_account", entity_id=1),
    ])
    db_session.commit()
    headers = _login(client, "owner@acme.nl")

    by_action = client.get("/api/v1/audit-log", params={"action": "role_change"}, headers=headers).json()
    assert all(i["action"] == "role_change" for i in by_action["items"])
    assert len(by_action["items"]) >= 1

    by_entity = client.get("/api/v1/audit-log", params={"entity_type": "bank_account"}, headers=headers).json()
    assert all(i["entity_type"] == "bank_account" for i in by_entity["items"])

    by_user = client.get("/api/v1/audit-log", params={"user_id": accountant.id}, headers=headers).json()
    assert all(i["user_id"] == accountant.id for i in by_user["items"])


def test_audit_log_free_text_search(client, db_session):
    tenant, owner, accountant = _setup(db_session)
    db_session.add(AuditLog(tenant_id=tenant.id, user_id=owner.id, action="user_deactivated", entity_type="user", entity_id=accountant.id))
    db_session.commit()
    resp = client.get("/api/v1/audit-log", params={"q": "deactiv"}, headers=_login(client, "owner@acme.nl"))
    assert any("deactiv" in i["action"] for i in resp.json()["items"])


def test_audit_log_date_range_filter(client, db_session):
    tenant, owner, accountant = _setup(db_session)
    db_session.add(AuditLog(tenant_id=tenant.id, user_id=owner.id, action="dated_event", entity_type="user", entity_id=owner.id))
    db_session.commit()
    headers = _login(client, "owner@acme.nl")

    future_only = client.get("/api/v1/audit-log", params={"date_from": "2099-01-01"}, headers=headers).json()
    assert all(i["action"] != "dated_event" for i in future_only["items"])

    past_through_today = client.get("/api/v1/audit-log", params={"date_from": "2020-01-01"}, headers=headers).json()
    assert any(i["action"] == "dated_event" for i in past_through_today["items"])


def test_audit_log_includes_actor_detail(client, db_session):
    tenant, owner, accountant = _setup(db_session)
    db_session.add(AuditLog(tenant_id=tenant.id, user_id=owner.id, action="whoami_test", entity_type="user", entity_id=owner.id))
    db_session.commit()
    resp = client.get("/api/v1/audit-log", params={"action": "whoami_test"}, headers=_login(client, "owner@acme.nl"))
    entry = resp.json()["items"][0]
    assert entry["actor"]["email"] == "owner@acme.nl"


def test_role_change_audit_entry_has_before_and_after(client, db_session):
    tenant, owner, accountant = _setup(db_session)
    headers = _login(client, "owner@acme.nl")
    client.patch(f"/api/v1/users/{accountant.id}/role", json={"role": "viewer"}, headers=headers)

    resp = client.get("/api/v1/audit-log", params={"action": "role_change"}, headers=headers)
    entries = resp.json()["items"]
    assert len(entries) == 1
    assert entries[0]["before"] == {"role": "accountant"}
    assert entries[0]["after"] == {"role": "viewer"}
    assert entries[0]["entity_type"] == "user"
    assert entries[0]["entity_id"] == accountant.id


def test_invite_user_audit_entry_never_contains_the_raw_token(client, db_session):
    _, owner, accountant = _setup(db_session)
    headers = _login(client, "owner@acme.nl")
    create = client.post("/api/v1/users/invitations", json={"invited_email": "new@acme.nl", "intended_role": "viewer"}, headers=headers)
    raw_token = create.json()["raw_token"]

    resp = client.get("/api/v1/audit-log", params={"action": "invite_user"}, headers=headers)
    entry = resp.json()["items"][0]
    serialized = str(entry)
    assert raw_token not in serialized


def test_login_events_are_audited(client, db_session):
    tenant, owner, accountant = _setup(db_session)
    client.post("/api/v1/auth/login", json={"email": "owner@acme.nl", "password": "wrong-password"})
    headers = _login(client, "owner@acme.nl")  # a correct login

    resp = client.get("/api/v1/audit-log", headers=headers)
    actions = [i["action"] for i in resp.json()["items"]]
    assert "login_failed" in actions
    assert "login_success" in actions


def test_audit_actions_and_entity_types_endpoints(client, db_session):
    tenant, owner, accountant = _setup(db_session)
    db_session.add(AuditLog(tenant_id=tenant.id, user_id=owner.id, action="distinct_action_x", entity_type="distinct_entity_y", entity_id=1))
    db_session.commit()
    headers = _login(client, "owner@acme.nl")
    assert "distinct_action_x" in client.get("/api/v1/audit-log/actions", headers=headers).json()
    assert "distinct_entity_y" in client.get("/api/v1/audit-log/entity-types", headers=headers).json()


# ---- redaction (unit-level, no HTTP needed) ----


def test_redact_strips_every_known_sensitive_field():
    snapshot = {
        "hashed_password": "x", "mfa_secret_encrypted": b"y", "bsn_encrypted": b"z",
        "token_hash": "h", "encrypted_access_token": b"t", "iban": "NL00TEST0000000000",
        "api_key": "k", "role": "admin", "email": "a@b.com",
    }
    result = redact(snapshot)
    for sensitive_key in ("hashed_password", "mfa_secret_encrypted", "bsn_encrypted", "token_hash", "encrypted_access_token", "iban", "api_key"):
        assert result[sensitive_key] == REDACTED
    assert result["role"] == "admin"
    assert result["email"] == "a@b.com"


def test_redact_passes_through_none():
    assert redact(None) is None
