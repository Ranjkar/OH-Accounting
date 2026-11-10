# Phase 17 — Test Results

Every command actually executed during Phase 17, with its actual output. Nothing here is inferred, estimated or carried over from the project's own documentation.

| | |
|---|---|
| **Date** | 2026-11-05 |
| **Companion document** | `docs/PHASE_17_SECURITY_REMEDIATION.md` |
| **Machine** | darwin, CPython 3.12.16 (`backend/.venv`), Node 22 (`frontend/node_modules`) |
| **Database** | PostgreSQL, `onholland_accounting_test` (disposable sibling derived by `tests/conftest.py:32`) |

---

## 1. Headline results

| Check | Command | Result |
|---|---|---|
| **Backend full suite** | `pytest tests/ -p no:randomly -q` | **624 passed, 0 failed, 0 errors, 0 skipped** in 282.11s |
| **Frontend unit suite** | `vitest run` | **175 passed, 0 failed** across 11 files in 1.97s |
| **TypeScript type check** | `tsc --noEmit` | **exit 0**, no diagnostics |
| **Production frontend build** | `next build` | **exit 0**, 55 routes emitted |
| **ESLint** | `eslint .` | **0 errors**, 4 warnings — all pre-existing, in files this phase did not touch |
| **Backend static checks** | `py_compile` + import of every changed module | **all OK** (see §7 — no linter or type checker is installed in this project) |
| **Migration check** | `alembic heads`, `git status app/models/ alembic/` | **single head `d90e97d4bc35`**, no model or migration file touched, so no migration required |
| **Security regression (mutation)** | revert the fix, re-run | **14 failed against vulnerable code**, 22 pass against the fix |
| **Font regression (mutation)** | revert `globals.css`, re-run | **5 failed against the historical bug**, 13 pass against the fix |

**Test-count reconciliation.** The pre-Phase-17 baseline was 542 collected items (540 test functions plus 2 from the single `@pytest.mark.parametrize` in `test_payroll_validation.py`). Phase 17 added **82 backend tests** (22 + 59 + 1). 542 + 82 = **624**, matching the full-suite result exactly.

An intermediate full run partway through the phase returned **622 passed, 0 failed** (285.46s); the two-test difference is the pair of CORS noise-suppression tests added afterwards, and the final run above supersedes it.

---

## 2. Backend full suite

```
$ cd backend && ANTHROPIC_API_KEY="" .venv/bin/python -m pytest tests/ -p no:randomly -q --no-header -rf

624 passed, 919 warnings in 282.11s (0:04:42)
failures: 0
errors: 0
skipped: 0
```

`ANTHROPIC_API_KEY=""` was set deliberately for every pytest invocation in this phase. Audit finding §7.13 identified two tests — `test_automation_api.py:131` and `test_financial_reports_api.py:278`, both named `..._uses_stub_provider_without_api_key` — that do **not** null the key and therefore make real, billable calls to `api.anthropic.com` when `backend/.env` supplies one, which it does. Nulling it forces the stub path those tests claim to exercise and avoids spending the project's API credits. This is recorded as a deviation from a bare `pytest` invocation; fixing the underlying leak is audit recommendation 11.3 item 24 / roadmap Tier 2.4 and was out of Phase 17 scope.

`-p no:randomly` was passed defensively; `pytest-randomly` is not installed, so ordering is the default alphabetical.

**No test was skipped, xfailed or deselected.** The five KVK network tests in `test_kvk_integration.py` ran and passed, meaning `api.kvk.nl` was reachable at execution time.

---

## 3. Per-file results for new and adjacent suites

```
$ for f in tests/test_cross_tenant_isolation.py tests/test_phase17_security_config.py \
           tests/test_auth_security.py tests/test_company_invitations.py \
           tests/test_banking_api.py tests/test_documents_api.py \
           tests/test_user_management.py tests/test_employee_self_service_api.py; do
    ANTHROPIC_API_KEY="" .venv/bin/python -m pytest $f -p no:randomly -q --no-header; done

tests/test_cross_tenant_isolation.py             22 passed, 50 warnings in 58.92s
tests/test_phase17_security_config.py            59 passed,  9 warnings in  0.03s
tests/test_auth_security.py                      11 passed, 27 warnings in  7.11s
tests/test_company_invitations.py                 7 passed, 26 warnings in  9.67s
tests/test_banking_api.py                         8 passed, 55 warnings in  5.84s
tests/test_documents_api.py                      15 passed, 59 warnings in  9.58s
tests/test_user_management.py                    25 passed, 45 warnings in 33.28s
tests/test_employee_self_service_api.py           6 passed, 45 warnings in  6.33s
```

