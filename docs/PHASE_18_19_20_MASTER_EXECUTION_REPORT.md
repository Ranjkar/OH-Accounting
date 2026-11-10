# Phases 18, 19 and 20 — Master Execution Report

| | |
|---|---|
| **Date** | 2026-11-05 |
| **Branch** | `phase-16-3-complete-internationalisation` |
| **HEAD** | `97f2d84` — **unchanged. No commits were made.** |
| **Working tree** | 28 modified files (+929 −80 vs HEAD), 22 untracked |
| **Release status** | ⚠️ **READY FOR INTERNAL TESTING** — not staging, not production |
| **Tests** | **662 backend passed / 0 failed / 0 skipped** · **175 frontend passed** · `tsc` exit 0 · `next build` exit 0 · ESLint 0 errors |

Companion documents, all in `docs/`:

| Phase | Documents |
|---|---|
| 18 | `PHASE_18_PRODUCTION_READINESS.md` · `PHASE_18_DEPLOYMENT_RUNBOOK.md` · `PHASE_18_TEST_RESULTS.md` |
| 19 | `PHASE_19_PRODUCT_COMPLETENESS.md` · `PHASE_19_ACCOUNTING_AND_TAX_REVIEW.md` · `PHASE_19_FEATURE_MATRIX.md` · `PHASE_19_TEST_RESULTS.md` |
| 20 | `PHASE_20_FINAL_QA_REPORT.md` · `PHASE_20_RELEASE_READINESS.md` · `PHASE_20_OPERATIONS_HANDOVER.md` · `PHASE_20_KNOWN_ISSUES.md` |
| Prior | `QWEN_TECHNICAL_AUDIT_REPORT.md` · `PHASE_17_SECURITY_REMEDIATION.md` · `PHASE_17_TEST_RESULTS.md` |

---

## 1. What was inspected

Read before changing anything, per rules 1–4.

**Repository state.** Branch, HEAD, all 88 commits, full working-tree diff, untracked file list. Confirmed the 5 pre-existing modified files and 3 stray backups from before this session, and that `main` is 81 commits behind HEAD with **no git remote**.

**Phase 17 documentation.** Both documents read in full. Their 8 vulnerability fixes, 120 added tests and 7 outstanding manual operations were treated as the starting baseline, and each was **re-verified in code** rather than trusted.

**Source inspected directly this session** (not via prior findings): `app/core/deps.py`, `config.py`, `main.py`, `crypto.py`, `token_crypto.py`, `mfa_crypto.py`, `rate_limit.py`, `security.py`; `app/models/accounting.py`, `company.py`, `user.py`, `financial_year.py`, `document.py`, `note.py`, `company_invitation.py`, `banking.py`, `balance_sheet.py`, `audit_log.py`, `enums.py`; `app/accounting/financial_reports.py`, `vat_engine.py`, `vat_rules.py`, `ledger_service.py`, `period_assignment.py`, `reconciliation_service.py`, `payroll_engine.py`, `dutch_tax_rules.py`, `bank_parsers.py`; `app/api/v1/` — `transactions.py`, `vat_returns.py`, `companies.py`, `documents.py`, `banking.py`, `workspace.py`, `auth.py`, `billing.py`, `payroll.py`; `app/schemas/accounting.py`, `company.py`, `auth.py`, `user.py`, `note.py`; `app/services/document_intake.py`, `document_approval.py`, `file_validation.py`, `storage.py`, `ai_provider.py`, `kvk_provider.py`; `alembic/env.py` and all 23 migration files; `scripts/backup_db.sh`, `restore_db.sh`, `rotate_bsn_key.py`; `tests/conftest.py`, `fakes.py` and 12 test modules; `frontend/lib/api.ts`, `auth-context.tsx`, `app/layout.tsx`, `app/globals.css`, `i18n/config.ts`, `e2e/i18n.spec.ts`, `components/glass/GlassSidebar.tsx`, `next.config.ts`, `package.json`; both Dockerfiles, both compose files, `.gitignore`, both `.env` examples, and all 31 pre-existing `docs/*.md`.

**Verified before relying on it.** Every defect fixed in Phase 19 was re-confirmed in the current source first — including the dead `determine_vat_period` import at `transactions.py:8` (`grep -c "determine_vat_period("` → **0**), the absence of any `VatPeriod.status` assignment (**zero** hits), and the absence of `__table_args__` on `AccountingTransaction`.

---

## 2. What was implemented

### Phase 18 — production readiness and deployment validation

**No application code was changed in Phase 18.** It was verification, and it produced the first end-to-end proof that this system can run in production mode.

Executed against **disposable scratch databases** (`onholland_p18_migration_check`, `onholland_p18_boot`), both created and dropped within the phase:

