"""Open Banking consent + sync orchestration. Uses whichever provider
app.services.open_banking_provider.get_open_banking_provider() returns --
always StubOpenBankingProvider in this build (see that module's
docstring and docs/open-banking.md). Reuses the exact same
BankTransaction dedup path as file import (app.accounting.bank_import)
-- an Open Banking sync is just another source of the same
ParsedBankTransaction shape, never a parallel transaction pipeline."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting.bank_import import insert_rows_with_dedup
from app.accounting.bank_parsers import ParsedBankTransaction
from app.core.token_crypto import decrypt_token, encrypt_token
from app.models.banking import BankAccount, BankImportBatch
from app.models.enums import BankConsentStatus, BankSourceFormat
from app.services.open_banking_provider import CONSENT_MAX_DAYS, OpenBankingProvider, ProviderTransaction


class OpenBankingError(Exception):
    pass


def initiate_connection(db: Session, bank_account: BankAccount, provider: OpenBankingProvider, redirect_uri: str) -> str:
    consent = provider.initiate_consent(redirect_uri)
    bank_account.consent_status = BankConsentStatus.pending
    bank_account.provider_name = provider.name
    bank_account.provider_account_id = consent.consent_id  # placeholder until complete_connection resolves the real account id
    db.flush()
    return consent.authorization_url


def _mask_iban(iban: str) -> str:
    return iban if len(iban) <= 8 else f"{iban[:4]}…{iban[-4:]}"


def _finalise(bank_account: BankAccount, provider_account_id: str) -> None:
    bank_account.provider_account_id = provider_account_id
    bank_account.pending_provider_accounts = None
    bank_account.consent_status = BankConsentStatus.connected
    bank_account.consent_granted_at = datetime.now(timezone.utc)
    bank_account.consent_expires_at = datetime.now(timezone.utc) + timedelta(days=CONSENT_MAX_DAYS)
    bank_account.last_sync_error = None


def complete_connection(db: Session, bank_account: BankAccount, provider: OpenBankingProvider, callback_params: dict) -> list[dict]:
    """Exchanges the callback for tokens and resolves which provider account
    this BankAccount is. Returns the candidate list that still needs a
    choice (empty when the connection was finalised automatically):
    - exactly one account, or one whose IBAN matches ours -> connected;
    - several accounts, none matching -> tokens stored, status stays
      PENDING, candidates (no tokens, masked IBANs) returned for
      `select_account`."""
    if bank_account.consent_status != BankConsentStatus.pending:
        raise OpenBankingError(f"Bank account consent is {bank_account.consent_status.value}, not PENDING -- call initiate_connection first")

    access_token, refresh_token = provider.complete_consent(bank_account.provider_account_id or "", callback_params)
    accounts = provider.list_accounts(access_token)
    if not accounts:
        raise OpenBankingError("Provider returned no accounts for this consent")

    bank_account.encrypted_access_token = encrypt_token(access_token)
    bank_account.encrypted_refresh_token = encrypt_token(refresh_token)

    own_iban = (bank_account.iban or "").replace(" ", "").upper()
    matched = next((a for a in accounts if a.iban.replace(" ", "").upper() == own_iban), None)
    if matched is None and len(accounts) == 1:
        matched = accounts[0]
    if matched is not None:
        _finalise(bank_account, matched.provider_account_id)
        db.flush()
        return []

    candidates = [
        {"provider_account_id": a.provider_account_id, "iban_masked": _mask_iban(a.iban), "account_name": a.account_name, "currency": a.currency}
        for a in accounts
    ]
    bank_account.pending_provider_accounts = candidates
    db.flush()
    return candidates


def select_account(db: Session, bank_account: BankAccount, provider_account_id: str) -> None:
    if bank_account.consent_status != BankConsentStatus.pending or not bank_account.pending_provider_accounts:
        raise OpenBankingError("No account selection is pending for this bank account")
    if not any(c["provider_account_id"] == provider_account_id for c in bank_account.pending_provider_accounts):
        raise OpenBankingError("That account is not one of the accounts covered by this consent")
    _finalise(bank_account, provider_account_id)
    db.flush()


def refresh_status(db: Session, bank_account: BankAccount) -> None:
    """PSD2 consents lapse after at most 90 days: flips CONNECTED to EXPIRED
    once consent_expires_at has passed, so the UI asks for a reconnect
    instead of a sync that would fail at the bank."""
    if bank_account.consent_status == BankConsentStatus.connected and bank_account.consent_expires_at and bank_account.consent_expires_at < datetime.now(timezone.utc):
        bank_account.consent_status = BankConsentStatus.expired
        db.flush()


def disconnect(db: Session, bank_account: BankAccount) -> None:
    """Revokes locally -- never calls the (stub) provider's own revoke
    endpoint since none exists to call yet. A real provider adapter would
    also need to call the provider's revocation endpoint here."""
    bank_account.consent_status = BankConsentStatus.revoked
    bank_account.encrypted_access_token = None
    bank_account.encrypted_refresh_token = None
    bank_account.pending_provider_accounts = None
    db.flush()


def _to_parsed_row(t: ProviderTransaction) -> ParsedBankTransaction:
    return ParsedBankTransaction(
        external_transaction_id=t.provider_transaction_id,
        booking_date=datetime.fromisoformat(t.booking_date).date(),
        value_date=None,
        amount=Decimal(t.amount),
        currency=t.currency,
        counterparty_name=t.counterparty_name,
        counterparty_iban=None,
        payment_reference=None,
        description=t.description,
        raw_data={"provider_transaction_id": t.provider_transaction_id},
    )


def sync_account(db: Session, bank_account: BankAccount, provider: OpenBankingProvider, synced_by_user_id: int) -> BankImportBatch:
    refresh_status(db, bank_account)
    if bank_account.consent_status != BankConsentStatus.connected:
        raise OpenBankingError(f"Bank account is {bank_account.consent_status.value}, not CONNECTED")
    if bank_account.encrypted_access_token is None:
        raise OpenBankingError("No access token stored for this connection")

    batch = BankImportBatch(
        tenant_id=bank_account.tenant_id, company_id=bank_account.company_id, bank_account_id=bank_account.id,
        source_format=BankSourceFormat.open_banking, original_filename=f"open-banking-sync-{provider.name}",
        storage_path="", imported_by_user_id=synced_by_user_id,
    )
    db.add(batch)
    db.flush()

    try:
        access_token = decrypt_token(bank_account.encrypted_access_token)
        provider_transactions = provider.list_transactions(access_token, bank_account.provider_account_id or "", since=bank_account.last_synced_at)
        parsed_rows = [_to_parsed_row(t) for t in provider_transactions]
        insert_rows_with_dedup(db, bank_account, batch, parsed_rows, BankSourceFormat.open_banking)
    except Exception as exc:
        bank_account.last_sync_error = str(exc)[:500]
        db.flush()
        raise OpenBankingError(f"Sync failed: {exc}") from exc

    bank_account.last_synced_at = datetime.now(timezone.utc)
    bank_account.last_sync_error = None
    db.flush()
    return batch
