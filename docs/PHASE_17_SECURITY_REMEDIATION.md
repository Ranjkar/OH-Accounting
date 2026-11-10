# Phase 17 — Critical Security Remediation

| | |
|---|---|
| **Branch** | `phase-16-3-complete-internationalisation` (unchanged — no commits made, see §8) |
| **Base commit** | `97f2d84` |
| **Date** | 2026-11-05 |
| **Source of findings** | `docs/QWEN_TECHNICAL_AUDIT_REPORT.md` |
| **Sub-phases completed** | 17.1, 17.2, 17.3, 17.4, 17.5, 17.6 |
| **Companion document** | `docs/PHASE_17_TEST_RESULTS.md` (every command run and its actual output) |

---

## 1. Scope and constraints honoured

Every constraint in the brief was treated as hard. Where a constraint conflicted with a finding, the constraint won and the item is recorded under §7 (manual operations) rather than actioned.

| Constraint | How it was honoured |
|---|---|
| Inspect Git status before changing anything | Done first; recorded in §8 |
| Preserve all existing uncommitted user changes | All five pre-existing modified files survived. `backend/app/api/v1/auth.py` is still `+8 −1` and untouched by this phase. The uncommitted `find_user_by_email` helper in `deps.py` was preserved verbatim while `require_company_access` below it was rewritten — verified by checksum after a temporary revert experiment (§4). |
| Do not reset, clean, stash or overwrite the working tree | No `git reset`, `git clean`, `git stash` or `git checkout --` was run at any point. One temporary revert was performed **by copying files to `/tmp` first and restoring by checksum** (§4), never by a git operation. |
| Do not delete project files unless explicitly justified | Nothing deleted. The three stray backup files (`main.py.bak`, two `globals.css.backup-*`) were **gitignored, not deleted** — deleting them is the user's call (§7). |
| No unrelated refactoring | No file was reformatted, renamed or restructured. The 61 now-redundant per-endpoint tenant checks were deliberately **left in place** as defence-in-depth rather than removed (§3.1). |
| Do not modify production data | No production system exists and none was touched. No database was written to except the disposable `onholland_accounting_test` sibling used by the existing test suite. |
| Do not deploy | Nothing deployed. No container was built or started. |
| Keep all existing functionality working | Full backend suite re-run: **564 passed, 0 failed** before the final `main.py` tweak, and re-verified after (see TEST_RESULTS). Positive-control tests were added specifically to prove the fixes do not simply break the endpoints (§4). |
| Add tests for every security fix | 22 + 57 + 1 backend tests and 7 + 13 frontend tests; every fix has at least one, and each was **mutation-tested** (§4). |
| Separate commits only if explicitly authorised | **Not authorised, so nothing was committed.** All work is in the working tree (§8). |
| Never print secrets or encryption keys | Enforced by construction and by test: the new validation reports variable **names** only, and `test_no_guarded_secret_value_ever_reaches_a_log_or_exception_message` + `test_settings_repr_never_renders_a_secret_value` assert canary values never appear in a message, a log line, `repr()` or `str()`. No key value appears anywhere in this document. |
| Never commit credentials | No credential was written to any tracked file. Only `.env.example` / `.env.prod.example` templates were edited, and only with **empty** values. |
| Never delete or overwrite existing encrypted data | **No key was rotated.** `backend/.env` was not modified. Existing ciphertext in the development database is untouched and still decrypts. |
| Never rotate keys without a tested re-encryption and rollback procedure | The procedure was **built and tested first** (`reencrypt_token_with_current_key`, `reencrypt_mfa_secret_with_current_key`, `scripts/rotate_encryption_keys.py`, and `test_full_rotation_procedure_for_every_secret_class` which walks all four steps including retirement of the old key). Rotation itself was then **not performed** — that is an operator action requiring a backup (§7). |
| Do not silently change production configuration | The one production-affecting change (`ENVIRONMENT` in `docker-compose.prod.yml`) is called out in §6 as a **breaking deployment change**, with its exact consequence. |
| Document and stop where a live credential or external permission is needed | §7 lists all seven such operations. None was attempted. |

---

## 2. Vulnerabilities fixed

Severity labels are those assigned by the audit.

### 2.1 Phase 17.1 — cross-tenant isolation

| Audit ID | Severity | Vulnerability | Status |
|---|---|---|---|
| CRITICAL-1 | **Critical** | `POST /companies/{id}/financial-years/{fy}/lock` and `/unlock` — an `owner`/`admin` of tenant A could lock or unlock tenant B's financial year, halting their bookkeeping or removing the period-integrity control, with the audit row written into the *attacker's* tenant | **Fixed** |
| CRITICAL-2 | **Critical** | `POST /payment-matches/bulk-approve-high-confidence` — any admin of any tenant could approve every HIGH-confidence suggested match on an arbitrary company's books in one request, posting real `Payment` rows and flipping reconciliation state | **Fixed** |
| HIGH-1 | High | `GET /companies/{id}/financial-years` — leaked fiscal years, lock state and the full VAT period calendar (labels, dates, filing and payment deadlines) for any integer company id; also the reconnaissance primitive for CRITICAL-1 | **Fixed** |
| HIGH-2 | High | `GET /companies/{id}/invitations` — leaked `invited_email`, `intended_role`, `status`, `invited_by_user_id`, `expires_at`, `token_hash` for another tenant's pending invitations | **Fixed** |
| HIGH-3 | High | `POST /companies/{id}/invitations/{inv}/revoke` — could revoke any pending invitation in another tenant, silently blocking that firm's onboarding of its accountant | **Fixed** |
| MEDIUM-1 | Medium | `GET /companies/{id}/notes` — any authenticated user in any tenant, **including a read-only `viewer`**, could read another firm's free-text accountant notes | **Fixed** |
| HIGH-4 | High | `POST /companies/invitations/accept` — granted cross-tenant company membership with no tenant comparison and no `None` check (the latter an `AttributeError`/500) | **Fixed** |