- **Migration chain applied to a clean database for the first time in the project's history.** 23 migrations, 48 tables, version `e4f7a9c2b1d8`. Then `downgrade -1` (constraint dropped, version reverted) and `upgrade head` again (constraint restored). The audit had found this chain had **zero** test coverage.
- **Fail-closed secret validation confirmed live.** `ENVIRONMENT=production` with placeholder secrets → `RuntimeError`, exit 1, naming all four offenders with generation commands. A search of the entire output for all five placeholder literals returned **0** matches.
- **Full production boot.** Migrations applied under `ENVIRONMENT=production`, a tenant and owner seeded, uvicorn started with freshly generated secrets. Empty startup log (the positive control). Then: `/health` → `200 {"status":"ok"}`; `/ready` → `200 {"status":"ready"}` (proving the DB revision matches the code head); security headers present; unauthenticated API access → 401; real login → token; `/auth/me` → 200 with the correct email; bad token → 401; **`POST /auth/logout` → 204 and the same token then → 401**; CORS preflight from the allowed origin echoed, from `https://evil.example` → **zero** `Access-Control-Allow-Origin` headers.
- **Configuration review** of compose, both Dockerfiles, both env templates, CORS, token and cookie handling, database settings and logging (§2 of the readiness doc).
- **Compose validated structurally** — `docker compose config` cannot run because `.env.prod` does not exist (a pre-existing requirement, not introduced here).

Documents produced: production-readiness review, an operator deployment runbook (including its own caveats about the backup scripts), and a test-results record.

### Phase 19 — accounting correctness

**Four defects fixed, each verified in source first, each with regression tests, three of four mutation-tested.**

| # | Fix | Audit | Sev | Tests |
|---|---|---|---|---|
| 1 | **Cash-based VAT companies produced permanently zero returns.** Added `period_assignment.assign_vat_period_on_payment()` and wired it into **both** payment paths — `record_payment` (replacing the dead import) and `reconciliation_service.approve_match`. No-op when a period is already assigned or the company is invoice-based. | 6.2 | **CRITICAL** | 9 |
| 2 | **`previous_period()` used day arithmetic.** Q1's "previous quarter" started on 3 October, dropping two days from every quarterly comparison; annual periods across a leap year shifted by one. Now steps back by whole calendar months for aligned periods, falling back to day count for arbitrary ranges. | 7.3 | HIGH | 12 |
| 3 | **Negative and zero payments were accepted.** `PaymentCreate.amount` had no bound; a negative payment inflated `remaining_balance`, could flip a settled invoice back to `UNPAID`, and corrupted aging, cash flow and DSO. Now `Field(gt=0)`. | 8.8 | MEDIUM | 5 |
| 4 | **No DB guard against double-posting a document.** SELECT-then-INSERT is single-threaded only; two concurrent approvals both inserted, double-counting revenue and input VAT into the VAT return. Added `UniqueConstraint("source_document_id")`, migration `e4f7a9c2b1d8` that **refuses** rather than repairs, and `IntegrityError → 409` with an explicit rollback. | 6.6 | **CRITICAL** | 3 |

**Five verified defects were deliberately NOT fixed**, because each requires an accounting or legal decision and guessing would change reported statutory figures without authority (rule 8, rule 14). Each is documented with evidence, consequence and options in `PHASE_19_ACCOUNTING_AND_TAX_REVIEW.md` §5:

- `VatPeriod.status` never assigned — balance-sheet VAT liability never clears (**the highest-value open item**)
- `approval_status` affects no reported figure — approval is cosmetic
- No FX handling outside the VAT engine — currencies summed together
- `ManualBalanceSheetItem` sums stocks as flows
- Tax rules frozen at 2025 / VAT at `nl-2024`, default year never clock-derived — **rates were not invented**

**No superficial work.** No new screens, no placeholder entities, no mock integrations. The feature matrix records absence as absence: 41 REAL, 15 PARTIAL, 3 CALC-ONLY, 14 ABSENT, 2 BLOCKED, 2 STUB.

### Phase 20 — final QA

**Seven end-to-end scenarios** added, driven through real HTTP against isolated test tenants, asserting exact figures at every step rather than status codes:

