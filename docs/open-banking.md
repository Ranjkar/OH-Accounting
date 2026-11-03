# Open Banking (PSD2 AISP)

## Provider evaluation

Researched this session (WebSearch/WebFetch, not assumed):

- **Tink** — licensed AIS/PIS provider (Swedish FSA, also BaFin Germany), PSD2-passported across 21 EEA countries since 2019. NL-specific business-account coverage not independently confirmed in search results.
- **GoCardless Bank Account Data** (formerly Nordigen) — claims 2,500+ bank coverage across UK/Europe including the Netherlands (ABN AMRO named), sandbox available. Its free tier is reportedly being wound down (~Aug 2026); current pricing not publicly listed.
- Yolt/Enfuce, Klarna Kosma, TrueLayer — not verified this session.

**Verification gap, stated explicitly: the DNB register (dnb.nl) and EBA register were not practically searchable via the tooling available this session** (direct URL fetch returned 404; the real search interface likely needs JS/forms this tooling can't drive). The authorization claims above come from secondary sources (openbankingtracker.com, the providers' own marketing) and **must be re-verified against the live DNB/EBA register before any production decision** — authorization status is point-in-time.

**PSD2 consent standard**: 90 days is the long-standing maximum consent re-authentication interval under the RTS on Strong Customer Authentication, applied across providers (`CONSENT_MAX_DAYS = 90` in `app/services/open_banking_provider.py`).

## Decision: no provider selected for integration this phase

Building an HTTP client against a provider whose API shape wasn't independently verified this session, with no real credentials to test against, would mean guessing request/response formats — directly against this project's own convention against inventing endpoints. **No provider is integrated.**

## What is implemented

- `app/services/open_banking_provider.py`: the `OpenBankingProvider` Protocol every real adapter would need to satisfy (`initiate_consent`, `complete_consent`, `list_accounts`, `list_transactions`), plus `StubOpenBankingProvider` — clearly `"stub-"`-prefixed synthetic data, same Protocol+Stub split already used by `app/services/ai_provider.py`.
- `BankAccount` extended (not a new table — Phase 6 already had `consent_status`/`consent_granted_at`/`consent_expires_at` as deliberate groundwork) with `provider_name`, `provider_account_id`, and Fernet-encrypted access/refresh tokens under a **dedicated** key (`app/core/token_crypto.py`, separate from BSN encryption).
- `app/accounting/open_banking_service.py`: consent initiation/completion/disconnect, and sync — which reuses the **exact same** `BankTransaction` dedup path as manual file import (`insert_rows_with_dedup`, extracted from `app/accounting/bank_import.py` so both call sites share one duplicate-prevention implementation).
- API: `POST /bank-accounts/{id}/open-banking/{connect,callback,sync,disconnect}`.
- Manual file import (CAMT.053/054, MT940, CSV) is completely unaffected and remains the primary, fully-working import path regardless of connection status.

## Status

| Capability | Status |
|---|---|
| Provider abstraction + stub | IMPLEMENTED |
| Encrypted token storage | IMPLEMENTED, tested (ciphertext verified, never returned in API responses) |
| Consent lifecycle (stub) | IMPLEMENTED |
| Real bank connectivity | BLOCKED BY EXTERNAL REQUIREMENT (no authorised provider agreement, no credentials, DNB/EBA authorization not independently re-verified) |
| Manual bank import | unaffected, still the primary path |