The last five files were run specifically because they exercise the code paths Phase 17 changed:

- `test_company_invitations.py` (7) — the pre-existing same-tenant invitation suite. **All 7 still pass**, confirming that rejecting *cross*-tenant acceptance did not break the documented same-tenant accountant-delegation flow.
- `test_banking_api.py` (8) — covers the bulk payment-match approval path and `require_company_access` in banking.
- `test_documents_api.py` (15) — contains the project's original `test_cross_tenant_access_is_blocked` and `test_viewer_cannot_upload_or_approve`.
- `test_user_management.py` (25) — role-escalation and last-owner protection, all of which route through the changed helper.
- `test_employee_self_service_api.py` (6) — the `employee` role's only access path.

`test_auth_security.py` went from 10 to 11 tests; the addition is `test_logout_revokes_the_token_for_protected_resources_not_just_auth_me`. The pre-existing uncommitted `test_login_normalizes_email_case_and_whitespace` is still present and passing.

---

## 4. Mutation testing — proof the new tests detect the vulnerabilities

A security regression test that passes both before and after a fix is not evidence. Every fix was therefore verified by reintroducing the vulnerability and observing the expected failures.

### 4.1 Cross-tenant isolation

The four fixed files were copied to `/tmp/phase17_backup/` with SHA-256 checksums recorded, then reverted: the three routers with `git show HEAD:…`, and `deps.py` with a targeted in-place replacement of `require_company_access` only — the script asserted `"find_user_by_email" in out` **before** writing, so the user's uncommitted helper could not be lost.

```
$ pytest tests/test_cross_tenant_isolation.py -p no:randomly -q     # against VULNERABLE code

FAILED test_require_company_access_rejects_every_role_from_another_tenant
FAILED test_require_company_access_allows_same_tenant_admin_without_membership
FAILED test_require_company_access_returns_the_company_for_members
FAILED test_same_tenant_non_member_still_gets_403_not_404
FAILED test_require_company_access_unknown_company_is_404
FAILED test_cross_tenant_financial_year_lock_is_denied_and_changes_nothing
FAILED test_cross_tenant_financial_year_unlock_is_denied_and_changes_nothing
FAILED test_cross_tenant_bulk_match_approval_is_denied_and_posts_nothing
FAILED test_cross_tenant_financial_year_listing_is_denied
FAILED test_cross_tenant_invitation_listing_is_denied
FAILED test_cross_tenant_invitation_revocation_is_denied_and_changes_nothing
FAILED test_cross_tenant_accountant_notes_are_denied
FAILED test_cross_tenant_invitation_cannot_be_accepted
FAILED test_accepting_an_invitation_for_a_missing_company_is_404_not_500

14 failed, 8 passed, 37 warnings in 57.13s
```

Every cross-tenant attack succeeded against the vulnerable code. The `accept_invitation` failure reproduced the exact crash the audit predicted from static reading alone:

```
File "/Users/sam/Projects/Accounting/backend/app/api/v1/companies.py", line 354, in accept_invitation
    if user not in company.users:
AttributeError: 'NoneType' object has no attribute 'users'
```

The 8 that passed were the positive controls (`test_same_tenant_*`) and `test_hash_reset_token_roundtrip_is_stable` — correct in both versions, which is precisely why they are there: they prove the suite cannot pass by simply breaking the endpoints for everyone.

Restoration was verified byte-for-byte:

```
$ shasum -a 256 -c /tmp/phase17_backup/CHECKSUMS
banking.py: OK
companies.py: OK
deps.py: OK
workspace.py: OK

$ git diff --stat <the four files>          # identical to the pre-experiment snapshot
 backend/app/api/v1/banking.py   | 16 +++++++++-
 backend/app/api/v1/companies.py | 69 +++++++++++++++++++++++++++++++++++++++--
 backend/app/api/v1/workspace.py |  9 +++++-
 backend/app/core/deps.py        | 61 +++++++++++++++++++++++++++++++-----
 4 files changed, 144 insertions(+), 11 deletions(-)

$ grep -c find_user_by_email app/core/deps.py
2                                             # the user's uncommitted helper survived
```

### 4.2 RTL font selection