- **A — Sales:** two-line invoice (21% + 9%) → `1250.00 / 232.50 / 1482.50` → partial payment → settling payment → negative payment refused with 422 → ledger still `PAID / 0.00` with exactly 2 payments → annual P&L revenue `1250.00` → debtors `total_outstanding 0.00`
- **B — Purchases:** eligible input VAT → approve → edit blocked with 409 → pay → `box_5b_vat == 105.00`, `box_5a_vat == 0.00`, `net_payable == -105.00`. A second test proves a `REQUIRES_REVIEW` line contributes **nothing** to box 5b.
- **C — Banking:** CSV import → re-import is idempotent (`0` new, `1` duplicate) → suggest → approve creates a `Payment` → reconciliation status moves → **reverse voids without deleting** (row count unchanged, exactly one `voided == True`)
- **D — VAT:** every box exact (`1a 1000.00/210.00`, `1b 500.00/45.00`, `5a 255.00`, `5b 42.00`, net `213.00`), **cross-checked against the independently-built reconciliation view**, all five "unsafe to file" lists empty, full lifecycle walked, edits blocked after locking, a locked return not silently recomputed by a GET. Plus period isolation, plus the cash-based fix end to end.
- **E — Tenant isolation:** covered by Phase 17's 22 mutation-verified tests; not duplicated.

---

## 3. Files changed

### Modified (28 tracked, +929 −80)

**Backend application (13):**

| File | Phase | Change |
|---|---|---|
| `app/core/deps.py` | 17 | `require_company_access` tenant-authoritative for all roles; returns `Company`. **The user's uncommitted `find_user_by_email` preserved verbatim.** |
| `app/core/config.py` | 17 | `environment`, `PERMISSIVE_ENVIRONMENTS`, `_GUARDED_SECRETS`, `insecure_placeholder_secrets()`, `_enforce_secret_hygiene()`, `INSECURE_TEMPLATE_JWT_SECRET`, `repr=False` on 11 secret fields |
| `app/main.py` | 17 | `_validate_cors_origins()`. **The user's uncommitted CORS default preserved untouched.** |
| `app/core/token_crypto.py` | 17 | `reencrypt_token_with_current_key()` |
| `app/core/mfa_crypto.py` | 17 | `reencrypt_mfa_secret_with_current_key()` |
| `app/accounting/bank_parsers.py` | 17 | `_DTD_PROBE` + `_safe_fromstring()` in both CAMT parsers |
| `app/api/v1/companies.py` | 17 | Financial-year and invitation tenant fixes; `accept_invitation` `None` check and cross-tenant refusal |
| `app/api/v1/banking.py` | 17 | `PaymentMatch.tenant_id` predicate on bulk approve |
| `app/api/v1/workspace.py` | 17 | `AccountantNote.tenant_id` predicate on `list_notes` |
| `app/accounting/period_assignment.py` | **19** | `assign_vat_period_on_payment()` |
| `app/api/v1/transactions.py` | **19** | Dead import replaced; period assigned on payment |
| `app/accounting/reconciliation_service.py` | **19** | Period assigned on bank-match approval |
| `app/accounting/financial_reports.py` | **19** | `_whole_calendar_months()` + calendar-based `previous_period()` |

**Backend schema, API contract and config (5):**

| File | Phase | Change |
|---|---|---|
| `app/models/accounting.py` | **19** | `UniqueConstraint("source_document_id")` |
| `app/schemas/accounting.py` | **19** | `PaymentCreate.amount = Field(gt=0)` |
| `app/api/v1/documents.py` | **19** | `IntegrityError → 409` with rollback and a warning log |
| `backend/.env.example` | 17 | `ENVIRONMENT`, the 3 missing secrets, `_PREVIOUS` variants, generation commands, CORS note |
| `.env.prod.example` | 17 | Same plus a BREAKING CHANGE notice and a note that `NEXT_PUBLIC_API_URL` still does not reach the browser |

**Infrastructure and frontend (5):** `docker-compose.prod.yml` (`ENVIRONMENT: ${ENVIRONMENT:-production}`), `.gitignore` (backup and build-artifact patterns), `frontend/lib/api.ts` (the missing `logout` method), `frontend/lib/auth-context.tsx` (async logout with `try/finally`), `frontend/components/glass/GlassSidebar.tsx` (`void logout()`), `frontend/app/globals.css` (split `:lang(fa)`/`:lang(ar)` stacks), `frontend/e2e/i18n.spec.ts` (+5 computed-font tests).

**Tests modified (2):** `backend/tests/test_auth_security.py` (+1 logout revocation test), `backend/tests/test_financial_reports.py` (one assertion corrected — see §6).

**Not touched:** `backend/app/api/v1/auth.py` still carries only the user's pre-existing `+7 −1` change.

### Created (22 untracked)

**Code (6):** `backend/alembic/versions/e4f7a9c2b1d8_…py` · `backend/scripts/rotate_encryption_keys.py` · `backend/tests/test_cross_tenant_isolation.py` · `backend/tests/test_phase17_security_config.py` · `backend/tests/test_phase19_accounting_fixes.py` · `backend/tests/test_phase20_e2e_scenarios.py` · `frontend/lib/__tests__/auth-context.test.tsx` · `frontend/test/locale-fonts.test.ts`

