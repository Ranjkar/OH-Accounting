"""Phase 22: bank connection wizard -- catalogue, redirect guard, account selection, expiry."""
from datetime import datetime, timedelta, timezone

from app.models.banking import BankAccount
from app.models.enums import BankConsentStatus
from app.services import open_banking_provider
from app.services.open_banking_provider import ProviderAccount, StubOpenBankingProvider
from tests.test_open_banking import _create_user, _login, _setup


class MultiAccountStub(StubOpenBankingProvider):
    def list_accounts(self, access_token):
        return [
            ProviderAccount("acct-a", "NL00STUB0000000001", "Savings", "EUR"),
            ProviderAccount("acct-b", "NL00STUB0000000002", "Current", "EUR"),
        ]


def test_catalogue_and_status(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    status_body = client.get("/api/v1/open-banking/status", headers=headers).json()
    assert status_body == {"provider": "stub", "is_sandbox": True, "live_connectivity": False}
    banks = client.get("/api/v1/open-banking/banks?q=rabo", headers=headers).json()
    assert [b["id"] for b in banks["banks"]] == ["rabobank"] and banks["banks"][0]["sandbox"] is True
    assert len(client.get("/api/v1/open-banking/banks", headers=headers).json()["banks"]) >= 10


def test_connect_rejects_foreign_redirect_and_unknown_bank(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    _, account_id = _setup(db_session, client, headers)
    r = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "https://evil.example/cb"}, headers=headers)
    assert r.status_code == 400
    r = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "http://localhost:3000/banking/connect/callback", "bank_id": "nope"}, headers=headers)
    assert r.status_code == 400
    r = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "http://localhost:3000/banking/connect/callback", "bank_id": "ing"}, headers=headers)
    assert r.status_code == 200 and r.json()["is_sandbox"] is True


def test_multi_account_consent_requires_selection(client, db_session, monkeypatch):
    monkeypatch.setattr(open_banking_provider, "_provider", MultiAccountStub())
    try:
        _create_user(db_session)
        headers = _login(client, "admin@acme.nl")
        _, account_id = _setup(db_session, client, headers)
        client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "http://localhost:3000/banking/connect/callback"}, headers=headers)
        r = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/callback", json={"callback_params": {}}, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["account"]["consent_status"] == "PENDING"
        assert [c["provider_account_id"] for c in body["candidates"]] == ["acct-a", "acct-b"]
        assert body["candidates"][0]["iban_masked"] == "NL00…0001"  # never the full IBAN of someone else's account
        # Sync must not run before an account is chosen; a non-candidate is refused.
        assert client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/sync", headers=headers).status_code == 409
        assert client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/select-account", json={"provider_account_id": "acct-zzz"}, headers=headers).status_code == 409
        r = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/select-account", json={"provider_account_id": "acct-b"}, headers=headers)
        assert r.status_code == 200 and r.json()["consent_status"] == "CONNECTED" and r.json()["pending_provider_accounts"] is None
        account = db_session.get(BankAccount, account_id)
        assert account.provider_account_id == "acct-b"
    finally:
        open_banking_provider.reset_provider_cache()


def test_expired_consent_is_reported_and_reconnectable(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, account_id = _setup(db_session, client, headers)
    client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "http://localhost:3000/banking/connect/callback"}, headers=headers)
    client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/callback", json={"callback_params": {}}, headers=headers)
    account = db_session.get(BankAccount, account_id)
    account.consent_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    listed = client.get(f"/api/v1/bank-accounts?company_id={company_id}", headers=headers).json()[0]
    assert listed["consent_status"] == "EXPIRED"
    assert client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/sync", headers=headers).status_code == 409
    # Reconnect starts a fresh consent.
    r = client.post(f"/api/v1/bank-accounts/{account_id}/open-banking/connect", json={"redirect_uri": "http://localhost:3000/banking/connect/callback"}, headers=headers)
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(BankAccount, account_id).consent_status == BankConsentStatus.pending


def test_unknown_provider_setting_refuses_to_start(monkeypatch):
    from app.core.config import settings
    open_banking_provider.reset_provider_cache()
    monkeypatch.setattr(settings, "open_banking_provider", "gocardless")
    try:
        open_banking_provider.get_open_banking_provider()
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
    finally:
        open_banking_provider.reset_provider_cache()