**The root cause was fixed once, not seven times.** All seven defects shared a single origin: `require_company_access` returned immediately for `ADMIN_ROLES` without comparing `user.tenant_id` to the company's, so isolation depended on each of the **61 call sites** independently remembering its own filter. Seven did not.

`require_company_access` is now authoritative for every role:

```python
company = db.get(Company, company_id)
if company is None or company.tenant_id != user.tenant_id:
    raise HTTPException(404, "Company not found")
if user.role not in ADMIN_ROLES:
    if not any(c.id == company_id for c in user.companies):
        raise HTTPException(403, "No access to this company")
return company
```

Three deliberate design decisions:

1. **404, not 403, across a tenant boundary** — matching the convention every pre-existing per-endpoint check already used (`documents.py:44`, `banking.py:45`, `transactions.py:33`, …), so a caller from another tenant learns neither that the company exists nor anything about its id space.
2. **The same-tenant non-member 403 is preserved** — so no existing behaviour or test changes for `accountant`/`viewer`/`customer` roles. Pinned by `test_same_tenant_non_member_still_gets_403_not_404`.
3. **It returns the `Company`** — backwards compatible (all 61 callers ignore the return value today) but lets future callers drop a redundant re-fetch.

Defence-in-depth predicates were added on the four highest-risk paths so the *query itself* cannot cross a tenant boundary even if a future caller reaches it another way: `PaymentMatch.tenant_id` (bulk approve), `AccountantNote.tenant_id` (notes), `CompanyInvitation.tenant_id` (list and revoke). `revoke_invitation` now mirrors the check `users.py:129-131` has always had for the equivalent user-invitation revoke.

**HIGH-4 required a judgement call.** Cross-tenant accountant delegation was *documented as an intended feature* (`docs/accountant-ecosystem.md`, "IMPLEMENTED, tested (7 tests)"). It never worked: the grant succeeded while every data endpoint rejected the grantee, and the company never appeared in their `GET /companies`. What it did do was defeat the membership check for the endpoints that relied on that alone. Acceptance is now rejected with 403, making the boundary explicit rather than half-open.

Real delegation needs a first-class `CompanyAccess` grant (per-company role, revocable, expiring) that resource queries authorise against **instead of** `tenant_id` — audit §6.7(b), roadmap Tier 4.2. That is a feature, not a security fix, and building it here would have violated the no-unrelated-refactoring rule. It is recorded under §7 as the one capability deliberately withdrawn.

### 2.2 Phase 17.3 — logout and session revocation

| Audit ID | Severity | Vulnerability | Status |
|---|---|---|---|
| 6.13 | **Critical** | "Log out" never called the backend. `lib/api.ts` had **no `logout` method at all**, so `auth-context.logout()` only cleared `localStorage`. With `access_token_expire_minutes = 60 * 24` and no refresh token, a JWT captured beforehand stayed cryptographically valid **and** kept passing the `token_version` check for 24 hours. | **Fixed** |

`POST /api/v1/auth/logout` already existed and was already correct — it bumps `token_version`, which invalidates every token ever issued for the account, and writes an audit row. Nothing invoked it.

The fix is three parts:

- **`lib/api.ts`** — added the missing `logout` method.
- **`lib/auth-context.tsx`** — `logout()` is now `async` and calls `api.logout(token)` inside `try`, with local state cleared in `finally` so a network failure, a 401 on an already-expired token, or an unreachable backend **still** logs the user out of the browser. It falls back to `localStorage.getItem("token")` when React state has not hydrated, so an early logout still revokes.
- **`components/glass/GlassSidebar.tsx`** — `onClick={() => void logout()}` to avoid a floating promise now that `logout` returns one.

The `AuthState` interface changed from `logout: () => void` to `logout: () => Promise<void>`; `tsc --noEmit` confirms every call site still type-checks.

### 2.3 Phase 17.4 — security configuration