**Documentation (14):** the 12 phase documents listed above plus `QWEN_TECHNICAL_AUDIT_REPORT.md` and this report.

---

## 4. Database changes

**One migration added: `e4f7a9c2b1d8_phase_19_unique_source_document_on_ledger_posting`.**

It adds `uq_accounting_transaction_source_document` on `accounting_transactions.source_document_id`. It is **non-destructive by construction**: it first queries for documents already posted more than once and, if any exist, raises `RuntimeError` listing each `document_id`, its posting count and the transaction ids, instructing the operator to resolve each pair with a voiding correction and re-run. It never deletes, updates or picks a winner among financial records. `downgrade()` drops the constraint.

Manual entries and corrections are unaffected — they set `source_document_id = NULL`, and Postgres treats NULLs as distinct. **Verified before adding the constraint** that `create_correction` routes through `create_manual_entry`, which passes `None` explicitly.

Verified: single head `e4f7a9c2b1d8`; `upgrade head` → `downgrade -1` → `upgrade head` round-trip clean on a scratch database; `pg_constraint` confirms the constraint's presence and absence at each step.

**No other schema change.** No column added, altered or dropped. No data migrated, modified or deleted. `git status --short backend/app/models/` shows only `accounting.py` (the constraint) and `alembic/` only the one new file. The migration's duplicate-refusal branch was **not exercised** — manufacturing duplicates would require writing bad financial data.

**Databases touched:** two scratch databases created and dropped; the disposable `onholland_accounting_test` used by the suite. The development database `onholland_accounting` was **not** modified — no migration was applied to it and `backend/.env` was not changed.

---

## 5. Tests actually executed, and real results

| Command | Result |
|---|---|
| `pytest tests/ -p no:randomly -q` (backend, full) | **662 passed, 0 failed, 0 errors, 0 skipped** in 286.56s |
| `pytest tests/test_phase19_accounting_fixes.py` | **29 passed** |
| `pytest tests/test_phase20_e2e_scenarios.py` | **7 passed** |
| `pytest tests/test_cross_tenant_isolation.py` | **22 passed** |
| `pytest tests/test_phase17_security_config.py` | **59 passed** |
| `pytest tests/test_auth_security.py` | **11 passed** |
| `pytest tests/test_company_invitations.py` | **7 passed** — confirms cross-tenant rejection did not break same-tenant delegation |
| `vitest run` (frontend, full) | **175 passed / 11 files** |
| `tsc --noEmit` | **exit 0**, no diagnostics |
| `next build` | **exit 0** — `✓ Compiled successfully in 643ms`, `✓ Generating static pages (58/58)` |
| `eslint .` | **0 errors**, 4 pre-existing warnings in untouched files |
| `alembic upgrade head` / `downgrade -1` / `upgrade head` (scratch DB) | **all exit 0**, constraint verified in `pg_constraint` at each step |
| `py_compile` over 14 changed backend files | **ALL OK** |
| Import of every changed module | **clean**, no circular import |
| Production boot + 11 HTTP assertions | **all PASS** (§2, Phase 18) |
| Mutation test: revert `previous_period` | **10 failed** → restore checksum-verified → 29 passed |
| Mutation test: revert cross-tenant fixes (Phase 17) | **14 failed**, including a live `AttributeError` at `companies.py:354` → restore checksum-verified → 22 passed |
| Mutation test: revert `globals.css` to `[lang="fa"]` (Phase 17) | **5 failed** → restore checksum-verified → 13 passed |

**Test-count reconciliation:** 542 baseline + 22 (17.2) + 1 (17.3) + 59 (17.4) + 29 (19) + 2 (one `previous_period` test replaced by three) + 7 (20.3) = **662** ✓

An intermediate run returned `1 failed, 652 passed`; the single failure was the pre-existing test that encoded the `previous_period` bug (§6). No other test failed at any point — **the new unique constraint and the payment validation broke nothing** in the existing 624-test suite.

`ANTHROPIC_API_KEY=""` was set for every pytest invocation. Audit 7.13 found two tests named `..._uses_stub_provider_without_api_key` that do not null the key and would otherwise make real, billable calls to `api.anthropic.com` using the key in `backend/.env`. Recorded as a deviation from a bare `pytest` invocation; fixing the leak itself is roadmap Tier 2.4.

### Tests NOT executed, and why

