# Phase 26 — Annual client agreements & electronic signatures

Implementation report, security/legal limitations, deployment and rollback.
Status at the end of the phase: **feature-complete behind a flag, not deployed, not enabled anywhere.**

## 1. What was built

### Backend (`backend/app`)
| Area | Files |
|---|---|
| Models (9 tables, 4 enums) | `models/contract.py`, `models/enums.py` |
| Migration (additive only) | `alembic/versions/b8d2e4f60026_phase_26_contracts.py` |
| Lifecycle service | `services/contract_service.py` |
| Scheduler (activation, expiry, renewals, reminders) | `services/contract_scheduler.py` |
| Template content (nl/en) + labels | `services/contract_templates.py` |
| Branded PDF + evidence page | `services/contract_pdf.py` (on the shared `reporting/pdf_builder.py`, which gained `paragraph()`/`new_page()`) |
| Signing-provider adapter | `services/signing_provider.py` |
| Emails (7 templates, nl + en; fa/ar fall back to en) | `services/email_templates.py` |
| API | `api/v1/contracts.py` |
| Hooks | `api/v1/companies.py` (quick create), `api/v1/company_setup.py` (wizard), `main.py` (scheduler thread) |
| Config | `core/config.py`: `CONTRACTS_ENABLED`, `CONTRACTS_EMAIL_AUTOMATION_ENABLED`, `CONTRACTS_SCHEDULER_INTERVAL_MINUTES`, `CONTRACTS_SIGNING_PROVIDER` |

Tables: `contract_templates`, `contract_template_versions`, `contract_settings`, `contracts`, `contract_versions`, `contract_signing_invitations`, `contract_signatures`, `contract_events`, `contract_reminders`. Email delivery/retry records reuse the existing `email_outbox` (linked by `email_outbox_id`).

### Status machine
`DRAFT → PENDING_APPROVAL → READY_TO_SEND → SENT → VIEWED → SIGNED → ACTIVE → RENEWAL_DUE → EXPIRED`, plus `CANCELLED` (before signature) and `TERMINATED` (after signature). Transitions are enforced in `contract_service.ALLOWED`; every admin action writes an `AuditLog` row and a `contract_events` row; signer/system actions write `contract_events` (and an `AuditLog` row for the signature itself).

- Only `DRAFT` is editable. **Approval** validates completeness (signer name/email, services, fee *or* fee description, payment and notice terms) and freezes the rendered content + branded PDF into an immutable `ContractVersion` with `content_hash` and `pdf_sha256`.
- **Send** issues a 256-bit random token (only its SHA-256 is stored), revokes earlier pending links, and queues the invitation through the existing email service. With `EMAIL_PROVIDER=none` the link is returned once to the admin (same convention as company invitations) and shown in the UI; it is never persisted.
- **Sign** (public, token-only, rate-limited): the signer sees the complete agreement, confirms the invited email address and types the legal name of the authorised representative, ticks explicit consent. The contract row is locked `FOR UPDATE`; `contract_signatures.contract_id` is UNIQUE; the invitation becomes `USED`. A second, final PDF with an evidence page is stored with its own hash. `GET /contracts/{id}/versions/{v}/verify` recomputes both hashes from storage.
- **Renewal**: the scheduler marks `RENEWAL_DUE` inside the first reminder window, prepares one renewal draft (`renews_contract_id` UNIQUE), copying the *current* commercial terms from the expiring agreement onto the currently approved template version. An admin reviews, approves and sends it like any other contract. Reminders at 60/30/14 days (configurable per tenant) are deduplicated by `UNIQUE (contract_id, kind)`; when several thresholds are crossed in one tick only the latest one emails. **An unsigned renewal is never treated as accepted**: the old agreement simply expires.
- **Cancellation / non-renewal / termination**: cancel (pre-signature, revokes links), non-renewal flag (stops renewal preparation), terminate (post-signature, with effective date and reason). Signed documents are never deleted.

### Frontend (`frontend`)
- `/contracts` list with stat strip, filters (company, status, signing status, expiry window), create modal.
- `/contracts/[id]` detail: terms (editable in draft), approval checklist, actions, documents with download + hash verification, signature evidence, invitations with email status, timeline.
- `/contracts/templates`: template versions (nl/en clause editor, commercial defaults, approve), renewal & signing settings, read-only server flags, manual scheduler run.
- `/sign/[token]`: public, branded, responsive signing portal (no app shell), explicit consent, confirmation screen with signed-PDF download and hash. axe-core clean in the unit test.
- Company workspace: **Contracts** tab. Sidebar: **Contracts** under Company & Settings. All copy in nl/en/fa/ar (`contracts` namespace, parity-checked).