```
$ cp app/globals.css /tmp/globals_phase17.css && shasum -a 256 /tmp/globals_phase17.css > /tmp/globals_phase17.sha
$ python3 -c "…replace(':root:lang(fa) {', ':root[lang=\"fa\"] {')…"
bug reintroduced: True

$ vitest run test/locale-fonts.test.ts

 FAIL  … > uses the :lang() pseudo-class, never a [lang=] attribute selector
 FAIL  … > gives Persian (fa-IR) Vazirmatn as its primary face
 FAIL  … > gives Arabic (ar-SA) Noto Sans Arabic as its primary face
 FAIL  … > keeps --font-sans in step with --font-app-sans for both RTL locales
 FAIL  … > covers all four locales, with exactly the two RTL ones getting an override

 Test Files  1 failed (1)
      Tests  5 failed | 8 passed (13)

$ cp /tmp/globals_phase17.css app/globals.css && shasum -a 256 -c /tmp/globals_phase17.sha
/tmp/globals_phase17.css: OK

$ vitest run test/locale-fonts.test.ts
 Test Files  1 passed (1)
      Tests  13 passed (13)
```

### 4.3 Not mutation-tested, and why

The Phase 17.3 and 17.4 fixes were **not** mutation-tested by reverting source. For 17.3 the pre-fix state is unambiguous and already documented — `lib/api.ts` contained no `logout` method at all, so there was no code path to revert to. For 17.4 the guards are exercised directly and parametrically: `test_every_guarded_secret_is_individually_enforced` walks all five secrets, `test_unrecognised_environment_fails_closed` proves the allowlist cannot be bypassed by a typo, and `test_blank_secrets_are_an_offence` proves an empty value is caught. Reverting `config.py` would remove the functions under test rather than make them fail, so it would not be a meaningful mutation.

---

## 5. Production build and CSS bundle verification

```
$ cd frontend && node_modules/.bin/next build
next build exit: 0
```

55 routes emitted (53 `ƒ` Dynamic, 6 `◐` Partial Prerender for the dynamic segments).

The audit's finding 6.12 was that `globals.css` at HEAD declared no rule consuming the loaded fonts. Because a source-level fix could still be undone by the CSS pipeline, the **built bundle** was inspected directly:

```
$ CSS=.next/static/chunks/1txo2n37p3yz2.css

$ grep -o ':root:lang(fa)[^}]*}' $CSS
:root:lang(fa){--font-app-sans:var(--font-vazirmatn), var(--font-noto-sans-arabic), sans-serif;--font-sans:var(--font-vazirmatn), var(--font-noto-sans-arabic), sans-serif}

$ grep -o ':root:lang(ar)[^}]*}' $CSS
:root:lang(ar){--font-app-sans:var(--font-noto-sans-arabic), var(--font-vazirmatn), sans-serif;--font-sans:var(--font-noto-sans-arabic), var(--font-vazirmatn), sans-serif}

$ grep -o '\-\-font-app-sans:[^;}]*' $CSS | sort -u
--font-app-sans:var(--font-geist-sans)
--font-app-sans:var(--font-noto-sans-arabic), var(--font-vazirmatn), sans-serif
--font-app-sans:var(--font-vazirmatn), var(--font-noto-sans-arabic), sans-serif

$ grep -o 'body{[^}]*font-family:[^;}]*' $CSS
body{background:var(--background);color:var(--foreground);font-family:var(--font-app-sans), Arial, Helvetica, sans-serif

$ grep -c '\[lang=' $CSS
0
```

Both CSS variables resolve to real family names, and all eight `@font-face` families are present:

```
$ grep -o '\-\-font-vazirmatn:[^;}]*' $CSS | sort -u
--font-vazirmatn:"Vazirmatn", "Vazirmatn Fallback"

$ grep -o '\-\-font-noto-sans-arabic:[^;}]*' $CSS | sort -u
--font-noto-sans-arabic:"Noto Sans Arabic", "Noto Sans Arabic Fallback"

$ grep -o '@font-face{font-family:[^;}]*' $CSS | sed 's/@font-face{font-family://' | sort -u
Geist
Geist Fallback
Geist Mono
Geist Mono Fallback
Noto Sans Arabic
Noto Sans Arabic Fallback
Vazirmatn
Vazirmatn Fallback
```

An earlier check appeared to show only one `Vazirmatn` occurrence; that was `grep -c`, which counts matching **lines**, and minified CSS is a single line. Recounted with `grep -o … | wc -l`: Vazirmatn 8, Noto Sans Arabic 10, `font-vazirmatn` 5, `font-noto-sans-arabic` 5, `font-geist-sans` 5.