| Not run | Reason |
|---|---|
| **Playwright e2e (21 tests, 5 new)** | Requires a backend on :8010, a frontend dev server and the seeded `mollie-visual@example.com` account; `playwright.config.ts` has no `webServer` block. **The largest verification gap** — the only way to confirm computed font selection in a browser and the only coverage of real user workflows. |
| **Backend lint / type check** | **No tooling exists.** ruff, mypy, flake8, black and pylint are all uninstalled; no config file anywhere. |
| **Coverage** | `pytest-cov`/`coverage` in neither `requirements.txt` nor the venv. No figure can be given. |
| **Docker image build** | Not attempted. Would have surfaced the frontend API-URL blocker but changes no source. |
| **`docker compose config`** | Exits 1: `.env.prod` does not exist (pre-existing `env_file` requirement). Validated structurally instead. |
| **Load / soak / concurrency** | No harness, no seeded large dataset; destructive load testing out of bounds. The double-posting race is verified at the DB level, not by concurrent HTTP. |
| **Backup restore** | Explicitly out of bounds against any database. |
| **Dependency vulnerability scan** | No `pip-audit`, no `npm audit` configuration. |
| **Migration duplicate-refusal branch** | Requires a database already containing duplicate postings. |
| **2026 Dutch tax rates** | Requires authoritative Belastingdienst sources. **Rates were not invented.** |

---

## 6. One pre-existing test was modified

`backend/tests/test_financial_reports.py::test_previous_period_same_length` asserted:

```python
assert (prev.end - prev.start).days == (period.end - period.start).days
```

For February 2027 that demands a 28-day predecessor ending 31 January — i.e. **4–31 January**, silently dropping 1–3 January. It is satisfiable only by the buggy day-arithmetic implementation. The failure that surfaced it:

```
>       assert (prev.end - prev.start).days == (period.end - period.start).days
E       assert 30 == 27
```

It was renamed to `test_previous_period_is_the_whole_preceding_calendar_period`; its first assertion (`prev.end == date(2027, 1, 31)`) was **kept unchanged because it was always correct**; and a docstring records precisely what the second assertion got wrong. Two sibling tests were added for the quarter and leap-year cases.

**This is the only pre-existing test changed across Phases 17–20**, and it was changed because it encoded a defect, not because it was inconvenient.

---

## 7. Security issues discovered

**No new security vulnerability was introduced.** Two were discovered *while* implementing the fixes:

1. **`repr(settings)` rendered every secret verbatim.** All secret fields were plain `str`, so pydantic included them in `repr()` — meaning any f-string, debug log, exception context, or **pytest fixture dump** printed them. Found for real: a failing test's fixture repr printed a configured webhook secret to the console. Fixed with `repr=False` on all 11 secret-bearing fields (`jwt_secret`, `database_url` — which embeds `POSTGRES_PASSWORD` in production — `anthropic_api_key`, `kvk_api_key`, the three encryption keys, their three `*_previous` counterparts, and `billing_webhook_secret`). `model_dump()` and attribute access are unchanged, so no consumer is affected. Pinned by a canary test.

2. **The `.env.example` JWT literal would have bypassed the new guard.** The template ships a `JWT_SECRET` value that is *not* the same string as the code default, so a check comparing only against the code default would let an operator copy the template into `.env.prod` and sail past it while running a publicly-known signing key. Closed by adding `INSECURE_TEMPLATE_JWT_SECRET` to the guarded set, plus treating blank as an offence (an empty HMAC key is worse than a placeholder and a value-equality check would miss it), plus failing closed on any unrecognised `ENVIRONMENT` so a typo cannot reach the permissive branch.

**Also confirmed still open** (all from the audit, none introduced here): MFA re-enrolment without step-up · rate limiting ineffective behind a proxy · password reset cannot deliver a token · five committed placeholder keys · CSV formula injection · JWT in `localStorage` with a 24h lifetime and no refresh · no frontend 401/403 handling · `partner_id` not validated · `invite_employee_self_service` writes no audit log · case-sensitive email uniqueness · `Employee.linked_user_id` has no unique constraint · unauthenticated write on `GET /billing/plans` · unvalidated `kvk_number` · latent open redirects in the stubs · reset tokens not revoked on re-request · audit redaction in 2 of 11 routers · no password policy · unmaintained `python-jose` and `passlib` · no dependency scanning.

Full list with evidence and fixes: `PHASE_20_KNOWN_ISSUES.md`.

### Secret handling during this session

