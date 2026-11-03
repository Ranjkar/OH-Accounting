# Phase 12 implementation summary

Unifies what the original spec split into Phase 12 (production/security/
GDPR), Phase 13 (Dutch government integrations) and Phase 14 (Open
Banking/automation) into one phase, on branch
`phase-12-complete-platform-infrastructure`, branched from Phase 11.1's
verified head.

This file is the index. Each area has its own doc with full detail --
this page states what was built, its real status, and where to read more.
It does not repeat their content.

## Workstream B -- Security & GDPR

Session revocation (`token_version` claim bumped on logout/password
change/deactivation), account lockout after repeated failed logins,
password reset (token-based, email delivery not wired up -- see
`docs/production-readiness.md`), GDPR data export and self-deactivation
(full erasure intentionally not implemented for linked financial records
-- legally required retention takes precedence over an erasure request).
Full detail: `docs/security.md`, `docs/gdpr-data-governance.md`.

**Status:** IMPLEMENTED (auth hardening, lockout, GDPR export/deactivate).
NOT IMPLEMENTED: MFA, transactional email delivery, full account erasure.

## Workstream C -- Infrastructure

Hardened, non-root, healthchecked Docker images for backend and frontend
(verified with real `docker build`/`docker run`, not just written);
separate dev (`docker-compose.yml`) and production-oriented
(`docker-compose.prod.yml`) compose files, the latter requiring every
secret with no default and isolating Postgres on an internal-only
network; structured JSON logging with per-request correlation IDs; a
`/ready` endpoint that checks the database's actual migration head
against the running code, not just connectivity. A real backup/restore
drill was run twice against disposable databases, never the live one.
Full detail: `docs/deployment.md`, `docs/monitoring.md`,
`docs/backup-restore.md`, `docs/production-readiness.md`.

**Status:** IMPLEMENTED and verified for images/compose config/logging/
health checks/backup-restore procedure. PRODUCTION CONFIGURED only
(never PRODUCTION VERIFIED) for the compose file itself -- it has never
been run against a real production host. NOT IMPLEMENTED: CI/CD, TLS
provisioning, automated backup scheduling, a metrics backend.

## Workstream D -- Government integrations (KVK, SBR/Digipoort)

A reusable provider-abstraction pattern (`Protocol` + `Http`/`Stub`
implementation + singleton cache), the same shape already used for
`app/services/ai_provider.py`. KVK: real integration against KVK's
published, no-registration test sandbox (`developers.kvk.nl`) -- a
genuine network call, verified independently via `curl` before writing
any code against it. SBR/Digipoort: researched from primary sources
(belastingdienst.nl, sbr-nl.nl, logius.nl) -- no comparable open sandbox
exists; it requires a PKIoverheid/Logius test certificate via an external
registration process this session cannot complete. The loonheffingen
declaration lifecycle itself (Draft through Accepted/Rejected) was
already built in Phase 10; this phase documented it and added the KVK
lookup on top, it did not rebuild the lifecycle.
Full detail: `docs/government-integrations.md`.

**Status:** KVK lookup -- SANDBOX VERIFIED. SBR/Digipoort transmission --
BLOCKED BY EXTERNAL REQUIREMENT. Declaration lifecycle state machine --
IMPLEMENTED (Phase 10, re-verified this phase).

## Workstream E -- Open Banking (PSD2 AISP)

Same provider-abstraction pattern as KVK: `OpenBankingProvider` Protocol,
`StubOpenBankingProvider` for development, encrypted token storage via a
*separate* Fernet key/module (`app/core/token_crypto.py`) from the one
already used for BSN encryption -- deliberately never shared, so a
compromised key only ever exposes one secret class. Research found no
independently verified DNB/EBA authorization for an AISP relationship for
this project; payment initiation is explicitly out of scope and was not
built. Existing Phase 6 manual file-import banking functionality is
untouched and works regardless of connection status.
Full detail: `docs/open-banking.md`.