| Audit ID | Severity | Vulnerability | Status |
|---|---|---|---|
| 6.4 | **Critical** | Five valid secrets committed to `config.py` with warning-only enforcement; the app booted and passed `/health` with all of them. `backend/.env` did not set `BSN_ENCRYPTION_KEY`, so this environment was encrypting Dutch citizen service numbers under a public key. `.env.example` and `.env.prod.example` each omitted three of the five variables, so following the documented setup *guaranteed* the insecure state. | **Fixed (fail-closed); keys deliberately NOT rotated** |
| 7.5 | High | Open Banking and MFA keys could not be rotated — `token_crypto.py` and `mfa_crypto.py` accepted a `*_PREVIOUS` key but had no `reencrypt_*` function and no script, despite both docstrings claiming "the same MultiFernet rotation pattern as crypto.py". `docs/encryption-key-rotation.md:3` still asserted BSN was the only encrypted data. | **Capability built; rotation not performed** |
| 7.19 | High | `bank_parsers.py` parsed attacker-supplied CAMT.053/054 with `ElementTree.fromstring` and zero hardening; no `defusedxml`. Entity expansion was blocked only incidentally by CPython 3.12's bundled expat (3.9 does not block it at all), and `requirements.txt` pins no Python version. | **Fixed** |
| 8.1 | Medium | CORS default widened to a hardcoded developer LAN IP (`192.168.68.105`) with `allow_credentials=True`; three stray backup files, none matched by `.gitignore`. | **Guard added; user's uncommitted default preserved** |
| — | New | Found while writing these tests: `repr(settings)` rendered **every** secret verbatim, because all were plain `str` fields. A failing test's fixture repr printed a configured webhook secret to the console. Any f-string, debug log or exception context touching the settings object did the same. | **Fixed (`repr=False`)** |

**Fail-closed secret validation.** A new `environment` setting (`development` default) selects the behaviour. Outside `PERMISSIVE_ENVIRONMENTS = {development, dev, test, testing}` the app **raises at import** and refuses to start. The permissive set is an allowlist, so a typo like `prodction` fails closed rather than open.

The guard is stricter than a simple equality check against the committed defaults:

- **Blank counts as an offence.** `JWT_SECRET=` in an env file yields an empty string; an empty HMAC signing key is worse than a placeholder and a value-equality comparison would not catch it.
- **The `.env.example` literal is also guarded.** The template ships `JWT_SECRET=change-me-in-production`, which is *not* the same string as the code default `dev-secret-change-in-production`. A check comparing only against the code default would have let an operator copy the template into `.env.prod` and sail straight past it while running a publicly-known signing key. `INSECURE_TEMPLATE_JWT_SECRET` closes that.
- **All five offenders are reported at once**, so an operator does not have to restart five times to find them all.

`insecure_placeholder_secrets()` is exported so tests, an operator pre-flight check and the rotation script all share one definition of "not good enough".

**Secrets are never rendered.** The validation table holds variable names, known-bad literals that are already public in the repository, and remediation hints. The warning and the exception name variables and explain how to generate a replacement; they never echo a configured value. Two tests enforce this with unique canaries.

**`repr=False` on every secret field** — `jwt_secret`, `database_url` (the production URL embeds `POSTGRES_PASSWORD`), `anthropic_api_key`, `kvk_api_key`, all three encryption keys, all three `*_previous` keys, and `billing_webhook_secret`. `model_dump()` and normal attribute access are unchanged, so no consumer is affected; only the incidental rendering paths are closed.