- No secret was printed, logged, echoed or written to any file. Keys for the boot test were generated in-shell into environment variables and never displayed; only `yes`/`NO` for token presence appears in any transcript.
- **The four Fernet/HMAC placeholder values were redacted from `QWEN_TECHNICAL_AUDIT_REPORT.md` §6.4** during this session, where they had been quoted verbatim as evidence. The finding now cites `config.py:7-11` and describes the values' shape instead. Verified: `grep` for all four across every document returns **zero** matches.
- Two inert JWT placeholder *strings* (`dev-secret-change-in-production`, `change-me-in-production`) remain in prose in four documents. **Deliberate:** both are already public in tracked files (`config.py`, `backend/.env.example`), neither is a functional credential here (`JWT_SECRET` is overridden in `.env`), and the template-vs-code-default gap cannot be explained without naming them. Flagged so the decision is visible rather than implicit.
- No credential was committed. Only empty placeholders were added to the two `.env` example templates.
- Scan of every changed non-documentation file for key material, `sk-ant-` prefixes and PEM headers: the only hits are the **pre-existing** `INSECURE_DEFAULT_*` definitions at `config.py:8-12`, which `git diff` confirms are **unchanged from HEAD** — the diff touches only their *usages* (wrapping in `Field(default=…, repr=False)`).

---

## 8. Accounting issues discovered

All four fixed issues and all five deliberately-unfixed issues are detailed in §2 and in `PHASE_19_ACCOUNTING_AND_TAX_REVIEW.md`. The two that matter most:

**Fixed — cash-based VAT companies filed all-zero returns.** Every such transaction kept `vat_period = NULL` permanently, and `calculate_vat_return` filters on `vat_period_id`, so every box computed to zero with no error and no reconciliation flag. The dead `determine_vat_period` import at `transactions.py:8` showed the fix had been intended and never written. Now assigned from the payment date through both payment paths, verified end to end: Q1 stays zero after a May payment, Q2 shows `1000.00 / 210.00 / 210.00`.

**Open — `VatPeriod.status` is never assigned by any code path.** `_outstanding_vat_position` filters `!= paid`, so it never excludes anything and **every VAT return ever computed is summed into the balance sheet's VAT liability forever**. Paying a VAT bill has no effect. Corrupts `total_liabilities`, `is_balanced`, `imbalance_amount`, current/quick ratios, ROA and the working-capital trend. The dashboard's "open VAT periods" is "all periods ever". Needs new endpoints and a decision about who may declare a period paid — the highest-value open item in the product.

**Also open:** approval status affects no reported figure · no FX outside the VAT engine · manual balance-sheet items summed as flows · tax rules frozen at 2025 in 2026 · VAT boxes 2a/3a/4a/1d unreachable automatically with no UI to set `vat_treatment` · no suppletie mechanism · no `FinancialYear(company_id, year)` uniqueness, which can make period assignment non-deterministic.

**Compliance position, stated plainly:** this application is **not** legally compliant and nothing in these phases makes it so. It contains tax calculations. No return of any kind is submitted to or accepted by any authority. RGS, SBR and XBRL are absent entirely. Every tax figure should be treated as requiring professional verification until the rule sets are versioned by tax year and confirmed against primary sources.

---

## 9. Remaining manual operations

Each needs a live credential, external permission, production access, or a decision that is not an engineering one. **All were stopped before execution**, per the brief.

| # | Operation | Blocking dependency |
|---|---|---|
| 1 | **Rotate all five secrets.** The four placeholders are burned and live in this environment. | Database backup first. Procedure and rollback in `PHASE_17_SECURITY_REMEDIATION.md` §7; `scripts/rotate_encryption_keys.py` now supports all three encrypted classes and refuses to migrate onto a placeholder. |
| 2 | **Set `BSN_ENCRYPTION_KEY` in `backend/.env`.** Must be a rotation (old key → `_PREVIOUS`), not a replacement, or existing ciphertext becomes undecryptable. `backend/storage/` holds what appear to be real invoices, so treat the local DB as holding real personal data. | Same as #1. |
| 3 | **Fix the frontend build-time API URL.** The deployment blocker. | A build-pipeline change; deliberately not attempted in a security/accounting phase. |
| 4 | **Revert the CORS default** in `app/main.py` and move the LAN origin into `backend/.env`. | It is an uncommitted **user** change, preserved per rule 5. The new guard detects it in dev and refuses to boot with it in production. |
| 5 | **Provision TLS and the reverse proxy**, with uvicorn `--proxy-headers` / `--forwarded-allow-ips`. | Environment-specific by design. |
| 6 | **Run the Playwright suite.** | Needs two servers and a seeded account; no `webServer` block. |
| 7 | **Configure a transactional email provider.** | Provider account. Unblocks password reset and both invitation flows. |
| 8 | **Add a git remote and push.** | Nothing. Five minutes. Do this first. |
| 9 | **Delete the three stray backup files** once the `globals.css` fix is committed. | They are gitignored, not deleted (rule: do not delete project files). They are currently the only record of the intermediate `:root[lang="fa"]` bug. |
| 10 | **Harden and schedule backups**; back up the storage volume. | Operator decision on tooling and retention. |
| 11 | **Add `defusedxml`** and swap the parser. | Package install changes the environment; the DTD rejection already closes the vector. |
| 12 | **Decide the fate of cross-tenant accountant delegation.** Now explicitly refused rather than silently broken, so `docs/accountant-ecosystem.md` is inaccurate. | Product decision: build a `CompanyAccess` grant model, or drop the multi-firm story and correct the docs. |
| 13 | **Decide single-entry vs. double-entry** (`PHASE_19_PRODUCT_COMPLETENESS.md` §3) before further feature investment. | Product decision. |
| 14 | **Verify 2026 Dutch tax rates** against primary Belastingdienst sources and add `RULES_2026` + a `nl-2026` VAT rule set. | Authoritative sources. The safe half — making the default year clock-derived so a missing rule set fails loudly — needs no rates and is ~1 day. |
| 15 | **Correct seven inaccurate documents**: `README.md` (stops at Phase 9; understates tests by 291), `production-readiness.md`, `security.md`, `encryption-key-rotation.md`, `gdpr-data-governance.md`, `untranslated-backend-messages-inventory.md`, `accountant-ecosystem.md`. | None. |

