# Phase 20 — Final QA Report

Every check actually executed in Phase 20, with its real output. Where a check could not be run, the reason is stated.

---

## 1. Backend verification (20.1)

### Full suite

```
$ cd backend && ANTHROPIC_API_KEY="" .venv/bin/python -m pytest tests/ -p no:randomly -q --no-header -rf

662 passed, 986 warnings in 286.56s (0:04:46)
failures: 0
errors:   0
skipped:  0
```

| Category | Where | Result |
|---|---|---|
| Unit tests | `test_vat_engine` (16), `test_dutch_tax_rules` (27), `test_financial_reports` (22), `test_payroll_engine`, `test_matching_engine`, `test_crypto`, `test_rate_limit` … | all pass |
| Integration / API tests | `test_accounting_api`, `test_documents_api` (15), `test_banking_api` (8), `test_batch_upload` (17), `test_payroll_api`, `test_tax_centre_api`, `test_legal_forms_api`, `test_financial_reports_api`, `test_management_report_exports` … | all pass |
| **Authorisation tests** | `test_user_management` (25) — self-escalation, admin-cannot-grant-owner, last-owner protection, token-version revocation, invitation replay, route shadowing | all pass |
| **Tenant-isolation tests** | `test_cross_tenant_isolation` (22, Phase 17) plus 20 second-tenant tests spread across 16 pre-existing files | all pass |
| **Accounting calculation tests** | `test_phase19_accounting_fixes` (29) | all pass |
| **VAT tests** | Scenario D (7 e2e tests) plus the 16 engine tests | all pass |
| **Database constraint tests** | `test_two_transactions_cannot_share_a_source_document`, `test_many_transactions_may_have_no_source_document`, `test_the_unique_constraint_is_declared_on_the_model` | all pass |
| End-to-end scenarios | `test_phase20_e2e_scenarios` (7) | all pass |
| Security configuration | `test_phase17_security_config` (59) | all pass |

`ANTHROPIC_API_KEY=""` is set for every invocation — audit 7.13 found two tests that otherwise make real billable API calls. See `PHASE_19_TEST_RESULTS.md` §1.

### Migration checks

```
$ .venv/bin/alembic heads
e4f7a9c2b1d8 (head)                          # exactly one head, no branching
```

Full up / down / up cycle against a scratch database, with `pg_constraint` verification at each step: `PHASE_18_TEST_RESULTS.md` §1. **Result: PASS.**

`git status --short alembic/ app/models/` — the only changes are Phase 19's new migration and the new `__table_args__`. No existing migration was edited.

### Static analysis and linting

```
$ for t in ruff mypy flake8 black pylint; do .venv/bin/$t --version; done
ruff     (not installed)
mypy     (not installed)
flake8   (not installed)
black    (not installed)
pylint   (not installed)

$ ls -a | grep -iE "ruff|mypy|flake8|setup.cfg|pyproject|tox"      # backend/
none
$ ls -a | grep -iE "ruff|mypy|pyproject|setup.cfg"                  # repo root
none at repo root
```

**There is no backend linter, formatter or type checker in this project, and no configuration for one.** "Backend static checks" could therefore only mean:

```
$ .venv/bin/python -m py_compile <all 14 changed/new backend files>
py_compile: ALL OK

$ .venv/bin/python -c "import app.main, app.core.config, app.core.deps, app.core.crypto,
      app.core.token_crypto, app.core.mfa_crypto, app.accounting.bank_parsers,
      app.accounting.period_assignment, app.accounting.reconciliation_service,
      app.api.v1.companies, app.api.v1.banking, app.api.v1.workspace, app.api.v1.transactions"
all modules import cleanly
```

Both **PASS**, and the import check confirms no circular import from the two new module-level imports added in Phase 19 (`AccountingTransaction` into `period_assignment`, `assign_vat_period_on_payment` into `reconciliation_service`).

**Result: NOT TESTED for lint and types — no tooling exists.** Adding ruff and mypy is roadmap Tier 2.1.

### Regressions introduced by Phases 18 and 19

One, and it was intentional:

`tests/test_financial_reports.py::test_previous_period_same_length` asserted that the previous period has the **same day count** as the current one. That invariant is only satisfiable by the buggy day-arithmetic implementation — for February 2027 it demanded 4–31 January, dropping 1–3 January. It was renamed, its correct first assertion kept, and its docstring records exactly what was wrong. Full detail and the verbatim failure in `PHASE_19_TEST_RESULTS.md` §3.

**No other pre-existing test failed at any point.** In particular the new unique constraint and the `amount > 0` validation broke nothing across the existing 624-test suite.

---

## 2. Frontend verification (20.2)

