"""Real sandbox integration test against KVK's own published test
environment (api.kvk.nl/test) -- not a mock. Requires network access;
skips gracefully (not a failure) if the sandbox is unreachable from the
test environment, since that's an infrastructure fact, not a code bug."""

import httpx
import pytest

from app.core.security import hash_password
from app.models.company import Company
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.services import kvk_provider


def _sandbox_reachable() -> bool:
    try:
        httpx.get(f"{kvk_provider.KVK_TEST_BASE_URL}/basisprofielen/90003942", headers={"apikey": kvk_provider.KVK_TEST_API_KEY}, timeout=5.0)
        return True
    except httpx.HTTPError:
        return False


skip_if_unreachable = pytest.mark.skipif(not _sandbox_reachable(), reason="KVK test sandbox not reachable from this environment")


def _create_user(db_session) -> User:
    tenant = Tenant(name="Acme Accounting")
    db_session.add(tenant)
    db_session.flush()
    user = User(tenant_id=tenant.id, email="admin@acme.nl", hashed_password=hash_password("secret123"), full_name="Admin", role=UserRole.admin)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client):
    token = client.post("/api/v1/auth/login", json={"email": "admin@acme.nl", "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@skip_if_unreachable
def test_kvk_provider_direct_sandbox_call():
    """Exercises the real HTTP call against KVK's published test key and
    a known test KVK number from their own documentation example."""
    kvk_provider.reset_provider_cache()
    provider = kvk_provider.get_kvk_provider()
    result = provider.lookup_basisprofiel("90003942")
    assert result.kvk_number == "90003942"
    assert result.name
    assert result.is_test_data is True


@skip_if_unreachable
def test_kvk_lookup_endpoint_sandbox_verified(client, db_session):
    _create_user(db_session)
    headers = _login(client)
    response = client.get("/api/v1/kvk/lookup/90003942", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kvk_number"] == "90003942"
    assert body["is_test_data"] is True


@skip_if_unreachable
def test_kvk_lookup_unknown_number_returns_404(client, db_session):
    _create_user(db_session)
    headers = _login(client)
    response = client.get("/api/v1/kvk/lookup/00000000", headers=headers)
    assert response.status_code == 404


@skip_if_unreachable
def test_verify_company_against_real_sandbox_record(client, db_session):
    user = _create_user(db_session)
    kvk_provider.reset_provider_cache()
    real_name = kvk_provider.get_kvk_provider().lookup_basisprofiel("90003942").name
    company = Company(tenant_id=user.tenant_id, name=real_name, kvk_number="90003942")
    db_session.add(company)
    db_session.commit()

    headers = _login(client)
    response = client.get(f"/api/v1/kvk/verify/{company.id}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name_matches"] is True
    assert body["kvk_number"] == "90003942"


@skip_if_unreachable
def test_verify_company_flags_a_name_mismatch(client, db_session):
    user = _create_user(db_session)
    company = Company(tenant_id=user.tenant_id, name="Totally Unrelated Name Ltd", kvk_number="90003942")
    db_session.add(company)
    db_session.commit()

    headers = _login(client)
    response = client.get(f"/api/v1/kvk/verify/{company.id}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["name_matches"] is False


def test_verify_company_without_kvk_number_is_a_client_error(client, db_session):
    user = _create_user(db_session)
    company = Company(tenant_id=user.tenant_id, name="No KVK Yet B.V.", kvk_number=None)
    db_session.add(company)
    db_session.commit()

    headers = _login(client)
    response = client.get(f"/api/v1/kvk/verify/{company.id}", headers=headers)
    assert response.status_code == 400