---

## 10. Production deployment blockers

| # | Blocker | Severity |
|---|---|---|
| 1 | **`NEXT_PUBLIC_API_URL` never reaches the browser bundle** — production frontend hardcoded to `localhost:8000` | **Critical** |
| 2 | Five committed placeholder secrets, four still in active use locally | **Critical** |
| 3 | No TLS / reverse proxy provisioned | High |
| 4 | Rate limiting is one shared bucket behind any proxy — and a trivial unauthenticated DoS | High |
| 5 | MFA re-enrolable without step-up | High |
| 6 | Password reset cannot deliver a token, and has no UI | High |
| 7 | No transactional email provider | High |
| 8 | Frontend image: `npm install` not `npm ci`, full devDependency tree in runtime, `npm` as PID 1 | Medium |
| 9 | No CI, no coverage, no backend linter or type checker | High |
| 10 | **No git remote** | High |
| 11 | `VatPeriod.status` never assigned — balance sheet materially wrong | High (functional) |
| 12 | Tax rules frozen at 2025 while operating in 2026 | High (compliance) |

**Breaking change already in the working tree:** `docker-compose.prod.yml` now sets `ENVIRONMENT: ${ENVIRONMENT:-production}`, so a production stack whose `.env.prod` omits any of the five guarded secrets **refuses to start** rather than starting insecurely. Intentional, and loud rather than silent — but it must not be discovered during a rollout. Verify locally with `ENVIRONMENT=production` and the real `.env.prod` before shipping.

---

## 11. Known risks

1. **Financial figures are wrong in known ways.** Balance-sheet VAT liability never clears; reports ignore currency; manual balance-sheet items double-count; approval status is cosmetic. Do not use any output for a real filing.
2. **Tax rules are stale for 2026** and the suite cannot detect it — every payroll test hardcodes 2025 and nothing derives the year from the clock. Payslips would print `tax_year: 2025` in 2026.
3. **Nothing is verified automatically.** No CI. Every guarantee in these documents rests on someone remembering to run the tests.
4. **No git remote.** One machine, no backup, no review path. `main` is 81 commits behind HEAD and nothing has ever passed through a PR.
5. **The single-entry ledger is a ceiling**, not a bug. Five separate outputs already declare themselves incomplete. See §13.
6. **Frontend workflow coverage is near zero.** 0 of 55 routes have a unit test; Playwright covers 5 routes and was not run this session. A build that compiles is the only frontend evidence.
7. **Performance is unmeasured and structurally capped.** Zero eager loading, all aggregation in Python, missing indexes on the hottest columns. No benchmark exists to detect a regression.
8. **Session security is weak by construction.** `localStorage` JWT, 24h lifetime, no refresh token, no client-side 401 handling. Logout now revokes (fixed), which materially helps, but the storage choice remains.
9. **The migration's duplicate-refusal path is unexercised.** If duplicates exist, the deploy fails with a list — which is the intended behaviour, but it has only been code-reviewed.
10. **Two tests still make real API calls** unless `ANTHROPIC_API_KEY` is nulled. Anyone running a bare `pytest` spends money.

---

## 12. Git branch and working-tree status

```
$ git rev-parse --abbrev-ref HEAD
phase-16-3-complete-internationalisation

$ git log --oneline -1
97f2d84 Phase 16.3: complete locale-aware formatting sweep, CSV compatibility,
        backend-message inventory, unused-key cleanup

$ git status --short | wc -l
50                                  # 28 modified + 22 untracked

$ git diff HEAD --stat | tail -1
28 files changed, 929 insertions(+), 80 deletions(-)

$ git remote -v
(empty — no remote)
```