**Not verified in a browser.** True computed `font-family` per locale requires the Playwright suite, which needs a running backend on port 8010, a frontend dev server and the seeded `mollie-visual@example.com` account, and `playwright.config.ts` has no `webServer` block (audit §9.6). The five new Playwright tests in `e2e/i18n.spec.ts` were **written but not executed**. Bundle inspection is strong evidence but is not a substitute; this is recorded as manual operation #6.

---

## 6. Fail-closed secret validation — direct verification

```
$ .venv/bin/python -c "import app.core.config as c; print(c.settings.environment); \
    print([n for n,_ in c.insecure_placeholder_secrets()])"
environment = development
offending var NAMES: ['BSN_ENCRYPTION_KEY', 'OPEN_BANKING_TOKEN_ENCRYPTION_KEY',
                      'MFA_SECRET_ENCRYPTION_KEY', 'BILLING_WEBHOOK_SECRET']
OK: imported without raising
```

`JWT_SECRET` is absent from that list because `backend/.env` sets a custom value — confirming the audit's finding that only the other four are on committed defaults in this environment.

```
$ ENVIRONMENT=production .venv/bin/python -c "import app.core.config"
OK: RuntimeError raised
secret values leaked into message: NONE

$ ENVIRONMENT=production JWT_SECRET=<generated> BSN_ENCRYPTION_KEY=<generated> \
  OPEN_BANKING_TOKEN_ENCRYPTION_KEY=<generated> MFA_SECRET_ENCRYPTION_KEY=<generated> \
  BILLING_WEBHOOK_SECRET=<generated> .venv/bin/python -c "import app.core.config as c; \
  print('offenders =', c.insecure_placeholder_secrets())"
OK: booted in production with real secrets; offenders = []
```

All three modes behave correctly: warn in development, refuse in production, boot in production with real secrets. The leak check confirms no key value reaches the exception message. Generated keys were produced inline by a subshell and were never echoed; the transcript above shows `<generated>` placeholders rather than the values.

The improved warning text is visible in ordinary use, still naming variables and never values:

```
$ .venv/bin/alembic heads
BSN_ENCRYPTION_KEY is still the insecure placeholder value. Employee BSNs would be
encrypted under a key that is committed to this repository, so anyone with database or
backup read access can decrypt every one of them. Generate one with: python -c
'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
…
d90e97d4bc35 (head)
```

---

## 7. Backend static checks — what exists and what does not

**This project has no backend linter, formatter or type checker.** Verified:

```
$ for t in ruff mypy flake8 black pylint; do .venv/bin/$t --version; done
ruff     (no output — not installed)
mypy     (no output — not installed)
flake8   (no output — not installed)
black    (no output — not installed)
pylint   (no output — not installed)

$ ls -a | grep -iE "ruff|mypy|flake8|setup.cfg|pyproject|tox"     # in backend/
none
$ ls -a | grep -iE "ruff|mypy|pyproject|setup.cfg"                 # at repo root
none at repo root
```

So "backend static checks" could only mean compilation and import verification. Both were run over every file this phase created or modified:

```
$ .venv/bin/python -m py_compile \
    app/core/config.py app/core/deps.py app/core/crypto.py app/core/token_crypto.py \
    app/core/mfa_crypto.py app/main.py app/accounting/bank_parsers.py \
    app/api/v1/companies.py app/api/v1/banking.py app/api/v1/workspace.py \
    scripts/rotate_encryption_keys.py tests/test_cross_tenant_isolation.py \
    tests/test_phase17_security_config.py tests/test_auth_security.py
py_compile: ALL OK

$ .venv/bin/python -c "import app.main, app.core.config, app.core.deps, app.core.crypto, \
    app.core.token_crypto, app.core.mfa_crypto, app.accounting.bank_parsers, \
    app.api.v1.companies, app.api.v1.banking, app.api.v1.workspace"
all modules import cleanly
```

The import check also confirmed there is **no circular import** from the new `from app.models.company import Company` in `core/deps.py`, and it exercised the new CORS guard, which correctly warned about the developer LAN address in development mode:

```
{"level": "WARNING", "logger": "app.main", "message": "CORS_ALLOWED_ORIGINS contains
 'http://192.168.68.105:3000': host is a private/loopback/link-local address
 (acceptable in local development only).", "request_id": "-"}
```