**Rotation capability built, rotation not performed.** Added `reencrypt_token_with_current_key()` and `reencrypt_mfa_secret_with_current_key()` (both one-liners over `MultiFernet.rotate()`, matching `crypto.py`'s existing `reencrypt_bsn_with_current_key`), plus `scripts/rotate_encryption_keys.py` covering all three classes with `--dry-run`, a required `--yes` to write, batched commits, and a hard refusal to migrate onto a key that is still a public placeholder.

The script **does not rotate a key** — it never reads, generates, prints or changes any key value. It migrates ciphertext from whatever key currently decrypts it onto whatever key is currently configured to encrypt with it. Changing the key remains an operator action.

No key was rotated in this phase, and `backend/.env` was not modified. Rotating now would have broken decryption of every existing BSN, bank token and MFA secret in the development database, which the brief explicitly forbids. The tested procedure and its rollback path are in §7.

**XXE / entity expansion.** A `_safe_fromstring()` gate now rejects any `<!DOCTYPE` or `<!ENTITY` (case-insensitive, since XML keywords are) before the parser is reached, in both `parse_camt053` and `parse_camt054`. Real CAMT files never carry a DTD — they identify themselves with `xmlns` on the root element — so legitimate imports are unaffected, and `test_legitimate_camt053_still_parses` / `test_legitimate_camt054_still_parses` pin that.

`defusedxml` was **not** added. It is not installed in the venv, and adding an import for a dependency that is not present would break the entire suite for anyone who has not re-installed. The explicit DTD rejection is strictly sufficient for this vector: no DTD means no internal entities means no expansion attack, and external entities already do not resolve in stock `ElementTree`. Adding `defusedxml` as belt-and-braces is recorded in §7.

**CORS.** `_validate_cors_origins()` now fails closed outside a permissive environment on a wildcard origin, a private/loopback/link-local host, or a plain `http://` origin on a named host. In development it warns — but only about non-loopback origins, so the documented `localhost`/`127.0.0.1` defaults do not print noise on every startup and desensitise people to the warning that matters.

**The user's uncommitted CORS default was deliberately not reverted.** Rule 2 (preserve existing uncommitted changes) conflicts with the audit's recommendation to remove the LAN IP. The conflict was resolved in favour of the rule: the guard now *detects and reports* that address at startup in development and *refuses to boot* with it in production, which is a stronger control than a silent revert, and reverting is listed in §7 as a one-line manual action.

**`.gitignore`** gained `*.bak`, `*.backup-*`, `*.orig`, `*.rej`, `*.save`, `*~`, plus `frontend/tsconfig.tsbuildinfo`, `frontend/test-results/`, `frontend/e2e/.auth/`, `frontend/e2e/.screenshots/` and a root-level `.pytest_cache/`. The three stray backups are now ignored rather than deleted.

**Env templates.** Both now document all five guarded secrets, their `_PREVIOUS` counterparts, `ENVIRONMENT`, and the exact generation command for each. `test_env_templates_document_every_guarded_variable` derives the required set from `_GUARDED_SECRETS` and fails if either template drifts, so this cannot silently regress again.

### 2.4 Phase 17.5 — RTL font correction

| Audit ID | Severity | Vulnerability | Status |
|---|---|---|---|
| 6.12 | **Critical** | `97f2d84` ("complete locale-aware formatting sweep") loaded Vazirmatn and Noto Sans Arabic and injected both CSS variables, but `globals.css` at that commit contained **no rule consuming them**. Every page downloaded two Arabic-script webfont families that were never rendered; Persian and Arabic fell back to Geist → Arial → browser default. The fix existed only as uncommitted working-tree state. | **Fixed and committed to the working tree** |

Four changes:

1. **Persian leads with Vazirmatn; Arabic now leads with Noto Sans Arabic.** Previously both shared one stack led by Vazirmatn — a typeface designed for Persian — so Arabic rendered in a Persian face. Each stack keeps the other as a fallback so mixed-script strings still render, and both end in a generic `sans-serif`. Dutch and English are untouched and still resolve to Geist.
2. **`:lang()` rather than `[lang=]`, and this is now enforced by test.** The intermediate state captured in `globals.css.backup-20261105-134650` used `:root[lang="fa"]`, an attribute selector requiring an exact match. `layout.tsx` emits the full BCP-47 tag (`"fa-IR"`, per `i18n/config.ts`'s `LOCALES`), so it never matched anything. `:root:lang(fa)` matches `"fa-IR"` correctly. A jsdom test asserts `document.documentElement.matches(":lang(fa)")` is `true` for `lang="fa-IR"` while `matches('[lang="fa"]')` is `false` — the exact historical bug, pinned.
3. **Verified through the production build**, not just the source. `next build` emitted `:root:lang(fa){--font-app-sans:var(--font-vazirmatn),…}` and `:root:lang(ar){--font-app-sans:var(--font-noto-sans-arabic),…}` into `.next/static/chunks/1txo2n37p3yz2.css`, with all eight `@font-face` families present (Geist, Geist Fallback, Geist Mono, Geist Mono Fallback, Vazirmatn, Vazirmatn Fallback, Noto Sans Arabic, Noto Sans Arabic Fallback), both variables resolving to real family names, `body` reading `var(--font-app-sans)`, and **zero** `[lang=` attribute selectors in the bundle.
4. **Automated tests at two levels**, because jsdom cannot resolve CSS `var()` through `getComputedStyle`: a structural vitest suite (`test/locale-fonts.test.ts`, 13 tests) that pins selectors, stacks, variable provisioning and `:lang()` semantics, and a Playwright suite (`e2e/i18n.spec.ts`, 5 new tests) that asserts the *computed* `font-family` in a real browser for all four locales plus a `document.fonts` check that a Dutch page never loads an Arabic-script face.

---

## 3. Files changed

### 3.1 Modified (20 tracked files, +760 −71)

| File | Δ | Phase | Change |
|---|---|---|---|
| `backend/app/core/deps.py` | +54 −7 | 17.1 | `require_company_access` tenant-authoritative for all roles, returns `Company`. **The user's uncommitted `find_user_by_email` helper is preserved verbatim.** |
| `backend/app/api/v1/companies.py` | +67 −2 | 17.1 | Documented fixes at `list_financial_years`, `_get_financial_year_or_404`; `invitation.tenant_id` predicate on list and revoke; `accept_invitation` gets a `None` check and rejects cross-tenant acceptance |
| `backend/app/api/v1/banking.py` | +15 −1 | 17.1 | `PaymentMatch.tenant_id` predicate on bulk approve |
| `backend/app/api/v1/workspace.py` | +8 −1 | 17.1 | `AccountantNote.tenant_id` predicate on `list_notes` |
| `backend/app/core/config.py` | +141 −40 | 17.4 | `environment` setting, `PERMISSIVE_ENVIRONMENTS`, `_GUARDED_SECRETS` table, `insecure_placeholder_secrets()`, `_enforce_secret_hygiene()` replacing five warning blocks, `INSECURE_TEMPLATE_JWT_SECRET`, `repr=False` on every secret field |
| `backend/app/main.py` | +77 −1 | 17.4 | `_validate_cors_origins()`. **The user's uncommitted CORS default line is preserved untouched.** |
| `backend/app/core/token_crypto.py` | +14 −0 | 17.4 | `reencrypt_token_with_current_key()` |
| `backend/app/core/mfa_crypto.py` | +14 −0 | 17.4 | `reencrypt_mfa_secret_with_current_key()` |
| `backend/app/accounting/bank_parsers.py` | +40 −2 | 17.4 | `_DTD_PROBE` + `_safe_fromstring()`, used by both CAMT parsers |
| `backend/.env.example` | +41 −3 | 17.4 | `ENVIRONMENT`, the three missing secrets, `_PREVIOUS` variants, generation commands, rotation-script pointer, CORS note |
| `.env.prod.example` | +48 −5 | 17.4 | Same, plus a prominent BREAKING CHANGE notice and a note that `NEXT_PUBLIC_API_URL` still does not reach the browser (audit 6.10, not in Phase 17 scope) |
| `docker-compose.prod.yml` | +9 −0 | 17.4 | `ENVIRONMENT: ${ENVIRONMENT:-production}` on the backend service — defaults to production so an `.env.prod` that forgets it still fails safe |
| `.gitignore` | +18 −0 | 17.4 | Backup-file and build-artifact patterns |
| `backend/tests/test_auth_security.py` | +54 −0 | 17.3 | One new test; the user's uncommitted email-normalisation test is preserved |
| `frontend/lib/api.ts` | +6 −0 | 17.3 | The missing `logout` method |
| `frontend/lib/auth-context.tsx` | +27 −6 | 17.3 | `async logout()` with `try/catch/finally`, localStorage fallback, `Promise<void>` in `AuthState` |
| `frontend/components/glass/GlassSidebar.tsx` | +1 −1 | 17.3 | `onClick={() => void logout()}` |
| `frontend/app/globals.css` | +39 −1 | 17.5 | Split `:root:lang(fa)` / `:root:lang(ar)` stacks, Arabic leads with Noto Sans Arabic, documented `:lang()` requirement |
| `frontend/e2e/i18n.spec.ts` | +80 −0 | 17.5 | Five Playwright tests for computed font selection |
| `backend/app/api/v1/auth.py` | +8 −1 | — | **Not touched by this phase.** Pre-existing user change, preserved. |

`backend/app/core/crypto.py` shows no diff — it already had `reencrypt_bsn_with_current_key`.

### 3.2 Created (5 files, excluding the audit report)

| File | Tests | Purpose |
|---|---|---|
| `backend/tests/test_cross_tenant_isolation.py` | 22 | Phase 17.2 regression suite |
| `backend/tests/test_phase17_security_config.py` | 57 | Phase 17.4 regression suite |
| `backend/scripts/rotate_encryption_keys.py` | — | Re-encryption tool for all three secret classes |
| `frontend/lib/__tests__/auth-context.test.tsx` | 7 | Phase 17.3 regression suite |
| `frontend/test/locale-fonts.test.ts` | 13 | Phase 17.5 structural regression suite |

### 3.3 Deliberately not changed

- **The 61 existing per-endpoint tenant checks.** Now redundant with the authoritative helper, but removing them across 28 routers would be a large, risky, unrelated refactor. They remain as defence-in-depth. Audit recommendation 11.3 item 22 covers consolidating them properly.
- **`backend/app/api/v1/auth.py`.** Contains an uncommitted user change. Nothing in Phase 17 required touching it.
- **The three stray backup files.** Gitignored, not deleted.
- **`backend/.env`.** Not modified. No key was rotated.
- **The CORS default in `main.py`.** Preserved per rule 2; now guarded rather than reverted.

---

## 4. Tests added, and proof they detect the vulnerabilities

**100 new tests**: 80 backend (22 + 57 + 1) and 20 frontend (7 + 13), plus 5 Playwright tests that require the e2e environment.

A security regression test that passes both before and after a fix is not evidence of anything, so **every fix was mutation-tested**: the vulnerability was reintroduced, the suite run, and the expected failures observed.

### 4.1 Cross-tenant (Phase 17.1/17.2)

The four fixed files were copied to `/tmp/phase17_backup/` with SHA-256 checksums recorded, then reverted — the three routers via `git show HEAD:…`, and `deps.py` via a targeted in-place replacement of `require_company_access` that **preserved the user's uncommitted `find_user_by_email`** (asserted in the script before writing).

**Result against the vulnerable code: 14 failed, 8 passed.**

All eight cross-tenant attack tests failed, meaning every attack succeeded:

```
FAILED test_require_company_access_rejects_every_role_from_another_tenant
FAILED test_cross_tenant_financial_year_lock_is_denied_and_changes_nothing
FAILED test_cross_tenant_financial_year_unlock_is_denied_and_changes_nothing
FAILED test_cross_tenant_bulk_match_approval_is_denied_and_posts_nothing
FAILED test_cross_tenant_financial_year_listing_is_denied
FAILED test_cross_tenant_invitation_listing_is_denied
FAILED test_cross_tenant_invitation_revocation_is_denied_and_changes_nothing
FAILED test_cross_tenant_accountant_notes_are_denied
FAILED test_cross_tenant_invitation_cannot_be_accepted
FAILED test_accepting_an_invitation_for_a_missing_company_is_404_not_500
```

The last of these produced the exact crash the audit predicted:

```
File ".../app/api/v1/companies.py", line 354, in accept_invitation
    if user not in company.users:
AttributeError: 'NoneType' object has no attribute 'users'
```

The 8 that passed were the positive controls and the token-roundtrip helper — correct in both versions, which is the point of having them.

Restoration was verified byte-for-byte: `shasum -a 256 -c` reported OK for all four files, and `git diff --stat` matched the pre-experiment snapshot exactly (144 insertions, 11 deletions).

**Test design.** Every endpoint test follows the shape the brief requires: two independent tenants built by `_build_tenant()`, four roles each (owner/admin/accountant/viewer) plus a same-tenant non-member admin, then attempt → assert denial → assert no mutation. Mutations are checked at the row level (`is_locked`, `locked_at`, `locked_by_user_id`, `status`, `revoked_at`, `approved_by_user_id`, `payment_id`, `reconciliation_status`) and by `Payment` row count.

Audit-log assertions are **entity-scoped, not tenant-scoped** — `AuditLog.entity_type == "financial_year" AND entity_id == <victim fy>`. This is deliberate and stronger: a successful cross-tenant write stamps the row with the *attacker's* `tenant_id`, so filtering by the victim's tenant would have missed it. A first attempt used a global `AuditLog` count and failed with `assert 2 == 0`, because each attacker login writes its own `login_success` row; the entity-scoped form is both correct and immune to that.

### 4.2 Logout (Phase 17.3)

Backend: `test_logout_revokes_the_token_for_protected_resources_not_just_auth_me` asserts `token_version` incremented and that the same token is then rejected on `/auth/me`, `/companies`, `/companies/{id}/financial-years`, `/companies/{id}/notes` and `/companies/{id}/workspace` — and that the rejection is specifically the revocation path (`"Session has been revoked, please sign in again"`), not a generic auth failure. The pre-existing `test_logout_revokes_the_token_immediately` covered only `/auth/me`.

Frontend: 7 tests. The load-bearing one is *"STILL clears local state and redirects when the revocation request fails"* — `mockLogout.mockRejectedValue(...)`, then assert token/user state cleared, `localStorage` emptied and the redirect issued. Also covered: the API is called with the live token, the localStorage-only fallback path, no API call when there is no token anywhere, and exactly-once per click.

### 4.3 Security configuration (Phase 17.4)

57 tests. Highlights:

- `test_unrecognised_environment_fails_closed` — `ENVIRONMENT=prodction` must refuse to start, not fall through to the permissive branch.
- `test_every_guarded_secret_is_individually_enforced` — parametrised over all five, so a table row wired to the wrong attribute cannot pass unnoticed.
- `test_blank_secrets_are_an_offence` — `""` and `"   "`.
- `test_the_env_template_jwt_literal_is_also_rejected` — the `change-me-in-production` gap.
- `test_no_guarded_secret_value_ever_reaches_a_log_or_exception_message` and `test_settings_repr_never_renders_a_secret_value` — canary-based leak detection over the exception message, every log record, `repr()`, `str()`; while asserting `model_dump()` still returns the real values so consumers are unaffected.
- `test_env_templates_document_every_guarded_variable` — derives the required set from `_GUARDED_SECRETS` and checks both templates.
- `test_full_rotation_procedure_for_every_secret_class` — parametrised over all three crypto modules, walking the four real steps: encrypt under OLD → set current=NEW/previous=OLD and confirm old ciphertext still reads → re-encrypt → remove OLD entirely and confirm the migrated value still reads **and the original no longer does**. Step four is the one that was impossible for two of the three classes before this phase.
- `test_billion_laughs_payload_is_rejected` and `test_external_entity_payload_is_rejected`, parametrised over both CAMT parsers, plus case-insensitivity (`<!DocType`, `<!EnTiTy`) and a bare `<!ENTITY` with no DOCTYPE keyword.
- `test_legitimate_camt053_still_parses` / `test_legitimate_camt054_still_parses` — the guard must not break real bank exports; asserts parsed amount and counterparty name.
- `test_rejection_is_a_clean_domain_error_not_a_500` — confirms `BankFileParseError`, which the caller maps to a 4xx, rather than a `ParseError` that would surface as a 500 with a traceback.
- 9 CORS tests covering wildcard, three private ranges, IPv6 ULA, loopback, plain-http-on-a-public-host, valid https, multiple origins, dev permissiveness, loopback noise suppression, and all-offenders-reported.

### 4.4 RTL fonts (Phase 17.5)

13 vitest tests, mutation-tested by reverting `globals.css` to the historical `:root[lang="fa"]` form: **5 failed**, restore verified by checksum, 13 passed again.

The test parses CSS properly rather than by `indexOf`, for two reasons found while writing it: `globals.css` declares `:root` several times (design tokens, then the font stack), so an `indexOf(":root")` lookup silently finds the wrong block; and the explanatory comment above the font rules contains the literal text `:root[lang="fa"]` describing the historical bug, so comments must be stripped before scanning or the attribute-selector check matches its own documentation.

Five Playwright tests were added for the *computed* result, since jsdom cannot resolve CSS `var()`. **These were not executed** — the suite requires a running backend and frontend with a seeded account and has no `webServer` block (audit §9.6). The production CSS bundle was inspected directly instead, which is recorded in TEST_RESULTS §5.

---

## 5. Is the application safer?

**Yes — substantially, and the improvement is verifiable rather than asserted.**

Before this phase, any authenticated `owner` or `admin` of any tenant could lock another tenant's financial year (halting their bookkeeping) and bulk-approve payment matches against another tenant's ledger (posting real payments to someone else's books), could enumerate another tenant's fiscal calendar and pending-invitation PII, could revoke another tenant's accountant invitations, and any user of any role including read-only `viewer` could read another tenant's free-text accountant notes. Those eight paths are closed, each with a test that was **observed to fail against the vulnerable code and pass against the fix**.

Logout now actually revokes. That closes a 24-hour window on every token leaked by XSS, a shared device, browser history or an intercepting proxy — and it is a one-line change that had been missing entirely.

The deployment can no longer come up with public encryption keys. This is the change with the largest blast radius: previously a `.env.prod` missing three variables produced a healthy-looking container that encrypted BSNs, bank tokens and MFA secrets under keys committed to the repository. It now refuses to start and names what is missing.

XML parsing no longer depends on which interpreter the image happened to be built with.

Two things are **not** safer yet, and are recorded honestly rather than quietly dropped: the committed key values are still in `config.py` and still in use by this development environment (rotating them is an operator action requiring a backup — §7), and `repr(settings)` was leaking secrets until this phase, which nobody had noticed.

The residual risk profile is dominated by items Phase 17 did not touch: the production frontend still cannot reach the API (audit 6.10), the rate limiter is still ineffective behind a proxy (6.9), MFA can still be re-enrolled without step-up (6.11), password reset still cannot deliver a token (6.8), and there is still no CI (11.1) — which is why every guarantee in this document rests on a test someone must remember to run.

---

## 6. Breaking changes

One, and it is intentional.

**`docker-compose.prod.yml` now sets `ENVIRONMENT: ${ENVIRONMENT:-production}` on the backend service.** A production stack whose `.env.prod` does not define all five guarded secrets will now **refuse to start** instead of starting insecurely. The container will crash-loop with a `RuntimeError` naming every offending variable and the command to generate each one.

This is the correct behaviour and the whole point of audit finding 6.4, but it is a change in deployment semantics and must not be discovered at 2 a.m. during a rollout. Before deploying:

1. Copy the updated `.env.prod.example` and fill in all five secrets plus their `_PREVIOUS` counterparts (leave `_PREVIOUS` empty unless mid-rotation).
2. Set `CORS_ALLOWED_ORIGINS` to the public `https://` origin(s). A wildcard, a private/loopback/link-local address, or a plain `http://` origin now also refuses to start.
3. Run the backend once locally with `ENVIRONMENT=production` and the real `.env.prod` to confirm it boots before shipping it.

Local development and the test suite are unaffected: `environment` defaults to `development`, which warns exactly as before.

The `AuthState.logout` type changed from `() => void` to `() => Promise<void>`. `tsc --noEmit` passes clean, and the single call site was updated.

---

## 7. Manual operations still required

Each of these needs a live credential, an external permission, a production system, or a decision that is not mine to make. **All were stopped before execution, per the brief.**

| # | Operation | Why it was not done | Blocking dependency |
|---|---|---|---|
| 1 | **Rotate all five secrets.** The committed values in `config.py` are burned — they are public in git history and cannot be un-leaked. `JWT_SECRET` is already custom in `backend/.env`; the other four are still placeholders there. | Rotating invalidates decryption of existing BSNs, bank tokens and MFA secrets unless the old key is kept in `_PREVIOUS`. The brief forbids rotation without a tested procedure **and** forbids overwriting existing encrypted data. | Take a database backup first (`scripts/backup_db.sh`), then follow the procedure below. |
| 2 | **Set `BSN_ENCRYPTION_KEY` in `backend/.env`.** This development environment is *currently* encrypting employee BSNs under the committed public key. | Changing it in place would make every existing `bsn_encrypted` value undecryptable. Must be done as a rotation (old key → `_PREVIOUS`), not a replacement. | Same as #1. Note `backend/storage/` contains what appear to be real uploaded invoices, so treat the local database as holding real personal data. |
| 3 | **Revert the CORS default in `backend/app/main.py`** to `http://localhost:3000` and move `http://192.168.68.105:3000` into `backend/.env`. | That line is an uncommitted user change; rule 2 required preserving it. The new guard detects and reports it, and refuses to boot with it in production. | A one-line edit plus a decision about whether the LAN origin is still wanted for device testing. |
| 4 | **Delete the three stray backup files** (`backend/app/main.py.bak`, `frontend/app/globals.css.backup-20261105-134537`, `…-134650`). | Rule 4 — do not delete project files unless explicitly justified. They are now gitignored, so they are inert. | Confirm the `globals.css` fix is committed first; those two backups are currently the only record of the intermediate `:root[lang="fa"]` bug. |
| 5 | **Add `defusedxml`** to `requirements.txt` and swap `xml.etree.ElementTree` for it in `bank_parsers.py`. | Installing a package changes the environment, and an import for an absent dependency would break the entire suite for anyone who has not re-installed. The DTD rejection already closes the vector. | `pip install defusedxml` in the venv and in the Docker image, then re-run the parser tests. |
| 6 | **Run the Playwright e2e suite** to confirm computed font selection in a real browser. | Requires a backend on port 8010, a frontend dev server, and the seeded `mollie-visual@example.com` account. The config has no `webServer` block (audit §9.6). | Start both servers, seed the account, then `npm run test:e2e`. |
| 7 | **Decide the fate of cross-tenant accountant delegation.** `POST /companies/invitations/accept` now rejects cross-tenant acceptance, so the capability described in `docs/accountant-ecosystem.md` is explicitly withdrawn rather than silently broken. That document, and Phase 14's "IMPLEMENTED, tested (7 tests)" claim, are now inaccurate and should be corrected. | Implementing real delegation needs a `CompanyAccess` grant model with per-company roles — a feature, not a security fix (audit §6.7(b), roadmap Tier 4.2). | A product decision: build `CompanyAccess`, or drop the multi-firm accountant story and update the docs. |

**Key-rotation procedure (for #1 and #2), now that the tooling exists:**

1. Back up the database: `backend/scripts/backup_db.sh`. Verify the dump is non-empty.
2. Generate a new key. Never paste it into a shell history, a ticket or a chat: `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
3. Move the **current** key into the matching `*_PREVIOUS` variable and set the new key as current. Both old and new now decrypt; only the new encrypts.
4. Restart the application and confirm it boots and `/health` passes.
5. Preview the migration: `.venv/bin/python scripts/rotate_encryption_keys.py --dry-run`. It reports row counts per secret class and writes nothing. It refuses to run at all if the current key is still a public placeholder.
6. Apply it: `.venv/bin/python scripts/rotate_encryption_keys.py --yes`. Batched commits, so a partial run is safe and re-running is idempotent.
7. **Verify before retiring anything**: a masked BSN displays on a payslip, an MFA code verifies, an Open Banking sync succeeds.
8. Only then remove the old key from `*_PREVIOUS` and restart.

**Rollback at any point up to step 8:** put the old key back as current and drop the new one. Nothing in the database needs restoring, because the old key still decrypts everything throughout — which is exactly why step 8 must not be rushed.

---

## 8. Git state

**No commits were made.** The brief authorises separate reviewable commits only if explicitly requested, and it was not. All Phase 17 work sits in the working tree alongside the pre-existing uncommitted changes, which were preserved.

Before this phase:
```
 M backend/app/api/v1/auth.py
 M backend/app/core/deps.py
 M backend/app/main.py
 M backend/tests/test_auth_security.py
 M frontend/app/globals.css
?? backend/app/main.py.bak
?? frontend/app/globals.css.backup-20261105-134537
?? frontend/app/globals.css.backup-20261105-134650
```

After this phase — 20 modified, 6 untracked (5 new files from this phase plus the audit report), and the three stray backups now gitignored so they no longer appear:
```
 M .env.prod.example                              M backend/app/core/mfa_crypto.py
 M .gitignore                                     M backend/app/core/token_crypto.py
 M backend/.env.example                           M backend/app/main.py
 M backend/app/accounting/bank_parsers.py         M backend/tests/test_auth_security.py
 M backend/app/api/v1/auth.py        (untouched)  M docker-compose.prod.yml
 M backend/app/api/v1/banking.py                  M frontend/app/globals.css
 M backend/app/api/v1/companies.py                M frontend/components/glass/GlassSidebar.tsx
 M backend/app/api/v1/workspace.py                M frontend/e2e/i18n.spec.ts
 M backend/app/core/config.py                     M frontend/lib/api.ts
 M backend/app/core/deps.py                       M frontend/lib/auth-context.tsx
?? backend/scripts/rotate_encryption_keys.py      ?? frontend/lib/__tests__/auth-context.test.tsx
?? backend/tests/test_cross_tenant_isolation.py   ?? frontend/test/locale-fonts.test.ts
?? backend/tests/test_phase17_security_config.py  ?? docs/QWEN_TECHNICAL_AUDIT_REPORT.md
```

If commits are authorised, the natural split is five reviewable units matching the sub-phases: (1) `deps.py` + the three routers + `test_cross_tenant_isolation.py`; (2) `api.ts` + `auth-context.tsx` + `GlassSidebar.tsx` + both logout tests; (3) `config.py` + `main.py` + the two crypto modules + `bank_parsers.py` + `rotate_encryption_keys.py` + `test_phase17_security_config.py`; (4) the env templates + compose + `.gitignore`; (5) `globals.css` + `locale-fonts.test.ts` + `i18n.spec.ts`. The pre-existing changes to `auth.py` and the CORS line in `main.py` should be separated out and decided on independently (§7 items 3).

Note also, unchanged from the audit: the repository still has **no git remote**. None of this work is backed up off this machine.
