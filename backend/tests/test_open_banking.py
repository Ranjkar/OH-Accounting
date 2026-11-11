"""Phase 12 Open Banking: consent lifecycle, encrypted token storage, sync
dedup reuse, and disconnect -- all against StubOpenBankingProvider, the
only provider configured anywhere in this codebase (see
app/services/open_banking_provider.py's docstring for why no real
provider integration exists). Never claims a live bank connection."""

from app.core.security import hash_password
from app.models.banking import BankAccount
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.services import open_banking_provider


def _create_user(db_session, tenant_name="Acme Accounting", email="admin@acme.nl", role=UserRole.admin):
    tenant = db_session.query(Tenant).filter(Tenant.name == tenant_name).first()
    if tenant is None:
        tenant = Tenant(name=tenant_name)
        db_session.add(tenant)
        db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Test", role=role)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, email, password="secret123") -> dict:
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _setup(db_session, client, headers):
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    account_id = client.post(
        "/api/v1/bank-accounts", json={"company_id": company_id, "iban": "NL91ABNA0417164300", "account_name": "Main"}, headers=headers
    ).json()["id"]
    return company_id, account_id


def test_connect_returns_stub_authorization_url(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    _, account_id = _setup(db_session, client, headers)

    response = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "http://localhost:3000/banking/connect/callback"}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "stub"
    assert "stub_consent_id" in body["authorization_url"]


def test_full_connect_sync_disconnect_lifecycle(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    _, account_id = _setup(db_session, client, headers)

    client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "http://localhost:3000/banking/connect/callback"}, headers=headers)
    completed = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/callback", json={}, headers=headers)
    assert completed.status_code == 200, completed.text
    assert completed.json()["account"]["consent_status"] == "CONNECTED"
    assert completed.json()["account"]["provider_name"] == "stub"
    assert completed.json()["candidates"] == []

    sync = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/sync", headers=headers)
    assert sync.status_code == 200, sync.text
    assert sync.json()["source_format"] == "OPEN_BANKING"

    disconnected = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/disconnect", headers=headers)
    assert disconnected.status_code == 200
    assert disconnected.json()["consent_status"] == "REVOKED"


def test_sync_requires_connected_status(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    _, account_id = _setup(db_session, client, headers)

    response = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/sync", headers=headers)
    assert response.status_code == 409


def test_access_token_is_never_returned_in_plaintext(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    _, account_id = _setup(db_session, client, headers)
    client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "http://localhost:3000/banking/connect/callback"}, headers=headers)
    completed = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/callback", json={}, headers=headers)

    assert "encrypted_access_token" not in completed.json()
    assert "encrypted_refresh_token" not in completed.json()
    assert "stub-access-" not in str(completed.json())


def test_access_token_is_actually_encrypted_at_rest(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    _, account_id = _setup(db_session, client, headers)
    client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "http://localhost:3000/banking/connect/callback"}, headers=headers)
    client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/callback", json={}, headers=headers)

    db_session.commit()
    account = db_session.get(BankAccount, account_id)
    assert account.encrypted_access_token is not None
    assert b"stub-access-" not in account.encrypted_access_token  # ciphertext, not plaintext with a prefix we can grep


def test_viewer_cannot_initiate_connection(client, db_session):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id, account_id = _setup(db_session, client, headers_admin)

    viewer = User(tenant_id=admin.tenant_id, email="viewer@acme.nl", hashed_password=hash_password("secret123"), full_name="Viewer", role=UserRole.viewer)
    db_session.add(viewer)
    db_session.commit()
    from app.models.user import user_companies
    db_session.execute(user_companies.insert().values(user_id=viewer.id, company_id=company_id))
    db_session.commit()
    headers_viewer = _login(client, "viewer@acme.nl")

    response = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "https://x"}, headers=headers_viewer)
    assert response.status_code == 403


def test_stub_provider_is_the_only_configured_provider():
    open_banking_provider.reset_provider_cache()
    provider = open_banking_provider.get_open_banking_provider()
    assert provider.name == "stub"