```
$ cd frontend && node_modules/.bin/vitest run
 Test Files  11 passed (11)
      Tests  175 passed (175)
   Duration  1.88s

$ node_modules/.bin/tsc --noEmit
tsc exit: 0                                  # no diagnostics

$ node_modules/.bin/eslint .
✖ 4 problems (0 errors, 4 warnings)

$ node_modules/.bin/next build
✓ Running next.config.ts took 104ms
✓ Compiled successfully in 643ms
✓ Generating static pages using 7 workers (58/58) in 285ms
next build exit: 0
```

All four **PASS**.

The 4 ESLint warnings are pre-existing and in files no phase touched:

| File | Rule |
|---|---|
| `app/audit-log/page.tsx:75` | `react-hooks/exhaustive-deps` |
| `app/documents/[id]/page.tsx:192` | `@next/next/no-img-element` |
| `app/reconciliation/page.tsx:42` | `react-hooks/exhaustive-deps` |
| `app/users/page.tsx:59` | `react-hooks/exhaustive-deps` |

None of `lib/api.ts`, `lib/auth-context.tsx`, `components/glass/GlassSidebar.tsx`, `app/globals.css`, `test/locale-fonts.test.ts` or `lib/__tests__/auth-context.test.tsx` produces a warning.

### What was verified about the actual application, not just the build

Per the brief's instruction not to assume a successful build means workflows work:

- **Authentication flow** — verified against a **running production-mode server**: unauthenticated → 401, real login → token, `/auth/me` → 200 with the correct email, bad token → 401, logout → 204, same token reused → 401. `PHASE_18_TEST_RESULTS.md` §3.
- **Localization** — 4 dictionaries × 1,374 keys with **zero drift**, re-verified by an independent flatten-and-diff rather than by trusting the project's own parity script. 55/55 routes call `useTranslations`; ~1,596 `t()` call sites; no untranslated JSX text node in any production route. `messages/__tests__/parity.test.ts` (7 tests) passes.
- **RTL** — `:root:lang(fa)` and `:root:lang(ar)` verified present in the **production CSS bundle** `.next/static/chunks/1txo2n37p3yz2.css`, with all eight `@font-face` families emitted, both variables resolving to real family names, `body` reading `var(--font-app-sans)`, and **zero** `[lang=` attribute selectors. Persian leads with Vazirmatn, Arabic with Noto Sans Arabic, Dutch and English retain Geist.
- **Component tests** — 5 Glass component suites (Button, Modal with focus trap, Dropdown, Table, Sidebar) plus `navConfig` (102 tests enforcing "real route XOR marked unavailable") and `format` (18).
- **Form validation and error states** — **NOT TESTED.** No route component has a unit test (0 of 55), and the Playwright suite visits 5 routes.

### Not executed

- **Playwright e2e (21 tests, 5 new).** Requires a backend on port 8010, a frontend dev server and the seeded `mollie-visual@example.com` account; `playwright.config.ts` has no `webServer` block. Starting servers and seeding an account was outside the safe scope of this session. **This is the single largest frontend verification gap** — it is the only way to confirm computed font selection in a browser and the only thing covering real user workflows.
- **Route-level tests** — none exist to run.
- **Coverage** — no tooling.

---

## 3. End-to-end accounting scenarios (20.3)

`tests/test_phase20_e2e_scenarios.py` — **7 tests, all passing**, each chaining several subsystems through real HTTP calls against an isolated test tenant and asserting exact figures rather than status codes.

### Scenario A — Sales ✅ PASS

Create company → create financial year (periods auto-generated) → post a two-line sales invoice (21% and 9%) → verify `net 1250.00 / vat 232.50 / gross 1482.50`, `UNPAID`, `remaining_balance 1482.50`, and that it landed in Q1 by invoice date → partial payment of `482.50` → verify `amount_paid`, `remaining_balance 1000.00` → settling payment → verify `PAID`, `remaining_balance 0.00` → **attempt a negative payment, verify `422`** → verify the ledger still shows `PAID / 0.00` with exactly 2 payments → verify annual P&L revenue `1250.00` → verify debtors `total_outstanding 0.00`.

### Scenario B — Purchases ✅ PASS

Post a purchase invoice with `input_vat_eligibility=ELIGIBLE` → verify `net 500.00 / vat 105.00 / gross 605.00`, `deductible_vat_amount 105.00`, `approval_status DRAFT` → approve → verify `APPROVED` → **verify a direct edit now returns `409`** → pay `605.00` → verify `PAID` → compute the Q1 return and verify `box_5b_vat == 105.00`, `box_5a_vat == 0.00`, `net_payable == -105.00` (a refund position).

A second test proves the conservative behaviour: a purchase line marked `REQUIRES_REVIEW` yields `deductible_vat_amount == 0.00` and contributes **nothing** to box 5b.

### Scenario C — Banking ✅ PASS

