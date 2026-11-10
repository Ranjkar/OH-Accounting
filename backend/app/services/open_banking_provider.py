"""Open Banking (PSD2 AISP) provider abstraction.

No authorised Account Information Service Provider agreement or
credentials exist for this project (see docs/open-banking.md for the
provider evaluation -- GoCardless Bank Account Data and Tink were
researched as candidates, but DNB/EBA authorisation for Dutch business
accounts was NOT independently re-verified against the live register
this session, and no API credentials were obtained). Building a "real"
HTTP client against an unverified, uncredentialed API would mean
guessing its request/response shape -- exactly what this project's
conventions prohibit ("do not invent endpoints").

What IS implemented: the provider interface every real adapter would
need to satisfy, and a StubOpenBankingProvider generating clearly-
labelled synthetic data for development/testing, following the exact
same pattern as app/services/ai_provider.py's Claude/Stub split.
Swapping in a real provider later means writing one new class, no
changes to callers.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

logger = logging.getLogger(__name__)

# PSD2 RTS on Strong Customer Authentication: 90 days is the standard
# maximum consent re-authentication interval across providers.
CONSENT_MAX_DAYS = 90


@dataclass
class ConsentResult:
    consent_id: str
    authorization_url: str
    expires_at: datetime


@dataclass
class ProviderAccount:
    provider_account_id: str
    iban: str
    account_name: str
    currency: str


@dataclass
class ProviderTransaction:
    provider_transaction_id: str
    booking_date: str
    amount: str
    currency: str
    counterparty_name: str | None
    description: str | None


class OpenBankingProvider(Protocol):
    name: str

    def initiate_consent(self, redirect_uri: str) -> ConsentResult: ...
    def complete_consent(self, consent_id: str, callback_params: dict) -> tuple[str, str]:
        """Returns (access_token, refresh_token) -- raw, to be encrypted by
        the caller (app.core.token_crypto) before storage. Never stores or
        logs a raw token itself."""
        ...
    def list_accounts(self, access_token: str) -> list[ProviderAccount]: ...
    def list_transactions(self, access_token: str, provider_account_id: str, since: datetime | None = None) -> list[ProviderTransaction]: ...


class StubOpenBankingProvider:
    """Deterministic, clearly-synthetic data for development and tests --
    never presented as a real bank connection. Every identifier is
    prefixed "stub-" so it can never be confused with a real provider's
    id in a log or support ticket."""

    name = "stub"

    def initiate_consent(self, redirect_uri: str) -> ConsentResult:
        consent_id = f"stub-consent-{secrets.token_hex(8)}"
        return ConsentResult(
            consent_id=consent_id,
            authorization_url=f"{redirect_uri}?stub_consent_id={consent_id}",
            expires_at=datetime.now(timezone.utc) + timedelta(days=CONSENT_MAX_DAYS),
        )

    def complete_consent(self, consent_id: str, callback_params: dict) -> tuple[str, str]:
        return f"stub-access-{secrets.token_hex(16)}", f"stub-refresh-{secrets.token_hex(16)}"

    def list_accounts(self, access_token: str) -> list[ProviderAccount]:
        return [ProviderAccount(provider_account_id="stub-acct-1", iban="NL00STUB0123456789", account_name="Stub Business Account", currency="EUR")]

    def list_transactions(self, access_token: str, provider_account_id: str, since: datetime | None = None) -> list[ProviderTransaction]:
        return []  # no fabricated transaction history -- an empty, honest result


_provider: OpenBankingProvider | None = None


def get_open_banking_provider() -> OpenBankingProvider:
    global _provider
    if _provider is not None:
        return _provider
    # No real provider is configured anywhere in this codebase (no API
    # credentials exist) -- always the stub. This is NOT a try/fallback
    # like ai_provider.py; there is nothing to try yet.
    logger.info("No Open Banking provider is configured -- using StubOpenBankingProvider (see docs/open-banking.md)")
    _provider = StubOpenBankingProvider()
    return _provider


def reset_provider_cache() -> None:
    global _provider
    _provider = None
