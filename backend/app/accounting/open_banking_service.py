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


def complete_connection(db: Session, bank_account: BankAccount, provider: OpenBankingProvider, callback_params: dict) -> None:
    if bank_account.consent_status != BankConsentStatus.pending:
        raise OpenBankingError(f"Bank account consent is {bank_account.consent_status.value}, not PENDING -- call initiate_connection first")

    access_token, refresh_token = provider.complete_consent(bank_account.provider_account_id or "", callback_params)
    accounts = provider.list_accounts(access_token)
    if not accounts:
        raise OpenBankingError("Provider returned no accounts for this consent")
    matched = accounts[0]  # single-account connections only in this build; see docs/open-banking.md

    bank_account.encrypted_access_token = encrypt_token(access_token)
    bank_account.encrypted_refresh_token = encrypt_token(refresh_token)
    bank_account.provider_account_id = matched.provider_account_id
    bank_account.consent_status = BankConsentStatus.connected
    bank_account.consent_granted_at = datetime.now(timezone.utc)
    bank_account.consent_expires_at = datetime.now(timezone.utc) + timedelta(days=CONSENT_MAX_DAYS)
    db.flush()


def disconnect(db: Session, bank_account: BankAccount) -> None:
    """Revokes locally -- never calls the (stub) provider's own revoke
    endpoint since none exists to call yet. A real provider adapter would
    also need to call the provider's revocation endpoint here."""
    bank_account.consent_status = BankConsentStatus.revoked
    bank_account.encrypted_access_token = None
    bank_account.encrypted_refresh_token = None
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