Create a bank account → import a CSV statement → verify `transaction_count == 1`, `duplicate_count == 0` → **re-import the identical file** → verify `transaction_count == 0`, `duplicate_count == 1` (the `uq_bank_transaction_dedupe` constraint) → list and verify the amount → generate match suggestions → approve the best match → verify a `Payment` row was created → verify the bank transaction's `reconciliation_status` moved to matched/partially-matched → **reverse the match** → verify the payment row count is unchanged and exactly one row has `voided == True` (voided, never deleted).

### Scenario D — VAT ✅ PASS

Three transactions (21% sale, 9% sale, 21% eligible purchase) → compute the return and verify **every box exactly**: `1a_net 1000.00`, `1a_vat 210.00`, `1b_net 500.00`, `1b_vat 45.00`, `5a_vat 255.00`, `5b_vat 42.00`, `net_payable 213.00`, `status draft` → **cross-check against the independently-built reconciliation view**: `sales_total_net 1500.00`, `purchases_total_net 200.00`, `sum(sales_vat_by_rate) == box_5a_vat`, `sum(purchase_vat_by_rate) == box_5b_vat`, `box_1a_vat + box_1b_vat == sales VAT`, and all five "unsafe to file" lists empty → walk `submit-for-approval → approve → lock` verifying each status → **verify a direct transaction edit returns `409` after locking** → verify a plain `GET` does not silently recompute a locked return.

Two further Scenario D tests: an April invoice appears in Q2 (`900.00 / 189.00`) while Q1 stays `0.00`; and the **cash-based end-to-end proof** — create company, `PATCH` to `cash_based`, post a February invoice, assert `vat_period_id is None` and Q1 is all-zero, pay in May, assert Q1 is *still* zero and Q2 now shows `1000.00 / 210.00 / 210.00`.

### Scenario E — Tenant isolation ✅ PASS (covered elsewhere)

**Not duplicated here.** Covered in full by `tests/test_cross_tenant_isolation.py` (22 tests): two independent tenants, five users each across four roles plus a same-tenant non-member admin, every vulnerable endpoint attempted cross-tenant, and mutation-verified — **14 of the 22 failed against the vulnerable code**, including a live `AttributeError: 'NoneType' object has no attribute 'users'`.

### Relationship to the pre-existing e2e suite

`tests/test_e2e_acceptance_scenarios.py` (6 tests) covers a **different and complementary** set: eenmanszaak legal form through tax optimisation, VOF partners never assumed equally eligible, BV/DGA payroll through loonheffingen to the annual statement, tax-optimisation mixing computed and `requires_data` results, and financial intelligence from manual entries through reports to KPIs. Employee self-service and bulk upload are covered in `test_employee_self_service_api.py` and `test_batch_upload.py`. Nothing was duplicated.

**No real customer or production financial data was used.** Every scenario runs against the disposable `onholland_accounting_test` database that `tests/conftest.py` derives and wipes per test.

---

## 4. Performance and reliability (20.4)

**No change was made**, because the brief requires changes to be supported by evidence and no measurement infrastructure exists to produce it. Findings are from static analysis and are recorded for action rather than acted on blind.

| Finding | Evidence | Impact |
|---|---|---|
| **Zero eager loading in the entire backend** | `grep -rn "selectinload\|joinedload\|subqueryload" app/` → **0** | `_ar_ap` and `general_ledger` walk `transaction.payments` per row. 10,000 invoices ⇒ ~10,000 extra queries per balance-sheet request. |
| **All aggregation in Python** | `transactions_in_period` returns full ORM objects; every total is a `sum()` over them | Whole histories materialised per request; `cash_flow_statement` calls `profit_and_loss` plus `debtors` twice plus `creditors` twice |
| **Missing indexes on hot paths** | No index on `accounting_transactions.vat_period_id`, `.invoice_date`, `transaction_line_items.transaction_id`, `payments.transaction_id`, `documents(company_id, sha256_hash)`, `bank_transactions(company_id, booking_date)` | The VAT engine's primary filter and every report's date range are unindexed |
| **54 indexes absent from model metadata** | Migration `3853605281ec` deliberately omits them; its own docstring warns `autogenerate` would propose dropping them | Tests run against a schema *without* those indexes, so no query-plan regression can be caught |
| `platform_overview` N+1 | `db.query(Tenant).all()` then a `Subscription` query and a `usage()` call per tenant, no pagination | Unbounded on a cross-tenant admin endpoint |
| Three overlapping dashboards, two forecast endpoints, duplicated report endpoints | `dashboard.py:43/184/236`, `automation.py:227` vs `forecasts.py:35`, `reports.py` vs `financial_reports.py` | Each duplicate is a second place for a tenant check or an FX fix to be missed |
| No connection-pool configuration | `create_engine(settings.database_url)` with no `pool_pre_ping` or sizing | A Postgres restart surfaces as 500s rather than transparent reconnection |
| Frontend bundle | 55/55 routes are `"use client"`; `lib/api.ts` is 1,513 lines; all four locale dictionaries (~328 KB JSON) are statically imported into the client bundle | No code-splitting benefit from the App Router; a language switch is synchronous by design |
| Background jobs | FastAPI `BackgroundTasks` plus an in-process `ThreadPoolExecutor` | No durability, no retry across restarts, no dead-letter visibility |
| Rate limiter | In-memory `defaultdict(list)`, never pruned | Resets on restart, not shared across workers, unbounded key growth |