**No commits were made in any phase.** Rule 10 of the Phase 17 brief authorised commits only if explicitly requested; the Phase 18–20 brief did not authorise them either. All work is in the working tree.

The three stray backup files no longer appear in `git status` because Phase 17 gitignored them — they are still on disk, not deleted.

**Suggested commit split if authorised** (five reviewable units, plus the pre-existing user changes handled separately):

1. `deps.py` + `companies.py` + `banking.py` + `workspace.py` + `test_cross_tenant_isolation.py` — Phase 17.1/17.2 cross-tenant isolation
2. `api.ts` + `auth-context.tsx` + `GlassSidebar.tsx` + `auth-context.test.tsx` + the `test_auth_security.py` addition — Phase 17.3 logout
3. `config.py` + `main.py` + both crypto modules + `bank_parsers.py` + `rotate_encryption_keys.py` + `test_phase17_security_config.py` — Phase 17.4 security config
4. Env templates + `docker-compose.prod.yml` + `.gitignore` — Phase 17.4 configuration
5. `globals.css` + `locale-fonts.test.ts` + `i18n.spec.ts` — Phase 17.5 RTL fonts
6. `period_assignment.py` + `transactions.py` + `reconciliation_service.py` + `financial_reports.py` + `models/accounting.py` + `schemas/accounting.py` + `documents.py` + the new migration + `test_phase19_accounting_fixes.py` + `test_phase20_e2e_scenarios.py` + the `test_financial_reports.py` correction — Phase 19/20 accounting
7. The 14 documents

The user's pre-existing changes to `backend/app/api/v1/auth.py` and the CORS default line in `main.py` should be separated out and decided independently (manual operations #4).

---

## 13. Recommended next actions

**Today, in this order.** Items 1–4 are each under a day and remove the largest risks.

1. **Add a git remote and push.** Nothing is backed up; no review path exists.
2. **Fix the frontend build-time API URL.** Without it there is no deployment. Prefer a same-origin `rewrites()` so the class of bug cannot recur.
3. **Take a backup and rotate the five secrets.** Tooling and a tested rollback path now exist.
4. **Stand up CI** with five jobs: `alembic upgrade head && downgrade base && upgrade head`; `alembic revision --autogenerate` **failing if non-empty**; the full pytest suite with `ANTHROPIC_API_KEY=""`; `tsc --noEmit && eslint && next build && vitest run`; and `gitleaks`. Add `pytest-cov` with a ratchet, and ruff plus mypy.
5. **Wire `VatPeriod.status`.** The highest-value functional fix — the balance sheet is materially wrong until it lands.
6. **Make the default tax year clock-derived** so a missing 2026 rule set fails loudly instead of silently serving 2025 rates. No new rates required; ~1 day.
7. **Fix the rate limiter's client-key resolution**, then MFA step-up, then wire an email provider.
8. **Correct the seven inaccurate documents** so the next engineer is not misled by them.

**Then make the product decision** in `PHASE_19_PRODUCT_COMPLETENESS.md` §3 before investing further in features: stay a single-entry VAT-administration and management-information tool (cheaper, honest, already supported by the code — but relabel "trial balance" and "balance sheet" as management estimates), or build the double-entry general ledger (~6–10 weeks, touching every report, and a prerequisite for RGS and credible annual statements). **The current state — statutory outputs from a ledger that cannot support them, with the gaps documented but not closed — is the worst of the three options.**

After that, work down `PHASE_20_KNOWN_ISSUES.md` in priority order: P1 items 4–12, then the P2 cluster (frontend auth handling, dark-mode contrast, CSV injection, eager loading and indexes, schema/migration parity, missing constraints), then P3 hygiene.

---

## 14. Closing statement

Phases 18, 19 and 20 did what the brief asked and stopped where it said to stop. Four accounting defects that produced wrong statutory or financial output are fixed, each with mutation-tested regressions. The migration chain was executed for the first time and a new non-destructive migration was verified up, down and up again. The application was proven to boot and operate correctly in production mode against a real server, including live confirmation that logout revokes a session and that CORS rejects a foreign origin. Seven end-to-end accounting scenarios now assert exact figures across the sales, purchases, banking and VAT chains.

Five further defects were verified and **left unfixed on purpose**, because fixing them correctly requires an accounting or legal decision, and guessing would have changed reported statutory numbers without authority. Dutch tax rates for 2026 were **not** invented. No return is submitted to or accepted by any authority, and nothing written here claims otherwise.

The application is **ready for internal testing** in development mode, with every financial figure treated as provisional. It is not ready for staging, because the frontend production image cannot reach the API. It is not ready for production, for the twelve reasons in §10.

Nothing was deployed. Nothing was committed. No production system was contacted. No real customer or financial data was used. The development database was not modified.