**Status:** Provider abstraction, consent flow, encrypted token storage,
sync (reusing the existing bank-import dedup path) -- IMPLEMENTED and
exercised against the stub provider (SANDBOX VERIFIED in the sense of
"verified against this project's own sandbox stub," not a real bank).
Real-provider connectivity -- BLOCKED BY EXTERNAL REQUIREMENT (no
authorised AISP agreement/credentials). Payment initiation -- NOT
IMPLEMENTED (by design, per the brief).

## Workstream F -- Financial automation & idempotency

Audited idempotency across every money-moving path. Found two already
correct (bank-import dedup via a DB-level unique constraint, loonheffingen
declaration uniqueness) and one real gap: payroll run creation had no
guard against a double-click/retry creating a duplicate run. Fixed with a
DB-level `uq_payroll_run_period` unique constraint plus an
`IntegrityError` -> `PayrollError` -> HTTP 409 mapping, tested. AI
continues to only *suggest* classifications/matches in this codebase; no
AI-initiated posting was added or exists.
Full detail: `docs/financial-automation.md`.

**Status:** IMPLEMENTED and tested (payroll run idempotency fix; all
other paths verified already idempotent, not modified).

## Workstream A & G -- Frontend

**Workstream A** (UI audit for the ~29 pages Phase 11.1 didn't
individually review): found and fixed missing accessible names
(`aria-label`) on ~40 filter/form controls across 24 pages, plus a stale
`BankAccount`/`BankConsentStatus` TypeScript type gap found while building
Workstream G. Full detail: `docs/ui-accessibility-audit.md`.

**Workstream G** (integration frontend screens, reusing the Phase 11
glass design system and real backend data only):

- **Government Integration Centre** (`/government`, new nav entry under
  Tax & Compliance): a KVK lookup tool against the real sandbox endpoint,
  an honest per-integration status panel using the same status labels as
  this document, and a real `companies` listing flagging which ones have
  no KVK number on file. No declaration-filing UI was duplicated here --
  that already lives in Payroll Tax (Loonheffingen) and VAT Returns.
- **Banking Connections** (added to the existing `/banking` page rather
  than a new page, to avoid a second, divergent banking UI): shows the
  real `consent_status`/`provider_name`/`last_synced_at`/
  `last_sync_error` fields and Connect/Complete-sandbox-consent/Sync/
  Disconnect actions against the real Open Banking endpoints. Every
  label makes the stub-provider nature explicit (e.g. "Sandbox
  authorization URL (no real bank redirect for a stub provider)") -- no
  fake "connected to your bank" status is shown.
- **Automation Centre**: the existing `/automation` page already surfaces
  real categorization-rule, anomaly, and forecast data from Phase 6; no
  changes were needed to meet "enhanced... using real backend data only"
  since it already did.

Verified with `tsc --noEmit`, `npm run lint`, `npm run build` (including
the new `/government` route), and `npm run test` (68/68 vitest + axe-core
tests).

## Workstream H -- Testing

Backend: 442 tests passing (`cd backend && pytest`), including new
suites for auth security (9), KVK integration against the real sandbox
(3, genuine network calls, not mocked), and Open Banking against the stub
provider (7), plus one new payroll-idempotency test. Frontend: 68 vitest
+ axe-core tests passing, `tsc --noEmit` clean, `npm run lint` clean
(two pre-existing, unrelated warnings), `npm run build` clean.

**What was not done:** no Playwright/browser-automation visual
verification this phase (same documented limitation as Phases 11/11.1);
no load/performance testing; no test against a real KVK production
endpoint or a real bank (neither is available to this session).

## Git

Branch: `phase-12-complete-platform-infrastructure`, branched from
Phase 11.1's verified head. Commits this phase (oldest first):
`171167e` (auth/GDPR/KVK), `672e79d` (logging/Docker/compose),
`1684102` (payroll idempotency), `15a5085` (Open Banking architecture),
`35ec5c4` (documentation), `3a70d0a` (accessibility fixes), plus this
commit (government/banking frontend screens + remaining docs + backup
doc rename). **Not merged into main. Not deployed. No production data
touched at any point.**