**Not measured:** API response times, bundle size in bytes, query counts under load. There is no benchmark harness, no seeded large dataset, no slow-query log and no APM. Building those is roadmap Tier 4.8 and is a prerequisite for fixing any of the above on evidence rather than on inspection.

**Concurrency:** the double-posting race is now defended at the database level and verified by `IntegrityError`, but **no concurrent-HTTP test exists**. `lock_vat_return` still commits twice, so a failure between the commits leaves a return locked with its transactions unlocked (audit 7.9).

---

## 5. Security final review (20.5)

Full detail in `PHASE_20_RELEASE_READINESS.md` §2. Summary of the re-check the brief asked for:

### Phase 17 findings re-verified in Phase 20

| Finding | Re-verification |
|---|---|
| Cross-tenant isolation (7 endpoints + membership grant) | **PASS.** All 22 tests still pass in the 662-test run. `require_company_access` confirmed tenant-authoritative for all four roles. |
| Logout revocation | **PASS — and upgraded from test-only to live verification.** Against a running production-mode server: `POST /auth/logout` → 204, then the same token → 401. |
| Fail-closed secrets | **PASS.** Verified raising with a non-zero exit, naming all four offenders, leaking zero secret values. |
| `repr(settings)` leak | **PASS.** Canary test confirms no secret appears in `repr()`, `str()`, any log record or the exception message, while `model_dump()` still returns them. |
| XXE / DTD | **PASS.** 14 tests across both CAMT parsers, including billion-laughs, external entities, case-insensitive `<!DocType`/`<!EnTiTy` and a bare `<!ENTITY`; legitimate statements still parse. |
| CORS | **PASS — verified behaviourally, not just by unit test.** Allowed origin echoed; `https://evil.example` received **zero** `Access-Control-Allow-Origin` headers. |
| Key rotation capability | **PASS** (capability). The four-step procedure is tested for all three crypto modules including retirement of the old key. **Rotation itself not performed** — requires an operator backup. |
| RTL fonts | **PASS** in the production CSS bundle. Browser-level computed style **NOT TESTED** (Playwright not run). |

### Still open

MFA re-enrolment without step-up (6.11) · rate limiting ineffective behind a proxy (6.9) · password reset cannot deliver a token and has no UI (6.8, 4.6) · five committed placeholder secrets still in active use locally (6.4) · CSV formula injection (8.13) · JWT in `localStorage` with a 24h lifetime and no refresh (7.17) · no frontend 401/403 handling (7.17) · `partner_id` not validated against company/tenant (8.14) · `invite_employee_self_service` writes no audit log (8.15) · case-sensitive email uniqueness (8.16) · `Employee.linked_user_id` has no unique constraint (8.17) · unauthenticated write on `GET /billing/plans` (8.18) · unvalidated `kvk_number` in an upstream URL path, endpoint unrate-limited (8.19, 7.20) · latent open redirects in the stub providers (8.20) · reset tokens not revoked on re-request (8.21) · audit redaction used in 2 of 11 routers (8.3) · no password policy beyond `min_length=8` on one path (8.2) · `python-jose` 3.3.0 and `passlib` 1.7.4 unmaintained (7.16) · no dependency scanning of any kind.

---

## 6. Checks that could not be performed

| Check | Reason |
|---|---|
| Backend lint / type check | **No tooling exists.** ruff, mypy, flake8, black and pylint are all uninstalled and there is no config file anywhere in the repository. |
| Coverage | `pytest-cov`/`coverage` in neither `requirements.txt` nor the venv. No figure can be given. |
| Playwright e2e | Requires two running servers and a seeded account; `playwright.config.ts` has no `webServer` block. |
| Docker image build | Not attempted; would have surfaced blocker 1 (frontend API URL) but changes no source. |
| `docker compose config` | Exits 1 because `.env.prod` does not exist — a pre-existing requirement of the compose file. Validated structurally instead. |
| Load / soak / concurrency | No harness, no seeded large dataset, and destructive load testing is out of bounds. |
| Backup restore | Explicitly out of bounds against any database. |
| Dependency vulnerability scan | No `pip-audit`, no `npm audit` configuration, no network scan performed. |
| 2026 Dutch tax rates | Requires authoritative Belastingdienst sources. **Rates were not invented.** |