Loopback origins (`localhost`, `127.0.0.1`) produce no warning in development — deliberate, so the noise does not desensitise anyone to the one that matters. Both behaviours are pinned by `test_development_warns_about_a_lan_origin_but_not_about_loopback` and `test_production_rejects_loopback_origins_too`.

Adding ruff and mypy is audit recommendation 11.1 item 4 / roadmap Tier 2.1, and was out of Phase 17 scope.

---

## 8. Migration checks

```
$ git status --short app/models/
(empty — no model file modified)

$ git status --short alembic/
(empty — no migration added or edited)

$ .venv/bin/alembic heads
d90e97d4bc35 (head)                    # exactly one head

$ .venv/bin/alembic history | wc -l
26                                     # 22 revisions plus headers
```

Phase 17 made **no schema changes**, so no migration was required and none was generated. This is worth stating explicitly because audit finding §7.14 established that the migration chain has **zero test coverage** (`conftest.py:37` builds the schema with `Base.metadata.create_all`, and `grep -rn alembic tests/` returns nothing), and §7.18 established that migration `3853605281ec` deliberately creates 54 indexes that are not mirrored in model metadata — so `alembic revision --autogenerate` would propose dropping them. Neither `upgrade head` nor `autogenerate` was run against a database in this phase; both are roadmap Tier 2.1 items.

---

## 9. Frontend checks

```
$ node_modules/.bin/vitest run
 ✓ lib/__tests__/auth-context.test.tsx            (7 tests)   107ms   ← NEW (17.3)
 ✓ messages/__tests__/parity.test.ts              (7 tests)   106ms
 ✓ components/glass/__tests__/GlassModal.test.tsx  (5 tests)   259ms
 ✓ components/glass/__tests__/GlassTable.test.tsx  (5 tests)   258ms
 ✓ components/glass/__tests__/GlassDropdown.test.tsx (5 tests) 286ms
 ✓ components/glass/__tests__/GlassButton.test.tsx (4 tests)   314ms
 ✓ components/glass/__tests__/GlassSidebar.test.tsx (5 tests)  405ms
 ✓ lib/__tests__/format.test.ts                  (18 tests)    27ms
 ✓ lib/__tests__/locale-context.test.tsx          (4 tests)    42ms
 ✓ test/locale-fonts.test.ts                     (13 tests)    13ms   ← NEW (17.5)
 ✓ components/glass/__tests__/navConfig.test.ts (102 tests)     6ms

 Test Files  11 passed (11)
      Tests  175 passed (175)
   Duration  1.97s
```

`GlassSidebar.test.tsx` (5 tests) passes unchanged despite the `onClick={() => void logout()}` edit.

```
$ node_modules/.bin/tsc --noEmit
tsc exit: 0                                    # no output, no diagnostics

$ node_modules/.bin/eslint .
✖ 4 problems (0 errors, 4 warnings)
eslint exit: 0
```

The 4 warnings are pre-existing and in files this phase did not touch:

| File | Warning |
|---|---|
| `app/audit-log/page.tsx:75` | `react-hooks/exhaustive-deps` |
| `app/documents/[id]/page.tsx:192` | `@next/next/no-img-element` |
| `app/reconciliation/page.tsx:42` | `react-hooks/exhaustive-deps` |
| `app/users/page.tsx:59` | `react-hooks/exhaustive-deps` |

None of `lib/api.ts`, `lib/auth-context.tsx`, `components/glass/GlassSidebar.tsx`, `test/locale-fonts.test.ts` or `lib/__tests__/auth-context.test.tsx` produces a warning. In particular the `async` logout and the `void` wrapper at the call site are clean.

`package.json` still has **no `typecheck` script** despite the project's docs repeatedly claiming `tsc --noEmit` was run; the command was invoked directly here. Adding the script is audit recommendation 11.5 item 52.

---

## 10. Tests added in Phase 17

| File | Tests | Executed? |
|---|---|---|
| `backend/tests/test_cross_tenant_isolation.py` | 22 | **Yes — 22 passed** |
| `backend/tests/test_phase17_security_config.py` | 59 | **Yes — 59 passed** |
| `backend/tests/test_auth_security.py` (+1) | 1 | **Yes — 11 passed in file** |
| `frontend/lib/__tests__/auth-context.test.tsx` | 7 | **Yes — 7 passed** |
| `frontend/test/locale-fonts.test.ts` | 13 | **Yes — 13 passed** |
| `frontend/e2e/i18n.spec.ts` (+5) | 5 | **No** — requires servers and a seeded account (§5) |
| **Total** | **107** | **102 executed, all passing; 5 written but not run** |