## 2. Release review (2026-11-11, second pass -- pre-release sign-off)

A second, independent pass was run specifically before release: full-repo code
review of all 36 changed/new files, a real Alembic upgrade/downgrade/upgrade
round trip on an isolated throwaway database, a focused security review of the
public signing portal, and a full re-run of every test suite (not a subset).

### 2.1 Code review findings

| # | File | Finding | Action |
|---|---|---|---|
| 1 | `services/contract_service.py` (`build_content`) | Clause/heading text was rendered with `str.format_map()`. Python's format mini-language supports attribute/index access inside a placeholder (e.g. `"{x.__class__.__mro__}"`), which is unnecessary capability to carry even though `custom_clauses` is only ever editor-authored for that editor's own tenant's own draft. | **Fixed**: replaced with a regex-only `{name}` substitution (`_substitute`, `_PLACEHOLDER_RE`) that has no attribute/index-access capability at all. Re-ran `tests/test_contracts.py` after the change: 21/21 still pass. |
| 2 | `api/v1/companies.py` (`create_company`) | Company creation, its audit-log row and the Phase 26 auto-draft are now one transaction (`db.flush()` + one final `db.commit()`) instead of two separate commits. This is an intentional atomicity improvement (satisfies the brief's "transactional state changes" requirement) but is a real behavioural change to an existing endpoint. | **Verified, not changed**: `auto_create_for_new_company` wraps its own work in `db.begin_nested()` and catches every exception, so it can never roll back company creation; covered explicitly by `test_auto_create_respects_tenant_setting_and_never_breaks_onboarding` (which forces `create_draft` to raise and asserts the company is still created). Full regression (707 backend tests) confirms no other test depends on the old two-commit timing. |
| 3 | every route in `api/v1/contracts.py` | Checked each of the 24 routes individually for its auth dependency. | **No issue**: every authenticated route carries `require_admin`/`require_editor`/`get_current_user` plus `_get_contract_or_404` (tenant filter + `require_company_access`, the same double-check convention `app/core/deps.py` documents for the rest of the codebase); the three public `/sign/{token}` routes correctly carry no user dependency (the token is the credential) and are individually rate-limited. |
| 4 | `models/__init__.py` | Pre-existing, unrelated drift noticed while diffing the migration: `UserInvitation` (`models/user_invitation.py`) is not imported here, so it is invisible to Alembic's `target_metadata`, and a large number of early-phase `ix_*_tenant_id`/`ix_*_company_id` indexes are not declared `index=True` on their model columns. Confirmed via `alembic check` against a from-scratch database. | **Not fixed, out of scope**: predates Phase 26 by many phases (the migration never touches `user_invitations` or any of those index names), would be its own correctness pass, and fixing it is a schema-metadata change with its own review, not a Phase 26 regression. Flagged here for a future pass. |
| 5 | all 36 files | No `dangerouslySetInnerHTML`, no new npm/pip dependency, no raw token ever passed to a `logger.*` call (grepped), email bodies still escaped through the existing `render()` helper exactly like the pre-existing `company_invitation`/`password_reset` templates. | No action needed. |

### 2.2 Migration verification

Run against an isolated, newly created database (`onholland_migration_check`),
never the dev or test database:

1. **Full chain from empty**: `alembic upgrade head` from a brand-new database applied all 26 migrations in order, ending cleanly at `b8d2e4f60026` (Phase 26).
2. **Rollback**: `alembic downgrade a7c3e9f10022` removed exactly the 9 Phase 26 tables and nothing else (`select count(*) from information_schema.tables where table_name like 'contract%'` → `0`); the 4 new enum types were also dropped.
3. **Re-upgrade**: `alembic upgrade head` re-applied cleanly; `alembic current` reports `b8d2e4f60026 (head)`.
4. **Schema-vs-model parity**: `alembic check` at head reports a number of pre-existing, unrelated drift items (finding #4 above) but **zero** mentions of any `contract_*` table or column -- the new schema matches the SQLAlchemy models exactly.
5. An earlier attempt to run `alembic downgrade base` directly against the **pytest-managed** `onholland_accounting_test` database (which is built by `Base.metadata.create_all()`, not by Alembic) partially dropped its tables and had to be recovered by dropping and recreating that database, after which `pytest` rebuilt its schema correctly on the next run. No other database was touched by this mistake; the real dev database (`onholland_accounting`) and its data were never in the command's path and were separately confirmed intact (`select count(*) from companies` unchanged) afterwards.

### 2.3 Public signing portal: security review

| Dimension | Review | Verdict |
|---|---|---|
| **Authentication** | Deliberately unauthenticated (bearer-capability model, same family as the existing password-reset/company-invitation links). No Authorization header is ever sent by the frontend's `getSigningPage`/`signContract`/`signingPdfUrl` calls (confirmed in `lib/api.ts`); the page itself renders with no `AuthGuard`/`Shell` wrapper. | Pass |
| **Token security** | `secrets.token_urlsafe(32)` = 256 bits of entropy; only the SHA-256 hash (`token_hash`, unique-indexed) is ever stored; the raw token is returned once to the admin (when no email provider is configured) or emailed once, never logged (grepped every `logger.*` call in the contract service/scheduler/API, confirmed clean), never included in any `AuditLog`/`contract_events` row. Links expire (`signing_link_expire_days`, default 14, per tenant); resending revokes the previous pending link. | Pass |
| **Replay protection** | `sign()` locks the contract row `FOR UPDATE`, checks `invitation.status == PENDING`, and `contract_signatures.contract_id` carries a UNIQUE constraint as the final backstop. Verified under real concurrency: two simultaneous threads calling `sign()` on the same token yield exactly one signature and one `409`. A used link can still be viewed/re-downloaded (90-day grace) but can never sign again. | Pass |
| **Document integrity** | SHA-256 of the exact rendered content and of the PDF bytes is computed at approval and again at signing; `GET /contracts/{id}/versions/{v}/verify` recomputes both from the bytes actually in storage, not from the stored hash column. No route updates or deletes a `ContractVersion`. PDFs are served only through authenticated routes or the token-gated `/sign/{token}/pdf` route, both with `Cache-Control: no-store`, never a static path. | Pass |
| **Tenant isolation** | The public routes accept no tenant/company/contract id from the client at all -- the only input is the opaque token, resolved purely by a server-side hash lookup. There is structurally no cross-tenant parameter to manipulate (stronger than ID-based isolation, which this app also uses correctly elsewhere). Every authenticated route additionally re-validates tenancy via `require_company_access`; `test_cross_tenant_access_is_denied_everywhere` exercises this directly across every mutating and read route. | Pass |

### 2.4 Full regression (this review session, run in full, nothing excluded)

Adding two routes (`/contracts`, `/contracts/templates`) to the responsive route inventory and a new three-test Playwright spec pushed the full serial suite (`workers: 1`, by design -- see `playwright.config.ts`) from 13.3 to 39.1 minutes. Two tests on the `ipad` project failed with a hard `page.evaluate: Test timeout of 600000ms exceeded` -- a timeout, not a layout/content assertion failure. Re-running `e2e/responsive.spec.ts --project=ipad` in isolation immediately afterwards passed all 10 tests, including both that failed in the marathon, in 1.5 minutes. This is consistent with resource contention from a much longer single serial run against one dev-server/browser-worker pair, not a defect introduced by this phase; nothing about the ipad viewport specifically changed by this phase's code. Flagging this because the suite's growing total runtime is itself worth knowing about for CI reliability going forward, even though the underlying code is verified correct.


| Suite | Command | Result |
|---|---|---|
| Full backend suite | `pytest` (all files, default plugins) | **707 passed**, 0 failed, 0 errors |
| Frontend unit tests | `npx vitest run` | **264 passed / 21 files** |
| TypeScript | `tsc --noEmit` | 0 errors |
| ESLint | `eslint .` | 0 errors, 5 pre-existing warnings in files this phase did not touch |
| i18n parity | `npm run check:i18n` | 1849 keys × 4 locales OK |
| Playwright, full suite (i18n, company creation, responsive × 8 devices, and the new `contracts.spec.ts` journey) | `npx playwright test` | **119 passed, 2 failed** (39.1 min) -- see note below |

Backend coverage (by test name in `tests/test_contracts.py`): feature flag; automatic draft on quick-create and wizard create; tenant setting + onboarding never breaks; manual create + approval validation; approval freezes version with hashes and PDF text (nl); send creates hashed-token invitation + outbox row, tokens never logged; role checks; full signing flow with evidence and final PDF; immutability + replay refused; invalid/expired/revoked links; concurrent sign (two threads → one signature); cross-tenant denial on every endpoint; scheduler activation/renewal/dedupe/expiry; automation-on emails incl. renewal signing request; non-renewal + termination; signing reminder re-issue; advisory lock; email retry/permanent failure; templates, settings, English rendering; list filters.

## 3. Security & legal limitations report

**Signature level.** The built-in provider produces a **simple electronic signature** (eIDAS Regulation (EU) 910/2014, art. 3(10)). Evidence: possession of the emailed secret link, typed legal name that must match the named representative, typed email that must match the invited address, explicit consent text, UTC timestamp, IP address, user agent, SHA-256 of the exact document shown, and the hash of the final PDF. This is admissible under Dutch law (art. 3:15a BW) but identity assurance rests on the email channel. It is **not** an advanced (art. 26) or qualified (art. 3(12)) signature; nothing in the UI, PDF or email calls it that. A qualified signature requires an accredited trust-service provider — the `SigningProvider` protocol and `CONTRACTS_SIGNING_PROVIDER` exist for that adapter; none is implemented.

**Template content.** `contract_templates.py` is a structured starting point only. The liability clause is an explicit placeholder; no fee, payment term or notice period is pre-filled. **A Dutch legal professional must review and approve the template version before production**, and an administrator must approve it in the UI (`/contracts/templates`). Until then contracts can still be drafted but every approval is a human decision on visible terms.

**Tokens.** Signing tokens are `secrets.token_urlsafe(32)`; only SHA-256 hashes are stored; links expire (default 14 days, per tenant); a used link can view/download the signed PDF for 90 days and never sign again; resend/reminder revokes earlier links. Tokens never appear in logs, audit rows or events (asserted by test). Public routes are rate-limited per client (30/min view, 10/min sign).

**Isolation.** Every authenticated route resolves the contract inside the caller's tenant and then calls `require_company_access`; cross-tenant attempts return 404 and change nothing (tested). PDFs are streamed through authenticated or token-checked endpoints only, with `Cache-Control: no-store`; nothing is served from a static path.

**Immutability.** No code path updates or deletes `contract_versions` rows or their files; `PATCH` on anything but `DRAFT` is 409; verification recomputes hashes from the stored bytes.

**GDPR / retention.** Signature evidence stores the minimum needed to evidence who signed what and when. Signer IP and user agent are kept with the contract. Retention follows the 7-year bookkeeping rule (`docs/gdpr-data-governance.md`); automated purge of IP/user-agent after the retention period is **not** implemented (same gap as the rest of the platform). Email bodies with links are never stored (`email_outbox` keeps metadata only).

**Known gaps / external dependencies**
1. Legal review of the template (blocking for production use).
2. Qualified/advanced signature provider (optional; adapter only).
3. Email attachments: signed PDFs are delivered as secure links, not attachments (the email provider abstraction has no attachment support).
4. Reminder scheduler runs in-process (daemon thread, Postgres advisory lock). For multi-instance deployments prefer `CONTRACTS_SCHEDULER_INTERVAL_MINUTES=0` plus an external cron calling `POST /api/v1/contracts/scheduler/run`.
5. One signer per contract. Multi-party counter-signature by the provider is not modelled.

## 4. Deployment & rollback (Docker Compose)

**Status as of this release: code and migration are committed and pushed; nothing has been deployed anywhere; nothing is enabled anywhere.** `CONTRACTS_ENABLED=false` and `CONTRACTS_EMAIL_AUTOMATION_ENABLED=false` in both `backend/.env.example` and `.env.prod.example` -- these are only the *templates*; the production `.env.prod` file itself lives only on the production host and is not touched by this commit.

### 4.1 Step A -- ship the code (safe to do any time, flags stay off)

This repo's production stack is `docker-compose.prod.yml`. The backend image's entrypoint already runs `alembic upgrade head` before starting `uvicorn` (see `backend/Dockerfile`), so **redeploying the backend automatically applies the Phase 26 migration** -- that is expected and safe: the migration is purely additive (9 new tables, 4 new enum types, no existing table altered), and with `CONTRACTS_ENABLED` unset/false the new code paths never execute (no draft is auto-created, the scheduler thread never starts, every `/contracts/*` route answers 404).

On the production host (see `docs/production-deployment.md` for how that host is reached and provisioned; this repo is checked out there from this same GitHub remote):
```
cd <path-to-repo-on-the-host>
git pull origin main                      # brings in this commit
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build backend frontend
```
(or the host's own two-file `-f docker-compose.prod.yml -f docker-compose.tailscale.yml` invocation if Tailscale networking is layered on, matching whatever the last deploy used). Do **not** add any `CONTRACTS_*` line to the real `.env.prod` in this step -- omitted variables fall back to the safe defaults (`false`) baked into `app/core/config.py`, so the feature stays dark even without touching the env file at all.

**Verify after Step A:** `GET https://<prod-host>/api/v1/contracts` returns `404 {"detail":"Contracts feature is not enabled (CONTRACTS_ENABLED)"}`, and creating a company still works exactly as before (no draft contract appears, because the flag is off).

### 4.2 Step B -- activate the feature (a separate, later, explicit decision -- NOT part of this release)

Only after: (1) the bundled template has been reviewed and approved by a Dutch legal professional, (2) acceptance testing has passed on a staging copy with real company/VAT data shapes, (3) someone has deliberately decided to turn this on.

1. Edit the real `.env.prod` on the host and add/change:
   ```
   CONTRACTS_ENABLED=true
   CONTRACTS_EMAIL_AUTOMATION_ENABLED=false   # keep off for a first cycle
   CONTRACTS_SCHEDULER_INTERVAL_MINUTES=60
   CONTRACTS_SIGNING_PROVIDER=internal
   ```
2. Recreate the backend container so it picks up the new env vars (no rebuild needed, image is unchanged):
   ```
   docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate --no-deps backend
   ```
3. Sign in as an owner/admin, open `/contracts/templates`: review the Dutch and English clause text, fill in the commercial defaults (fee, payment term, notice period), and **approve** a template version. Nothing can be sent to a real client until this step is done -- approval of an individual contract is still blocked until its own terms are complete.
4. Create one real or test company and walk the full cycle once (draft → complete terms → approve → send → sign on the portal → verify) before relying on it for real clients.
5. Only once satisfied, flip `CONTRACTS_EMAIL_AUTOMATION_ENABLED=true` (same recreate step) to let the renewal/reminder scheduler send email on its own; until then, admin-initiated "send for signature" already emails normally (or shows the link if no `EMAIL_PROVIDER` is configured), unaffected by this flag.

### 4.3 Rollback

- **Turn the feature back off**: set `CONTRACTS_ENABLED=false`, recreate the backend container (same command as 4.2 step 2). Every `/contracts/*` route 404s again, the scheduler thread stops starting on the next restart; no row is deleted, nothing already signed is affected.
- **Roll back the code**: `git checkout <previous commit>` on the host and rebuild/redeploy, per `docs/deployment.md`'s existing rollback procedure. The schema is left at the newer revision (both repo convention and this phase's own migration verification -- see §2.2 -- confirm that's safe; the new tables are simply unused by older code).
- **Roll back the schema** (only if truly necessary, and only if no agreement has been signed yet -- signed documents must be retained, same statutory rule as every other financial record in this app): `docker compose exec backend alembic downgrade a7c3e9f10022`. Verified in §2.2 to cleanly remove exactly the 9 Phase 26 tables and 4 enum types and nothing else.

### 4.4 Verification checklist once Step B is actually performed

- [ ] `/contracts/templates` shows an **APPROVED** template version with real commercial defaults, not the placeholder liability clause left unreviewed
- [ ] A new company gets a `DRAFT` agreement automatically
- [ ] Completing terms → Approve produces a version with a 64-character SHA-256 `pdf_sha256`
- [ ] Send → the signing link works in a private/incognito window with no login
- [ ] Signing produces a second, final version whose hash verifies via `/contracts/{id}/versions/{v}/verify`
- [ ] `POST /contracts/scheduler/run` (admin-only) returns a counts object with no error
- [ ] `CONTRACTS_EMAIL_AUTOMATION_ENABLED=false` still shows reminders recorded with `status=skipped_disabled` rather than emailed, until deliberately turned on

## 5. Definition of done — status
- Newly registered company receives a draft annual contract: **done** (both creation paths, tested).
- Administrator can approve and send: **done**.
- Authorised client can electronically sign: **done** (simple e-signature).
- Signed document and evidence preserved: **done** (immutable versions, hashes, verify endpoint).
- New agreement prepared and sent each year with approval, security and audit controls: **done** (scheduler prepares + reminds; admin approves + sends; no silent renewal).
- Blocked externally: legal review of template text; accredited provider for advanced/qualified signatures.
