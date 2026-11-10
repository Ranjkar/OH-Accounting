"""Phase 16: per-user language preference -- personal override vs. tenant
default, persistence, and validation."""

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User


def _setup(db_session, default_locale="nl"):
    tenant = Tenant(name="Acme Accounting", default_locale=default_locale)
    db_session.add(tenant)
    db_session.flush()
    user = User(tenant_id=tenant.id, email="owner@acme.nl", hashed_password=hash_password("secret123"), full_name="Owner", role=UserRole.owner)
    db_session.add(user)
    db_session.commit()
    return tenant, user


def _login(client, email="owner@acme.nl", password="secret123") -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_new_tenant_defaults_to_dutch(db_session):
    tenant = Tenant(name="No locale specified")
    db_session.add(tenant)
    db_session.commit()
    assert tenant.default_locale == "nl"


def test_new_user_has_no_personal_override_and_inherits_tenant_default(client, db_session):
    _setup(db_session, default_locale="en")
    me = client.get("/api/v1/auth/me", headers=_login(client))
    assert me.json()["locale"] is None
    assert me.json()["tenant_default_locale"] == "en"


def test_user_can_set_a_personal_override(client, db_session):
    _setup(db_session, default_locale="nl")
    headers = _login(client)
    resp = client.patch("/api/v1/auth/me/locale", json={"locale": "ar"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["locale"] == "ar"
    assert resp.json()["tenant_default_locale"] == "nl"

    # Persists across a fresh login (new token, same account).
    me = client.get("/api/v1/auth/me", headers=_login(client))
    assert me.json()["locale"] == "ar"


def test_user_can_clear_their_override_to_revert_to_tenant_default(client, db_session):
    _setup(db_session)
    headers = _login(client)
    client.patch("/api/v1/auth/me/locale", json={"locale": "fa"}, headers=headers)
    cleared = client.patch("/api/v1/auth/me/locale", json={"locale": None}, headers=headers)
    assert cleared.json()["locale"] is None


def test_invalid_locale_code_is_rejected(client, db_session):
    _setup(db_session)
    headers = _login(client)
    resp = client.patch("/api/v1/auth/me/locale", json={"locale": "xx"}, headers=headers)
    assert resp.status_code == 400


def test_changing_locale_never_touches_tenant_default(client, db_session):
    tenant, _ = _setup(db_session, default_locale="nl")
    headers = _login(client)
    client.patch("/api/v1/auth/me/locale", json={"locale": "en"}, headers=headers)
    db_session.refresh(tenant)
    assert tenant.default_locale == "nl"