### What the 22 cross-tenant tests cover

Two fully independent tenants built by `_build_tenant()`, each with five users (owner, admin, accountant, viewer, and a same-tenant admin who is *not* a company member), a company, a 2026 financial year, an accountant note, a pending invitation, and a bank account → import batch → bank transaction → accounting transaction → HIGH-confidence SUGGESTED `PaymentMatch` chain.

Five unit tests on the helper itself (all four roles rejected cross-tenant; same-tenant admin without membership still allowed; member allowed and `Company` returned; same-tenant non-member still 403 **not** 404; unknown company 404), then one test per vulnerable endpoint asserting denial across every applicable role, then the positive controls.

Mutation assertions check the actual columns — `is_locked`, `locked_at`, `locked_by_user_id`, `invitation.status`, `revoked_at`, `match.status`, `approved_by_user_id`, `approved_at`, `payment_id`, `bank_tx.reconciliation_status` — plus `Payment` row count, and entity-scoped `AuditLog` counts. Audit assertions are scoped by `entity_type` + `entity_id` rather than by tenant, because a successful cross-tenant write stamps the row with the **attacker's** `tenant_id` and a tenant-scoped count would have missed it.

### What the 59 configuration tests cover

Fail-closed secret validation (all five secrets individually, blank values, the `.env.example` literal, unrecognised `ENVIRONMENT`, all offenders reported at once, dev warns instead of raising); secret-leak prevention (canary values never appear in the exception message, any log record, `repr()` or `str()`, while `model_dump()` still returns them); env-template completeness derived from `_GUARDED_SECRETS`; the full four-step rotation procedure for **all three** crypto modules including retirement of the old key; the rotation script's refusal to migrate onto a public placeholder and its coverage of all three classes; XXE/DTD rejection for both CAMT parsers across four prolog variants including case-insensitivity and a bare `<!ENTITY`; legitimate CAMT.053 and CAMT.054 still parsing; `BankFileParseError` rather than a 500; and nine CORS cases.

---

## 11. Known gaps in this verification

Stated plainly rather than left implicit.

1. **The five new Playwright tests were not executed.** No server was started. Computed `font-family` per locale is therefore verified only by inspecting the production CSS bundle (§5), not by a browser.
2. **No coverage measurement exists.** `pytest-cov` and `coverage` are in neither `requirements.txt` nor the venv, so no line or branch coverage figure can be given for the new tests or for the codebase.
3. **No end-to-end HTTP test of the CORS or secret guards.** Both are verified by calling `_validate_cors_origins()` and `_enforce_secret_hygiene()` directly with monkeypatched settings. The guards run at import time, so exercising them through a real server start would require a subprocess with a crafted environment — worth adding, not done here.
4. **The rotation script was never run against a database**, only its guard function and its `SECRET_CLASSES` table were tested. Its `--dry-run` and `--yes` paths are unexercised. Running it is manual operation #1/#2 and requires a backup first.
5. **The full suite was run three times, always in the same alphabetical order.** `pytest-randomly` is not installed, so the order-dependent provider-singleton issue from audit §7.13 was neither triggered nor fixed.
6. **Concurrency was not tested.** The cross-tenant tests are sequential. Audit finding §6.6 (no DB-level idempotency guard on ledger posting) is a race condition and remains open — it was not in Phase 17 scope.
7. **`docker compose config` could not be run.** Docker 29.4.0 is installed, but the command exits 1 with `env file /Users/sam/Projects/Accounting/.env.prod not found` — that file is gitignored and operator-created, and this is a pre-existing requirement of the compose file (`env_file: .env.prod`), not something Phase 17 introduced. Creating it was out of scope. The edit was validated structurally instead:

```
$ python -c "import yaml; …"
docker-compose.prod.yml: valid YAML, services = ['backend', 'frontend', 'postgres']
docker-compose.yml:      valid YAML, services = ['backend', 'frontend', 'postgres']
backend.environment keys: ['DATABASE_URL', 'ENVIRONMENT']
ENVIRONMENT value: ${ENVIRONMENT:-production}
env_file preserved: ['.env.prod']
postgres still has no published ports: OK
networks: {'internal': {'internal': True}, 'public': {}}
```

So the new key is correctly placed under the backend service, `env_file` is untouched, and Postgres remains internal-only with no host publishing. No image was built and no container was started.
