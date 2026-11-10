# OnHolland Accounting — Technical Audit Report

| | |
|---|---|
| **Repository** | `/Users/sam/Projects/Accounting` |
| **Branch reviewed** | `phase-16-3-complete-internationalisation` @ `97f2d84` (plus uncommitted working tree) |
| **Audit date** | 2026-11-05 |
| **Prepared by** | Qwen Code (senior architect / principal engineer review) |
| **Mode** | **Read-only.** No project file was created, modified or deleted other than this report. No build, test run, server start or database connection was performed. |

---

## 0. Scope, method and confidence

### 0.1 What was reviewed

| Area | Method | Depth |
|---|---|---|
| Architecture (backend, frontend, data, integration, deployment) | Direct reading of source, configs, Dockerfiles, compose files | Full |
| Backend domain logic (VAT, ledger, payroll, financial reports, tax rules) | Direct reading of `app/accounting/`, `app/services/`, `app/reporting/` | Full |
| Database schema and migrations | All 22 migrations, all 30 model modules, chain-integrity analysis | Full |
| Authentication and authorisation | `core/security.py`, `core/deps.py`, `core/crypto.py`, `core/mfa_crypto.py`, `core/token_crypto.py`, `core/rate_limit.py`, `api/v1/auth.py`, `api/v1/users.py`, `api/v1/companies.py`, `api/v1/transactions.py`, `api/v1/vat_returns.py`, `api/v1/documents.py`, `api/v1/billing.py` | Deep but not exhaustive across all 28 routers |
| Frontend | Delegated deep review; load-bearing claims independently re-verified | Full |
| Test suite (backend) | Delegated deep review; load-bearing claims independently re-verified | Full |
| Git history and working tree | `git log`, `git diff HEAD`, `git show`, branch topology, history secret scan | Full |
| Documentation vs. implementation | All 31 `docs/*.md`, root `README.md`, cross-checked against code | Full |
| Operational scripts | `scripts/backup_db.sh`, `scripts/restore_db.sh`, `scripts/rotate_bsn_key.py` | Full |

### 0.2 Scale of the codebase

| Metric | Value |
|---|---|
| Backend Python (`backend/app`) | 18,411 lines across ~120 modules |
| Backend tests | 10,419 lines, 62 files, **540 test functions**, 1,318 assertions |
| Frontend TS/TSX | 17,884 lines |
| Frontend routes (`page.tsx`) | 55 |
| API routers | 28 modules, 217 route decorators |
| Alembic migrations | 22, single clean head `d90e97d4bc35` |
| Git commits | 88 |
| Development window | 2026-11-02 → 2026-11-05 (**4 days**) |
| Self-declared phases | 16 (Phase 7 never existed; Phases 10/11/11.1 present as branches) |

### 0.3 Verification caveats — read before acting on any finding

1. **Nothing was executed.** No `pytest`, no `next build`, no `tsc`, no `alembic upgrade`, no `uvicorn`, no `docker build`. Every "this is broken" claim below is derived from static reading of source and configuration. Where a defect depends on runtime behaviour, that is stated explicitly.
2. **The authorisation matrix is complete.** An exhaustive endpoint-by-endpoint authorisation and IDOR review was commissioned and **did** report; its findings are incorporated at §2.7, §4.6, §6.7, §6.13, §7.19–§7.20 and §8.13–§8.21, and the full 217-route inventory is at §13.5. All 26 routers were covered by AST walk (decorators + signature defaults + decorator-level `dependencies=`); no router-level `dependencies=[...]` exist anywhere, so every guard is per-function. **I independently re-verified the five highest-severity new findings myself** (§6.7 CRITICAL-1/CRITICAL-2, HIGH-1, MEDIUM-1, and §6.13) by reading the cited line ranges directly; the quoted code in those entries is my own extraction, not the agent's.
   One delegated claim was **disproved on re-verification and is excluded**: the assertion that all 88 commits share an identical author date (implying a rewritten history). `git log --format='%ad' --date=short | sort | uniq -c` gives 6 commits on 2026-11-02, 54 on 11-03, 25 on 11-04 and 3 on 11-05 — a genuine four-day timeline, consistent with §10.1. The XXE version-dependence measurements at §7.19 were performed by the delegated review and **not re-run by me**; the static facts (parser, absence of `defusedxml`) are verified.
3. **Where a delegated finding was load-bearing, I re-verified it myself** with independent commands. Those re-verifications are marked ✓ and the exact command result is quoted. Delegated findings I did *not* re-verify are attributed to their source.
4. **Dutch tax figures were not re-derived from primary sources.** I verified that the code contains a single 2025 rule set and that nothing derives the year from the clock. I did **not** independently confirm against the Belastingdienst whether any 2026 rate differs from 2025; the finding is that the system *cannot know*, not that a specific rate is wrong.
5. **Contrast ratios are computed from hex values**, not measured in a browser.

---

## 1. Executive summary

OnHolland Accounting is an unusually ambitious four-day build: a multi-tenant Dutch accounting and VAT platform with AI document extraction, bank reconciliation, deterministic Dutch payroll, financial reporting, budgets, forecasting, KPIs, MFA, GDPR tooling, a 4-locale internationalisation layer including RTL Persian and Arabic, and 540 backend tests. The engineering *discipline* is well above what the timeline would predict: `Decimal` end-to-end in the ledger, content-sniffed uploads, three purpose-isolated Fernet keys, void-never-delete corrections, an AI layer that is architecturally incapable of writing to the database, and documentation that is candid about its own gaps to a degree that is genuinely rare.

It is also **not production-ready, and several of its central claims do not survive contact with the code.** The defects are not cosmetic. They cluster into four themes:

**A. Controls that exist but are not wired to anything.** `VatPeriod.status` is never assigned by any code path, so the balance sheet's VAT liability never clears and the dashboard's "open periods" counter never decreases. `TransactionApprovalStatus` is never used as a filter by any report or VAT calculation, so approving a transaction changes no reported figure. The password-reset raw token is generated, hashed and then discarded — never emailed, logged or returned — so the feature cannot work, and its own docstring claims otherwise. The Phase 14 cross-tenant accountant invitation feature grants access that every data endpoint then rejects. In each case the *machinery* is real and the *effect* is zero.

**B. Financial correctness gaps that produce silently wrong numbers.** No FX handling anywhere outside the VAT engine, so dollars and euros are summed into one unlabelled revenue figure. Manual balance-sheet items are point-in-time stocks summed as though they were flows, so re-recording a fixed asset doubles it. `previous_period()` uses day arithmetic and returns 3 October for the quarter before Q1. Cash-based VAT companies get `vat_period = NULL` on every transaction and therefore permanently zero returns — and the function that would fix it is imported into `transactions.py` and never called.

**C. Security defaults that fail open.** Four valid Fernet keys are committed to the repository and used whenever the environment does not override them; `BSN_ENCRYPTION_KEY` is *not* set in the working `backend/.env`, so this environment is currently encrypting Dutch citizen service numbers under a public key. MFA can be re-enrolled by anyone holding a session token, without proving possession of the existing factor. The rate limiter keys on `request.client.host`, which behind the reverse proxy the deployment docs prescribe is the proxy — one shared bucket for all users. There is no CI, no linter, no coverage tooling and no git remote.

**D. A deployment that cannot work as configured.** `NEXT_PUBLIC_API_URL` is supplied at container *runtime* but read from the *browser* bundle, which Next.js inlines at *build* time. The production frontend image therefore ships hardcoded to `http://localhost:8000/api/v1` and every visitor's browser calls their own machine. The compose file's `${NEXT_PUBLIC_API_URL:?must be set}` guard fails loudly when unset and then silently has no effect when set.

None of these are hard to fix. Most are one-line to one-day changes. What is missing is not effort but **verification**: the project has 540 tests and no CI, no coverage measurement, no migration testing, and a documentation set whose claims were checked by their author rather than by a machine or a reviewer. The single highest-leverage recommendation in this report is not a code change — it is §12.1, standing up a pipeline that would have caught items A, B and D automatically.

**Bottom line:** the platform is a strong prototype with real domain depth and honest documentation. It is roughly 3–5 weeks of focused engineering from a defensible production candidate for a single-tenant or trusted-tenant deployment, and considerably further from a multi-tenant public SaaS, because the multi-tenancy model is the part that is least coherent (§6.7, §7.9).

---

## 2. Architecture overview

### 2.1 System shape

```
                        ┌──────────────────────────────────────┐
   Browser ──HTTPS──►   │  Reverse proxy (nginx/Caddy)         │  DOCUMENTED ONLY,
                        │  TLS termination — not provisioned   │  never deployed
                        └───────────────┬──────────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    │                                       │
        ┌───────────▼──────────┐              ┌─────────────▼─────────────┐
        │  Next.js 16 frontend │              │  FastAPI backend          │
        │  55 routes, 100%     │  Bearer JWT  │  28 routers, /api/v1      │
        │  "use client"        │─────────────►│  3 JSON middleware        │
        │  localStorage token  │   (CORS)     │  layers                   │
        └──────────────────────┘              └─────┬─────────────┬───────┘
                                                    │             │
                                          ┌─────────▼──────┐  ┌───▼──────────────┐
                                          │ PostgreSQL 16  │  │  Anthropic API   │
                                          │ 22 migrations  │  │  (Claude)        │
                                          │ single head    │  │  forced tool use │
                                          └────────────────┘  └──────────────────┘
                                                                     │
                                          ┌──────────────────────────┼─────────────┐
                                          │                          │             │
                                  ┌───────▼──────┐          ┌────────▼───┐  ┌──────▼──────┐
                                  │ Local disk   │          │ KVK sandbox│  │ Tesseract   │
                                  │ ./storage    │          │ (real net) │  │ OCR + nld   │
                                  │ tenant/comp/ │          └────────────┘  └─────────────┘
                                  └──────────────┘
```

**Absent by design and documented as such:** Celery/Redis (background work uses FastAPI `BackgroundTasks` plus an in-process `ThreadPoolExecutor`), Prometheus/metrics, Sentry/error tracking, a real payment provider, SBR/Digipoort transmission, and a live PSD2/Open Banking connection.

### 2.2 Backend layering

The backend separates concerns more cleanly than a four-day build has any right to:

| Package | Responsibility | Assessment |
|---|---|---|
| `app/accounting/` (33 modules) | Deterministic domain logic: VAT rules/engine, ledger, period assignment, matching, reconciliation, cash flow, forecasting, scenarios, KPIs, working capital, Dutch tax rules, entity tax, payroll engine/service, hours, tax optimisation, structure comparison, anomaly and recurring detection, categorisation, budget, subscription, completeness, loonheffingen, bank import/parsers, open banking | **The strongest part of the codebase.** Pure `Decimal` functions, no AI, no I/O beyond the session. Explicitly labelled estimates vs. actuals. |
| `app/services/` (19 modules) | AI providers (extraction, assistant, categorisation, budget), OCR, text extraction, spreadsheet parsing, file validation, storage, document intake/processing/approval, batch processing, retry, validation engine, VAT period generation, KVK, open banking, billing | Clean `Protocol` + `Http`/`Stub` + cached-singleton pattern, applied consistently. |
| `app/reporting/` (7 modules) | PDF (PyMuPDF), XLSX (openpyxl), CSV (stdlib) generation; 726-line 4-locale label dictionary | Deterministic; never renders AI output. |
| `app/api/v1/` (28 routers) | HTTP surface, authorisation, audit logging, JSON-safety | Where most defects live. Authorisation is per-endpoint rather than centralised (§6.7). |
| `app/models/` (30 modules) | SQLAlchemy 2.0 typed ORM | Good typing; weak on constraints (§7). |
| `app/core/` (13 modules) | Config, security, three crypto modules, deps, rate limit, TOTP, request context, locale, message i18n, audit redaction | Purpose-isolated keys are a genuine strength; defaults are the opposite (§6.4). |

**The architectural boundary the project is most proud of holds up.** The AI layer has no database session and no write path: `assistant_facts.py` computes a JSON bundle with deterministic Python and hands it to Claude, which is asked only to narrate. Forced tool use (`tool_choice={"type":"tool", …}`) constrains extraction output to a Pydantic-derived JSON schema. Nothing in `app/services/ai_*.py` imports a model or a session. That is a real structural control, not a prompt instruction, and it is correctly described in the documentation.

**The fundamental architectural limitation is that this is not a double-entry ledger.** There is no chart of accounts, no journal, no balanced debit/credit entries. `AccountingTransaction` carries `net_amount`/`vat_amount`/`gross_amount` and a `ledger_side` (`SALES`/`PURCHASES`). Fixed assets, inventory, equity and loans exist only as manually-entered `ManualBalanceSheetItem` rows. Consequences, all honestly documented in the code:

- `trial_balance()` is labelled "best-effort … not a formal double-entry trial balance".
- `balance_sheet()` computes an `imbalance_amount` and reports `is_balanced: false` rather than forcing a balance — the right behaviour, and there is a test that *requires* it to report failure.
- `cash_flow_statement()`'s accrual-vs-cash reconciliation carries a note that the two "will not match exactly".
- Retained earnings is derived as cumulative net profit from the P&L engine, which is a genuine link rather than a plug.

For an internal management-information tool this is defensible. **For a product that files a statutory VAT return and issues payslips, the absence of a general ledger is a material limitation** — it means no auditable journal trail, no period-close process, no account-level reporting, and a balance sheet that can only balance if an accountant manually enters everything the ledger cannot derive. `components/glass/navConfig.ts:63` marks "Chart of accounts" as `unavailableKey` in the UI, so this is a known and surfaced gap rather than a hidden one.

### 2.3 Frontend architecture

| Aspect | Finding |
|---|---|
| Runtime dependencies | **Four total:** `next` 16.4.3, `next-intl` ^4.14.9, `react` 19.3.0, `react-dom` 19.3.0 |
| Rendering model | **55/55 routes are `"use client"`** ✓ (verified: `grep -rl '^"use client"'` over all `page.tsx` → 55 of 55). One `layout.tsx`, `async`, fetching only the locale. Zero `loading.tsx`, `error.tsx`, `not-found.tsx`, `middleware.ts`, route groups. |
| Data fetching | Hand-rolled `useState` + `useEffect` + `.then/.catch` per route. No SWR, no TanStack Query, no cache, no deduplication, no retry, **no `AbortController`** — rapid filter changes can paint a stale response. |
| API client | `lib/api.ts`, **1,513 lines**: ~750 lines of hand-maintained interfaces mirroring the Pydantic schemas, then a 210-method object over one private `request<T>()`. |
| State | Four client contexts: `auth`, `company`, `theme`, `locale`. |
| Prerendering | `next.config.ts` sets `cacheComponents: true` and `partialPrefetching: true`; `app/layout.tsx:70` sets `export const instant = false`, opting the whole tree out. |
| Types | `strict: true`; **exactly one `any`** in 15,515 lines (`lib/api.ts:750`, a documented `JsonReport` escape hatch). Money is `string` throughout — correct for `Decimal`. |

This is a client-side SPA inside an App Router shell. It forgoes every benefit the framework offers — no server-side data fetching, no streaming, no per-route error boundaries, no caching — while paying its complexity cost. It is not *broken*; it is a mismatch between tool and usage.

**`CompanyProvider` is effectively dead weight.** It fetches and holds the company list app-wide, but only 3 files call `useCompany()`; **38 of 55 pages** independently re-call `api.listCompanies(token)` and render their own `<select>`. Every navigation costs a redundant `/companies` round-trip, and the header's `CompanySwitcher` selection is ignored by 38 pages.

### 2.4 Data model

30 model modules, ~50 tables. Tenancy is a `tenant_id` column on nearly every table; company access is a `user_companies` association table. Notable design decisions:

| Decision | Assessment |
|---|---|
| `Numeric(14,2)` for all ledger money (`MONEY`), `Numeric(6,3)` rates, `Numeric(12,6)` FX | Correct |
| Separate `_eur` columns alongside native-currency columns, nullable until an FX rate is confirmed | Correct and thoughtful — unresolved-FX transactions are excluded from VAT boxes rather than guessed at rate 1 |
| Corrections are new rows (`corrects_transaction_id`), never in-place edits; payments are voided, never deleted | Correct audit design |
| Budgets are immutable versioned rows (`version`, `supersedes_budget_id`) | Correct |
| BSN stored only as `bsn_encrypted LargeBinary`; API returns masked only | Correct and well executed |
| Three separate Fernet keys for three secret classes (BSN, Open Banking tokens, MFA secrets) | Correct isolation design — undermined by committed defaults (§6.4) |
| `AuditLog` append-only by convention, four composite indexes, `request_id` correlation | Good |
| `Document` staging tables use `Float` for money | Documented as deliberate; see §8.6 |
| **Constraint coverage** | **Weak.** Only 4 `UniqueConstraint`s exist in the entire model layer, and the most important one is missing (§6.6, §7.2) |

### 2.5 Integration status — verified against code, not documentation

| Integration | Documented status | Verified status |
|---|---|---|
| Anthropic Claude (extraction, assistant, categorisation, budget) | Real, verified live | **Real.** Forced tool use, retry with backoff, stub fallback when no key. |
| KVK (Chamber of Commerce) | Sandbox verified | **Real network calls**, including at test *collection* time (§9.3). Test API key is KVK's own published sandbox key — not a secret leak. |
| Open Banking / PSD2 | Blocked by external requirement | **Stub only.** `StubOpenBankingProvider` is the only implementation. Payment initiation: no code path exists. Correctly documented. |
| SBR / Digipoort | Blocked by external requirement | **No transmission code.** Loonheffingen lifecycle state machine is real and local. Correctly documented. Note `docs/government-integrations.md` records that the old Digipoort retired 2026-04-01 — already past as of this audit. |
| Billing / Mollie | Sandbox | **Stub only**, with genuine HMAC-SHA256 webhook signature verification. No price is hardcoded. Correctly documented. |
| Email | Not configured | **Not configured, and the consequence is worse than documented** (§6.8). |

### 2.6 Deployment topology

`docker-compose.prod.yml` is well constructed: Postgres on an `internal: true` network with no host route, `POSTGRES_PASSWORD` required with no default, `restart: unless-stopped`, `service_healthy` gating, and a deliberate decision not to bundle a reverse proxy. Both images run as non-root `appuser` with healthchecks.

It has never been run against a real host, and it would not work if it were — see §6.10 (frontend API URL) and §7.6 (Dockerfile defects).

### 2.7 API surface: 217 routes, with substantial duplication

The full inventory is at §13.5. Structural observations:

**All 26 routers are mounted; none is orphaned** ✓. Every module in `app/api/v1/` is imported and `include_router`'d in `__init__.py` (`_json_safe.py` is a helper, not a router). There is no router-level `dependencies=[...]` anywhere, so **every guard is per-function** — which is why the seven omissions at §6.7 exist.

**Duplicated computation behind two authorisation paths.** `reports.py` and `financial_reports.py` both expose P&L and balance sheet, calling the *same* engine functions:

| `reports.py` | `financial_reports.py` | Both call |
|---|---|---|
| `GET /reports/profit-and-loss` (`:147`) | `GET /financial-reports/profit-and-loss` (`:37`) | `fr.profit_and_loss(db, company_id, period)` |
| `GET /reports/balance-sheet` (`:170`) | `GET /financial-reports/balance-sheet` (`:64`) | `fr.balance_sheet(…)` |

The only difference is a `_render(…)` wrapper producing pdf/xlsx/csv instead of JSON. Each file defines its **own** tenant-checking helper with identical logic (`financial_reports.py:21-27` `_get_company_or_404` vs `reports.py:28-33` `_get_company`) — so there are two authorisation paths and two places to get wrong for one computation.

**Three dashboards.** `GET /dashboard` (`dashboard.py:43`), `/dashboard/accountant` (`:184`), `/dashboard/business-owner` (`:236`). The last recomputes P&L, balance sheet, debtors, creditors, forecast and budget variance for one company — overlapping `/dashboard?company_id=X`, all of `/financial-reports/*` and `/forecasts/full` — and issues an unbounded `db.query(Budget)` plus an N+1 loop over companies and periods.

**Two cash-flow forecasts.** `GET /companies/{id}/cash-flow-forecast` (`automation.py:227` → `cash_flow.build_cash_flow_forecast`) and `GET /forecasts/full` (`forecasts.py:35` → `financial_forecast.full_forecast`). Distinct modules, overlapping purpose, both surfaced in the UI.

**Duplicated comparison endpoints.** `/reports/period-comparison` vs `/assistant/period-comparison`; `/reports/scenario-comparison` vs `/scenarios/compare` — the last pair call the same `scenario_engine.compare_scenarios` with the tenant-check logic duplicated.

**Consequence.** Every duplicate is a second place where a tenant check, a role guard, an FX fix (§7.1) or an `approval_status` filter (§6.3) must be applied and can be missed. §6.7's seven omissions are the realised form of this risk. Consolidating the report surface behind one authorisation path is a prerequisite for the centralised tenant check recommended at §11.2/§12 Tier 4, not an alternative to it.

---

## 3. Completed functionality (verified as real)

These are capabilities I traced to working code, not to documentation claims.

### 3.1 Multi-tenant accounting core
- Tenant → company → user model with a `user_companies` grant table; six roles (`owner`, `admin`, `accountant`, `viewer`, `customer`, `employee`).
- Financial years with deterministic VAT-period generation (monthly/quarterly/annual) and the Dutch filing-deadline rule.
- **Financial-year locking is real and enforced**: `ledger_service._ensure_financial_year_open()` is the single choke point for document posting, manual entries and corrections, and raises rather than silently posting. This closes the gap Phase 8's README explicitly admitted to.
- Company CRUD, workspace, completeness tracking, accountant notes with a status workflow.

### 3.2 Document intelligence
- Upload of PDF/JPEG/PNG/XLSX/CSV with **magic-byte content sniffing** (`file_validation.detect_kind`), never trusting client MIME or extension. XLSX is additionally parsed with openpyxl to confirm it is a real workbook and not an arbitrary zip.
- SHA-256 hashing with per-company duplicate detection, plus a business-duplicate heuristic (invoice number + counterparty VAT number + date + gross across *different* files) surfaced as a warning, never an auto-reject.
- PyMuPDF text extraction with Tesseract OCR fallback (Dutch language pack installed in the image).
- Claude extraction behind a provider interface with forced tool use and a null-safe stub that routes everything to manual review.
- Deterministic validation engine: 13 rule codes, mathematical checks only, never a deductibility judgement.
- Status machine `pending → processing → extracted/needs_review → approved/rejected | failed`; low confidence or validation errors always force manual review; nothing auto-approves.
- A lifespan hook resets documents stuck in `PROCESSING` after a crash.
- Bulk batch upload with bounded-concurrency `ThreadPoolExecutor`, per-file rejection that never aborts the batch, and bulk approve/reject sharing `document_approval.py` with the single-document path so the two cannot drift.

### 3.3 Dutch VAT engine
- Versioned rate sets and an explicit `(ledger_side, vat_treatment) → box` mapping table covering 1a/1b/1c/1d/1e/2a/3a/3b/3c/4a/4b/5a/5b.
- Correct treatment of self-assessed purchases (reverse charge, import, EU acquisition) counting toward both 5a and 5b.
- Input-VAT eligibility that **only ever auto-assigns `ELIGIBLE` or `REQUIRES_REVIEW`** — never `INELIGIBLE` or `PARTIALLY_ELIGIBLE`, which require accountant judgement. Pro-rata defaults to 0% deducted rather than guessing.
- Foreign-currency transactions without a confirmed FX rate are excluded from box totals and flagged, not silently converted at rate 1.
- Return workflow `draft → needs_review → ready_for_approval → approved → locked`, with locking cascading to every transaction in the period.
- A reconciliation view surfacing ledger totals, VAT by rate, pending documents, duplicates, validation errors, unresolved FX and prior corrections.
- Honest handling of the non-existent "5g" box: `net_payable` is exposed under that label with a docstring explaining the real form computes rather than labels it.

*Subject to §6.1, §6.2, §6.3 — the engine's mathematics are sound and well tested; the wiring around it is not.*

### 3.4 Banking and reconciliation
- File import for CAMT.053, CAMT.054, MT940 and CSV behind an adapter-shaped boundary.
- Idempotent import via a DB-level `UniqueConstraint(bank_account_id, dedupe_hash)` — a real constraint, not application logic.
- Parsed source fields are immutable; only `reconciliation_status` and match bookkeeping change.
- Deterministic named-signal matching (exact amount, invoice number in reference, payment reference, IBAN, counterparty name, date proximity) with transparent numeric scoring banded into HIGH/MEDIUM/LOW/NONE, plus bounded combinatorial search for 1:many matches and an explicit overpayment signal.
- Approving a match creates a real `Payment`; reversing **voids** it (`voided`, `voided_by_user_id`, `voided_at`, `void_reason`) rather than deleting, preserving the audit trail.
- No bank credential is ever stored.

### 3.5 Automation and intelligence
- Expense-categorisation rules scoped by `company_id`, verified never to match cross-company.
- Recurring-pattern detection by counterparty with interval classification and a `MISSING` flag.
- Six anomaly rules, each evidence-carrying and idempotent, none of which ever applies a "fraud" label.
- Cash-flow forecasting that labels every figure `actual` / `confirmed` / `estimated` and marks projection rows `is_estimate: true`.
- Automation Centre aggregating all of the above into one dashboard query.

### 3.6 Financial reporting and planning
- P&L, balance sheet, cash-flow statement, best-effort trial balance, general ledger, debtors/creditors with aging buckets, VAT overview, revenue/expense breakdowns — all through one `resolve_period()`.
- Period-over-period and year-on-year comparison reusing the same P&L function twice.
- Budgets with draft → submitted → approved workflow, approval restricted so a business owner cannot approve their own, and revisions as new immutable rows.
- Forecasting that explicitly imports Phase 6's cash-flow builder rather than reimplementing it.
- Scenario engine storing only assumptions, recomputed fresh on every read — nothing cached, nothing staleable — with a test proving it never writes to `AccountingTransaction`.
- KPI engine returning `{value, formula, source, period, explanation, missing_data}` for every metric, returning `value: null` with an explanation rather than a misleading 0% or infinite ratio when inputs do not exist. **This is exactly the right design and is rare.**
- Working capital with DSO/DPO computed and DIO reported as *unavailable* rather than assumed zero.
- Exports in PDF, XLSX and CSV; `_json_safe.py` converts every `Decimal` and date to string at the API boundary so money is never silently floated.

### 3.7 Dutch tax and payroll
- Legal-form registry: 13 forms with real, differentiated tax-obligation flags, effective-dated history, `Partner` (VOF/Maatschap/CV) and `Shareholder` (BV/NV with DGA marking) models.
- `entrepreneur_hours_eligible` defaults to **false** and must be explicitly set — never assumed shared across partners.
- Tax-rules engine covering box 1/2 brackets, Vpb, zelfstandigenaftrek, startersaftrek, mkb-winstvrijstelling, KOR, DGA gebruikelijk-loon, algemene heffingskorting with its phase-out curve, all four arbeidskorting brackets, AWf/Aof/Whk/Zvw employer premiums with the annual `max_premieloon` cap, the official *tabel bijzondere beloningen*, and WKR free space. Every consumer function returns `requires_accountant_confirmation: True`.
- Sources are cited inline, including two official Belastingdienst PDFs the author states were fetched and read directly rather than paraphrased. `test_payroll_validation.py:45` parametrises three official table rows and validates the annualize/divide approximation against them within €1.00.
- Payslips are never edited in place: a correction voids the original and creates a linked new one. Payroll-run idempotency is a **DB-level** `UniqueConstraint` with an `IntegrityError → 409` mapping.
- Entrepreneur-hours logging feeding a 1,225-hour urencriterium dashboard that states meeting the threshold is *necessary but not sufficient* and never auto-grants the deduction.
- Tax-optimisation catalogue that computes real before/after figures only where the data exists (zelfstandigenaftrek, KOR) and returns `estimated_tax_before/after: null` with `confidence: "requires_data_not_tracked"` for KIA/EIA/MIA/VAMIL/WKR/pension/loss-utilisation — **never a fabricated savings number**.
- Legal-structure comparator that is a pure what-if function, verified by test never to write to `AccountingTransaction`, and which explicitly refuses to claim one structure is always best.

### 3.8 Security and identity — what genuinely works
- bcrypt password hashing; JWT with a `ver` claim checked against `User.token_version` on every request, making stateless tokens revocable without a session store.
- Account lockout after 5 failures for 15 minutes, audit-logged, with a deliberately distinct 423 message.
- Uniform 401 for unknown-email / wrong-password / locked, so enumeration is limited.
- **BSN protection is the standout control.** Fernet-encrypted at rest; the API returns only `mask_bsn(decrypt_bsn(...))`; `employee_self_service` returns no BSN at all, not even masked; `test_crypto.py` verifies the encrypted bytes never contain the plaintext substring. Grep confirms no logger call site anywhere in `app/` touches a password, BSN or token.
- Password-reset and company-invitation tokens are stored as SHA-256 hashes only, single-use, expiry-enforced.
- MFA is a genuine RFC 6238 TOTP implementation using only stdlib (`hmac`/`hashlib`/`base64`/`struct`), with the secret persisted **only after** a real code verifies, so an unconfirmed secret is never stored. Its key is isolated in a third module.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`) on every response; `/health` does a real `SELECT 1`; `/ready` additionally compares the DB's `alembic_version` against the code's migration head and returns no internal detail on failure.
- Structured JSON logging with `X-Request-ID` correlation propagated through a `ContextVar`, echoed to the client, and attached to audit rows.
- ORM-only data access. I found **no raw string-interpolated SQL anywhere** in `backend/app`; the only `text()` uses are `SELECT 1` and the `alembic_version` read.

### 3.9 Internationalisation
Independently re-verified ✓ — this is the strongest claim in the project and it holds:

```
nl: namespaces=57  leaf keys=1374
en: namespaces=57  leaf keys=1374      en vs nl: missing=0 extra=0 identical=True
fa: namespaces=57  leaf keys=1374      fa vs nl: missing=0 extra=0 identical=True
ar: namespaces=57  leaf keys=1374      ar vs nl: missing=0 extra=0 identical=True
```

- File sizes 72 KB (nl) / 68 KB (en) / 96 KB (fa) / 93 KB (ar) — RTL scripts byte-heavier, consistent with genuine translation.
- Only **7 of 1,374** values per RTL locale are byte-identical to English, and all 7 are legitimately untranslatable (`EBITDA`, `EBIT`, `name@example.com`, `KVK {number}` ×2, `ICP:`, `OSS:`). This is not a stub dictionary.
- 55/55 routes call `useTranslations`; ~1,596 `t()` call sites; **zero untranslated JSX text nodes in any production route**.
- `global.d.ts` augments next-intl's `AppConfig` so a typo'd key is a compile error; `check-translation-parity.mjs` is a genuine hard gate (`process.exit(1)`) and is duplicated as a vitest test.
- `i18n/request.ts` implements `getMessageFallback` against a flattened Dutch dictionary so a missing key renders Dutch rather than `users.inviteButton`.
- Locale-aware formatting: **0 of 140** `formatEUR`/`formatDate`/`formatPercent`/`formatRelativeDate` calls omit the `locale` argument.
- **RTL CSS is unusually well executed.** Logical properties throughout; exactly one deliberate `text-align: right` on numeric columns with an 8-line comment explaining the Excel/Sheets convention; `background-position` given an explicit `[dir="rtl"]` override because CSS has no logical form for it; opt-in `.icon-directional { transform: scaleX(-1) }` so magnifying glasses and euro signs never mirror. Zero `pl-*`/`pr-*`/`ml-*`/`mr-*`/`left-*`/`right-*`/directional `border-l-*`/`rounded-l-*` in the app; one `space-x-2`. `lang` and `dir` are set server-side from the cookie so the first byte is already correct.
- Backend PDF/XLSX localisation including a real Persian/Arabic shaping pipeline (`arabic-reshaper` + `python-bidi`) with embedded fonts and RTL-mirrored layout.

### 3.10 Documentation
31 documents totalling 2,591 lines, including a `production-readiness.md` that opens **"Honest status, not a claim of full readiness"**, answers "Would this go live today?" with **"No"**, and lists its own hard blockers. Every phase document states "Not merged into main. Not deployed. No production data touched." Deferrals are reasoned rather than glossed. This is materially better than typical and should be preserved as a practice — the failures identified in this report are almost all cases where the *verification* behind a claim was manual, not cases where a gap was concealed.

---

## 4. Missing and incomplete functionality

### 4.1 Declared unavailable in the UI (surfaced, not hidden)

`components/glass/navConfig.ts` marks these with `unavailableKey` and renders them `aria-disabled` with a tooltip; `navConfig.test.ts:28` enforces "real route XOR marked unavailable" as a test invariant. This is good practice and worth crediting.

| Nav item | Line | Reason |
|---|---|---|
| Chart of accounts | `:63` | No GL exists (§2.2) |
| Customers | `:74` | `Customer` model exists; no CRUD surface |
| Suppliers | `:75` | No entity at all |
| Leave & absence | `:100` | Not modelled |

### 4.2 Blocked by external requirement (correctly documented, no fake)

| Capability | Blocker |
|---|---|
| SBR/Digipoort VAT, ICP, income-tax, corporate-tax filing | PKIoverheid certificate + Logius registration + conformance suite. Research-only doc exists. Old Digipoort retired 2026-04-01. |
| Live PSD2/Open Banking (AISP) | DNB/EBA-authorised TPP registration and bank sandbox access |
| Payment initiation | Explicitly out of scope; **no code path exists that could move money** — verified |
| Real payment processing | No provider account; stub only, with real HMAC webhook verification |
| Transactional email | No provider configured — but see §6.8, the consequence is understated |
| TLS / reverse proxy | Documented nginx example; never provisioned |

### 4.3 Genuinely not implemented

| Gap | Impact | Evidence |
|---|---|---|
| **Per-company roles** | `User.role` is one value for the whole account. An accountant with access to 40 client companies has the same role in all of them. `intended_role` is recorded on an invitation but never applied. | `docs/accountant-ecosystem.md` states this plainly |
| **Customer portal** | Backend supports it (customer role, scoped access, upload-without-approve, tested). No customer-facing screens exist; a customer sees the accountant UI with mutations blocked server-side. | README Phase 5 deferral |
| **Employee self-service portal** | `Employee.linked_user_id` and a `/me/*` router exist and are tested; the auth/permission flow was completed in Phase 11. Functional but narrow (payslips, timesheets, hours). | `employee_self_service.py` |
| **Full GDPR erasure** | Export and deactivation work. Hard-delete for accounts with no financial link is not wired up. | `docs/gdpr-data-governance.md` |
| **Automated retention enforcement** | 7/10-year Dutch `bewaarplicht` is a documented policy, not enforced code. | same |
| **MFA backup/recovery codes** | A lost authenticator device requires an operator to clear `mfa_enabled` directly in the database. | `docs/security.md`, `models/user.py` comment |
| **CI/CD** | None. No `.github/workflows`, no GitLab CI, no Jenkinsfile, no Makefile. | verified by repo-wide `find` |
| **Metrics, alerting, log aggregation** | Request timing is logged, never aggregated. No Prometheus/Datadog, no Sentry. | `docs/monitoring.md` |
| **Automated backups** | Scripts exist and were drilled twice against disposable databases. No schedule, no off-host copy, no encryption, no retention. | `docs/backup-restore.md` |
| **Automated linter/formatter/type-check for backend** | No ruff, black, flake8 or mypy in `requirements.txt`; no config file anywhere. | verified |
| **Coverage measurement** | `pytest-cov`/`coverage` in neither `requirements.txt` nor the venv. True coverage is unknowable. | verified |
| **Malware scanning of uploads** | Magic-byte validation catches mismatched files; nothing scans content. Deliberately deferred. | README Phase 5 |
| **Department/cost-centre budgets** | No such entity exists; budget lines are company + category + month. | README Phase 8 |
| **Inventory tracking** | Only a manually-entered balance, so inventory turnover and the full cash-conversion cycle are reported unavailable. | README Phase 8 |
| **Corporate income tax** | Never fabricated; explicitly VAT-only. Correct decision. | README Phase 8 |
| **Suppletie (VAT correction return)** | Corrections always land in the *current* period (`ledger_service.create_correction` uses `invoice_date=date.today()`). Dutch rules require a suppletie against the original period above €1,000. No mechanism exists. | `ledger_service.py:~300` |
| **Locale-prefixed routing** | Locale is cookie-only; all four languages share one URL per page. Defensible, but not shareable or indexable per language. | `i18n/config.ts`, no `i18n/routing.ts` |

### 4.4 Documented deferrals that are reasonable

These were deferred with stated reasoning and I agree with the reasoning:

- Per-row AI extraction for XLSX/CSV (data is already structured).
- DB-editable tax-rule admin screen (rates are versioned in code).
- A dedicated calendar-grid UI (the by-month list carries the same information).
- Celery/Redis (single-process `BackgroundTasks` is adequate at current volume, with a documented upgrade path).
- Three separate named report products collapsed into one parameterised P&L/balance-sheet export.
- Localising persisted validation/anomaly messages — `docs/untranslated-backend-messages-inventory.md` gives a genuinely correct four-step analysis of why this needs a schema change (store rule code + interpolation params, render at read time in the requesting user's locale) rather than a rushed string swap. **This is the best-reasoned deferral in the repository.**

### 4.5 Incomplete i18n — the residual gap

The parity claim is true for UI chrome. It is not true for all user-visible text:

| Gap | Sites | Severity |
|---|---|---|
| Hardcoded English `aria-label`s in shared Glass components | 6 — `GlassSidebar.tsx:112,171` (which *does* import `useTranslations` and translates everything else), `GlassLoadingState.tsx:7`, `CompanySwitcher.tsx:22,34`, `GlassModal.tsx:74` | Screen readers announce English in all four locales |
| `AuthGuard.tsx:16` renders hardcoded English `Loading…` | 1 — but on first paint of all 53 guarded routes | Visible |
| Raw backend enum values rendered via `.replace(/_/g," ")` | 7 — **`app/kpis/page.tsx:32` labels the entire KPI dashboard from backend JSON keys**, `review-centre:114`, `loonheffingen:30`, `banking:196,223`, `bank-transactions:129`, `page.tsx:136` | Contradicts `docs/untranslated-backend-messages-inventory.md`, which asserts the frontend translates enum values "where a human-facing label exists". For `consent_status`, `reconciliation_status` and the KPI keys it demonstrably does not. |
| Raw backend free-text messages shown verbatim | 9 — `vat/[id]:190` (`{v.rule_code}: {v.message}`), `anomalies:112,114`, `ai-intelligence:147,153`, `review-centre:131,133`, `documents/[id]:221`, `companies/[id]/workspace:117` | English validation/anomaly strings shown to Persian/Arabic users. Self-documented as deferred. |
| Backend explanatory notes | 16 across `financial_reports.py` (3), `financial_forecast.py` (2), `entity_tax.py` (2), `payroll_service.py` (1, appears in the annual-statement PDF), `scenario_engine.py` (1), `dutch_tax_rules.py` (1), `tax_centre.py` (6) | Self-documented; threading `locale` through multi-level call chains is real work |
| Hardcoded Dutch legal-form names | `legal-structure/page.tsx:79,81` | Arguably proper nouns |

Also: `check-unused-translations.mjs` is explicitly **not** a gate (never exits non-zero) and can only detect *unused dictionary keys*, not *hardcoded strings*. So there is **no automated guard against the class of defect above** — a new `aria-label="Foo"` passes every check the project runs.

And the backend has **three** independent translation stores (`frontend/messages/*.json`, `reporting/report_i18n.py` at 726 lines, `core/messages_i18n.py`) plus **at least four** hardcoded copies of the supported-locale list — including `auth.py`'s `SUPPORTED_LOCALES = {"nl","en","fa","ar"}` with the comment "Kept in sync by hand with frontend/i18n/config.ts". Adding a fifth language means touching all of them, with a parity test guarding only the frontend. The two backend `t()` helpers also disagree on robustness: `report_i18n.t()` falls back to Dutch for an unknown key, while `messages_i18n.t()` does `MESSAGES[DEFAULT_LOCALE][key]` and raises `KeyError`.

### 4.6 Backend endpoints with no frontend caller

Of 217 routes, **7 have no frontend caller of any kind** — verified by grepping each path fragment across `frontend/app` and `frontend/lib`, including `${API_BASE}` direct-`fetch` and URL-builder forms (which account for the other 20 apparent misses; the remaining query-string template literals all resolve to real routes). **No frontend path points at a non-existent backend route** ✓.

| Endpoint | Assessment |
|---|---|
| `POST /auth/password-reset/request` (`auth.py:185`) | **The entire password-reset flow has no UI.** Users cannot self-recover a password at all. Compounds §6.8 — the backend cannot deliver a token either, so the feature is absent at both ends. |
| `POST /auth/password-reset/confirm` (`auth.py:211`) | Same — orphaned backend. |
| `GET /auth/me/data-export` (`auth.py:231`) | **The GDPR Art. 15/20 right of access is not reachable by any user.** `docs/gdpr-data-governance.md` presents this as implemented; the endpoint exists and is correctly scoped, but there is no button. A data-subject request cannot be self-served. |
| `POST /auth/me/deactivate` (`auth.py:267`) | Self-service deactivation has no UI. (The admin-side `POST /users/{id}/deactivate` *is* wired, `lib/api.ts:858`.) |
| `POST /employees/{id}/invite-self-service` (`employees.py:101`) | **The most consequential omission.** This is the *only* way an `employee`-role account is ever created — `get_current_employee` (`deps.py:107-118`) requires `Employee.linked_user_id`. With no UI, the entire `employee_self_service.py` router (9 endpoints) and `frontend/app/employee-portal/` **cannot be onboarded except by hand-crafted API calls**. It is also the one privileged user-creation path with no audit log (§8.15). |
| `PATCH /transactions/{id}/line-items/{line_item_id}` (`transactions.py:174`) | Dead endpoint. The per-line VAT-eligibility override — the mechanism by which an accountant resolves `input_vat_eligibility = REQUIRES_REVIEW`, and therefore the mechanism that makes box 5b correct (§7.11) — is **unreachable from the UI**, even though `TransactionLineItem` is displayed. |
| `POST /auth/logout` (`auth.py:145`) | **See §6.13** — classified separately because it is a live security defect, not merely missing functionality. |

The last two rows matter more than they look. Together they mean: **an accountant cannot resolve a VAT eligibility review through the product**, and **an employee cannot be given an account through the product**. Both are documented as working capabilities.

**Fix.** Wire all six (plus `logout`). The eligibility override and the employee invite are the priorities — they gate correctness (§7.11) and an entire router respectively. Where a capability is genuinely deferred, mark it `unavailableKey` in `navConfig.ts` the way the four items at §4.1 are, rather than leaving an orphaned endpoint.

---

## 5. Implemented functionality vs. project requirements

No original requirements document exists in the repository. `.claude/` is empty; the phase documents reference "the brief" and "the phase spec" but neither is checked in. The requirements baseline below is therefore reconstructed from `README.md`, the 31 `docs/*.md`, and the phase briefs quoted inside them.

**This is itself a finding:** a 16-phase, 88-commit project with no committed specification has no way to verify completion, and no reviewer — human or automated — can distinguish "deliberately out of scope" from "forgotten". Every status claim in the table below is the project's own.

| Requirement area | Claimed | Audit verdict |
|---|---|---|
| Multi-tenant accounting core | Complete | **Met**, with the tenancy caveat at §6.7 |
| AI document intelligence | Complete, verified against live Claude | **Met** |
| Dutch VAT engine | Complete, all boxes | **Met mathematically.** Boxes 2a/3a/4a are unreachable by the automatic pipeline (§7.11); cash-based companies produce zero returns (§6.2); draft transactions are counted (§6.3) |
| Accountant assistant / reports / tax calendar | Complete | **Met.** Assistant has no write path by construction |
| Bulk upload, customer role, rate limiting, prod infra | Complete | **Met** except rate limiting is ineffective behind a proxy (§6.9) and the prod infra does not work as configured (§6.10) |
| Bank import + reconciliation | Complete; no live PSD2 | **Met**, honestly scoped |
| Financial reporting, budgets, forecasting, scenarios, KPIs | Complete | **Met structurally.** Figures are wrong where FX (§7.1), manual balance-sheet items (§7.2) or `previous_period` (§7.3) are involved |
| Dutch legal forms, tax rules, payroll, hours | Complete | **Met**, with the payroll approximation honestly labelled and validated against official tables. **Stale for 2026** (§6.5) |
| Compliance/production: auth hardening, GDPR, Docker, logging, health | Complete | **Partially met.** Auth hardening and logging are real. Docker images build but the frontend one is broken at runtime (§6.10). GDPR export/deactivate work; erasure and retention enforcement do not. Email does not exist (§6.8) |
| Government integrations | Blocked externally | **Correctly scoped.** Loonheffingen lifecycle real; no transmission |
| Open Banking | Blocked externally | **Correctly scoped** |
| MFA | Complete | **Met, with a bypass** (§6.11) |
| AI accounting intelligence, anomaly detection, review centre | Complete | **Met** |
| Access governance: owner role, user management, audit log | Complete | **Met.** `test_user_management.py` is the strongest negative-testing file in the suite |
| Company invitations / accountant ecosystem | Complete, tested (7 tests) | **Not met.** The feature cannot deliver its stated purpose (§6.7) |
| Subscription/billing sandbox, platform admin | Complete | **Met** as a sandbox. `is_platform_admin` is settable only by seed/DB, as claimed ✓ |
| Mollie UI transformation, design tokens, light/dark/system | Complete | **Partially met.** Token architecture is real; 228 hardcoded palette colours survive the "app-wide sweep", producing a 2.53:1 contrast failure in dark mode (§7.7) |
| Internationalisation nl/en/fa/ar + RTL | "Full application-wide coverage" | **Substantially met** for UI chrome and dictionary parity ✓. **Not met** for RTL fonts at HEAD (§6.12) or the residual strings at §4.5 |
| Locale-aware formatting sweep | Complete | **Met** ✓ (0 of 140 formatting calls missing `locale`) |
| CSV compatibility | Complete | **Met** — BOM assertions verified correct (the invisible U+FEFF in source is a readability hazard, not a bug) |

**Overall:** of 21 requirement areas, 11 are fully met, 7 are met with material caveats, 2 are partially met, and 1 (cross-tenant accountant delegation) does not work. The project's own `production-readiness.md` reaches a similar conclusion by a different route and answers "Would this go live today?" with "No". I agree with that answer, and would add that two of its "READY" ratings are wrong: Docker images (§6.10) and tenant isolation (§6.7).

---

## 6. Critical issues

Severity key: **C** = produces wrong statutory figures, breaks a security control, or prevents deployment. **H** = materially wrong data or a real but bounded risk. **M/L** = §8.

Each finding below states the evidence, the consequence, and the fix. All were confirmed by direct reading of the cited lines.

### 6.1 [C] `VatPeriod.status` is never assigned anywhere in the codebase

**Evidence.** `grep -rn "\.status = VatPeriodStatus\|status=VatPeriodStatus" app/` → **zero results**. The column is declared with `default=VatPeriodStatus.open` (`models/financial_year.py:46`) and is only ever *read*:

```python
# app/accounting/financial_reports.py:280-286  (_outstanding_vat_position)
returns = (
    db.query(VatReturn).join(VatPeriod, VatReturn.vat_period_id == VatPeriod.id)
    .filter(VatReturn.company_id == company_id,
            VatPeriod.end_date <= as_of_date,
            VatPeriod.status != VatPeriodStatus.paid)   # never excludes anything
    .all()
)
```
```python
# app/api/v1/dashboard.py:76
open_periods = [p for p in periods if p.status == VatPeriodStatus.open]   # always all of them
```

There is no endpoint, service or migration that ever sets a period to `filed` or `paid`. `VatReturnStatus` has its own `approved`/`locked` states and nothing maps between the two systems.

**Consequence.**
1. `_outstanding_vat_position` sums **every VAT return the company has ever computed, forever**. Paying a VAT bill has no effect on the balance sheet. `vat_payable` grows monotonically every quarter, which corrupts `total_liabilities`, `is_balanced`, `imbalance_amount`, the current/quick ratios, ROA, and the working-capital trend — i.e. most of the balance-sheet-derived output of the platform.
2. The dashboard's "open VAT periods" is "all VAT periods ever". README Phase 1 advertises "open VAT periods, upcoming deadlines" as a dashboard figure.
3. `VatPeriodStatus` is exported in `schemas/company.py:42`, so the API serves a field that is constant and meaningless.

This is a **dead state machine**: the enum, the column, the migration, the schema field and two readers all exist; the writer does not.

**Fix.** Add `POST /vat-returns/{id}/mark-filed` and `mark-paid` (or derive `VatPeriod.status` from `VatReturn.status` plus a recorded payment), write the transition, audit-log it, and add a test that the balance sheet's VAT liability clears after payment. Until then, `_outstanding_vat_position` should filter on `VatReturn.status not in (approved, locked)` as the closest available proxy, and the dashboard should count returns rather than periods.

### 6.2 [C] Cash-based VAT companies get permanently zero returns

**Evidence.** The chain is complete and unbroken:

```python
# app/accounting/period_assignment.py:29-33
if company.vat_accounting_basis == VatAccountingBasis.cash_based:
    if payment_date is None:
        return None                      # ← every cash-based transaction
    anchor_date = payment_date
```

Both callers omit `payment_date`, which therefore defaults to `None`:

```python
# app/accounting/ledger_service.py:185   (post_document_to_ledger)
transaction.vat_period = determine_vat_period(
    db, company, financial_year.id, ledger_side, invoice_date, received_date
)                                                          # 5 positional args
# app/accounting/ledger_service.py:284   (create_manual_entry)
transaction.vat_period = determine_vat_period(db, company, financial_year_id,
                                              ledger_side, invoice_date, invoice_date)
```

Nothing reassigns the period afterwards. `record_payment` (`api/v1/transactions.py`) updates only `payment_status`; `reconciliation_service.approve_match` creates a `Payment` and never touches `vat_period`.

**The smoking gun:** `app/api/v1/transactions.py:8` contains
```python
from app.accounting.period_assignment import determine_vat_period
```
and `grep -c "determine_vat_period(" app/api/v1/transactions.py` → **0**. The import is dead. The fix was intended for the payment path and never written.

`vat_accounting_basis` is user-settable through `CompanyUpdate` (`schemas/company.py:31`) and the README advertises "company settings gained VAT accounting basis (invoice/cash-based)".

**Consequence.** Every transaction for a cash-based company has `vat_period = NULL`. `calculate_vat_return` filters `AccountingTransaction.vat_period_id == vat_period_id`, so all boxes compute to `Decimal("0")`. **The platform produces an all-zero statutory VAT return, silently, with no error, no warning and no reconciliation flag** — for any company an accountant configures as cash-based. `reconciliation.py` and `completeness.py` filter the same way and would also report empty.

**Fix.** In `record_payment` and in `reconciliation_service.approve_match`, after the `Payment` is flushed, call `determine_vat_period(db, tx.company, tx.financial_year_id, tx.ledger_side, tx.invoice_date, tx.received_date, payment_date=<the new payment date>)` and assign the result when the company is cash-based. Add a test that a cash-based company's return is zero before payment and correct after. Consider a DB `CHECK` or a reconciliation warning for cash-based transactions with a NULL period.

### 6.3 [C] Transaction approval has no effect on any reported figure

**Evidence.** `grep -rn "approval_status" app/accounting/ app/reporting/` returns **exactly one** hit — the FX-rate guard at `ledger_service.py:195`. Not `vat_engine.py`, not `financial_reports.py`, not `kpi_engine.py`, not `working_capital.py`, not `reporting/*`.

`vat_engine.calculate_vat_return` filters only on `vat_period_id` and `company_id`. `financial_reports.transactions_in_period` filters only on `company_id`, `invoice_date` and `ledger_side`.

`post_document_to_ledger` never sets `approval_status`, so a transaction posted from an *approved document* remains `DRAFT`. `create_manual_entry` likewise. `document_approval.approve_document_record` approves the `Document` and never touches the transaction.

**Consequence.** `POST /transactions/{id}/approve` writes an audit-log row and flips a flag whose only effect is to block later edits (`transactions.py:138, 182, 216`). **Approving or not approving a transaction changes nothing that is computed.** The official VAT return, the P&L, the balance sheet, the trial balance, the general ledger, every KPI and every exported PDF/XLSX/CSV all include unreviewed `DRAFT` entries.

This inverts the control the whole platform is built around. The README states the workflow is `draft → needs_review → ready_for_approval → approved → locked` and that "once approved, direct transaction edits are blocked (409) and a new, audit-logged correction transaction is required instead" — true for *editability*, false for *inclusion in figures*. A reviewer approving a VAT return has no assurance that the transactions inside it were themselves approved.

It also means the `DRAFT` state is doing double duty: "posted from an approved document but nobody clicked approve on the transaction" is indistinguishable from "an accountant created a manual entry and has not finished it". Both are counted.

**Fix.** Decide the semantics explicitly, then enforce them:
- If a transaction posted from an approved document should be immediately effective, `post_document_to_ledger` must set `approval_status = APPROVED`, and manual entries should be the only `DRAFT` path.
- Add `AccountingTransaction.approval_status != DRAFT` to `calculate_vat_return`, `transactions_in_period`, `_ar_ap`, `_cash_balance` and the reconciliation/completeness queries.
- Add a reconciliation line reporting the count and value of `DRAFT` transactions inside a period being approved, so an accountant sees what is excluded.
- Add tests: a draft manual entry is absent from the VAT return; approving it makes it present.

### 6.4 [C] Valid encryption keys are committed to the repository and are in active use

**Evidence.** `app/core/config.py:7-11` defines five module-level constants — `INSECURE_DEFAULT_JWT_SECRET`, `INSECURE_DEFAULT_BSN_ENCRYPTION_KEY`, `INSECURE_DEFAULT_OPEN_BANKING_KEY`, `INSECURE_DEFAULT_MFA_SECRET_KEY` and `INSECURE_DEFAULT_BILLING_WEBHOOK_SECRET` — each holding a **real, well-formed** value: four are syntactically valid 44-character base64url Fernet keys and one is a 43-character URL-safe HMAC secret. They are used directly as the defaults for the corresponding `Settings` fields, so the application runs on them whenever the environment does not override.

> The literal values are deliberately **not reproduced here**. They are in `backend/app/core/config.py:7-11`, which is the exposure this finding describes; copying them into a second document would widen it. They are not functional credentials in this environment for `JWT_SECRET` (overridden in `backend/.env`) but the other four **are** live — see the verification below.

The only enforcement is `logger.warning(...)` at import time (lines 88-114). **The application starts normally.**

`backend/.env` currently sets `DATABASE_URL`, `JWT_SECRET` (a custom value — good), `ANTHROPIC_API_KEY`, `STORAGE_ROOT`, `MAX_UPLOAD_SIZE_BYTES`. It does **not** set `BSN_ENCRYPTION_KEY` — the variable is absent from the file entirely, so `Settings` falls back to the committed default. (Verified by testing for the `config.py` constant's value in the file, not by printing either.)

`backend/.env.example` lists only `JWT_SECRET`, `BSN_ENCRYPTION_KEY` (empty) and `BSN_ENCRYPTION_KEY_PREVIOUS`. **It does not list `MFA_SECRET_ENCRYPTION_KEY`, `OPEN_BANKING_TOKEN_ENCRYPTION_KEY` or `BILLING_WEBHOOK_SECRET` at all.** Neither does `.env.prod.example`. So an operator who follows the documented setup *cannot* set three of the four secrets, and is guaranteed to run on the committed defaults.

**Consequence.**
- **BSNs** (Dutch citizen service numbers — GDPR special-category-adjacent, statutory identification) are currently encrypted in this environment under a key that is public in the repository. Anyone with read access to the database, a `pg_dump` file, or a backup can decrypt every BSN. The elaborate `mask_bsn` / never-log / never-send-to-AI discipline is defeated at the storage layer.
- **MFA TOTP seeds** likewise. An attacker with DB read access decrypts the seed and generates valid codes indefinitely — **MFA is fully defeated**, not weakened.
- **Open Banking access/refresh tokens** likewise.
- **`BILLING_WEBHOOK_SECRET`** known ⇒ webhook HMAC signatures can be forged, so `subscription.status` can be flipped to `active` or `past_due` at will once a real provider is connected.
- **`JWT_SECRET`** at its default ⇒ anyone can mint a token for any email with any `ver`, i.e. complete authentication bypass including `owner` and `is_platform_admin`. Currently mitigated only because this `.env` sets a custom value — a mitigation that depends on a step the operator must remember.

The three-key isolation design (§3.8) is genuinely good and is entirely negated by all three keys being public.

**Fix (fail closed, do not warn).**
1. Add an `environment: dev | staging | production` setting. When it is not `dev`, **raise at import** if any secret equals its known-insecure default or is unset. A warning in a log stream nobody reads is not a control.
2. Remove the literal key values from source. Use `""` as the default so absence is unambiguous, and generate at first run in dev only (writing to a gitignored local file).
3. Add the three missing variables to `backend/.env.example` and `.env.prod.example`, each with the `Fernet.generate_key()` command beside it.
4. Treat the four committed values as **burned**. Rotate all of them. For BSNs the rotation path exists (`rotate_bsn_key.py`); for MFA and Open Banking it does not (§7.5) — write those scripts first.
5. Add a CI secret-scanning step (gitleaks/trufflehog) so this cannot recur.
6. Because `backend/storage/` on this machine contains uploaded documents including what appears to be a genuine Dutch invoice (`storage/2/1/6_Factuur-Factuur-augustus-2026-320216912258.pdf`), assume the local database holds real personal and financial data and treat this as a live exposure, not a theoretical one. The files are correctly gitignored ✓ — verified `git ls-files backend/storage` is empty.

### 6.5 [C] Tax rules are frozen at 2025 and the system is running in 2026

**Evidence.**
```python
# app/accounting/dutch_tax_rules.py:226-237
_RULE_SETS: dict[int, DutchTaxRuleSet] = {2025: RULES_2025}
CURRENT_TAX_YEAR = 2025

def get_rule_set(year: int | None = None) -> DutchTaxRuleSet:
    year = year or CURRENT_TAX_YEAR
    if year not in _RULE_SETS:
        raise ValueError(f"No Dutch tax rule set recorded for {year} -- ...")
```
```python
# app/accounting/vat_rules.py:48-49
RULE_VERSIONS: dict[str, VatRuleSet] = {"nl-2024": VatRuleSet(..., standard_rate=Decimal("21"), low_rate=Decimal("9"))}
CURRENT_RULE_VERSION = "nl-2024"
```

Six production call sites invoke `get_rule_set()` with **no argument** — `payroll_engine.py:70`, `structure_comparator.py:32`, `hours_service.py:64`, `tax_optimization.py:149`, `entity_tax.py:18/66/87`, `tax_centre.py:139` — and two more default through `CURRENT_TAX_YEAR` (`payroll_service.py:30`, `tax_centre.py:222`).

**The fail-closed guard never fires on the path that matters.** `get_rule_set(2026)` raises. `get_rule_set()` returns 2025 silently, because nothing derives the year from the clock. `payroll_service.create_payroll_run` does `tax_year = tax_year or tax.CURRENT_TAX_YEAR` and then `tax.get_rule_set(tax_year)` — the comment says "fail fast, not silently", but the failure mode is precisely silent: an omitted `tax_year` in November 2026 yields `2025`, which exists, which computes.

**The test suite cannot detect this** (verified by the delegated review): 26 of 28 `get_rule_set` calls in `tests/` pass `2025` explicitly; the other two are `get_rule_set(1999)` asserting `ValueError` and one bare call. Every payroll test hardcodes `period_year=2025` / `tax_year=2025`; **zero derive the year from `date.today()`**. Nothing asserts `CURRENT_TAX_YEAR == date.today().year`. So the suite stays fully green while production computes stale tax.

**Consequence.** A payroll run created today for a 2026 period computes 2025 box-1 brackets, 2025 algemene heffingskorting and arbeidskorting, 2025 AWf (2.74%/7.74%), Aof (6.28%/7.64%), Whk (1.33%), Zvw (6.51%), the 2025 `max_premieloon` of €75,864, the 2025 DGA norm of €56,000, the 2025 zelfstandigenaftrek of €2,470 and the 2025 KOR threshold of €20,000. Payslips and the annual statement PDF print `tax_year: 2025` — the one place a reviewer might notice, buried in a field.

Separately, `CURRENT_RULE_VERSION = "nl-2024"` is stamped onto every `VatReturn.rules_version`, so 2026 VAT returns record that they were computed under a 2024 rule set. At least that is auditable. **I did not independently verify against the Belastingdienst whether any 2026 rate differs from the 2025/2024 values** — the finding is that the system has no mechanism to know, and no mechanism to warn.

**Fix.**
1. Add `RULES_2026` with sources cited, exactly as `RULES_2025` was built. Add a `nl-2026` VAT rule set — note the versioning mechanism has never been exercised; both dicts have exactly one entry.
2. Make the default derive from the clock: `CURRENT_TAX_YEAR` → a function `current_tax_year()` returning `date.today().year`, so `get_rule_set()` raises for a year nobody has loaded rather than silently serving last year's.
3. Add a startup check that logs `CRITICAL` (or refuses to start outside dev) when `current_tax_year() not in _RULE_SETS`.
4. Add a test asserting `get_rule_set(date.today().year)` succeeds and that `CURRENT_TAX_YEAR` matches the calendar year — a test that is *designed* to fail once a year, forcing the annual update. This is the single cheapest high-value test in this report.
5. Surface `tax_year` prominently in the payslip and annual-statement UIs, not only in the PDF footer.

### 6.6 [C] Ledger posting has no database-level idempotency guard

**Evidence.** `app/accounting/ledger_service.py:73-79`:
```python
existing = (
    db.query(AccountingTransaction)
    .filter(AccountingTransaction.source_document_id == document.id).first()
)
if existing is not None:
    return existing  # idempotent: re-approving never double-posts
```
`AccountingTransaction` declares no `UniqueConstraint`. `grep -rn "UniqueConstraint" app/models/*.py` finds exactly four in the entire model layer: `bank_accounts(company_id, iban)`, `bank_transactions(bank_account_id, dedupe_hash)`, `payroll_runs(company_id, period_type, period_year, period_number)`, and `vat_returns(vat_period_id)` via `unique=True`.

**Consequence.** Two concurrent `POST /documents/{id}/approve` requests — a double-click, a browser retry, a load-balancer replay — both execute the `SELECT`, both see nothing, both `INSERT`. The document is **double-posted to the ledger**: revenue and input VAT are counted twice, and the duplicate flows into the VAT return, the P&L, the balance sheet and every export. `approve_document_record` also sets `document.status = approved`, which would make the second call raise `DocumentNotApprovableError` — but only if the first has committed; with two concurrent requests and `autoflush=False` neither has.

The project **already knows this class of bug and already solved it once**: Phase 12 added `uq_payroll_run_period` plus an `IntegrityError → PayrollError → 409` mapping specifically because "payroll run creation had no guard against a double-click/retry creating a duplicate run" (`docs/phase-12-implementation.md`, Workstream F). The same treatment was not applied to the far more consequential document→ledger path. `README.md` claims "Idempotent, restart-safe: re-approving never double-posts (existing Phase 3 guarantee)" — the guarantee is single-threaded only.

**Fix.** Add `UniqueConstraint("source_document_id", name="uq_accounting_transaction_source_document")` (partial, `WHERE source_document_id IS NOT NULL`, since manual entries and corrections have NULL) via a migration, and map `IntegrityError` to a 409 in `documents.py`/`batches.py` exactly as `payroll.py` already does. Add a concurrency test using two sessions.

### 6.7 [C] Multi-tenancy is enforced by convention, and the cross-tenant accountant feature is non-functional

Two related defects in the same mechanism.

**(a) `require_company_access` gives `owner`/`admin` a full bypass with no tenant comparison.**
```python
# app/core/deps.py
def require_company_access(company_id: int, user: User, db: Session) -> None:
    if user.role in ADMIN_ROLES:
        return                                   # ← no tenant_id check
    has_access = any(c.id == company_id for c in user.companies)
    if not has_access:
        raise HTTPException(403, "No access to this company")
```
`User.tenant_id` and `Company.tenant_id` both exist. They are simply never compared here. For the two highest-privilege roles the central authorisation helper provides **zero** protection, and isolation depends entirely on each of 28 routers independently remembering `if obj.tenant_id != user.tenant_id: raise 404`.

Most routers I read do remember — `transactions.py:33`, `vat_returns.py:52/64/83`, `documents.py:44`, `companies.py:94/109/146`, `banking.py:45-71`, `tax_centre.py:44`, `legal_forms.py:27`, `kvk.py:44`. And the delegated test review confirmed **20 tests create a genuine second tenant** across 16 named isolation tests asserting 404-not-403 — so this is not an untested claim, and `docs/security.md`'s "Extensively tested" is fair.

But the pattern is fragile by construction: one new endpoint written by anyone who trusts the helper's name leaks a tenant's financial data to any admin of any other tenant. **The full 217-route audit found seven such endpoints, two of them cross-tenant writes** — enumerated immediately below. Note also that `financial_reports.py` — 13 of whose 21 endpoints have no test at all (§9.4) — is exactly where a further omission would go unnoticed.

*Fix:* make the helper authoritative. Load the company inside `require_company_access` and compare `company.tenant_id == user.tenant_id` for **all** roles, returning the resource so callers cannot skip the check. Then treat any endpoint-level `tenant_id` comparison as defence-in-depth rather than the primary control. Add a lint rule or a test that enumerates every route taking a resource id and asserts it passes through the helper.

##### The bypass is exploitable today — verified enumeration

The full 217-route matrix (§13.5) classified every identifier-taking endpoint. **Seven are reachable cross-tenant by any `owner`/`admin` of any tenant, and one more grants cross-tenant membership to any role.** All code below is my own extraction from the cited lines, re-verified independently.

**CRITICAL-1 — cross-tenant WRITE: lock or unlock another tenant's financial year.**
`app/api/v1/companies.py:196-201`, reached from `lock_financial_year` (`:205`, `require_admin`) and `unlock_financial_year` (`:227`, `require_admin`):
```python
def _get_financial_year_or_404(db: Session, user: User, company_id: int, financial_year_id: int) -> FinancialYear:
    require_company_access(company_id, user, db)          # no-op for owner/admin
    financial_year = db.get(FinancialYear, financial_year_id)
    if financial_year is None or financial_year.company_id != company_id:
        raise HTTPException(404, "Financial year not found")
    return financial_year                                  # ← no tenant_id comparison
```
Both `company_id` and `financial_year_id` are attacker-supplied, and line 199 only ties them to *each other*. An `owner` of tenant A who supplies tenant B's real pair passes both checks and mutates tenant B's row (`is_locked`, `locked_at`, `locked_by_user_id` at `:212-214`).

This is not cosmetic. Per the endpoint's own docstring and `ledger_service._ensure_financial_year_open`, **locking a victim's financial year halts their bookkeeping** — no new postings, no corrections — while unlocking removes the period-integrity control the project identifies as its defence against backdating into a filed period. The `AuditLog` row is written with `tenant_id=user.tenant_id` (`:217-220`), i.e. into the *attacker's* tenant, so the victim's audit trail shows nothing at all.

**CRITICAL-2 — cross-tenant WRITE: bulk-approve another tenant's payment matches.**
`app/api/v1/banking.py:235-257`, `require_editor`:
```python
def bulk_approve_high_confidence(company_id: int, db = …, user: User = Depends(require_editor)):
    require_company_access(company_id, user, db)           # no-op for owner/admin
    matches = (
        db.query(PaymentMatch)
        .filter(PaymentMatch.company_id == company_id,
                PaymentMatch.status == "SUGGESTED",
                PaymentMatch.confidence_level == "HIGH")
        .all()                                             # ← no tenant_id predicate
    )
    for match in matches:
        reconciliation_service.approve_match(db, match, user.id)
```
No `PaymentMatch.tenant_id == user.tenant_id` predicate, and no `db.get(Company, company_id)` tenant check — unlike `create_bank_account` (`banking.py:68-73`) in the same file, which does both. The three sibling single-match endpoints all route through `_get_match_or_404` (`:62-68`), which *does* check `match.tenant_id != user.tenant_id`. This one was missed.

`approve_match` creates real `Payment` rows and flips `BankTransaction.reconciliation_status`. So any admin of any tenant can, **in one request**, post ledger entries and change reconciliation state across every HIGH-confidence suggested match on an arbitrary company's books in another tenant. An `accountant`-role user is blocked (the helper does check membership for non-admins); `owner` and `admin` are not.

**HIGH-1 — cross-tenant READ: financial years and the whole VAT calendar.**
`app/api/v1/companies.py:184-193`, `get_current_user` only:
```python
def list_financial_years(company_id: int, db = …, user: User = Depends(get_current_user)):
    require_company_access(company_id, user, db)           # no-op for owner/admin
    return db.query(FinancialYear).filter(FinancialYear.company_id == company_id).order_by(FinancialYear.year).all()
```
Every other company-resolving endpoint in this file does `db.get(Company, company_id)` + `company.tenant_id != user.tenant_id` (`:93-94`, `:108-109`, `:145-146`, `:259-260`, `:268-269`, `:285-286`). **This is the sole omission in the file.** It leaks fiscal years, `is_locked`, and — via `FinancialYearOut`'s nested periods — every VAT period label, start/end, filing and payment deadline plus `vat_return_id`, for any integer `company_id`. It is also the reconnaissance primitive for CRITICAL-1: it hands the attacker exactly the `financial_year_id` values to lock.

**HIGH-2 / HIGH-3 — cross-tenant READ of invitation PII, and WRITE to revoke.**
`companies.py:306-314` (`list_invitations`) and `:317-333` (`revoke_invitation`) are both guarded only by `_require_company_owner` (`:35-42`), which is `require_company_access` plus a role check — **no tenant comparison**. `list_invitations` leaks `invited_email`, `intended_role`, `status`, `invited_by_user_id`, `expires_at` and `token_hash` for another tenant's pending accountant invitations. (`token_hash` is SHA-256 of a 256-bit token per `core/security.py:59-60`, so the tokens themselves are not recoverable — the exposure is the PII and the invitation graph.) `revoke_invitation` then only ties the invitation to the attacker-supplied `company_id` (`:320`), so an owner in tenant A can **revoke any pending invitation in tenant B**, silently blocking that firm's onboarding of its accountant, with the audit row landing in the attacker's tenant (`:327-329`). The correct pattern exists in the sibling router — `users.py:129-131` (`revoke_user_invitation`) *does* check `invitation.tenant_id != user.tenant_id` — and was simply not applied here.

**MEDIUM-1 — cross-tenant READ: accountant notes in free text.**
`app/api/v1/workspace.py:102-110`, `get_current_user` only:
```python
def list_notes(company_id: int, db = …, user: User = Depends(get_current_user)):
    require_company_access(company_id, user, db)           # no-op for owner/admin
    return db.query(AccountantNote).filter(AccountantNote.company_id == company_id).order_by(…).all()
```
No `AccountantNote.tenant_id` filter and no company tenant check. The three sibling endpoints in the same file are all correct — `get_company_workspace` (`:26-29`), `create_note` (`:116-119`), `update_note_status` (`:151-154`, which checks `note.tenant_id`). Only `list_notes` was missed. It exposes full `NoteOut` including `body`: unstructured accountant commentary about a client which in this domain routinely contains amounts, disputes and personnel detail. Guarded only by `get_current_user`, so **any role in any tenant, including `viewer`**, can read it.

**Verified clean.** Every other identifier-taking endpoint compares `tenant_id` to `user.tenant_id` or scopes through a base query filtered on it. Three patterns, all correct:
- *Helper-with-tenant-check* (`db.get` → `tenant_id != user.tenant_id` → 404, then `require_company_access`): `assistant.py:21-26`, `tax_centre.py:42-48`, `legal_forms.py:24-30`, `financial_reports.py:21-27`, `forecasts.py:19-33`, `budgets.py:20-34`, `payroll.py:26-58`, `loonheffingen.py:15-30`, `documents.py:41-46`, `batches.py:71-77`, `banking.py:45-68`, `transactions.py:31-37`, `employees.py:29-43`, `automation.py:35-40`, `reports.py:28-33`, `dashboard.py:27-32`.
- *Inline check on the fetched row*: `vat_returns.py:48-50/63-65/78-81`, `automation.py:68-71/83-86/158-161/173-176`, `employees.py:150-183`, `workspace.py:151-154`, `kvk.py:44-46`, `reports.py:69-70/99-101/198-199/222-225`, `legal_forms.py:123-125`, `users.py:44-48/129-130`.
- *Base-query tenant filter* on list endpoints, with the `company_id`/`user_id` filter applied **on top of** `tenant_id == user.tenant_id` and, for non-admins, on top of `Company.id.in_(accessible_ids)` — so a foreign id yields an empty set rather than a leak: `dashboard.py:52-58/189-194`, `tax_calendar.py:25-33`, `documents.py:100-107`, `batches.py:162-171`, `transactions.py:59-67`, `banking.py:92-100/150-160`, `companies.py:45-51`, `audit_log.py:36/81/87`, `users.py:62/118-123`. **This is the correct shape, and it is exactly what the seven endpoints above are missing.**

Notable sub-checks that came back clean:
- **`employee_self_service.py` is safe**, confirming the project's own claim. No endpoint accepts `employee_id`; identity comes only from `get_current_employee` (`deps.py:107-118`). `my_payslip_pdf` takes `payslip_id` from the path but funnels it through `_own_payslip_or_404` (`:60-64`, `payslip.employee_id != employee.id` → 404); `submit_my_timesheet_entry` does the same (`:130-132`); `create_my_timesheet_entry` even rejects a payload-supplied `employee_id` mismatch (`:115-116`). Its single `tenant_id` reference (`:118`) is a *write* deriving the value from the resolved employee — correct, not a gap.
- The low `tenant_id` grep counts I flagged earlier in `tax_centre.py`, `legal_forms.py`, `kvk.py` and `tax_calendar.py` are **good factoring, not gaps** — the check lives once in a shared helper and every route calls it. Verified: all 6 `tax_centre` routes call `_get_company_or_404` (`:66,138,157,190,220,240`); all 8 `legal_forms` routes do (`:41,64,75,97,111,125,139,152`).
- **`/billing/admin/overview`** is genuinely cross-tenant by design, gated by `if not user.is_platform_admin` (`:108`), and returns only `tenant_id`, `tenant_name`, `plan_code`, `subscription_status`, `companies_used`, `users_used` — no financial records, documents or ledger. The model comment's claim holds.
- **The file-download and export surface is clean.** Every primary-key fetch is paired with an ownership or tenant predicate: `documents.py:122` via `_get_document_or_404`; `payroll.py:152/158/174` via `_get_payslip_or_404`/`_get_employee_or_404`; `employee_self_service.py:67/88` via `_own_payslip_or_404`; `reports.py:60/86/113/147/170/192/213` all tenant-checked, with `scenario_comparison_report` checking **both** `tenant_id` and `company_id` per scenario (`:222-225`); `batches.py:240` via `_get_batch_or_404`. Secondary-id resolution inside guarded endpoints is also correct throughout (`documents.py:73-75/250-252`, `payroll.py:96-98`, `budgets.py:39-41/71-73`, `transactions.py:88-90/275-277`, `vat_returns.py:26-28`, `batches.py:189`).

**HIGH-4 — `accept_invitation` creates cross-tenant membership with no tenant check.**
`companies.py:336-364`, defect at `:353-355`:
```python
if invitation.invited_email.lower() != user.email.lower():
    raise HTTPException(403, "This invitation was issued to a different email address")
company = db.get(Company, invitation.company_id)
if user not in company.users:
    company.users.append(user)          # ← neither invitation.tenant_id nor company.tenant_id compared to user.tenant_id
```
`User.email` is **globally** unique (`models/user.py:22`), not per-tenant. A tenant-B admin can invite an email that already belongs to a tenant-A user; that user calls this endpoint with the token and is appended to `company.users` for a company in tenant B, creating a cross-tenant `user_companies` row. `company` is also dereferenced at `:353` with no `None` check → `AttributeError`/500 if the company was deleted while an invitation was pending.

This is the mechanism behind §6.7(b) — the feature is documented as intentional cross-tenant delegation. The problem is that it is *half* implemented: the grant succeeds, and every data endpoint then rejects the grantee. Worse, it **chains into the seven endpoints above for non-admin roles**. `list_financial_years`, `list_notes` and `list_invitations` authorise purely from `user.companies` when the role is not `owner`/`admin`, so a `viewer` or `accountant` in tenant A holding this membership can read tenant B's financial years, VAT calendar and accountant notes **without being an admin anywhere**. That is a privilege path the `require_company_access` admin-bypass analysis alone does not reveal.

And it is self-serviceable: `POST /companies/{id}/invitations` returns the **raw invitation token in the HTTP response** (`CompanyInvitationCreateResult.raw_token`, `companies.py:280-282`) because no email provider exists (§4.2). Combined with the case-sensitive email uniqueness check at §8.16, an owner in tenant A can invite an alternate-case spelling of their own address, receive the token directly, and self-grant membership of any company whose owner invites them — with no out-of-band channel involved.

**(b) The Phase 14 cross-tenant invitation feature cannot deliver its stated purpose.**

`docs/accountant-ecosystem.md` describes this as "the actual multi-company mechanism: one accountant user, several client companies across several tenants, each access grant explicit and revocable", and Phase 14 records it as "IMPLEMENTED, tested (7 tests)".

`companies.py:335-364` `accept_invitation` does:
```python
company = db.get(Company, invitation.company_id)
if user not in company.users:
    company.users.append(user)          # ← user.tenant_id is NOT changed
```
So a tenant-B accountant is added to a tenant-A company's `users` while remaining in tenant B. Every consumer then rejects them:

```python
# companies.py:45-51 — the company never appears in their list
def _accessible_companies_query(db, user):
    query = db.query(Company).filter(Company.tenant_id == user.tenant_id)   # ← excludes it
    if user.role not in ADMIN_ROLES:
        query = query.filter(Company.id.in_([c.id for c in user.companies]))
```
```python
# documents.py:42-46 — and neither does its data
if document is None or document.tenant_id != user.tenant_id:   # tenant A != tenant B → 404
    raise HTTPException(404, "Document not found")
require_company_access(document.company_id, user, db)          # would have passed
```
The same shape appears in `transactions.py:33`, `banking.py:45-61`, `vat_returns.py:52`, `employees.py`, `tax_centre.py:44`, `legal_forms.py:27`, `kvk.py:44`.

**Consequence.** An external accountant accepts an invitation, sees no new company in `GET /companies`, and receives 404 on every document, transaction, bank account and VAT return in the company they were just granted. The feature is dead on arrival. Its 7 tests evidently assert that `company.users` contains the user after acceptance and that the token flow is single-use and expiry-enforced (all real and worth having) — but never that the grantee can subsequently *read anything*.

Worse, the two mechanisms point in opposite directions: membership is deliberately cross-tenant while every data query is strictly tenant-scoped. If any endpoint ever relies on `require_company_access` alone — which for a non-admin *is* just a membership check — the cross-tenant user gets in. The design is simultaneously over-permissive and non-functional.

*Fix.* Choose one model and make it explicit:
- **Delegation model (recommended, matches the documented intent):** introduce a `CompanyAccess` row (`user_id`, `company_id`, `role`, `granted_by`, `granted_at`, `revoked_at`, `expires_at`) and authorise against *it* rather than against `tenant_id`. Resource lookups become "does this user have a live grant on this company's tenant's company", and `User.tenant_id` becomes purely an organisational home. This also delivers the missing **per-company roles** (§4.3) for free, since the role lives on the grant.
- **Shared-tenant model:** move the accountant's user row into the client tenant on acceptance. Simpler, but contradicts the documented design and breaks an accountant serving 40 clients.

Either way, add an end-to-end test: tenant-B accountant accepts a tenant-A invitation, then successfully `GET`s the company, its documents and a VAT return. That single test would have caught this.

### 6.8 [C] Password reset cannot work — the token is generated and thrown away

**Evidence.** `app/api/v1/auth.py`, `request_password_reset`:
```python
user = db.query(User).filter(User.email == payload.email).first()
if user is not None:
    raw_token, token_hash = generate_password_reset_token()
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.commit()
    logger.warning("Password reset requested for user %s. No email provider is configured -- "
                   "reset token (not logged here) must be delivered out-of-band by an operator …")
    # Deliberately never logged: the raw token is as sensitive as a password.
    _ = raw_token
```

The docstring above it states "the reset link is logged server-side instead of emailed". **The code explicitly does not log it** — the comment on the very next line says so. `raw_token` exists only as a local variable and is discarded. It is not emailed, not logged, not returned in the response, and not stored (only its SHA-256 hash is).

**Consequence.** No human and no system can ever obtain a valid reset token. `POST /password-reset/confirm` is reachable only with a token nobody possesses. **Password reset is completely non-functional**, and the docstring actively misinforms a reader about why.

This is not merely an "email provider not wired up" gap. `docs/production-readiness.md` rates password reset "PARTIAL — Works end-to-end except email delivery", and `docs/security.md` describes a working "request/confirm flow". Neither is accurate: even with an operator standing by, there is nothing to deliver.

Two corroborating details:
- The company-invitation flow solves the identical problem the other way — `UserInvitationCreateResult` returns `raw_token` in the API response (`schemas/user.py:57`), so an admin can hand it to the invitee. The two flows made opposite choices and only one works.
- **`test_password_reset_full_flow` never completes the flow.** It asserts 204 on request, `token_hash != ""`, and 400 for a *wrong* token. No test anywhere submits a *valid* token. That is why this could not have been caught.

**Fix.** Either (a) return `raw_token` once in the response to an authenticated admin/operator, mirroring the invitation flow, or (b) wire a transactional email provider and send it. Then write the missing test: request → read the token from the response or a captured email → confirm → log in with the new password → assert the old token is rejected as single-use.

Also fix two adjacent defects in the same function: it uses `User.email == payload.email` **exact match**, contradicting the uncommitted `find_user_by_email` helper whose docstring claims to be "the one place this comparison happens, used by every endpoint that looks a user up by an email address someone typed (login, **password reset**, invitation/signup uniqueness checks)" (§8.1); and `PasswordResetConfirm.new_password: str` has **no strength constraint**, while `AcceptUserInvitationRequest.password` requires `Field(min_length=8, max_length=255)` (§8.2).

### 6.9 [C] Rate limiting is ineffective in the documented production topology

**Evidence.** `app/core/rate_limit.py`:
```python
def _client_key(request: Request, scope: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{scope}:{client_host}"
```
Called from 5 sites: `auth.py:46` (`login`, 10/min), `auth.py:193` (`password_reset`, 10/min), `documents.py:68` (`upload`, 30/min), `banking.py:111` (`upload`, 30/min), `batches.py:92` (`batch-upload`, 30/min).

`docs/production-deployment.md` and `docker-compose.prod.yml` both place an nginx/Caddy reverse proxy in front of the stack. Under any such proxy, `request.client.host` is **the proxy's address**, identical for every user.

**Consequence.**
1. **All users of the platform share one 10-request-per-minute login bucket.** The eleventh legitimate login attempt anywhere in the system receives 429. This is a self-inflicted denial of service that triggers as soon as there are more than a handful of concurrent users — and it makes brute-force protection *worse* than useless, because an attacker can lock out the entire platform by making 10 requests.
2. Conversely, an attacker rotating source IPs is not individually limited either, since the key never varies.
3. `_buckets: dict[str, list[float]] = defaultdict(list)` is **never pruned**. Keys accumulate for the process lifetime. The module is unbounded memory growth driven by client address — a slow leak, and a memory-exhaustion vector if the proxy ever forwards a varied client address.
4. It correctly does **not** trust `X-Forwarded-For` ✓, which is the right default — but that means it needs the proxy to be configured to set the real client address, and nothing in the repo does so.

`docs/security.md` lists rate limiting under its OWASP "Weak authentication" row as in effect. It is in effect only for a single-process, directly-exposed deployment — which is not the deployment the project documents.

**Fix.** Configure the ASGI server with `--proxy-headers` and uvicorn's `ProxyHeadersMiddleware` (or `forwarded_allow_ips`), then read the leftmost untrusted-trimmed `X-Forwarded-For` **only** when `request.client.host` is a trusted proxy. Add a bounded LRU or a periodic sweep of `_buckets`. Longer term, move to Redis so the limiter survives restarts and works across workers, as the module's own docstring anticipates. Add a test that two distinct client addresses get independent buckets and that the bucket map does not grow without bound.

Separately: account lockout keys on the *account*, so anyone who knows an email address can lock that user out indefinitely with 5 wrong passwords every 15 minutes. Consider locking the (account, IP) pair, or exponential backoff with a CAPTCHA, rather than a hard account lock.

### 6.10 [C] The production frontend image cannot reach the API

**Evidence.**
```ts
// frontend/lib/api.ts:1
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
```
This is a module-level constant that executes **in the browser**. Next.js statically inlines `NEXT_PUBLIC_*` into the client bundle at **build time**.

```dockerfile
# frontend/Dockerfile
FROM node:22-slim AS build
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build          # ← no ARG/ENV NEXT_PUBLIC_API_URL in scope
```
```yaml
# docker-compose.prod.yml:58-61
  frontend:
    build: ./frontend      # ← no build.args
    environment:
      NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:?NEXT_PUBLIC_API_URL must be set to the public API URL}
```
`environment:` sets the variable for the **runtime** Node process. It has no effect on JavaScript already compiled into `.next/static/chunks`.

**Consequence.** The production bundle inlines `undefined`, the `??` fallback fires, and **every visitor's browser calls `http://localhost:8000/api/v1` — their own machine.** The application is completely non-functional on first deploy. Even if the host resolved, an `http://` call from an `https://` page is mixed-content-blocked by every browser.

The `${…:?must be set}` guard makes this actively misleading: it fails loudly when the variable is *unset*, giving the operator strong confirmation that they configured it correctly, and then the value is silently discarded. Local development masks the bug because the fallback string happens to equal the correct dev value (`docker-compose.yml:48` sets the same value, also at runtime, also ineffectively, also harmlessly).

`docs/production-readiness.md` rates "Docker images | READY | Build clean, non-root, healthchecked (verified with real `docker build`)". A `docker build` does succeed. The image is broken in the browser, and nothing short of deploying and opening DevTools would reveal it.

**Fix.** Either:
```dockerfile
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build
```
with `build: { context: ./frontend, args: { NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL} } }` in compose — or, better, avoid build-time coupling entirely by proxying `/api` through Next (`rewrites()` in `next.config.ts`) so the browser only ever calls a same-origin relative path and the target is resolved server-side at runtime. Add a smoke test that loads the built app and asserts no request goes to `localhost:8000`.

### 6.11 [C] MFA can be re-enrolled without proving possession of the existing factor

**Evidence.** `app/api/v1/auth.py`:
```python
@router.post("/mfa/enable", status_code=204)
def mfa_enable(payload: MfaEnableRequest, user: User = Depends(get_current_user), db = …):
    if not verify_code(payload.secret, payload.code):        # verifies the NEW secret
        raise HTTPException(400, "Invalid code …")
    user.mfa_secret_encrypted = encrypt_mfa_secret(payload.secret)   # ← overwrites
    user.mfa_enabled = True
```
`MfaEnableRequest` is `{secret: str, code: str}`. There is no `current_code`, no password re-entry, and no check that `user.mfa_enabled` is already true. `mfa_setup` is unauthenticated beyond the session and can be called repeatedly.

By contrast `mfa_disable` **does** require a valid code from the *existing* secret — so disabling is protected and replacing is not.

**Consequence.** An attacker holding a valid session token can call `POST /auth/mfa/setup`, enrol their own authenticator, and call `POST /auth/mfa/enable` with their own secret and code. The victim's secret is overwritten; the attacker now has a persistent second factor they control and the victim is locked out of their own MFA. Session tokens are obtainable: JWTs live in `localStorage` (`lib/auth-context.tsx:44`) with a **24-hour** lifetime (`access_token_expire_minutes = 60 * 24`), no refresh token, and — per the delegated frontend review — **no 401 handling anywhere in the client**, so there is no short-lived-token mitigation.

**Fix.** Require step-up authentication before replacing an enrolled factor: if `user.mfa_enabled`, demand a valid code from the *existing* secret (and ideally the password as well) before accepting a new one. Reject `mfa_enable` when a secret is already persisted unless the step-up succeeds. Audit-log the replacement distinctly from initial enrolment, and notify the user by email once email exists. Also shorten the access-token lifetime and introduce a refresh token, and reconsider `localStorage` in favour of an `httpOnly` `SameSite=Strict` cookie plus a CSRF token — `docs/security.md` currently argues CSRF is "not applicable", which is true today but is a consequence of the weaker storage choice, not a virtue of it.

### 6.12 [C] The committed Phase 16.3 does not render Persian or Arabic in the fonts it loads

**Evidence ✓ (independently verified).**
```
$ git show HEAD:frontend/app/globals.css | grep -cE "font-app-sans|:lang\(|vazirmatn|noto-sans-arabic"
0
```
while at the same commit:
```
$ git show HEAD:frontend/app/layout.tsx | grep -nE "Vazirmatn|Noto_Sans_Arabic|font-vazirmatn"
2:import { Geist, Geist_Mono, Noto_Sans_Arabic, Vazirmatn } from "next/font/google";
46:const notoSansArabic = Noto_Sans_Arabic({ variable: "--font-noto-sans-arabic", … })
51:const vazirmatn = Vazirmatn({ variable: "--font-vazirmatn", … })
```
and `layout.tsx` at HEAD still has `body { font-family: var(--font-sans), Arial, Helvetica, sans-serif; }` — Geist only. The CSS variables are injected onto `<html>` and nothing ever reads them.

The entire fix exists **only as uncommitted working-tree state** (`git diff HEAD -- frontend/app/globals.css`, the same diff reviewed in §8.1). The two untracked `.backup-*` files show the intermediate state was itself broken: `:root[lang="fa"]` is an *attribute* selector requiring `lang` to equal exactly `"fa"`, but `layout.tsx:81` emits the full BCP-47 tag `"fa-IR"` (per `i18n/config.ts:7`), so it never matched. `:root:lang(fa)` does. Someone caught that at 13:46:50 on 5 November, one minute before the final save — and never committed it.

**Consequence.** Anyone cloning `97f2d84` — the branch tip, the thing labelled "Phase 16.3: complete locale-aware formatting sweep" — downloads two full Arabic-script webfont families on every page and never renders them. Persian and Arabic text falls back to Geist → Arial → the browser default, with no Persian-tuned metrics and no proper ligatures. `layout.tsx`'s committed comment pointing readers to "globals.css for where `:lang(fa)` applies these" describes a rule that does not exist at that commit.

This is a small code defect and a large process one: **the headline deliverable of the newest commit is in the working tree, not in the commit.**

**Fix.** Commit the `globals.css` change. Delete the three stray backup files (§8.1). Add an e2e assertion — the Playwright suite already visits pages in all four locales — that the computed `font-family` of `<body>` under `lang="fa-IR"` contains `Vazirmatn`. That test would have failed at HEAD.

### 6.13 [C] "Logout" never revokes the session — tokens stay valid for 24 hours

**Evidence ✓ (independently verified).** `frontend/lib/auth-context.tsx:50-55`:
```ts
function logout() {
  localStorage.removeItem("token");
  setToken(null);
  setUser(null);
  router.push("/login");
}
```
Purely client-side. Grepping `frontend/lib/api.ts`, `frontend/app` and `frontend/components` for `logout` returns only `GlassSidebar.tsx:21,144` (which calls this context function) and a `vi.fn()` test mock. **No frontend code calls `POST /api/v1/auth/logout` at all.**

The backend endpoint exists and is correct — `auth.py:145-152` bumps `user.token_version` and writes an `AuditLog` row — but nothing invokes it.

**Consequence.** With `access_token_expire_minutes = 60 * 24` (`config.py:18`), a JWT remains cryptographically valid *and* passes the `token_version` check in `deps.py:60-62` for **24 hours after the user "logs out"**. Any token captured beforehand — via XSS against a `localStorage`-held bearer token (§7.17), a shared or rented device, browser history, an intercepting proxy, or an `Authorization` header written to a log — stays fully usable, and the user has no way to invalidate it. The revocation machinery the codebase documents at length (`models/user.py:31-36`, `docs/security.md`'s "Session revocation | READY | New this phase, tested") is never triggered by the single most common revocation event in the application.

`docs/production-readiness.md` rates session revocation "READY". It is implemented and unit-tested; it is not wired to the UI.

This is a **one-line frontend fix with a disproportionate security payoff**, and it compounds §6.11 (MFA re-enrolment with a stolen token) and §7.17 (no 401 handling, no refresh, `localStorage` storage).

**Fix.** Make `logout()` `async`, `await api.logout(token)` in a `try/finally`, and clear local state in the `finally` so logout succeeds locally even if the call fails. Add the `logout` method to `lib/api.ts` if absent. Add a test asserting `token_version` incremented and that the pre-logout token is subsequently rejected — the backend test for this exists (`test_logout_revokes_the_token_immediately`), so only the frontend side is missing.

---

## 7. High-severity issues

### 7.1 [H] No FX handling anywhere outside the VAT engine

**Evidence.** `grep -rn "net_amount_eur\|currency" app/accounting/financial_reports.py app/accounting/working_capital.py app/accounting/financial_forecast.py app/accounting/kpi_engine.py app/accounting/budget_service.py` → **zero results**.

`AccountingTransaction` carries `currency`, `fx_rate_to_eur` and `_eur` mirror columns, and `vat_engine.calculate_vat_return` handles them carefully — excluding unresolved-FX transactions, converting resolved ones, never guessing rate 1. That discipline stops at the VAT engine.

`financial_reports.profit_and_loss` does:
```python
revenue = sum((t.net_amount for t in sales), ZERO)
```
— `net_amount`, not `net_amount_eur`, with no currency filter and no conversion. Same in `_category_total`, `revenue_breakdown`, `expense_breakdown`, `_ar_ap` (via `gross_amount`), `retained_earnings`, `balance_sheet`, `cash_flow_statement`, and everything downstream: KPIs, working capital, forecasts, budgets, scenarios, and every PDF/XLSX/CSV export.

**Consequence.** A company with a $1,000 invoice and a €1,000 invoice reports revenue of "2,000" with no currency label. Debtors aging, the balance sheet, every margin and every KPI mix currencies. There is no warning, no exclusion and no `missing_data` flag — the opposite of the treatment the VAT engine and the KPI engine give to data they cannot compute honestly.

**Fix.** Add a shared helper that returns the EUR-equivalent amount or raises/flags when unresolved, and use it in every aggregation. Exclude unresolved-FX transactions from reports as the VAT engine does, and surface the exclusion count. Add a test with a mixed-currency company asserting revenue equals the EUR-equivalent total, not the naive sum.

### 7.2 [H] Manual balance-sheet items are summed as flows but represent stocks

**Evidence.**
```python
# app/accounting/financial_reports.py:251-262
def _manual_items_total(db, company_id, category, as_of_date) -> Decimal:
    items = db.query(ManualBalanceSheetItem).filter(
        ManualBalanceSheetItem.company_id == company_id,
        ManualBalanceSheetItem.category == category,
        ManualBalanceSheetItem.as_of_date <= as_of_date,
    ).all()
    return sum((i.amount for i in items), ZERO)
```
`ManualBalanceSheetItem` has `label`, `amount`, `as_of_date` — and no `version`, no `supersedes_item_id`, no `is_movement` flag, and no unique constraint. The model docstring calls these *balances*: "Fixed assets, inventory, equity, and loans … are only ever what an accountant explicitly records here."

**Consequence.** A balance-sheet item is a point-in-time **stock**. Summing every stock ever recorded produces nonsense:
- Recording "Fixed assets €50,000 as of 2025-01-01" and then re-recording the same position a year later yields €100,000.
- There is no way to correct an entry except by adding another row — and no convention, UI affordance or test telling an accountant that the row must be a signed delta rather than the new balance.
- The error propagates into `total_assets`, `total_liabilities`, `total_equity`, `is_balanced`, `imbalance_amount`, the trial balance, the cash-flow statement's investing and financing sections (which compute deltas between two `_manual_items_total` calls, so they double-count too), and every liquidity and ROA KPI.

Budgets solved exactly this problem correctly, with `version` and `supersedes_budget_id` and immutable revisions. Balance-sheet items did not get the same treatment.

**Fix.** Decide the semantics and enforce them. Cleanest: make rows *movements* (additions/disposals) and keep summing — but rename the field, document it, and require a signed amount. Alternative: keep them as balances and change the query to "latest row per `(category, label)` with `as_of_date <= X`", plus a unique constraint on `(company_id, category, label, as_of_date)` so an accidental duplicate is rejected. Add `supersedes_item_id` for corrections either way, and add a test that re-recording a balance does not double it.

### 7.3 [H] `previous_period()` is wrong for quarters and for leap years

**Evidence.**
```python
# app/accounting/financial_reports.py:70-74
def previous_period(period: DateRange) -> DateRange:
    length = (period.end - period.start).days
    return DateRange(period.start - relativedelta(days=length + 1),
                     period.start - relativedelta(days=1))
```

Q1 2026 is 1 Jan – 31 Mar, `length = 89`. The previous period becomes `1 Jan − 90 days = 3 Oct 2025` to `31 Dec 2025`. Q4 2025 actually starts on **1 October** — so **2 days of the prior quarter are silently dropped** from every period-over-period comparison.

For an annual period in a leap year (1 Jan – 31 Dec 2024, `length = 365`), the previous period is `31 Dec 2022 – 31 Dec 2023` instead of `1 Jan 2023 – 31 Dec 2023`.

`year_on_year_period()` three lines below does this correctly with `relativedelta(years=1)`.

**Consequence.** `compare_periods()` — used by the P&L comparison endpoint, the management-report exports and the period-comparison assistant facts — reports a change percentage computed against a period missing its first two days (quarterly) or shifted by one (annual across a leap year). The error is small in magnitude and invisible in the output, which is what makes it dangerous: `change_pct` is presented to an accountant as an exact figure.

**Fix.** Replace day arithmetic with calendar arithmetic — `relativedelta(months=-3)` for a quarter, `-1` for a month, `years=-1` for a year — or store the period type alongside the range and derive from it. Add tests asserting the previous period of Q1 is exactly Q4 (1 Oct – 31 Dec) and that annual comparison across 2024 yields exactly 2023.

### 7.4 [H] No eager loading anywhere; all aggregation done in Python

**Evidence.** `grep -rn "selectinload\|joinedload\|subqueryload" app/` → **0**.

```python
# financial_reports._ar_ap — loads every transaction ever, then N+1 on payments
for t in transactions:
    remaining = _remaining_balance_as_of(t, as_of_date)   # accesses t.payments → one query each
```
```python
# financial_reports.general_ledger — same pattern
for t in sorted(transactions, key=lambda x: x.invoice_date):
    …
    for p in t.payments:      # lazy load per transaction
```
`transactions_in_period` returns `list[AccountingTransaction]` — full ORM objects — and every total is a Python `sum()` over them. `balance_sheet` calls `debtors` and `creditors` (each a full scan plus N+1) and `retained_earnings` calls `profit_and_loss` over the company's entire history. `cash_flow_statement` calls `profit_and_loss` plus `debtors` twice plus `creditors` twice. `platform_overview` queries `Tenant.all()` then loops with a `Subscription` query per tenant.

**Consequence.** A single balance-sheet request for a company with 10,000 invoices issues on the order of 10,000+ queries and materialises the whole history in Python. Response times degrade linearly with ledger size from day one, with no pagination on the AR/AP item lists. This is a hard scalability ceiling well below any real accounting firm's volume.

**Fix.** Add `.options(selectinload(AccountingTransaction.payments))` to the AR/AP and GL queries (one-line, large win). Push aggregation into SQL — `func.sum()` with `group_by` — for the category and counterparty breakdowns. Restrict `_ar_ap` to transactions with a non-zero remaining balance via a subquery rather than loading all of them. Cache or memoise the repeated `profit_and_loss`/`debtors`/`creditors` calls within one request. Add a slow-query log and a benchmark against a seeded 50k-transaction dataset.

### 7.5 [H] Two of the three encryption keys cannot be rotated

**Evidence.** `app/core/crypto.py` provides `reencrypt_bsn_with_current_key()` using `MultiFernet.rotate()`, and `scripts/rotate_bsn_key.py` drives it. `app/core/token_crypto.py` (Open Banking) and `app/core/mfa_crypto.py` (MFA) both construct a `MultiFernet` from `[current] + previous` and both have a `*_previous` setting — but **neither exposes a re-encrypt function**, and `ls backend/scripts/` shows only `backup_db.sh`, `restore_db.sh`, `rotate_bsn_key.py`.

`docs/encryption-key-rotation.md:3` states: *"The only thing encrypted at rest in this system is the employee BSN."* That was true when written and has been false since Phase 12 (Open Banking tokens) and Phase 13 (MFA secrets).

**Consequence.** An operator who suspects the Open Banking or MFA key is compromised — including because it is one of the committed defaults from §6.4 — can add a new key and keep the old one in `_PREVIOUS` forever, but can **never retire it**. Every existing ciphertext remains decryptable with the burned key indefinitely. And the rotation document, which is the thing an operator would follow, tells them the problem does not exist.

**Fix.** Add `reencrypt_token_with_current_key()` and `reencrypt_mfa_secret_with_current_key()` (both are one-liners over `MultiFernet.rotate()`), generalise `rotate_bsn_key.py` into a single `rotate_key.py --secret-class {bsn,open_banking,mfa}`, and rewrite `encryption-key-rotation.md` to cover all three. Add a test that a value encrypted under a retired key can be re-encrypted and still decrypts after the retired key is removed.

### 7.6 [H] Dockerfile and compose defects

| Defect | Evidence | Consequence |
|---|---|---|
| `NEXT_PUBLIC_API_URL` supplied at runtime, needed at build time | §6.10 | Production frontend calls `localhost:8000` from every browser |
| `npm install` instead of `npm ci`; `package-lock.json*` wildcard | `frontend/Dockerfile:4-5` | Non-reproducible builds; a missing lockfile passes silently |
| Full `node_modules` copied into the runtime image | `frontend/Dockerfile:14` | Ships Playwright, vitest, axe-core, TypeScript and ESLint to production — large image, large attack surface. No `output: "standalone"` configured. |
| `CMD ["npm", "start"]` | `frontend/Dockerfile:22` | npm at PID 1 does not forward `SIGTERM`; `docker stop` waits for the 10s timeout then SIGKILLs |
| `pytest` and `httpx` in production requirements | `backend/requirements.txt:13-14` | Test tooling in the runtime image |
| No `pool_pre_ping` / pool sizing on the engine | `app/db/session.py:6` — bare `create_engine(settings.database_url)` | Stale connections after a Postgres restart surface as 500s rather than transparently reconnecting |
| Backend runs `alembic upgrade head && uvicorn …` as `CMD` | `backend/Dockerfile:26` | Racing migrations if the service is ever scaled beyond one replica |
| No `read_only`, `security_opt: no-new-privileges`, `cap_drop`, or resource limits | `docker-compose.prod.yml` | Container hardening left at defaults |
| Frontend healthcheck accepts any status < 500 | `frontend/Dockerfile:19-20` | A 404 or a broken SPA shell reports healthy |
| Hardcoded developer LAN IP committed | `frontend/next.config.ts:12` `allowedDevOrigins: ["192.168.68.105"]`, and the uncommitted `backend/app/main.py` CORS default | Dev-only settings in version control; see §8.1 |

`docker-compose.prod.yml` is otherwise good: `internal: true` Postgres network, required password with no default, `service_healthy` gating, non-root users, no bundled proxy guessed at. The defects above are all fixable in under a day.

### 7.7 [H] Dark-mode contrast failure on the app's primary error surface

**Evidence ✓ (independently verified).** The pattern appears in **48 elements across 43 files**:
```tsx
// app/assistant/page.tsx:51
{error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
```
`bg-red-50` is a fixed Tailwind palette colour (`#fef2f2`); `text-error` resolves through `--color-error → --status-error`, which is `#b91c1c` in light mode (`globals.css:32`) and `#f87171` in dark mode (`:145`).

Computed WCAG contrast:

| Theme | Foreground | Background | Ratio | AA (normal text) |
|---|---|---|---|---|
| Light | `#b91c1c` | `#fef2f2` | **5.91:1** | Pass |
| Dark | `#f87171` | `#fef2f2` | **2.53:1** | **Fail** (needs 4.5:1) |

`grep -ro "dark:" frontend/app frontend/components` → single digits, against **228 occurrences of 34 distinct hardcoded raw palette colours**: `bg-red-50` ×48, `text-white` ×35, `text-green-700` ×16, `text-amber-700` ×12, `bg-amber-100` ×11, and `bg-slate-100`/`text-slate-600` ×5 each in `components/CalendarStatusBadge.tsx` alone. None respond to `data-theme`.

**Why their own tooling cannot see it.** `frontend/scripts/contrast-check.py` evaluates only token-vs-token pairs parsed from the `:root` and `:root[data-theme="dark"]` blocks of `globals.css`. It has no knowledge of Tailwind palette classes, so a `bg-red-50` + `text-error` combination is invisible to it. `docs/ui-accessibility-audit.md` reports contrast as "verified with frontend/scripts/contrast-check.py" — the verification is real but its scope excludes this entire defect class. `frontend/test/axe.ts` disables the `color-contrast` rule because jsdom has no layout engine, and says so honestly in a 10-line comment; so the axe tests cannot catch it either.

This also means three commits claiming a colour sweep — `e665299 "app-wide hardcoded slate-colour sweep"`, `8619b94 "convert … remaining hardcoded-white components"`, `4eed228 "fix remaining raw/non-Dutch currency formatting"` — are incomplete by 228 occurrences.

**Fix.** Replace raw palette classes with semantic tokens (`bg-error-subtle`, `text-error`) that have real dark-mode values, and add the token pairs to `globals.css` so `contrast-check.py` covers them. Where a raw class must stay, add a `dark:` variant. Then extend the Playwright suite — which already runs all four locales — to run axe with `color-contrast` **enabled** against a real browser in both themes. That is the only check in the project's reach that can catch this class.

### 7.8 [H] Accessibility gaps beyond what the project's own audit records

| Gap | Count | Detail |
|---|---|---|
| `<label>` with no `htmlFor` and no wrapping relationship | **24** across 13 files | Verified concretely at `app/companies/page.tsx:70-76` and `app/ledger/[id]/page.tsx:163-188`: the label is a *sibling* of the input and the input has no `id`, so the control has **no accessible name**. `docs/ui-accessibility-audit.md` documents this gap but names only 4 files — it is under-counted by 3×. |
| `<th scope=…>` | **2 of 196** `<th>` elements | Essentially no table header semantics across ~30 data tables. For an accounting product whose primary output is tabular financial data, this is the most consequential accessibility gap in the app. |
| `<caption>` | **1** app-wide | |
| `aria-live` / `role="status"` / `role="alert"` | **4** across 55 routes | Async data arrival and mutation results are announced on a handful of surfaces |
| Hardcoded English `aria-label` | 6 shared components + `AuthGuard.tsx:16` | §4.5 |
| `window.prompt()` used as an input dialog | 3 — `documents/[id]:123`, `payroll:96`, `batches/[id]:76` | Unstylable, no validation, no `required`, returns `null` on cancel (silently aborting the mutation), inaccessible. `GlassModal` exists and is axe-tested with a real focus trap — this is a shortcut, not a missing capability. |

To the project's credit: `GlassTable.tsx:44-48` makes clickable rows keyboard-operable (`tabIndex={0}`, Enter/Space, `role="button"`); `GlassModal` has a genuine focus trap; `GlassDropdown` has arrow-key navigation; `LanguageSelector.tsx:16-27` is a correct `radiogroup`/`radio`/`aria-checked` implementation; `prefers-reduced-motion` is respected; and Phase 14 wrapped 27 pages' `<table>` elements in `overflow-x-auto` for mobile.

### 7.9 [H] `GET /vat-returns` mutates state, is not idempotent, and writes no audit log

**Evidence.**
```python
# app/api/v1/vat_returns.py:31-42
@router.get("", response_model=VatReturnOut)
def get_or_compute_vat_return(company_id, vat_period_id, db = …, user: User = Depends(get_current_user)):
    period = _get_period_or_404(db, user, company_id, vat_period_id)
    vat_return = db.query(VatReturn).filter(VatReturn.vat_period_id == period.id).first()
    if vat_return is None or vat_return.status not in (VatReturnStatus.approved, VatReturnStatus.locked):
        vat_return = vat_engine.recalculate_and_store(db, company_id, user.tenant_id, period)
        db.commit()                                    # ← write inside a GET
        db.refresh(vat_return)
    return vat_return
```

Four distinct problems:
1. **A GET with side effects** violates HTTP semantics. Browsers, proxies, prefetchers and link scanners may replay it; the operation is not safe and not idempotent in the HTTP sense.
2. **A `viewer` can mutate a VAT return.** The guard is `get_current_user`, not `require_editor`. Any authenticated user with company access — including read-only roles — recomputes and overwrites the stored return.
3. **A return in `ready_for_approval` is silently recomputed.** The condition excludes only `approved` and `locked`. So the figures an accountant submitted for approval can change underneath the approver between submission and approval, with no notification.
4. **No `AuditLog` row is written**, while the explicit `POST /{id}/recalculate` endpoint does write one. The same mutation is audited on one path and invisible on the other.

`_transition` also commits twice (once inside, once after the `LOCKED` cascade update at `:140-144`), so a failure between them leaves the return locked with its transactions unlocked.

**Fix.** Make the GET read-only: return the stored return if one exists, and a 404 or an explicit `computed: false` preview payload if not. Require the caller to hit `POST /recalculate` (guarded by `require_editor`, audit-logged) to persist. Wrap the lock cascade in the same transaction as the status change.

### 7.10 [H] `find_user_by_email` defeats the index on `users.email` for every authenticated request

**Evidence.** The uncommitted `app/core/deps.py`:
```python
def find_user_by_email(db: Session, email: str) -> User | None:
    normalized = email.strip().lower()
    return db.query(User).filter(func.lower(User.email) == normalized).first()
```
`get_current_user` calls this on **every authenticated request**. `users.email` is declared `String(255), unique=True, index=True` (`models/user.py:22`), and migration `3853605281ec` added `ix_users_tenant_id`. Wrapping the column in `lower()` makes the b-tree index unusable — Postgres must sequentially scan `users` for each request.

Three further problems with the same change:
- **The stated single-source-of-truth is violated in the same commit.** `auth.py:47-52` inlines its own `func.lower(func.trim(User.email)) == normalized_email` rather than calling the helper — and adds `trim()` on the *column*, which the helper does not. Two normalisations now exist, with different semantics, and the helper's docstring explicitly claims to cover "login, password reset, invitation/signup uniqueness checks". Password reset still uses `User.email == payload.email` exact match (§6.8).
- **The trim is on the wrong side.** Trimming the column means a stored email with accidental surrounding whitespace matches; trimming only the input (as the helper does) does not. Neither is a substitute for normalising at write time.
- **A test was added** (`test_login_normalizes_email_case_and_whitespace`) covering login only — not `get_current_user`, not password reset, not invitation acceptance.

**Fix.** Normalise on write: lowercase and strip in a `validates("email")` hook or a `before_insert` event, add a migration to normalise existing rows, and keep a plain `User.email == normalized` comparison so the unique index is used. If case-insensitive matching must stay in the query, use the `citext` extension or create a functional index on `lower(email)`. Consolidate on one helper and delete the inlined variant in `auth.py`.

### 7.11 [H] Four VAT declaration boxes are unreachable by the automatic pipeline

**Evidence.** `vat_rules.classify_default_treatment` can only return `domestic_standard`, `domestic_low`, `domestic_other`, `domestic_zero_or_exempt`, `eu_supply` or `eu_acquisition`:
```python
if vat_rate is not None:
    if vat_rate == rules.standard_rate:  return VatTreatment.domestic_standard
    if vat_rate == rules.low_rate:       return VatTreatment.domestic_low
    if vat_rate != 0:                    return VatTreatment.domestic_other
counterparty_country = country_from_vat_number(counterparty_vat_number)
if counterparty_country and counterparty_country != "NL" and counterparty_country in EU_COUNTRY_CODES:
    return VatTreatment.eu_supply if ledger_side == LedgerSide.sales else VatTreatment.eu_acquisition
return VatTreatment.domestic_zero_or_exempt
```
`domestic_reverse_charge_received` (box 2a), `export_non_eu` (3a), `import_non_eu` (4a), `private_use` (1d) and `exempt` are **never returned**. The docstring states this is deliberate: "Never guesses reverse-charge/export/import — those require explicit accountant confirmation."

**Consequence.** The design decision is correct — guessing a reverse charge would be worse. But the *consequence* is not surfaced: boxes 2a, 3a, 4a and 1d are always `Decimal("0")` unless an accountant happens to create a manual entry with the right treatment. There is no UI affordance to change a line's `vat_treatment` (`PATCH /transactions/{id}/line-items/{line_item_id}` updates only `input_vat_eligibility`), and no reconciliation warning that a zero-rate EU or non-EU counterparty was defaulted to `domestic_zero_or_exempt` rather than flagged for classification. A company that exports outside the EU or receives reverse-charge services will under-declare, and the platform will not tell them.

Note that 2a is doubly affected: reverse-charge VAT belongs in both 5a and 5b, and `box_5b_vat` accumulates only `line.deductible_vat_amount`, which for a `REQUIRES_REVIEW` line is `Decimal("0")` by design.

**Fix.** Add a `vat_treatment` field to `LineItemEligibilityUpdate` (guarded by `require_editor`, audit-logged, draft-only). Add a reconciliation finding listing transactions classified `domestic_zero_or_exempt` whose counterparty country is non-NL, and any purchase from a non-NL EU counterparty, so an accountant is prompted to confirm. Document in the VAT return UI which boxes can only be populated manually.

### 7.12 [H] Backup and restore scripts have real defects

| Defect | Evidence | Consequence |
|---|---|---|
| **The restore overwrite guard is defeated by any connection error** | `restore_db.sh:16`: `EXISTING_TABLES=$(psql -d "$DB_NAME" -tAc "…" 2>/dev/null \|\| echo "0")` | If `psql` fails because the DB is unreachable, credentials are wrong, or the database does not exist, `EXISTING_TABLES` becomes `"0"` and the guard passes. The README specifically credits this guard with refusing to restore onto a non-empty database — true only when `psql` succeeds. |
| Dumps are unencrypted, with default permissions | `backup_db.sh:15` — plain `pg_dump --file="$OUT_FILE"` | The dump contains plaintext employee names, addresses, salaries and the full financial ledger (BSNs are encrypted, but under the committed key from §6.4, so effectively not). No `chmod 600`, no `umask`, no GPG/age. Written to `./backups`. |
| No retention or rotation | — | Backups accumulate indefinitely, each containing a full copy of personal data — itself a GDPR data-minimisation concern |
| Docstring contradicts behaviour | `backup_db.sh:2-3` claims it "Dumps the database named in `DATABASE_URL` (or `$1`)" | `DATABASE_URL` is never read; `DB_NAME` defaults to the literal `onholland_accounting` and host/user/password come implicitly from `PG*` env vars. Against the prod compose stack (user `${POSTGRES_USER}`, host `postgres`) it connects to the wrong place or fails. |
| Argument parsing footgun | `FORCE="${3:-}"` | `restore_db.sh dump --force` (omitting the DB name) sets `DB_NAME="--force"` and `FORCE=""`, then runs `createdb -- --force` |
| `createdb "$DB_NAME" 2>/dev/null \|\| true` | — | Swallows every error, including a genuine failure |
| No off-host copy, no schedule | `docs/production-readiness.md` concedes this | A disk failure loses the database and its backups together |

`rotate_bsn_key.py` is correct and appropriately cautious (`--dry-run`, single atomic commit), but loads every employee into memory at once — fine at current scale.

**Fix.** Fail closed on the guard: run `psql` without `|| echo "0"`, check its exit status explicitly, and abort on any error. `chmod 600` the dump and pipe through `age`/`gpg`. Add `--keep=N` retention. Parse `DATABASE_URL` or require an explicit `--dbname`. Validate argument count and reject a `DB_NAME` starting with `-`. Add a cron/systemd-timer example and an off-host copy step to `docs/backup-restore.md`.

### 7.13 [H] Two tests make real, billable Anthropic API calls

**Evidence ✓ (independently verified).**
```python
# tests/test_automation_api.py:131
def test_category_suggestion_uses_stub_provider_without_api_key(client, db_session):
# tests/test_financial_reports_api.py:278
def test_budget_suggestion_endpoint_uses_stub_without_api_key(client, db_session):
```
Neither signature includes `monkeypatch`; `grep -c monkeypatch` returns **0** for both files. `grep -rn "anthropic_api_key" tests/` returns exactly one hit — `test_budget_service.py:146`, which does it correctly. `backend/.env` contains a live non-empty `ANTHROPIC_API_KEY` ✓, and `app/core/config.py:78` declares `env_file = ".env"`, resolved relative to CWD; the documented invocation is `cd backend && pytest`.

So `get_categorization_provider()` / `get_budget_provider()` construct the real Claude providers (`ai_categorization_provider.py:37`, `ai_budget_provider.py:42` raise only if the key is *absent*) and issue a real `messages.create` to `api.anthropic.com`.

Three aggravating factors:
1. **The assertion cannot detect it.** `requires_accountant_review is True` is returned by `StubCategorizationProvider` *and* is a plausible field of Claude's structured output. The test passes either way and never verifies the stub path its name claims.
2. **The categorisation fake is unpatchable at the current boundary.** `app/api/v1/automation.py:30` uses `from app.services.ai_categorization_provider import get_categorization_provider` — a direct name import ✓. Patching the module attribute in conftest would **not** affect this call site; you must patch `app.api.v1.automation.get_categorization_provider` or null the key. (`budgets.py` uses `from app.services import ai_budget_provider`, so that one is patchable.)
3. **It is order-dependent.** `_provider` is a module-level cached singleton in both modules. `test_budget_service.py:151` calls `reset_provider_cache()` at teardown, leaving `_provider = None`; the next caller alphabetically re-evaluates with the real key and caches the Claude provider for the rest of the session.

`tests/fakes.py`'s module docstring asserts "Real Claude/Tesseract calls are never made in the automated test suite." **That claim is false.** This is the exact bug class README Phase 4 says was found and fixed — it has recurred in Phases 8 and 11.

The three fakes that *are* wired correctly are wired very well: conftest patches the module attribute, call sites use module-qualified lookup, and the `client` fixture lists all three fakes in its signature so no API test can reach the network for extraction, OCR or the assistant. That is the right design and is why the Phase 4 incident did not repeat for those three.

**Fix.** Convert `automation.py:30` to `from app.services import ai_categorization_provider` and call through the module, matching the established pattern. Add fakes for the categorisation and budget providers to `conftest.py`'s `client` fixture so they are transitively mandatory. Add an autouse fixture that sets `settings.anthropic_api_key = None` for the whole session, so a missing fake fails loudly rather than spending money. Rename the two tests to describe what they assert.

### 7.14 [H] The migration chain has zero test coverage

**Evidence ✓ (independently verified).** `tests/conftest.py:37` builds the schema with `Base.metadata.create_all(engine)`; `grep -rn "alembic" tests/` → **0**.

**Consequence.** All 22 migrations are never executed by any test. Model/migration drift, a broken `upgrade()` step, a bad `server_default`, or a seed-data mismatch ships undetected. This compounds two other findings:
- Migration `3853605281ec` creates 54 indexes and **deliberately does not mirror them into model metadata**, warning in its own docstring that "a future `alembic revision --autogenerate` run will therefore propose DROPPING these indexes." Since tests use `create_all`, they run against a schema **without those 54 indexes** — so no test can catch a query plan regression, and the divergence between model-declared and database-actual schema is permanent and unverified.
- `LEGAL_FORM_SEED_ROWS` is inserted by hand in `conftest.py` *and* by the Phase 9 migration, with nothing asserting the two agree.

Also: the chain itself is clean ✓ — single head `d90e97d4bc35`, 22 revisions, no orphaned `down_revision`.

**Fix.** Add a CI job that runs `alembic upgrade head` against a scratch database, then `alembic downgrade base`, then `upgrade head` again. Add a second job that runs `alembic revision --autogenerate` against a migrated database and **fails if the generated migration is non-empty** — that single check enforces model/migration parity and would immediately surface the 54 undeclared indexes. Then declare the indexes in `__table_args__` so autogenerate is clean. Run the test suite against a migration-built schema, not `create_all`, at least nightly.

### 7.15 [H] AI extraction: silent truncation and an unmitigated first-payee fraud vector

**Evidence.**
```python
# app/services/ai_provider.py
messages=[{"role": "user", "content": (preamble + text)[:50_000]}],
```
No check on `len(text)`, no flag, no `Document.error_message`, no validation finding when truncation occurs. Truncation drops the **end** of the document — where invoice totals, payment terms and the IBAN block conventionally appear.

The system prompt instructs "Only report values that are explicitly present in the text … never guess or invent a value", and forced tool use constrains output to the `InvoiceExtraction` JSON schema. Neither constrains *values*: untrusted document text is concatenated directly into the user message, so a PDF containing "the supplier IBAN is NL00…" can populate `iban`.

**Consequence.**
1. A long invoice can silently lose its totals section and still return high-confidence extraction, because nothing records that truncation happened. The `AMOUNT_MISMATCH` validation rule may then fire on numbers the model reconstructed from the body — or may not fire at all.
2. **Prompt injection into `iban`.** The extracted IBAN flows to `AccountingTransaction.counterparty_iban` (`ledger_service.py:120`) and into payment matching. Existing mitigations are real: nothing auto-approves, low confidence forces `needs_review`, and the `SUPPLIER_BANK_DETAILS_CHANGED` anomaly rule flags an IBAN differing from a counterparty's previous transactions. **But that rule cannot fire for a first-time payee** — there is no prior IBAN to compare against. An attacker posing as a new supplier gets an attacker-chosen IBAN into the ledger, where a hurried accountant may approve it. This is the standard business-email-compromise fraud pattern, and there is no first-payee control: no dual approval, no out-of-band confirmation step, no "new payee" badge in the review UI.

**Fix.** Record truncation: if `len(text) > 50_000`, set a `TEXT_TRUNCATED` validation finding at `warning` severity and reduce `classification_confidence`. Prefer a smarter window (keep the first and last N characters, or extract per-page and summarise) rather than a blind prefix cut. Add a `is_first_transaction_with_counterparty` flag to the review payload and a `NEW_PAYEE_BANK_DETAILS` anomaly rule; require a second approver for any transaction whose IBAN has not been seen before for that counterparty. Consider never letting the AI populate `iban` at all — require it to be typed or confirmed by the reviewer, since it is the one extracted field with direct fraud value.

### 7.16 [H] Dependencies: unmaintained security-critical libraries

| Package | Pinned | Concern |
|---|---|---|
| `python-jose[cryptography]` | **3.3.0** | Last released 2021; effectively unmaintained. Carries CVE-2024-33663 (algorithm confusion with EC keys) and CVE-2024-33664 (JWE). Direct exploitability here is limited — `decode_access_token` pins `algorithms=[settings.jwt_algorithm]` with HS256 and never accepts a JWE — but a JWT library that will not receive patches is the wrong dependency for the authentication boundary. Migrate to `PyJWT` or `joserfc`. |
| `passlib` | **1.7.4** | Unmaintained since 2020; known incompatibility with `bcrypt >= 4.1` (hence the `bcrypt==4.0.1` pin). Works today, blocks upgrades. `bcrypt.hashpw` directly, or `pwdlib`, removes the dependency. |
| `bcrypt` | 4.0.1 | Silently truncates passwords at 72 bytes. No maximum length is enforced on `LoginRequest.password` or any password field, so a very long password is a mild DoS vector and truncation is invisible. Add `max_length=72` (or pre-hash with SHA-256, the standard workaround). |
| `pandas` | 2.2.3 | Heavy dependency used only for XLSX/CSV parsing alongside `openpyxl`. Large image and attack-surface cost for a narrow use. |
| `pytest`, `httpx` | 8.3.4, 0.28.1 | **In the production `requirements.txt`** and therefore in the runtime image. Split into `requirements.txt` / `requirements-dev.txt`. |

No `pip-audit`, `safety`, Dependabot, Renovate or `npm audit` configuration exists anywhere. `requirements.txt` is fully pinned ✓ and `package-lock.json` is committed ✓, so builds are reproducible — but nothing detects a newly-disclosed CVE.

**Fix.** Split dev from prod requirements. Add `pip-audit` and `npm audit --audit-level=high` to CI. Replace `python-jose` and `passlib`. Enforce a password length ceiling. Re-evaluate whether `pandas` earns its weight.

### 7.17 [H] Frontend authentication has no failure path

Findings from the delegated frontend review, consistent with my own reading of the backend contract:

- **JWT in `localStorage`** (`lib/auth-context.tsx:44`) — readable by any script on the origin. `docs/security.md` dismisses CSRF as "not applicable" because auth is a bearer header rather than a cookie; that is true, but it is a consequence of choosing the more XSS-exposed storage, not an independent virtue.
- **No refresh token in the API contract at all.** `TokenResponse` is `{access_token, token_type, mfa_required}`. With `access_token_expire_minutes = 60 * 24`, refresh is impossible without a backend change.
- **No expiry awareness.** The client never decodes the token or reads `exp`.
- **No 401 or 403 handling anywhere.** `lib/api.ts:22-26` throws `ApiError` on any `!res.ok` and that is the entirety of it. `ApiError.status` is captured but **never read by any caller**. The only two redirects to `/login` in the codebase are `AuthGuard.tsx:12` (fires on *absent* token, never on *rejected* token) and explicit `logout()`.

**Consequence.** When a token expires mid-session, `AuthGuard` still sees a non-null token, renders the children, and every route's `.catch(e => setError(e.message))` paints the backend's raw English `detail` string into a red banner — which is also the 2.53:1 dark-mode contrast failure from §7.7. The user is never redirected, the stale token is never cleared, and recovery requires a manual full page reload (which then hits `api.me()` → `catch(() => localStorage.removeItem("token"))` and finally redirects).

`AuthGuard` is applied by hand in **53 of 55** pages rather than once in `app/layout.tsx`, and there is no `middleware.ts`. The two unguarded routes (`/login`, `/users/invitations/accept`) are correctly public ✓ — no route renders tenant data unguarded. But protection is cosmetic client-side routing; every HTML shell is served to any unauthenticated caller. That is acceptable *only* because the backend enforces authorisation, which is precisely the control §6.7 shows to be convention-based.

**Fix.** Add a response interceptor in `lib/api.ts` that branches on `ApiError.status`: on 401, clear the token and redirect to `/login?next=<path>`; on 403, show a translated permission-denied state. Move `<AuthGuard>` into `app/layout.tsx` so new routes are guarded by default. Shorten the access-token lifetime and add a refresh token. Move the token to an `httpOnly` `SameSite=Strict` cookie with a CSRF token, and add a `middleware.ts` server-side check so the shell is not served unauthenticated.

### 7.18 [H] Missing indexes on the hottest query paths

Migration `3853605281ec` adds 54 single-column indexes on `tenant_id`/`company_id`. None of the following exist:

| Missing index | Query that needs it |
|---|---|
| `accounting_transactions(vat_period_id)` | `vat_engine.calculate_vat_return`, `reconciliation.py:19`, `completeness.py:25`, `vat_report.py:42`, `assistant_facts.py:103` — the primary filter of every VAT computation |
| `accounting_transactions(company_id, invoice_date)` | `transactions_in_period` — every P&L, balance sheet, trial balance, GL, KPI and export |
| `transaction_line_items(transaction_id)` | The VAT engine's join; no index at all on this FK |
| `payments(transaction_id)` | `_remaining_balance_as_of`, `general_ledger`, `payment_engine` |
| `documents(company_id, sha256_hash)` | Duplicate detection on every upload |
| `bank_transactions(company_id, booking_date)` | `_cash_balance`, `cash_flow_statement` |
| `audit_logs(created_at)` beyond the composite | Already covered by `ix_audit_logs_tenant_created` ✓ |

Single-column `company_id` indexes are low-selectivity within a tenant; Postgres will often prefer a sequential scan or a bitmap heap scan over them for the composite predicates the reports actually issue.

**Fix.** Add the composite indexes above, and consider dropping the single-column `company_id` ones they supersede. Verify with `EXPLAIN ANALYZE` against a seeded dataset of realistic size — which requires the benchmark harness from §7.4.

### 7.19 [H] Bank-statement XML parsing has zero XXE hardening

**Evidence ✓ (static facts independently verified).** `app/accounting/bank_parsers.py:17`:
```python
from xml.etree import ElementTree
```
and the only two parse sites in the entire codebase:
```python
141:    root = ElementTree.fromstring(content)     # parse_camt053
152:    root = ElementTree.fromstring(content)     # parse_camt054
```
Each is wrapped only in `except ElementTree.ParseError`. **No `XMLParser` is constructed**, so no parser settings are configured at all — no `forbid_dtd`, no `forbid_entities`, no `resolve_entities=False`, no custom entity handler. `defusedxml` is **not** in `backend/requirements.txt` (verified: `grep -c defusedxml` → 0) and **not installed** in `backend/.venv` (verified); `lxml` is likewise absent (the only match is `et_xmlfile`, an openpyxl dependency). MT940 and CSV parsing are line/`csv.DictReader`-based and involve no XML.

Both parse sites are reachable from `banking.py:103` `import_bank_statement` — `require_editor`, 20 MB cap, `"upload"` rate-limit scope. **The input is an attacker-supplied file.**

**Assessment.** The delegated review tested the actual behaviour empirically (I did not re-run these; §0.2 caveat 2):
- **External-entity XXE (file disclosure / SSRF) is NOT exploitable.** `<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/hostname">]><r><Nm>&x;</Nm></r>` raises `ParseError: undefined entity &x;`. Stock `ElementTree` installs no external entity reference handler, so external general entities never resolve. No file read, no outbound request.
- **Internal-entity expansion (billion laughs) is blocked only incidentally, by the interpreter.** On the project venv (Python 3.12.16, matching `FROM python:3.12-slim`) a 349-byte payload expanding to 10,000,000 characters fails with `ParseError: limit on input amplification factor (from DTD and entities) breached`. Measured ceiling: expansion to ~1,000,000 characters from 305 bytes **succeeds**. On the same machine's **system Python 3.9.6 the identical payload succeeds**, yielding 10,000,000 characters — no protection at all.

So the severity is **not** "critical XXE". It is: *the application supplies zero defence, and the only thing preventing entity-expansion DoS is an implicit property of the CPython 3.12 build's bundled expat.* That protection is unpinned — `requirements.txt` specifies no Python version — and vanishes on any 3.9–3.11 base image, any distro Python, or any future interpreter build change.

**Residual exposure even on 3.12.** With `max_upload_size_bytes = 20 MB`, a crafted CAMT file can still drive roughly 100× amplification before expat aborts — of the order of **1–2 GB of transient RSS in a single-process uvicorn worker** (`backend/Dockerfile:26` has no `--workers`). An authenticated `require_editor` user can therefore OOM-kill the entire service. The `"upload"` limiter (30/min) does not meaningfully constrain this, and §8.17 notes it is shared with document uploads.

**Fix.** One line plus a policy decision:
```python
import defusedxml.ElementTree as ElementTree
```
add `defusedxml` to `requirements.txt`, and reject any document containing a `DOCTYPE` outright — CAMT.053/054 and MT940 never legitimately carry one. Add a test with a billion-laughs payload asserting rejection, so the guarantee does not silently depend on the interpreter version again. Pin the Python version in `requirements.txt` or a `.python-version` file.

### 7.20 [H] Rate limiting: shared buckets and unprotected expensive endpoints

Extending §6.9. `grep -rn "enforce_rate_limit(" app/` → **5 call sites only**: `auth.py:46` (`login`, 10/min), `auth.py:193` (`password_reset`, 10/min), `documents.py:68` (`upload`, 30/min), `batches.py:92` (`batch-upload`, 30/min), `banking.py:111` (`upload`, 30/min).

- **MEDIUM — two unrelated features share one bucket.** `documents.py:68` and `banking.py:111` both pass the scope string `"upload"`. Document uploads and bank-statement imports therefore draw from the same 30/min allowance per client. A user in the middle of a bank-import session silently blocks their own invoice uploads, with a confusing 429 and no indication why.
- **LOW — `GET /kvk/lookup/{kvk_number}` is not rate-limited** (`kvk.py:20`, `get_current_user` only). Any authenticated user, **including an `employee`-role account**, can drive unlimited calls to the KVK API through the server using the operator's key. KVK's published pricing is €6.40/month + €0.02/query, so this is direct cost abuse; the cached provider singleton (`kvk_provider.py:105-110`) holds one key for the whole process.
- **Not rate-limited, and acceptable:** `/auth/password-reset/confirm` and `/users/invitations/accept` — both use 256-bit single-use tokens, so brute force is infeasible. `/billing/webhook` is HMAC-verified before any state change ✓ and replay-blocked by `BillingEvent.provider_event_id` uniqueness ✓.
- **MEDIUM — `GET /billing/plans` is unauthenticated *and writes*.** `billing.py:19-22` calls `subscription_service.ensure_plans_seeded(db)` **then `db.commit()`** on every request, with no auth dependency and no rate limit. Idempotent in effect, but it is an unauthenticated write-and-commit path — see §8.18.

**Fix.** Give bank imports their own scope (`"bank-import"`). Add a limiter to `/kvk/lookup` and validate `kvk_number` against `^\d{8}$` (§8.19). Move plan seeding to application startup or a migration so `GET /billing/plans` is a pure read.

---

## 8. Medium and low severity issues, and technical debt

### 8.1 Working-tree hygiene and the uncommitted CORS change

`git status --short`:
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

**The CORS regression.** `backend/app/main.py`:
```python
# Comma-separated allowed origins via CORS_ALLOWED_ORIGINS, defaulting to the
# local dev frontend. Production deployments must set this explicitly --
# never widen this to "*" once credentials are allowed.
_allowed_origins = [o.strip() for o in os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://192.168.68.105:3000"   # ← was "http://localhost:3000"
).split(",") if o.strip()]
```
A specific developer's LAN IP is baked into the **default** for `allow_credentials=True` CORS, directly beneath a comment warning against widening it. The same IP appears committed at `frontend/next.config.ts:12` (`allowedDevOrigins`). If this is committed and ever deployed without `CORS_ALLOWED_ORIGINS` set, a page served from that address on anyone's network can make credentialed cross-origin calls to the API.

The severity is bounded — `http://192.168.68.105:3000` is unlikely to be attacker-controlled, and the API uses bearer tokens rather than cookies so `allow_credentials` matters less than it would otherwise. But it is a local debugging convenience in the wrong place, and it establishes the precedent the comment warns against.

**The stray backups.** Three untracked files, none matched by `.gitignore` (which covers `backend/.venv/`, `__pycache__/`, `.pytest_cache/`, `backend/.env`, `backend/storage/`, `*.pyc`, `frontend/node_modules/`, `frontend/.next/`, `frontend/.env.local`, `.env.prod`, `.DS_Store` — but no `*.bak` or `*.backup-*`). All three are correctly untracked today ✓ (verified with `git ls-files`), but `git add -A` would commit them, and `next build` globs CSS from `app/`.

The two `globals.css` backups are also **the only record of the RTL font fix** (§6.12) and of an intermediate bug: `backup-20261105-134650` differs from the current file by one character class — `:root[lang="fa"]` → `:root:lang(fa)`. The attribute selector can never match the `lang="fa-IR"` that `layout.tsx:81` emits; the pseudo-class does. Someone found and fixed that at 13:46:50 on 5 November and never committed it.

Also present on disk and correctly untracked: `frontend/tsconfig.tsbuildinfo` (176 KB) and `frontend/test-results/.last-run.json`.

**Fix.** Revert the CORS default to `http://localhost:3000` and put the LAN origin in `backend/.env`. Add `*.bak`, `*.backup-*`, `*.orig`, `*.rej` and `tsconfig.tsbuildinfo` to `.gitignore`. Delete the three backup files **after** committing the `globals.css` fix they document. Use git rather than timestamped copies for in-progress work.

### 8.2 No password policy

`grep -rn "min_length\|field_validator" app/schemas/` finds exactly one password constraint in the entire backend:
```python
# schemas/user.py:66  (AcceptUserInvitationRequest)
password: str = Field(min_length=8, max_length=255)
```
Absent from `PasswordResetConfirm.new_password` (§6.8) and from any user-creation path. No complexity rule, no breach-list check, no maximum length (relevant to bcrypt's 72-byte truncation, §7.16). Two flows that both set a password apply different policies.

**Fix.** One shared `PasswordPolicy` annotated type (`Annotated[str, Field(min_length=12, max_length=72)]` plus a validator against a common-breached-password list) used by every password field.

### 8.3 Audit redaction is defined but almost never used

`app/core/audit_redaction.py` exists and `models/audit_log.py`'s docstring mandates it: *"Before/after snapshots must never contain a raw secret — see `app.core.audit_redaction.redact` for the shared redaction helper every new call site should use."* There are **41 `AuditLog(` call sites** across `app/`; `grep -rln "redact" app/api/` returns **2 files** — `users.py` and `banking.py`.

Most of the other 39 hand-pick their dict contents and are safe today. The exception is the pattern at `transactions.py:~155`:
```python
after=payload.model_dump(exclude_unset=True, mode="json"),
```
which serialises an entire request body into the audit log unredacted. `TransactionUpdate` currently holds only `fx_rate_to_eur`, `due_date` and `accounting_classification`, so nothing sensitive leaks *now* — but any field added to that schema lands in a permanent append-only table automatically.

**Fix.** Route every `before`/`after` through `redact()`, and add a test that fails if an `AuditLog(` call site constructs `after=` without it.

### 8.4 JWT subject is an email address, not a user id

`create_access_token(subject=user.email)` and `get_current_user` resolves it with `find_user_by_email`. If an email address is ever edited and later reused by a different account, an unexpired token issued to the first holder authenticates as the second — provided `token_version` happens to match (both default to `0`). Bounded today because tokens live 24h and users are deactivated rather than deleted, but it is an unnecessary coupling.

Also: `create_access_token` emits no `iat`, `nbf`, `jti`, `iss` or `aud`. `decode_access_token` pinning `algorithms=[settings.jwt_algorithm]` correctly prevents algorithm confusion ✓.

**Fix.** Use `user.id` as `sub` and look up by primary key — which also restores index usage (§7.10). Add `iss`/`aud` and validate them.

### 8.5 `seed.py` hardcodes a weak admin and creates no owner

```python
ADMIN_EMAIL = "admin@onholland.nl"
ADMIN_PASSWORD = "changeme123"
…  role=UserRole.admin,
```
Running `python -m app.seed` against any environment creates a known-password administrator. It also creates an `admin`, not an `owner` — and Phase 15 introduced `owner` as the tenant super-role with last-owner protection in `users.py`. A seeded tenant therefore has **zero owners**, so `_count_active_owners()` returns 0 and the owner-management paths are unexercisable until someone promotes a user by hand. `seed.py` also uses `User.email == ADMIN_EMAIL` exact match, inconsistent with §7.10.

**Fix.** Generate a random password and print it once; refuse to run unless an explicit `--i-understand-this-is-insecure` flag is passed or the environment is `dev`; create an `owner`; use the shared email lookup.

### 8.6 `Float` for money in the extraction staging tables

`ExtractedInvoiceFields.net_amount/vat_rate/vat_amount/gross_amount` and `DocumentLineItem.quantity/unit_price/net_amount/vat_rate/vat_amount/gross_amount` are `Float`. The README documents this as deliberate — staging data for AI extraction, converted once at the document→transaction boundary — and the ledger itself is `Numeric(14,2)` throughout ✓.

The conversion is `Decimal(str(value))` (`ledger_service._to_decimal`), which uses the shortest round-tripping repr. That is usually right and is better than `Decimal(float)`, but it is not a principled conversion, and the validation engine's `net + vat == gross` tolerance check operates on binary floats.

Separately, `_to_decimal` swallows `InvalidOperation` and returns `Decimal("0")` — a malformed extracted amount becomes a **zero-value line item** rather than an error, which then posts to the ledger.

**Fix.** Change the staging columns to `Numeric` (a migration plus a schema change; Pydantic already round-trips `Decimal` from JSON strings). At minimum, make `_to_decimal` raise or record a validation finding rather than silently zeroing.

### 8.7 Schema constraint gaps

| Gap | Consequence |
|---|---|
| No `UniqueConstraint(company_id, year)` on `FinancialYear` | Two financial years for the same company and year can coexist, each with its own VAT periods. `determine_vat_period` uses `.first()` on a date-range query, so period assignment becomes **nondeterministic** across overlapping ranges. |
| No uniqueness on `VatPeriod(financial_year_id, label)` or on its date range | Overlapping periods possible if `generate_vat_periods` runs twice |
| No `UniqueConstraint(source_document_id)` on `AccountingTransaction` | §6.6 |
| No FK `ondelete=` anywhere | Company deletion raises an FK violation rather than cascading. Combined with the unimplemented GDPR erasure (§4.3), rows are effectively undeletable. |
| `ExtractedInvoiceFields.review_status: String(20)` | Free text where every comparable field is an `Enum`; `document_approval.py` writes raw `"approved"`/`"rejected"` strings. No DB-level validity. |
| No `CHECK` that an approved/locked transaction has a `vat_period_id` | A cash-based transaction (§6.2) can be locked with no period |
| No `CHECK` that `Payment.amount > 0` | §8.8 |

By contrast `bank_accounts`, `bank_transactions`, `payroll_runs` and `vat_returns` all have correct DB-level uniqueness ✓ — so the discipline exists and was simply not applied uniformly.

### 8.8 `PaymentCreate.amount` accepts zero and negative values

```python
# schemas/accounting.py:41-44
class PaymentCreate(BaseModel):
    amount: Decimal
    payment_date: date
    reference: str | None = None
```
No `gt=0`. `record_payment` (`transactions.py`) creates the `Payment`, recomputes `payment_status` via `payment_engine.compute_payment_status(transaction.gross_amount, transaction.due_date, transaction.payments, date.today())`, and commits. A negative payment inflates `remaining_balance`, can flip a settled invoice back to `UNPAID`, and feeds `_ar_ap` aging, the cash-flow statement and working-capital DSO. It is audit-logged ✓ but not prevented.

Also: `record_payment` has **no `approval_status` check** (you can record a payment against a `LOCKED` transaction) and does **not** call `_ensure_financial_year_open`, unlike every other ledger-writing path. Both may be intentional — payments genuinely arrive after a period is locked — but neither is documented, and the inconsistency with `ledger_service`'s "single choke point" claim is unexplained.

**Fix.** `amount: Decimal = Field(gt=0)`. Decide and document whether payments may post into a locked year; if not, route through `_ensure_financial_year_open`.

### 8.9 `storage.read()` path check is a string prefix, not a path-component check

```python
# app/services/storage.py
def read(storage_path: str) -> bytes:
    full_path = (_root() / storage_path).resolve()
    if not str(full_path).startswith(str(_root().resolve())):
        raise ValueError("Invalid storage path")
```
With `storage_root = /app/storage`, a resolved path of `/app/storage_evil/secret` satisfies `startswith("/app/storage")`. Exploitability is low because `storage_path` is written only by `save()`, which builds it from integer IDs and a sanitised filename ✓ — the module's own docstring is accurate that there is no traversal surface *today*. It is a latent flaw that becomes live the moment any other code path writes `storage_path`.

`secure_filename` is otherwise sound: it splits on both `/` and `\`, replaces everything outside `[A-Za-z0-9._-]` with `_`, strips leading/trailing dots and underscores, and caps at 200 characters. Because truncation happens *after* stripping, a result can still begin with a dot (creating a hidden file) — cosmetic.

Also `_root()` calls `mkdir(parents=True, exist_ok=True)` on every `read()` and twice per call.

**Fix.** `if not full_path.is_relative_to(_root().resolve()): raise`. Hoist `_root()` to a cached module-level value.

### 8.10 Upload handling reads entire files into memory

`create_document_record(…, content: bytes, …)` takes the whole file as bytes; `detect_kind` and `sha256_hex` both operate on it, and `detect_kind` additionally calls `openpyxl.load_workbook(BytesIO(content))` for any zip-magic payload. With `max_upload_size_bytes = 20 MB` and `batch_max_files = 100`, a single batch request can hold ~2 GB. A small zip-magic file that expands enormously is a decompression-bomb vector through openpyxl.

I did not verify where the size limit is enforced relative to reading the body; that falls inside the authorisation/surface review that did not complete (§0.2 caveat 2).

**Fix.** Stream to a temp file, hash incrementally, and enforce the size cap while reading rather than after. Cap the uncompressed size openpyxl will expand, or reject zip payloads whose declared uncompressed size exceeds a threshold.

### 8.11 `/health` and `/ready` implementation details

`/ready` constructs an `alembic.config.Config` and calls `ScriptDirectory.from_config(...)` — reading and parsing the migration directory from disk — on **every invocation**. Under a 30s container healthcheck that is harmless; under a 5s orchestrator probe across replicas it is needless I/O. Cache the head revision at startup.

`/health`'s error branch interpolates an exception class name into a hand-built JSON string:
```python
return Response(content=f'{{"status": "error", "detail": "{exc.__class__.__name__}"}}', status_code=503, …)
```
Only the class name is exposed ✓ (no message, no traceback), so this is not an information leak — but building JSON by f-string is fragile if a class name ever contains a quote. Use `json.dumps`.

Neither endpoint is authenticated ✓ (correct), and neither returns schema details or migration ids ✓, as `docs/monitoring.md` claims.

### 8.12 Backend structural observations

- **Three translation stores and four hardcoded locale lists** (§4.5).
- **`report_i18n.py` is 726 lines** — the largest file in the backend — and is a hand-maintained nested dict. `t()` silently falls back to Dutch for an unknown key in a known locale, so a missing Persian string renders Dutch in a Persian PDF with no error and no test failure. `messages_i18n.t()` instead raises `KeyError` for a key missing from Dutch. Two helpers, two failure modes.
- **Plural handling** uses "(s)"-style English and "(n)"-style Dutch simplifications, documented as deliberate. Arabic has dual and plural forms; Persian does not inflect for number the same way. For a product targeting `fa`/`ar` this will read as machine-translated.
- **`/billing/admin/overview`** loads every `Tenant` then issues a `Subscription` query plus a `usage()` call per tenant — unbounded N+1 with no pagination on a cross-tenant administrative endpoint.
- **`app/api/v1/_json_safe.py`** is good discipline and should be applied uniformly; `transactions.py` returns ORM objects directly through Pydantic instead, so two serialization conventions coexist.
- **`backend/app/main.py.bak`** sits beside the live module. Python will not import it, but it is a maintenance hazard and would be copied into the Docker image (`COPY . .` with no `.dockerignore` rule for `*.bak` — `backend/.dockerignore` exists but I did not verify its contents).

### 8.13 CSV formula injection via unsanitised `original_filename`

`batches.py:250-254` (`export_batch`, `require_uploader` — so the `customer` role reaches it):
```python
writer.writerow([d.id, d.original_filename, d.upload_category.value if d.upload_category else "", …])
```
`d.original_filename` is the **raw client-supplied filename**: `document_intake.py:44` stores `original_filename=filename or clean_name`, while only `secure_filename` (`:45`) passes through `file_validation.secure_filename`. `csv.writer` does not neutralise a leading `=`, `+`, `-` or `@`, so an uploader who names a file `=HYPERLINK(…)` or `=cmd|…` produces a CSV that executes on open in Excel. Requires a viewer in the same tenant to export the batch and open it — so this is insider/lateral, not remote.

The same value reaches `vat_report.py:154` as PDF text (inert) and is returned in `DocumentOut` to the frontend, where React escapes it — no `dangerouslySetInnerHTML` exists anywhere in `frontend/app` or `frontend/lib` ✓.

**Path traversal is NOT reachable** ✓: `storage.py:20-24` builds the relative path from `str(tenant_id)/str(company_id)/f"{document_id}_{filename}"` where `filename` is the already-sanitised `clean_name` (`document_intake.py:55`), and `secure_filename` replaces everything outside `[A-Za-z0-9._-]` with `_` before truncation, so no `/` or `\` survives. `Content-Disposition` (`documents.py:129`) interpolates `secure_filename`, whose charset excludes `"` and CR/LF, so no response-header injection either.

**Fix.** Prefix any cell beginning with `=`, `+`, `-`, `@`, tab or CR with a single quote (or wrap in a leading apostrophe) in every CSV writer, via one shared helper. Apply it to `original_filename` and to any other user-controlled string. Add a test exporting a document named `=1+1`.

### 8.14 `partner_id` is never validated against the company or tenant

`employees.py:202-215` (`create_entrepreneur_hours_entry`) tenant-checks the company via `_get_company_or_404` (`:204`) but writes `partner_id=payload.partner_id` (`:207`) with **no check that the Partner belongs to that company or tenant**. An `accountant` in tenant A can create an hours entry under their own company carrying a `partner_id` from tenant B.

All read paths filter by `company_id` first (`employees.py:219-222`, `hours_service.py:65-70`), so this does **not** leak tenant B's data back. The impact is referential integrity: a dangling cross-tenant FK value that silently mis-attributes urencriterium hours and will never reconcile against `legal_forms.list_partners`. Compare `payroll.py:96-98`, which correctly validates the analogous `employee_id` against the run's company.

**Fix.** Resolve the `Partner`, 404 unless `partner.company_id == company_id`, mirroring the payroll pattern. Add a DB-level composite FK or a CHECK where practical.

### 8.15 `invite_employee_self_service` creates a user and password with no audit log

`employees.py:101-127`, `require_admin`. This is **the only endpoint in the codebase that creates a `User` row, sets a password, and links it to an `Employee` record** — and it writes no `AuditLog`. The comparable `accept_user_invitation` (`users.py:178-182`) does log, as do 40 other call sites.

Compounding this, §4.6 shows the endpoint has **no frontend caller at all**, so the only way to create an employee-role account is a hand-crafted API call that leaves no trace. For a system whose stated GDPR position is that every security-relevant action is audited (`docs/gdpr-data-governance.md`), that is a gap in exactly the wrong place.

**Fix.** Add an `AuditLog` row (`action="employee_self_service_invited"`, `entity_type="employee"`) with `redact()` applied.

### 8.16 Case-sensitive email uniqueness contradicts the codebase's own stated invariant

`deps.py:15-30` documents `find_user_by_email` as *"the one place this comparison happens, used by every endpoint that looks a user up by an email address someone typed (login, password reset, invitation/signup uniqueness checks)"*. **Four call sites do not use it** and compare case-sensitively:

| Site | Query |
|---|---|
| `users.py:89` | `User.email == payload.invited_email` (invitation uniqueness) |
| `users.py:159` | same, in `accept_user_invitation` |
| `employees.py:110` | same, in `invite_employee_self_service` |
| `auth.py:191` | `User.email == payload.email` in `request_password_reset` |

`login` (`auth.py:47-52`) and `get_current_user` (`deps.py:29`) *do* normalise. The Postgres unique index on `users.email` (`models/user.py:22`) is **case-sensitive**, so inviting `victim@corp.com` when `Victim@Corp.com` already exists passes the guard at `users.py:89` and the `INSERT` at `:161-164` succeeds, producing two rows differing only in case. `find_user_by_email` then does `func.lower(User.email) == normalized` with `.first()` and **no deterministic `ORDER BY`** — which row a subsequent login resolves to is unspecified, and the attacker controls the shadow row's password.

This is a plausible impersonation path. **I could not confirm from the code alone** whether any collation or index in the migrations makes differently-cased emails collide at the DB level, so I am flagging the mechanism, not asserting a confirmed exploit (§13.3). The `auth.py:191` instance is availability-only: a user who types different casing silently receives no reset, behind an unconditional 204.

**Fix.** One normalisation rule applied at write time (§7.10), a unique index on `lower(email)` (or `citext`), a deterministic `ORDER BY id` on any `.first()` lookup, and a test asserting that inviting an alternate-case spelling of an existing address is rejected.

### 8.17 `Employee.linked_user_id` has no unique constraint

`models/employee.py:42` — the model has no `__table_args__` and no `unique=True` anywhere. `get_current_employee` (`deps.py:115`) uses `.first()` with no `ORDER BY`, so if two `Employee` rows ever share a `linked_user_id`, employee self-service resolves to an arbitrary one — potentially showing one employee another's payslips.

Currently prevented only by application logic: `employees.py:109-110` rejects relinking an already-linked employee, and each invite creates a fresh `User`. Unenforced at the schema level.

**Fix.** `UniqueConstraint("linked_user_id")` (partial, `WHERE linked_user_id IS NOT NULL`) plus a deterministic `ORDER BY`.

### 8.18 Unauthenticated write on `GET /billing/plans`

`billing.py:19-22` — no auth dependency, calls `subscription_service.ensure_plans_seeded(db)` then `db.commit()`, and is not rate-limited. Idempotent in effect, but it is an unauthenticated request that performs a database write and commit on every call. It is also the only one of the 6 unauthenticated routes that is not a credential or webhook endpoint (§13.5).

**Fix.** Seed plans at application startup or in a migration; make the endpoint a pure read.

### 8.19 Unvalidated `kvk_number` interpolated into an upstream URL path

`kvk.py:20` declares `kvk_number: str` with no pattern constraint, and it is interpolated at `kvk_provider.py:70`:
```python
httpx.get(f"{self._base_url}/basisprofielen/{kvk_number}", …)
```
`base_url` comes from operator config (`config.py:52`) or the hardcoded sandbox constant — never from a request — so **this is not SSRF** ✓. But percent-encoded delimiters in the path segment (`%3F`, `%23`, `%26`) survive Starlette routing and would let a caller append or override query parameters on the request sent to KVK. KVK numbers are 8 digits; nothing enforces that.

**Fix.** `kvk_number: str = Path(pattern=r"^\d{8}$")`, and add the rate limit from §7.20.

### 8.20 Latent open redirects in the stub providers

`open_banking_provider.py:84` returns `f"{redirect_uri}?stub_consent_id={consent_id}"` where `redirect_uri` is caller-supplied (`banking.py:265` → `open_banking_service.py:26-27`) with no allowlist; `billing_provider.py:77` embeds `success_redirect` (`billing.py:44`) unencoded. **Both are returned in a JSON body, not issued as HTTP redirects**, so neither is an open redirect today — but both become one the moment a real provider is wired and the value is used for a `302`.

**Fix.** Allowlist redirect targets against a configured set of origins now, before the stubs are replaced.

### 8.21 Password-reset tokens are not revoked on re-request

`auth.py:191-196` inserts a new `PasswordResetToken` without expiring that user's prior unused tokens, so N requests leave N concurrently valid 30-minute tokens. Bounded by the rate limiter and by expiry, but a wider window than necessary. `/password-reset/confirm` is also the only unauthenticated state-changing endpoint with no rate limiter (immaterial at 256 bits, but inconsistent).

**Fix.** Mark prior unused tokens `used_at = now` (or `revoked`) on each new request.

### 8.22 Stale reference to a module that was never written

`models/user.py:56` states the platform admin "can see cross-tenant subscription/usage/system-health data (**`app.api.v1.admin`**)", and `billing.py:105` repeats it. **There is no `admin.py` anywhere under `backend/app`** ✓ (`ls app/api/v1/*.py` → 28 files, none named `admin`). The functionality lives in `billing.py:103-124` at `/billing/admin/overview`. The functional claim holds; the pointer is wrong, and a reader looking for the platform-admin surface would not find it.

Also: `open_banking_service.py:30` sets `bank_account.provider_account_id = consent.consent_id` with the comment *"placeholder until `complete_connection` resolves the real account id"*. Between `connect` and `callback` the column holds a consent id rather than an account id. Self-documented and transient, but a reader of `BankAccount` cannot tell which it holds — worth a distinct column or a status flag.

Otherwise the marker sweep is clean: `grep -rn "TODO|FIXME|XXX|HACK|NotImplementedError|not implemented|placeholder"` over `backend/app` returns **9 hits — zero `TODO`, zero `FIXME`, zero `NotImplementedError`**. Five are the secret-default warnings at `config.py:85-111` (§6.4); one is a deliberate and correct honest-status string at `tax_centre.py:122` (`NOT_CONFIGURED` for SBR/Digipoort, with `NOT_TRACKED` for ICP/OSS and `NOT_FILED` for income/corporate tax — genuinely absent functionality, correctly labelled, not faked); two are historical notes describing a *corrected* former placeholder Zvw rate (5.65% → 6.51%) at `payroll_engine.py:25` and `dutch_tax_rules.py:43`; one is the `open_banking_service.py:30` interim state above.

---

## 9. Test suite assessment

### 9.1 Inventory ✓

AST count of functions named `test_*`, excluding `@pytest.fixture`:

| Point in time | Files | Test functions |
|---|---|---|
| Working tree (now) | 62 | **540** |
| `HEAD` (`97f2d84`, Phase 16.3) | 61 | 539 |
| `a09cfa1` (last Phase 9 commit) | 41 | **358** |
| `d05e49f` (last Phase 8 commit) | 31 | **281** |
| `fa85fa9` (last Phase 6 commit) | 23 | **205** |

**All three README counts are exactly accurate for the phase they were written.** `README.md` was last modified 3 Nov (Phase 9) and never updated for Phases 10–16, so the 358 figure is stale rather than dishonest — 182 tests have been added since. Collected items ≈ 542 (one `@pytest.mark.parametrize` at `test_payroll_validation.py:45` with 3 cases). 1,318 assertions = 2.44/test. Parametrisation is essentially unused across 540 tests.

Naming hazard: `conftest.py:46` defines a **fixture** called `test_session_local`. Pytest does not collect it, but it inflates naive `grep -c "^def test_"` counts and will confuse future tooling.

### 9.2 Fixture architecture

**Correct on the two things that matter most.**
- **Real Postgres, same dialect as production** ✓ — `conftest.py:32` derives a sibling `onholland_accounting_test` from `DATABASE_URL`. `Numeric`/`Decimal`, JSON columns, native enums and collations all behave as in production. The SQLite-hides-bugs concern does not apply.
- **`autoflush=False` genuinely matches production** ✓ — `conftest.py:51` vs `app/db/session.py:7` (`autocommit` defaults to `False` in SQLAlchemy 2.0, so they are equivalent). The Phase 6 bug that motivated this has a real regression guard: `test_matching_engine.py:159` does `db_session.refresh(bank_tx); assert bank_tx.reconciliation_status == matched`, which fails if the explicit `db.flush()` in `reconciliation_service._refresh_bank_transaction_status` is removed. That is a well-executed fix-and-guard.

**Weaknesses.**
- **Migrations are never exercised** (§7.14) — `create_all` builds the model schema, so tests run without the 54 Phase-10 indexes.
- **The app and the assertions share one session.** `conftest.py:96-98`'s `override_get_db` yields *the same* `db_session` the test holds, so the app's uncommitted in-memory state is visible to assertions. This masks "forgot to commit" bugs that would break in production, where each request gets a fresh session.
- **Isolation is DELETE-based, not transactional** (`conftest.py:54-63`), with **no sequence reset**. Autoincrement IDs climb for the whole session. Currently benign — zero hardcoded-PK assertions found — but any future test asserting a specific ID becomes order-dependent.
- **No pytest configuration anywhere.** No `pytest.ini`, `pyproject.toml`, `setup.cfg` or `tox.ini`. No `testpaths`, no `addopts`, no marker registration, no `--strict-markers`. Both `import app` and `config.py`'s `env_file = ".env"` resolve against CWD, so **the suite's behaviour silently depends on being invoked from `backend/`** — which is what causes §7.13.
- `LEGAL_FORM_SEED_ROWS` is inserted by hand in conftest *and* by the Phase 9 migration, with nothing asserting they agree.
- `tmp_storage` (per-test `mkdtemp`, monkeypatched `settings.storage_root`, `rmtree` teardown) ✓ and `_reset_rate_limits` (autouse, clears the module-global `_buckets` before *and* after each test — necessary because `TestClient` always reports the same client host) ✓ are both correct.

### 9.3 Determinism and non-hermetic tests

**Unusually deterministic on the classic axes.** Grep across all of `tests/` for `datetime.now(`, `date.today(`, `utcnow`, `time.sleep`, `random.` → **9 hits total**, all safe: three `date.today() - timedelta(days=30)` for deliberately stale data, one `+ timedelta(days=15)`, one `date.today().year + 5` for a permanently-future financial year, and four `time.sleep` sites that are **fully monkeypatched** — two with `lambda s: pytest.fail("should not sleep…")` to assert no backoff occurs. No `random` anywhere. Zero hardcoded-PK assertions. Hardcoded years are dominated by 2027 (×204) and 2026 (×165), which do not rot because a `FinancialYear(year=2027, …)` is valid forever; `test_backend_message_locale.py:75` uses FY 2020 specifically so its VAT period is permanently overdue — also correct.

**Two non-hermetic dependencies.**
1. `test_kvk_integration.py:25` performs a **live HTTPS request at module import time**: `skip_if_unreachable = pytest.mark.skipif(not _sandbox_reachable(), …)` where `_sandbox_reachable()` calls `httpx.get("https://api.kvk.nl/test/…", timeout=5.0)`. This runs on every pytest invocation during collection, before any deselection — `pytest -k unrelated` still triggers it. Offline runs stall up to 5s and every local run phones home to a third party. The 5 network tests do assert real values (`result.kvk_number == "90003942"`, `body["name_matches"] is True/False`), but they silently degrade to zero coverage whenever the sandbox is down. The API key is KVK's own published sandbox key, so this is not a secret leak ✓.
2. The two Anthropic leaks at §7.13.

**Fix.** Move the KVK reachability check into a session-scoped fixture or gate it behind an explicit `-m integration` marker excluded from the default run. Add `pytest.ini` with `testpaths`, `addopts = -ra --strict-markers`, registered markers, and an `env` override that forces `ANTHROPIC_API_KEY=""` and a dedicated test `DATABASE_URL` regardless of the ambient `.env`.

### 9.4 Coverage gaps

**No coverage tooling and no CI.** `pytest-cov`/`coverage` appear in neither `requirements.txt` nor the venv; no `.coveragerc`, no `[tool.coverage]`. A repo-wide search for CI configuration returns exactly two YAML files — `docker-compose.yml` and `docker-compose.prod.yml`. No `.github/`, `.gitlab-ci.yml`, `.circleci/` or `Jenkinsfile`. **True line/branch coverage is unknowable from this repository**, and nothing runs these 540 tests automatically. Every "all passing" claim in the README and phase docs is a manual, unrecorded assertion.

**29 of 217 endpoints are never called by any test.** The worst is `financial_reports.py` — **13 of 21**:

```
GET /financial-reports/cash-flow-statement      GET /financial-reports/working-capital/trend
GET /financial-reports/trial-balance            GET /financial-reports/working-capital/cash-conversion-cycle
GET /financial-reports/general-ledger           GET /financial-reports/working-capital/customer-concentration
GET /financial-reports/creditors                GET /financial-reports/working-capital/supplier-dependency
GET /financial-reports/vat-overview             GET /financial-reports/working-capital/customer-payment-behavior
GET /financial-reports/revenue-breakdown        GET /financial-reports/working-capital/supplier-payment-trends
GET /financial-reports/expense-breakdown
```

Important nuance: the underlying **engine** functions *are* well tested — `cash_flow_statement`, `trial_balance`, `debtors`, `revenue_breakdown` all have exact-value unit tests in `test_financial_reports.py`, and `working_capital.py` is covered by `test_kpi_and_working_capital.py`. What is untested is the **API layer**: auth guards, query-parameter validation, `company_id` scoping via `require_company_access`, `Decimal`→string serialisation, and PDF/XLSX/CSV format switching. Given that this file's cross-tenant tests cover only 2 of 21 endpoints, that is a real isolation-coverage hole — and it sits directly on top of §6.7(a) and §7.1/§7.2/§7.3.

Remaining untested endpoints: `assistant.py` (3 of 6 — `POST /assistant/ask`, `GET /assistant/missing-documents`, `GET /assistant/period-comparison`), `banking.py` (2 of 16), `billing.py` (`GET /billing/plans`, `POST /billing/cancel`), `budgets.py` (`/revise`, `/history`), `employees.py` (`/timesheet-entries/{id}/reject`, `/employees/{id}/hours-summary`), `employee_self_service.py` (`GET /me/annual-statement/pdf`), `legal_forms.py` (`POST`/`GET /shareholders`), `tax_centre.py` (`GET /tax-centre/corporate-tax-estimate`), `transactions.py` (`PATCH /transactions/{id}/line-items/{line_item_id}`).

Routers with **zero** untested endpoints: `audit_log`, `auth`, `automation`, `batches`, `companies`, `dashboard`, `documents`, `forecasts`, `kvk`, `loonheffingen`, `payroll`, `reports`, `tax_calendar`, `users`, `vat_returns`, `workspace`.

**Role-denial breadth.** Of **102 mutating endpoints**, 62 have at least one 4xx denial assertion nearby and **40 have none**. Guard distribution: 62 behind `require_editor`, 11 `require_admin`, 6 `require_editor_or_owner`, 2 `require_uploader`, 14 bare `get_current_user` — yet the whole suite contains only **45 `== 403` assertions**, concentrated in `users`, `companies` and `documents`. Untested-for-denial surfaces include all automation mutations (`/categorize`, `/apply-categorization-rules`, `/detect-recurring`, `/detect-anomalies`, `/anomalies/{id}/acknowledge|dismiss`), all five reconciliation mutations, all four timesheet mutations, `/payslips/{id}/correct`, `/transactions/{id}/payments`, `/shareholders`, `/partners`, `/budgets/{id}/revise`. (This is a path-proximity heuristic with known false positives — treat 40 as an upper bound on the gap and 62/102 as a lower bound on coverage.)

**Cross-tenant isolation IS tested** — this corrects a concern I held going in. `Tenant(` appears in 43 test files; **20 tests create a genuine second tenant** and 16 are explicitly named isolation tests spanning documents, bank accounts, transactions, employees, users, audit log, batches, reports, tax centre, notes, assistant and automation. `test_documents_api.py:193` checks three vectors (GET detail → 404, GET `/file` → 404, absent from listing) and correctly asserts **404 rather than 403** so existence is not leaked. Status-code totals: 45 × 403, 20 × 404, 6 × 401, 11 × 400, 4 × 422, plus 409, 423 and 429. For a four-day codebase that is a serious negative-testing effort, and `docs/production-readiness.md`'s "Extensively tested" is fair — the gap is breadth over the endpoint surface, not concept.

Two test names over-promise: `test_banking_api.py:211 test_viewer_cannot_import_or_approve` asserts 403 on `/import` only and never calls `/payment-matches/{id}/approve`; `test_documents_api.py:217 test_viewer_cannot_upload_or_approve` asserts 403 on `/upload` only. `UserRole.employee` is never constructed as a literal but *is* exercised properly through the real `invite-self-service` flow, with `test_employee_self_service_api.py:143-145` asserting 403 for an employee hitting `/employees`, `/employees/{id}` and `/companies/{id}/financial-years` ✓.

### 9.5 Assertion quality

Much stronger than expected for the timeline. Classification of all 540 tests:

| Category | Count | Assessment |
|---|---|---|
| Zero `assert` statements | 23 | **All 23 use `pytest.raises`** — legitimate. Zero tests have neither. |
| Every assertion is 2xx / bare truthiness / `is not None` | **5** | Genuinely weak (below) |
| Every assertion is 4xx only | ~71 | **Not weak** — for an authorisation test, `assert resp.status_code == 403` *is* the complete assertion |
| All value assertions relational (`>`, `<`, `in`) | 44 | Mixed; ~9 numeric monotonicity-only are weak |

**The strong core is genuinely strong.**
- `test_vat_engine.py` — 16 tests, every one asserting exact box values (`totals.box_1a_net == Decimal("100.00")`, `net_payable == Decimal("126.00")`), covering credit notes, multi-rate splits, reverse charge, EU acquisition, partial eligibility, FX conversion, out-of-period exclusion and the approved-return immutability guard.
- `test_dutch_tax_rules.py` — 27 tests with expected values **recomputed in the test** from published rates (`expected = Decimal("38441") * Decimal("0.3582") + (income - Decimal("38441")) * Decimal("0.3748")`). `test_special_remuneration_tax_matches_official_worked_example` pins `Decimal("1021.44")` and cites the source PDF.
- `test_financial_reports.py` — 20 tests with the arithmetic shown in comments (`# ebitda = gross_profit - opex - personnel - uncategorized = 600 - 60 - 100 - 30 = 410`). `test_balance_sheet_flags_imbalance_from_vat_not_yet_booked` asserts `is_balanced is False` and `imbalance_amount == Decimal("105.00")` — **a test that requires the code to report failure correctly**, the opposite of a smoke test.
- `test_data_integrity.py:44 test_monthly_pnl_sums_reconcile_to_annual_pnl` — sums 12 monthly P&Ls and asserts equality with the annual figure *and* with `Decimal("1200.00")`. A real cross-check invariant.
- `test_user_management.py` — 25 tests, the best negative-testing file in the suite: self-escalation, admin-cannot-grant-owner, last-owner protection (409), token-version revocation verified by re-using the pre-deactivation token, invitation replay (409), and a route-shadowing regression test at `:199` documenting a bug found by manual testing.

**Tests that cannot fail.**
1. `test_tax_optimization_and_structure.py:76-79` — **the weakest in the suite**:
   ```python
   result = structure_comparator.compare_structures(assumptions)
   assert "never" in result["disclaimer"].lower() or "not" in result["disclaimer"].lower()
   ```
   `disclaimer` is a hardcoded literal at `structure_comparator.py:83-89` containing both words four times over. The test compares a constant to itself.
2. `:63-73 test_structure_comparison_runs_all_three_structures` — `assert result["lowest_total_tax_option"] in ("eenmanszaak", "vof", "bv")` where `lowest_total_tax_option` is computed at `:80` as `min([...])` over exactly those three keys. Tautological. The other assertions are `> 0`, so a BV/eenmanszaak comparison off by an order of magnitude passes.
3. `test_data_integrity.py:88-107 test_locked_transaction_figures_are_immutable_so_past_reports_stay_reproducible` — sets `approval_status = locked`, reads the report, refreshes, asserts the amount is unchanged. **Nothing ever attempts a mutation.** Its own docstring concedes enforcement lives in `api/v1/transactions.py` and is "verified at the API layer" — but no such API test exists (`PATCH /transactions/{id}/line-items/{line_item_id}` is untested, §9.4).
4. `test_data_integrity.py:110-141 test_duplicate_bank_import_never_doubles_reported_cash_position` — inserts **one** bank transaction and asserts `cash_and_bank == Decimal("500.00")`. The comment admits it: *"Simulate the dedupe guarantee directly…"*. It tests that the sum of one row equals that row, and passes identically whether `dedupe_hash` enforcement exists or not.
5. `test_e2e_acceptance_scenarios.py:225-238` (Scenario F tail) — for a scenario whose stated purpose is manual entries "flowing through to P&L, **balance sheet, and the KPI engine**", it asserts `pnl.json()["current"]["revenue"] == "1000.00"` and then only `balance_sheet.status_code == 200` and `kpis.status_code == 200`. The two named outputs are never inspected, in the file that is supposed to be the end-to-end safety net.
6. `test_management_report_exports.py:46-59` — loops pdf/xlsx/csv asserting only status 200, content-type prefix and `len(content) > 0`. A report of entirely wrong numbers, or a corrupt-but-nonempty PDF, passes. The better pattern exists in the same suite at `test_report_i18n_full.py:190`, which extracts the workbook and asserts cell types and `'EBITDA' in extracted`.
7. `test_auth_security.py:104-118 test_password_reset_full_flow` — never completes the flow (§6.8).
8. Inequality-only payroll engine tests — `test_payroll_engine.py:91/202/218`, `test_payroll_service.py:114`: `high["wage_tax…"] > low["wage_tax…"]`, `flexible["employer_premium_awf"] > permanent[…]`, `near_cap["employer_premiums_total"] < well_under_cap[…]`; `test_monthly_salaried_employee_basic:8` asserts only `net_salary < gross_salary`. Monotonicity survives a wrong rate table, a wrong cap or a wrong bracket boundary. Mitigating: the same quantities *are* pinned exactly one layer down in `test_dutch_tax_rules.py`, so these are redundant-but-weak rather than the sole guard.
9. `test_dutch_tax_rules.py:109 test_arbeidskorting_never_negative_at_high_income` — `assert result >= Decimal("0")`. Passes if the credit is wrongly zero for everyone.
10. One circular assertion in the suite — `test_payroll_engine.py:145-153` computes `expected_special_tax` by calling the same production function under test. Acceptable only because `test_dutch_tax_rules.py:139` independently pins the same value to `Decimal("1021.44")`.

**The two tiny files, in full.**

`test_rate_limit.py` — 9 lines, 1 test. Monkeypatches the limit to 3, makes 3 requests, asserts the 4th is 429. Does **not** cover: that the first 3 were processed (a limiter blocking from request #1 would pass); window expiry; per-client keying; or **3 of the 4 rate-limited scopes** — only `login` is tested, and `rate_limit_upload_per_minute = 30` is never exercised. It also cannot catch §6.9, since `TestClient` reports one constant client host.

`test_health_and_security_headers.py` — 11 lines, 2 tests. Asserts `/health` → 200 `{"status":"ok"}` and three exact header values **on `/health` only**. Does **not** cover: the **failure branch** — the health check is DB-aware, yet nothing asserts 503/`"error"` when the DB is unreachable, which is the only behaviour that matters for a liveness probe; `Content-Security-Policy`, `Strict-Transport-Security`, `Permissions-Policy`, `Cache-Control`; whether the headers apply to non-`/health` routes (both tests hit only `/health`, so a narrowly-mounted middleware would pass); CORS configuration; or the two custom `@app.middleware("http")` handlers.

**A retraction worth recording.** `test_batch_upload.py:356`, `test_report_i18n_full.py:113` and `:300` read on screen as `assert resp.content.startswith("".encode("utf-8"))`, which would be always-true and would mean the Phase 16.3 CSV-BOM work is unguarded. **This is a false positive.** Codepoint inspection shows a literal invisible U+FEFF inside the string (`repr` → `'startswith("\ufeff".encode("utf-8")'`, codepoints `0x22, 0xfeff, 0x22`). All three BOM assertions are correct. It is flagged only as a maintainability hazard: an invisible BOM in source will be misread by reviewers and editors.

### 9.6 Frontend tests

| Suite | Content | Gap |
|---|---|---|
| vitest (jsdom) | **53 static blocks / 9 files**, ≈68 runtime cases after `it.each` expansion | **Zero tests for any of the 55 route components.** None for `auth-context`, `company-context`, `theme-context`, `AuthGuard` or `Shell`. **None for `lib/api.ts`** — 1,513 lines, the largest file in the frontend. No coverage configuration or threshold exists. |
| Playwright | `e2e/i18n.spec.ts`, 348 lines, **16 tests** | Visits **5 distinct routes of 55 (9%)**: `/`, `/login`, `/settings`, `/users`, `/audit-log`. The 50 untested routes include every financial report, the whole VAT flow, document upload/review, banking, reconciliation, payroll, loonheffingen, budgets, scenarios, KPIs, working capital, tax centre and all 6 dynamic detail routes. |
| axe-core | `test/axe.ts`, invoked from 4 of 5 component tests | `color-contrast` is **disabled** (jsdom has no layout engine) with an honest 10-line comment. No page-level axe, no Playwright+axe integration — so §7.7 and §7.8 are outside the reach of every check the project runs. |

The 53 unit tests are well chosen for what they cover: `format.test.ts` (17 tests) exercises all four locales; `navConfig.test.ts` enforces "real route XOR marked unavailable" and that every `unavailableKey` resolves in `nl.json`; `parity.test.ts` guards the four dictionaries; `GlassModal` tests the focus trap. The Playwright suite's `expectNoConsoleErrors` helper (`:38-45`) is genuinely valuable — its header comment credits it with catching a real `t.rich()` misuse that surfaced as "Functions are not valid as a React child", missed by TypeScript, ESLint and vitest alike. That is a credible and specific claim, and exactly the class of defect only a browser finds.

**The Playwright suite cannot run in CI as configured.** `playwright.config.ts` has **no `webServer` block** and documents that both a backend (`uvicorn … --port 8010`) and a frontend dev server must already be running against a seeded dev database. `e2e/i18n.spec.ts:28-30` hardcodes credentials (`mollie-visual@example.com` / `VisualTest!23`) and mutates server state directly via `page.evaluate` + `fetch(PATCH /auth/me/locale)` to work around the app's own "saved preference beats cookie" rule. `@playwright/test ^1.64.1` **and** a redundant `playwright ^1.64.1` are both in `devDependencies`.

`docs/ui-accessibility-audit.md` claims "68/68 vitest + axe-core tests passing"; 53 static blocks expanding to ≈68 via `it.each` is entirely consistent, so the claim is plausible — but it was never independently verified here, and no CI record exists.

---

## 10. Git and working-tree review

### 10.1 Branch topology

```
main                                        d05e49f  Phase 8   ← 81 commits behind HEAD
 └─ phase-9-full-platform
     └─ phase-10-compliance-production
         └─ phase-11-glassmorphism-ui
             └─ phase-11.1-ui-quality
                 └─ phase-12-complete-platform-infrastructure
                     └─ phase-13-production-accounting-intelligence
                         └─ phase-14-complete-commercial-platform
                             ├─ phase-14-mollie-ui-transformation
                             │   └─ phase-14-mollie-ui-completion
                             └─ phase-15-access-governance-audit
                                 └─ phase-16-internationalisation
                                     └─ phase-16-1-translation-pdf-completion
                                         └─ phase-16-2-i18n-finalisation
                                             └─ phase-16-3-complete-internationalisation  ← HEAD 97f2d84
```

- **88 commits, 2026-11-02 → 2026-11-05.** All 15 branches are merged into HEAD; history is linear with no merge commits.
- **`main` is 81 commits behind**, at Phase 8. `git diff main..HEAD --stat` → **291 files changed, 38,760 insertions, 5,413 deletions.**
- **There is no git remote.** `git remote -v` is empty. The entire repository — 88 commits, ~36k lines — exists only on this machine. There is no backup, no offsite copy, and no way for anyone else to review or contribute.
- Every phase document states "Not merged into main. Not deployed. No production data touched." That is accurate and consistent.

**Consequence.** There is no stable, reviewed baseline. Nothing has ever passed through a pull request, a review gate, or a merge check. `main` at Phase 8 predates MFA, access governance, company invitations, billing, the entire i18n layer and the Mollie UI — so the branch that would conventionally be deployable is eight phases behind the code that actually exists. The linear stacked-branch structure means a mistake in any phase propagates to all fifteen descendants with no isolation.

**Fix.** Add a remote today and push — this is the highest-effort-to-value ratio item in the entire report. Fast-forward `main` to HEAD (or to the last commit you consider stable), and adopt a merge/PR gate with required CI. Retire the phase branches; they have served their purpose and now obscure the topology.

### 10.2 Secret history scan

`git log --all -- backend/.env` → **empty**. `.env` was never committed ✓. A `-S "change-me-in-production"` pickaxe search across all history returns nothing. `git check-ignore -v backend/.env` confirms `.gitignore:5` covers it ✓. `backend/storage/` is untracked ✓. **No secret has ever entered git history.** That is a clean result and worth stating plainly.

The exposure at §6.4 is not a history leak — it is hardcoded defaults in tracked source, which is a different and in some ways worse problem, because it is invisible to secret scanners that only look for high-entropy strings in diffs.

### 10.3 The uncommitted change

Five modified files, 59 insertions, 4 deletions. Reviewed in full at §7.10 (email normalisation), §8.1 (CORS) and §6.12 (RTL fonts). Summary:

| File | Change | Verdict |
|---|---|---|
| `core/deps.py` | New `find_user_by_email` helper, used by `get_current_user` | Right diagnosis (case-sensitive login was a real, silent 401), wrong implementation — defeats the email index on every request, and is not actually the single source of truth |
| `api/v1/auth.py` | Login normalises email | Correct fix, but duplicates the helper with divergent `trim()` semantics |
| `tests/test_auth_security.py` | One new test | Covers login only; not `get_current_user`, not password reset, not invitation acceptance |
| `main.py` | CORS default widened to include a LAN IP | **Revert.** Local debugging convenience in a security-relevant default |
| `frontend/app/globals.css` | The entire RTL font feature | **Commit.** This is §6.12 — the headline deliverable of Phase 16.3 is not in Phase 16.3 |

Plus three untracked backup files (§8.1).

**Recommendation.** Split this into three commits: (1) the email-normalisation fix, done properly per §7.10 with tests for all three lookup paths; (2) the RTL font CSS, with an e2e assertion on computed `font-family`; (3) delete the backups and revert the CORS default. Do not commit them as one.

---

## 11. Recommended improvements

### 11.1 Verification infrastructure (do this first)

Everything in §6 and §7 is a defect that **some ordinary piece of CI would have caught**. The absence of verification, not the absence of skill, is the root cause.

1. **Add a git remote and push.** §10.1. Non-negotiable and takes five minutes.
2. **Stand up CI** running, on every push and PR:
   - `alembic upgrade head` → `downgrade base` → `upgrade head` against a scratch Postgres (§7.14)
   - `alembic revision --autogenerate` failing if the output is non-empty — enforces model/migration parity and immediately surfaces the 54 undeclared indexes
   - `pytest` against a **migration-built** schema, with `ANTHROPIC_API_KEY=""` forced by config (§7.13), `-m "not integration"` by default, and a separate nightly job for the KVK network tests
   - `pytest --cov` with a ratchet threshold (start at whatever today's number is; never let it fall)
   - `ruff check` + `ruff format --check` + `mypy` on `backend/app`
   - `tsc --noEmit`, `npm run lint`, `npm run build`, `npm run test`, `check-translation-parity`
   - `pip-audit` and `npm audit --audit-level=high`
   - `gitleaks` secret scanning
   - **A container smoke test**: build both images, start the stack, load the built frontend in a headless browser, and assert no request goes to `localhost:8000` (§6.10). This one check catches a defect class that no unit test can.
3. **Add a `pytest.ini`** with `testpaths`, `addopts = -ra --strict-markers`, registered markers, and forced env overrides so the suite no longer depends on CWD or the ambient `.env`.
4. **Add backend linting and typing.** No ruff/black/mypy exists. `strict` typing is already enforced on the frontend; the backend has none.

### 11.2 Correctness

5. Wire `VatPeriod.status` (§6.1) — the single highest-value functional fix.
6. Fix cash-based VAT period assignment (§6.2) and delete the dead import.
7. Filter every calculation by `approval_status` (§6.3) and decide what `DRAFT` means.
8. Add FX awareness to the reporting layer (§7.1) via one shared helper.
9. Fix `ManualBalanceSheetItem` semantics (§7.2) — choose movements or latest-balance and enforce it.
10. Replace `previous_period()` day arithmetic with `relativedelta` (§7.3).
11. Add the missing unique constraints and composite indexes (§6.6, §8.7, §7.18).
12. Make `GET /vat-returns` read-only and audit the recompute path (§7.9).
13. Add `Field(gt=0)` to `PaymentCreate.amount` (§8.8).
14. Surface unreachable VAT boxes and prompt for classification (§7.11).

### 11.3 Security

15. **Fail closed on insecure defaults** (§6.4) — raise at import outside `dev`, remove the literals, rotate all four burned secrets, and add the three missing variables to both `.env` examples.
16. Add 2026 tax rules and make the default year clock-derived, with a test designed to fail annually (§6.5).
17. **Fix the seven cross-tenant endpoints now** (§6.7): add `tenant_id` checks to `companies.py:196` (`_get_financial_year_or_404`), `companies.py:184` (`list_financial_years`), `companies.py:306`/`:317` (invitations), `banking.py:242` (`bulk_approve_high_confidence`) and `workspace.py:102` (`list_notes`). Each is a one-to-three-line change and two of them are cross-tenant **writes**.
18. **Wire `logout()` to `POST /auth/logout`** (§6.13). One line; removes a 24-hour window on every stolen token.
19. Require step-up authentication to replace an enrolled MFA secret (§6.11).
20. Fix the rate limiter for proxied deployments, bound `_buckets`, split the shared `"upload"` scope, and limit `/kvk/lookup` (§6.9, §7.20).
21. Make password reset actually work, and test its happy path (§6.8, §4.6).
22. **Centralise tenant enforcement in `require_company_access`** (§6.7a) — load and return the company, compare `tenant_id` for *all* roles. Then add a test that enumerates every route taking a resource identifier and asserts it resolves through the helper, so the seven omissions cannot recur.
23. Choose and implement one multi-company access model (§6.7b, HIGH-4), which also delivers per-company roles and fixes the orphaned cross-tenant invitation feature.
24. **Harden XML parsing**: `defusedxml`, reject `DOCTYPE`, pin the Python version, add a billion-laughs test (§7.19).
25. **Neutralise CSV formula injection** in every CSV writer via one shared helper (§8.13).
26. **Normalise email at write time**, add a unique index on `lower(email)`, add deterministic `ORDER BY` to every `.first()` lookup, and fix the four case-sensitive call sites (§7.10, §8.16).
27. Add `reencrypt_*` and a rotation script for the Open Banking and MFA keys; correct `encryption-key-rotation.md` (§7.5).
28. Shorten token lifetime, add a refresh token, move off `localStorage`, add 401 interception (§7.17).
29. Replace `python-jose` and `passlib`; split dev from prod requirements; enforce a password length ceiling (§7.16, §8.2).
30. Record text truncation and add a first-payee control (§7.15).
31. Add the missing audit log to `invite_employee_self_service`; validate `partner_id` against the company; add `UniqueConstraint(linked_user_id)`; make `GET /billing/plans` a pure read; allowlist redirect targets; validate `kvk_number`; revoke prior reset tokens on re-request (§8.14–§8.21).
32. Fix `storage.read()` to use `is_relative_to` (§8.9); stream uploads and cap zip expansion (§8.10).
33. Harden backups: fail-closed restore guard, `chmod 600`, encryption, retention, off-host copy (§7.12).
34. Route all audit snapshots through `redact()`, stop persisting free-text note bodies verbatim, and test it (§8.3).
35. Correct the stale `app.api.v1.admin` references in `models/user.py:56` and `billing.py:105` (§8.22).

### 11.4 Performance and scalability

36. Add `selectinload` to the AR/AP and GL queries — one line, large win (§7.4).
37. Push aggregation into SQL; stop materialising whole histories in Python.
38. Paginate AR/AP item lists and `/billing/admin/overview`.
39. Add `pool_pre_ping=True` and explicit pool sizing to `create_engine` (§7.6).
40. Seed a 50k-transaction benchmark dataset and record baseline timings, so regressions are visible.

### 11.5 Frontend

41. Fix the build-time API URL (§6.10) — preferably via a same-origin rewrite so it cannot recur.
42. Commit the RTL font CSS and add the computed-`font-family` e2e assertion (§6.12).
43. Replace the 228 hardcoded palette colours with semantic tokens; extend `contrast-check.py` or, better, run axe with `color-contrast` enabled in a real browser in both themes (§7.7).
44. Add 401/403 interception and move `AuthGuard` into `app/layout.tsx` (§7.17).
45. Actually use `CompanyProvider`; delete the 38 duplicated company fetches (§2.3).
46. Adopt a data-fetching library (TanStack Query or SWR) to get caching, deduplication, retry, abort and refetch-on-focus in one step, replacing ~38 copies of the same `useEffect`.
47. Fix the 24 unassociated labels and add `scope` to table headers (§7.8). Replace the 3 `window.prompt()` calls with the existing, axe-tested `GlassModal`.
48. Translate the 6 hardcoded `aria-label`s, `AuthGuard`'s `Loading…`, and the 7 raw enum renderings — starting with `kpis/page.tsx:32` (§4.5).
49. Add route-level tests. Zero of 55 routes has one.
50. Replace `frontend/README.md` (unmodified `create-next-app` boilerplate) and populate `frontend/AGENTS.md` with real conventions.
51. Fix `next.config.ts:12`'s committed LAN IP; use an env var.
52. Split `lib/api.ts` (1,513 lines) by domain, and generate the interfaces from the OpenAPI schema rather than maintaining ~750 lines by hand. Add the missing `typecheck` script the docs already reference.

### 11.6 Product surface and process

53. **Wire the 6 orphaned endpoints** (§4.6) — the line-item VAT-eligibility override and the employee self-service invite are correctness- and capability-gating, not cosmetic.
54. **Consolidate the duplicated report/dashboard/forecast endpoints** (§2.7) behind one authorisation path, so a tenant check or an `approval_status` filter can only be written once.
55. **Commit the original phase briefs.** No specification exists in the repository (§5), so "done" is unfalsifiable.
56. Update `README.md` — it stops at Phase 9 and understates the test count by 182.
57. Correct the documents this audit found to be factually wrong: `production-readiness.md` (Docker images, tenant isolation, session revocation, password reset), `security.md` (rate-limiting effectiveness, CSRF/`localStorage` framing, "every company-scoped query goes through `require_company_access`"), `encryption-key-rotation.md` (BSN is not the only encrypted data), `gdpr-data-governance.md` (data export is not user-reachable), and `untranslated-backend-messages-inventory.md` (enum values are *not* all translated by the frontend).
58. Keep the honesty practice. It is the project's best feature. The problem is that claims were verified by their author, manually, once. The fix is a machine that re-verifies on every commit — not less candour.

---

## 12. Prioritised implementation roadmap

Sequenced so that each tier makes the next one safer. Effort is rough and assumes one experienced engineer.

### Tier 0 — Stop the bleeding (before any further feature work)

| # | Item | Ref | Effort |
|---|---|---|---|
| 0.1 | **Patch the seven cross-tenant endpoints.** Two are cross-tenant *writes* (locking a victim's financial year halts their bookkeeping; bulk-approving their payment matches posts to their ledger). Each fix is 1–3 lines. Add a regression test per endpoint using the second-tenant pattern the suite already has. | §6.7 | 1 day |
| 0.2 | **Wire `logout()` to `POST /auth/logout`.** One line; closes a 24-hour window on every stolen or leaked token. | §6.13 | 1 hour |
| 0.3 | **Add a git remote and push everything.** | §10.1 | 15 min |
| 0.4 | **Revert the CORS default; delete the 3 stray backup files; add `*.bak`/`*.backup-*` to `.gitignore`.** | §8.1 | 30 min |
| 0.5 | **Commit the RTL font CSS** — it is the missing deliverable of the current HEAD. | §6.12 | 30 min |
| 0.6 | **Fail closed on insecure secret defaults**; remove the literals from `config.py`; add the 3 missing vars to both `.env` examples. | §6.4 | 0.5 day |
| 0.7 | **Rotate all four burned secrets.** Requires 0.8 first for two of them. | §6.4 | 0.5 day |
| 0.8 | Write `reencrypt_*` + a rotation script for Open Banking and MFA keys; correct the rotation doc. | §7.5 | 0.5 day |
| 0.9 | Set `BSN_ENCRYPTION_KEY` in `backend/.env` and re-encrypt existing rows. | §6.4 | 1 hour |
| 0.10 | **Harden XML parsing** — `defusedxml`, reject `DOCTYPE`, pin the Python version. Three lines plus a dependency; removes an interpreter-version-dependent DoS. | §7.19 | 2 hours |

**Tier 0 total: ~3 days.** After this, no tenant can write to another, no secret is public, logout actually logs out, no local debugging artifact is in a security default, the XML parser is hardened, and the repository has a backup.

**0.1 and 0.2 are the two highest-value hours in this entire report.** Both are trivially small, both are exploitable or impactful today, and neither is visible to any test the project currently runs.

### Tier 1 — Make the numbers right

These produce incorrect statutory or financial figures today.

| # | Item | Ref | Effort |
|---|---|---|---|
| 1.1 | **Wire `VatPeriod.status`**: filed/paid transitions, endpoints, audit log, tests. | §6.1 | 1.5 days |
| 1.2 | **Fix cash-based VAT period assignment** on both payment paths; delete the dead import; add the before/after-payment test. | §6.2 | 1 day |
| 1.3 | **Decide and enforce `approval_status` semantics**; filter every calculation; add the draft-excluded reconciliation line. | §6.3 | 2 days |
| 1.4 | **Add 2026 tax and VAT rule sets**; make the default year clock-derived; add the deliberately-annually-failing test. | §6.5 | 2 days (incl. source verification) |
| 1.5 | **FX-aware reporting** via one shared helper; exclude-and-flag unresolved FX as the VAT engine does. | §7.1 | 2 days |
| 1.6 | **Fix `ManualBalanceSheetItem` semantics** + unique constraint + correction link. | §7.2 | 1.5 days |
| 1.7 | **Fix `previous_period()`** with calendar arithmetic + quarter/leap-year tests. | §7.3 | 0.5 day |
| 1.8 | **Add `UniqueConstraint(source_document_id)`** + `IntegrityError → 409` + concurrency test. | §6.6 | 0.5 day |
| 1.9 | **Make `GET /vat-returns` read-only**; audit the recompute path; single-transaction lock cascade. | §7.9 | 0.5 day |
| 1.10 | `PaymentCreate.amount` `gt=0`; decide and document payment-into-locked-year. | §8.8 | 0.5 day |
| 1.11 | Missing `FinancialYear`/`VatPeriod` uniqueness; `review_status` → enum. | §8.7 | 1 day |
| 1.12 | Surface unreachable VAT boxes; add `vat_treatment` to the line-item PATCH; add the classification-prompt reconciliation finding. | §7.11 | 2 days |
| 1.13 | **Wire the line-item eligibility override into the UI** — without it an accountant cannot resolve `REQUIRES_REVIEW`, so box 5b stays understated no matter how correct the engine is. | §4.6, §7.11 | 1 day |

**Tier 1 total: ~16 days.**

### Tier 2 — Make verification automatic

| # | Item | Ref | Effort |
|---|---|---|---|
| 2.1 | **CI pipeline**: migrations up/down/up, autogenerate-empty gate, pytest on a migration-built schema, coverage ratchet, ruff, mypy, tsc, lint, build, vitest, parity check, pip-audit, npm audit, gitleaks. | §11.1 | 3 days |
| 2.2 | **Container smoke test** — build both images, start the stack, load the built frontend headless, assert no request to `localhost:8000`. | §6.10 | 1 day |
| 2.3 | **`pytest.ini`** with forced env overrides; `-m integration` for the KVK network tests. | §9.3 | 0.5 day |
| 2.4 | **Fix the two Anthropic leaks**: module-qualified import in `automation.py`, fakes in the `client` fixture, session-wide `anthropic_api_key = None` autouse fixture. | §7.13 | 0.5 day |
| 2.5 | **Write the missing tests**: valid-token password reset, locked-transaction mutation *attempt*, real bank-import dedupe, e2e Scenario F balance-sheet/KPI values, report-export content, the 29 untested endpoints (starting with the 13 in `financial_reports`), and denial tests for the 40 uncovered mutating endpoints. | §9.4, §9.5 | 5 days |
| 2.6 | Delete or fix the 5 tests that cannot fail; replace the 10 monotonicity-only assertions with pinned values. | §9.5 | 1 day |
| 2.7 | Frontend route tests — start with the 6 dynamic detail routes and the VAT flow. | §9.6 | 3 days |
| 2.8 | Playwright in CI: add a `webServer` block, remove hardcoded credentials, run axe with `color-contrast` enabled in both themes. | §7.7, §9.6 | 2 days |
| 2.9 | Merge `main` forward; adopt a PR gate with required CI; retire the phase branches. | §10.1 | 0.5 day |

**Tier 2 total: ~16 days.** Tier 2 should overlap Tier 1 — 2.1 and 2.2 in particular should be built *first* and used to verify each Tier 1 fix.

### Tier 3 — Make it deployable

| # | Item | Ref | Effort |
|---|---|---|---|
| 3.1 | **Fix the frontend API URL** (build arg, or better, same-origin rewrite). | §6.10 | 0.5 day |
| 3.2 | **Fix the rate limiter** for proxied deployments; bound `_buckets`. | §6.9 | 1 day |
| 3.3 | **Make password reset work**; choose the delivery mechanism. | §6.8 | 1–3 days |
| 3.4 | **Wire a transactional email provider** (also unblocks invitations and MFA-change notification). | §4.2 | 2 days |
| 3.5 | **MFA step-up** before re-enrolment; add backup/recovery codes. | §6.11, §4.3 | 2 days |
| 3.6 | **Dockerfile fixes**: `npm ci`, multi-stage without devDeps, `output: "standalone"`, direct `node` CMD, split backend requirements, `pool_pre_ping`. | §7.6 | 1.5 days |
| 3.7 | **Harden the backup/restore scripts**: fail-closed guard, `chmod 600`, encryption, retention, `DATABASE_URL` parsing, argument validation; add a scheduled job and off-host copy. | §7.12 | 2 days |
| 3.8 | **Provision TLS and the reverse proxy** per `docs/production-deployment.md`; set `forwarded_allow_ips`. | §4.2, §6.9 | 1–2 days |
| 3.9 | Replace `python-jose` and `passlib`; enforce password bounds; re-evaluate `pandas`. | §7.16 | 2 days |
| 3.10 | Frontend auth hardening: shorter tokens, refresh token, `httpOnly` cookie + CSRF, 401 interception, `AuthGuard` in the layout, `middleware.ts`. | §7.17 | 4 days |
| 3.11 | Add metrics and error tracking (Prometheus + Sentry, or equivalent). | §4.3 | 2 days |
| 3.12 | Neutralise CSV formula injection in every CSV writer via one shared helper. | §8.13 | 0.5 day |

**Tier 3 total: ~21 days.**

### Tier 4 — Make it correct at scale and coherent for multiple companies

| # | Item | Ref | Effort |
|---|---|---|---|
| 4.1 | **Centralise tenant enforcement** in `require_company_access`; add the enumeration test/lint. | §6.7a | 2 days |
| 4.2 | **Implement `CompanyAccess` with per-grant roles**; make cross-tenant delegation actually work; add the end-to-end test. | §6.7b, §4.3 | 5 days |
| 4.3 | **Eager loading + SQL aggregation** across the reporting layer; paginate AR/AP and the platform overview. | §7.4 | 4 days |
| 4.4 | **Composite indexes** on the hot paths; verify with `EXPLAIN ANALYZE` against seeded volume. | §7.18 | 2 days |
| 4.5 | **Declare the 54 indexes in model metadata** so autogenerate is clean. | §7.14 | 1 day |
| 4.6 | **Stream uploads**; cap zip expansion; fix `storage.read()` to `is_relative_to`. | §8.9, §8.10 | 2 days |
| 4.7 | **Truncation flag + first-payee control** for AI extraction. | §7.15 | 2 days |
| 4.8 | Benchmark harness with a 50k-transaction seeded dataset. | §7.4 | 2 days |

**Tier 4 total: ~20 days.**

### Tier 5 — Product and quality

| # | Item | Ref | Effort |
|---|---|---|---|
| 5.1 | Replace 228 hardcoded palette colours with semantic tokens; fix dark-mode contrast. | §7.7 | 3 days |
| 5.2 | Accessibility: 24 labels, table `scope`, live regions, replace 3 `window.prompt()` with `GlassModal`. | §7.8 | 3 days |
| 5.3 | Finish i18n residuals: 6 `aria-label`s, `AuthGuard`, 7 enum renderings (start with KPI names), 16 backend notes. | §4.5 | 3 days |
| 5.4 | Persist validation/anomaly messages as structured code + params; render at read time in the caller's locale. | §4.4 | 4 days |
| 5.5 | Consolidate the 3 translation stores and 4 locale lists into one source of truth. | §4.5, §8.12 | 2 days |
| 5.6 | Adopt TanStack Query; delete the 38 duplicated company fetches; use `CompanyProvider`. | §2.3, §11.5 | 5 days |
| 5.7 | Split `lib/api.ts`; generate interfaces from OpenAPI; add the `typecheck` script. | §11.5 | 3 days |
| 5.8 | Migrate staging columns from `Float` to `Numeric`; make `_to_decimal` fail loudly. | §8.6 | 2 days |
| 5.9 | Customer portal screens (backend already supports it). | §4.3 | 5 days |
| 5.10 | Suppletie (VAT correction return) mechanism. | §4.3 | 4 days |
| 5.11 | GDPR erasure for unlinked accounts; automated retention flagging. | §4.3 | 3 days |
| 5.12 | Documentation corrections: `README.md` (stale at Phase 9), `production-readiness.md`, `security.md`, `encryption-key-rotation.md`, `gdpr-data-governance.md`, `untranslated-backend-messages-inventory.md`; correct the stale `app.api.v1.admin` references; commit the phase briefs. | §11.6, §8.22 | 2 days |
| 5.13 | **Wire the remaining orphaned endpoints**: GDPR data export, self-service deactivation, employee self-service invite, password-reset UI. | §4.6 | 4 days |
| 5.14 | **Consolidate duplicated report/dashboard/forecast endpoints** behind one authorisation path. | §2.7 | 4 days |
| 5.15 | **Chart of accounts / double-entry ledger** — see below. | §2.2 | 6–10 weeks |

**Tier 5 total: ~48 days**, excluding 5.15.

### On 5.15 — the double-entry question

This is not a task, it is a product decision, and it should be made before Tier 5 begins.

The platform files a statutory VAT return and issues payslips while running on a single-entry invoice ledger with no chart of accounts. Everything that a real general ledger would provide is currently either manually entered (`ManualBalanceSheetItem`), derived by heuristic (`retained_earnings` as cumulative P&L), or explicitly reported as unavailable (trial balance labelled "best-effort", DIO and inventory turnover reported as `missing_data`, the cash-flow reconciliation carrying a note that it "will not match exactly").

That last behaviour — reporting a gap rather than papering over it — is admirable and is applied consistently. But it means the platform's own outputs declare themselves incomplete in five separate places. An accountant using this for a real Dutch BV will hit the ceiling quickly: no journal trail, no account-level reporting, no period-close, no way to record anything the invoice pipeline does not produce.

**Two defensible paths:**
- **Stay single-entry and reposition** as a VAT-administration and management-information tool for accountants, not a general ledger. Cheaper, honest, and the existing code already supports it. Then remove or relabel "trial balance" and "balance sheet" as management estimates rather than statutory statements.
- **Build the general ledger.** `Account` with a Dutch RGS-referenced chart, `JournalEntry` with balanced `JournalLine`s, posting of every existing transaction as a journal, an opening-balance mechanism replacing `ManualBalanceSheetItem`, and a real period close. This is 6–10 weeks and touches every report, but it is what makes the product an accounting system rather than an invoice-and-VAT system.

The current state — statutory outputs from a ledger that cannot support them, with the gaps documented but not closed — is the worst of the three options.

### Sequencing summary

```
Tier 0 (3d)   cross-tenant writes, logout, secrets, XML, remote  ──► do now
Tier 1 (16d)  correct statutory and financial figures            ──► overlapping
Tier 2 (16d)  CI, coverage, missing tests                        ──► with Tier 1
Tier 3 (21d)  deployable: email, TLS, rate limit, MFA, Docker, CSV
Tier 4 (20d)  tenancy coherence, scale, indexes
Tier 5 (48d)  UI/a11y/i18n polish, portal, orphaned endpoints,
              endpoint consolidation, docs, product decision
              ───────────────────────────────────────────────
              ~124 engineering days to a defensible production
              candidate, excluding the double-entry decision
```

**Tier 0 is the only tier that should start before anything else.** Three of its ten items (0.1, 0.2, 0.10) are under a day each and close live cross-tenant write access, a 24-hour session-revocation gap, and an interpreter-dependent denial of service. Everything else in this roadmap can be sequenced; those three cannot.

---

## 13. Appendix

### 13.1 Findings index by severity

| ID | Severity | Title | Primary evidence |
|---|---|---|---|
| 6.1 | C | `VatPeriod.status` never assigned | `financial_reports.py:284`, `dashboard.py:76`; zero write sites |
| 6.2 | C | Cash-based companies get zero VAT returns | `period_assignment.py:29`, `ledger_service.py:185/284`, dead import `transactions.py:8` |
| 6.3 | C | Approval status affects no calculation | one `approval_status` hit in `app/accounting/` + `app/reporting/` |
| 6.4 | C | Committed encryption keys in active use | `config.py:7-11`; `BSN_ENCRYPTION_KEY` absent from `backend/.env` and from both `.env` examples |
| 6.5 | C | Tax rules frozen at 2025 | `dutch_tax_rules.py:226-237`, `vat_rules.py:48-49` |
| 6.6 | C | No DB idempotency guard on ledger posting | `ledger_service.py:73-79`; 4 `UniqueConstraint`s total |
| 6.7 | C | Tenant bypass in `require_company_access`; cross-tenant invitations non-functional | `deps.py`; `companies.py:45-51,335-364`; `documents.py:42-46` |
| 6.8 | C | Password reset token discarded | `auth.py` `_ = raw_token`; docstring contradicts code |
| 6.9 | C | Rate limiter ineffective behind a proxy | `rate_limit.py` `_client_key`; unbounded `_buckets` |
| 6.10 | C | Production frontend cannot reach the API | `lib/api.ts:1`; `frontend/Dockerfile`; `docker-compose.prod.yml:58-61` |
| 6.11 | C | MFA re-enrolment without step-up | `auth.py` `mfa_enable` |
| 6.12 | C | RTL fonts loaded but never applied at HEAD | `git show HEAD:frontend/app/globals.css` → 0 matches |
| 7.1 | H | No FX handling in the reporting layer | zero `currency`/`_eur` hits across 5 report modules |
| 7.2 | H | Manual balance-sheet items summed as flows | `financial_reports.py:251-262` |
| 7.3 | H | `previous_period()` wrong for quarters/leap years | `financial_reports.py:70-74` |
| 7.4 | H | No eager loading; Python-side aggregation | zero `selectinload`/`joinedload` hits |
| 7.5 | H | Two of three keys unrotatable | `token_crypto.py`, `mfa_crypto.py`; `scripts/` listing; `encryption-key-rotation.md:3` |
| 7.6 | H | Dockerfile and compose defects | both Dockerfiles, `docker-compose.prod.yml`, `db/session.py:6` |
| 7.7 | H | Dark-mode contrast 2.53:1 on error surfaces | 48 elements / 43 files; `globals.css:32,145` |
| 7.8 | H | Accessibility gaps exceed the project's own audit | 24 labels / 13 files; 2 of 196 `<th scope>`; 3 `window.prompt()` |
| 7.9 | H | `GET /vat-returns` writes, unaudited, viewer-accessible | `vat_returns.py:31-42` |
| 7.10 | H | Email lookup defeats the index; duplicated normalisation | `deps.py` `find_user_by_email`; `auth.py:47-52` |
| 7.11 | H | Four VAT boxes unreachable automatically | `vat_rules.classify_default_treatment` |
| 7.12 | H | Backup/restore script defects | `restore_db.sh:16`; `backup_db.sh:2-3,15` |
| 7.13 | H | Two tests make real billable API calls | `test_automation_api.py:131`, `test_financial_reports_api.py:278`; `automation.py:30` |
| 7.14 | H | Migration chain has zero coverage | `conftest.py:37`; zero `alembic` hits in `tests/` |
| 7.15 | H | Silent truncation; first-payee fraud vector | `ai_provider.py` `[:50_000]` |
| 7.16 | H | Unmaintained security dependencies | `requirements.txt` |
| 7.17 | H | No frontend auth failure path | `lib/api.ts:22-26`; `auth-context.tsx:44`; `AuthGuard.tsx:12` |
| 7.18 | H | Missing indexes on hot paths | migration `3853605281ec` index list |
| 6.13 | C | "Logout" never calls the backend; tokens valid 24h | `auth-context.tsx:50-55`; zero `api.logout` callers ✓ |
| 7.1–7.18 | H | FX, manual balance-sheet items, `previous_period`, N+1, key rotation, Dockerfiles, dark-mode contrast, a11y, `GET /vat-returns` writes, email index, VAT boxes, backup scripts, API-call leaks in tests, migration coverage, AI truncation, dependencies, frontend auth, indexes | as cited |
| 7.19 | H | Bank XML parsed with zero hardening; no `defusedxml` | `bank_parsers.py:17,141,152` ✓ |
| 7.20 | H | Rate-limit scopes shared; `/kvk/lookup` unlimited; `/billing/plans` unauthenticated write | 5 `enforce_rate_limit` call sites |
| 8.1–8.12 | M/L | Working tree, password policy, audit redaction, JWT subject, seed, `Float`, constraints, payment validation, storage prefix check, upload memory, health endpoints, i18n structure | as cited |
| 8.13 | M | CSV formula injection via raw `original_filename` | `batches.py:252`; `document_intake.py:44` |
| 8.14 | M | `partner_id` never validated against company/tenant | `employees.py:202-207` |
| 8.15 | M | `invite_employee_self_service` creates a user + password with no audit log | `employees.py:101-127` |
| 8.16 | M | Case-sensitive email uniqueness → shadow-account path | `users.py:89,159`; `employees.py:110`; `auth.py:191` |
| 8.17 | L | `Employee.linked_user_id` has no unique constraint | `models/employee.py:42`; `deps.py:115` |
| 8.18 | M | Unauthenticated DB write + commit on `GET /billing/plans` | `billing.py:19-22` |
| 8.19 | L | Unvalidated `kvk_number` in an upstream URL path | `kvk.py:20`; `kvk_provider.py:70` |
| 8.20 | L | Latent open redirects (`redirect_uri`, `success_redirect`) | `open_banking_provider.py:84`; `billing_provider.py:77` |
| 8.21 | L | Reset tokens not revoked on re-request; `/confirm` unrate-limited | `auth.py:191-196,211` |
| 8.22 | L | Stale `app.api.v1.admin` references; interim `provider_account_id` | `models/user.py:56`; `billing.py:105`; `open_banking_service.py:30` |
| 4.6 | H | 7 endpoints with no frontend caller, incl. the only employee-account creation path and the VAT-eligibility override | §13.5 |
| 2.7 | M | Duplicated report/dashboard/forecast endpoints behind two authorisation paths | `reports.py` vs `financial_reports.py` |

**Cross-tenant sub-index (§6.7)** — the seven endpoints reachable across tenants by any `owner`/`admin`, plus one membership grant:

| ID | Type | Endpoint | Location |
|---|---|---|---|
| CRITICAL-1 | **WRITE** | `POST /companies/{id}/financial-years/{fy_id}/lock` and `/unlock` | `companies.py:196-201` → `:205`, `:227` |
| CRITICAL-2 | **WRITE** | `POST /payment-matches/bulk-approve-high-confidence` | `banking.py:235-246` |
| HIGH-1 | READ | `GET /companies/{id}/financial-years` | `companies.py:184-193` |
| HIGH-2 | READ (PII) | `GET /companies/{id}/invitations` | `companies.py:306-314` |
| HIGH-3 | **WRITE** | `POST /companies/{id}/invitations/{inv}/revoke` | `companies.py:317-333` |
| MEDIUM-1 | READ (free text) | `GET /companies/{id}/notes` | `workspace.py:102-110` |
| HIGH-4 | membership grant | `POST /companies/invitations/accept` | `companies.py:336-355` |

### 13.2 Claims verified as TRUE

Recorded so the report is not read as uniformly negative. Each was checked against code, not documentation.

- Migration chain is clean: 22 revisions, single head `d90e97d4bc35`, no orphaned `down_revision`.
- `.env` was never committed; no secret has ever entered git history.
- BSN is encrypted at rest, returned masked only, never returned by employee self-service, never logged.
- No logger call site in `app/` touches a password, BSN or token.
- No raw string-interpolated SQL anywhere in `backend/app`; the only `text()` uses are `SELECT 1` and the `alembic_version` read.
- Payment initiation has no code path at all — the "never moves money" claim holds.
- `is_platform_admin` is settable only by seed/DB, never through an API endpoint.
- The AI assistant has no database session and no write path.
- All four i18n dictionaries have identical 1,374-key / 57-namespace structure with zero drift.
- 55/55 routes call `useTranslations`; zero untranslated JSX text nodes in production routes.
- 0 of 140 locale-aware formatting calls omit the `locale` argument.
- RTL CSS uses logical properties throughout, with exactly one deliberate and well-commented physical declaration.
- Tests run against real Postgres with `autoflush=False` matching production, and the Phase 6 fix has a genuine regression guard.
- 20 tests create a real second tenant; 16 are named cross-tenant isolation tests asserting 404 not 403.
- `navConfig` marks 4 unbuilt features as unavailable rather than faking pages, with a test enforcing the invariant.
- Zero dead nav links; zero frontend calls to nonexistent backend endpoints (184 client paths vs 217 route decorators).
- No TODO/FIXME/HACK/XXX markers anywhere in `backend/app`; one false positive in the frontend.
- Zero eager-loading-related correctness bugs from the `autoflush` mismatch class, since the fixture now matches production.
- `docker-compose.prod.yml` correctly isolates Postgres on an internal network and requires a password with no default.
- Financial-year locking is real and enforced at a single choke point.
- The three CSV BOM assertions that look like no-ops contain a literal U+FEFF and are correct.

Added after the full 217-route authorisation audit:

- **No raw string-interpolated SQL anywhere in `backend/app`.** Exactly two `text()` uses, both static literals with no interpolation: `main.py:150` (`SELECT 1`) and `main.py:172` (`SELECT version_num FROM alembic_version`). No f-string SQL, no `.format()` SQL, no `%` SQL, no `raw_connection`, no `executescript`. Every other `.execute(` hit is `pdf.text(...)` from `reporting/pdf_builder.py` — PyMuPDF text placement. The one `ilike` with an f-string (`audit_log.py:41-43`, `like = f"%{q}%"`) is properly parameterised; a user can inject LIKE wildcards to widen *their own tenant's* search, which is not a boundary crossing.
- **No SSRF.** No user-controlled URL is ever fetched. `kvk_provider.py:69-73` interpolates only a path segment against a config-derived base; `StubOpenBankingProvider` performs no network I/O at all and `get_open_banking_provider()` always returns the stub; `StubBillingProvider` *builds* a sandbox URL string but nothing fetches it; the Anthropic SDK is the only outbound client with a real endpoint and its base URL is not request-derived.
- **External-entity XXE is not exploitable** (empirically tested by the delegated review, §7.19) — stock `ElementTree` installs no external entity reference handler, so `file://` and outbound-request entities raise `ParseError`.
- **No secrets in logs.** Every `logger.*` call in `backend/app` filtered for `password|token|secret|bsn|iban|payload|body|header|credential` returns zero hits. `_JsonLogFormatter` (`main.py:24-40`) emits only `timestamp`, `level`, `logger`, `message`, `request_id`, `exc_info` — never request bodies or headers. The request logger (`main.py:132`) records method, path, status, duration only.
- **Upload validation is solid.** Magic-byte sniffing for PDF/JPEG/PNG/ZIP; ZIP payloads are additionally parsed with `openpyxl` to prove they are real workbooks; CSV requires both extension and a successful UTF-8 decode; client MIME is never consulted — `content_type` is set from the server-side `CONTENT_TYPES[kind]` map, so `download_document_file` can never be coerced into serving `text/html`. Size limits are enforced before processing.
- **No storage path traversal.** Paths are built server-side from integer IDs plus a filename whose charset excludes `/`, `\`, and `"`; `Content-Disposition` cannot be header-injected.
- **`is_platform_admin` is not settable through any API.** All 8 occurrences accounted for: column definition, a **response-only** schema field, the read-side guard, a comment, one test, and the migration's `server_default=sa.false()`. It appears in **no request schema**. `PATCH /users/{id}/role` accepts only a `role` enum; `CompanyUpdate` contains only `vat_accounting_basis` and `input_vat_pro_rata_percentage`; both user-creation paths construct `User(...)` with explicit keyword fields, never `**payload.model_dump()`. No mass-assignment vector exists.
- **No privilege-escalation path to `owner`/`admin`.** `users.py:88-89` requires `user.role == owner` to invite as owner/admin, and `update_user_role` re-checks server-side: self-change blocked (`:214-215`), non-owner blocked on either side of an owner/admin transition (`:217-219`, correctly symmetric so an admin cannot demote an owner or a peer), last-active-owner protected (`:221-223` and again in `deactivate_user:255-256`). `customer`/`employee` are excluded from `ASSIGNABLE_ROLES`, so that endpoint cannot mint them. `PATCH /users/{id}/role` is `require_admin`, so accountant and customer cannot reach it at all.
- **`/billing/admin/overview` exposes counts only** — `tenant_id`, `tenant_name`, `plan_code`, `subscription_status`, `companies_used`, `users_used`. No financial records, documents or ledger, exactly as the model comment claims.
- **Password-reset and invitation tokens are safe by construction.** 256-bit (`secrets.token_urlsafe(32)`), stored only as SHA-256, single-use (`used_at`/status checked and stamped), expiry-enforced, and the target user is resolved by primary key from the hashed-token row — never from request input. `accept_user_invitation` re-filters `initial_company_ids` to the invitation's tenant (`users.py:170-172`), so a stored list cannot be replayed across tenants. Duplicate-email guarded.
- **`employee_self_service.py` has no swappable identifier.** No endpoint accepts `employee_id`; both path-parameter endpoints compare against the resolved `employee.id`; `create_my_timesheet_entry` additionally rejects a payload-supplied `employee_id` mismatch. The project's own claim holds.
- **The file-download and export surface is clean.** Every primary-key fetch across `documents`, `payroll`, `employee_self_service`, `reports` and `batches` is paired with an ownership or tenant predicate; secondary IDs are tied back to a tenant-checked parent throughout.
- **All 26 routers are mounted; none is orphaned**, and no frontend path points at a non-existent backend route.
- **`/billing/webhook` verifies HMAC-SHA256 with `hmac.compare_digest` before any state change**, and blocks replay via `BillingEvent.provider_event_id` uniqueness.
- **Security headers are applied to every response** (`main.py:96-105`): `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`. HSTS is correctly deferred to the reverse proxy and documented as such.
- **The rate limiter does not trust `X-Forwarded-For`** — it uses the TCP peer address, so it is not spoofable by header injection. (The proxy problem at §6.9 is the opposite failure: it trusts the peer *too much*.)
- **Commit timestamps corroborate the four-day timeline**: 6 commits on 2026-11-02, 54 on 11-03, 25 on 11-04, 3 on 11-05. The history has not been rewritten.

### 13.3 Could not be determined

Stated explicitly rather than inferred.

1. **Whether the 540 backend tests currently pass.** Nothing was executed. All "passing" claims are the project's own, verified only for arithmetic consistency (the 358/281/205 counts are exact for their phases) and code-level plausibility.
2. **Whether the frontend builds, typechecks, lints or passes its tests.** `frontend/tsconfig.tsbuildinfo` (mtime 5 Nov 10:06) and `.next/` (10:07) suggest both succeeded that morning; that is inference from file timestamps, not verification.
3. **True line/branch coverage.** No coverage tool is configured or installed. Unknowable from this repository.
4. **~~The complete endpoint authorisation matrix.~~ RESOLVED.** This was outstanding when the report was first drafted; the delegated review subsequently completed and covered all 26 routers via AST walk. Its findings are at §2.7, §4.6, §6.7, §6.13, §7.19–§7.20, §8.13–§8.22 and §13.5. The five highest-severity new findings were independently re-verified by me against the cited lines. One delegated claim was disproved and excluded (§0.2 caveat 2, commit dates).
5. **Whether the two Anthropic network leaks are currently firing.** Depends on the ambient `ANTHROPIC_API_KEY` when pytest runs. I verified the key is present and non-empty in `backend/.env` and that no test nulls it; I did not execute anything.
6. **The exact count of unused `lib/api.ts` methods.** The detector required the literal `api.<name>` form and produced at least one demonstrable false positive (`trialBalance`), so "43 of 210" is an upper bound. A real unused-export AST analysis is needed.
7. **Actual rendered contrast ratios.** The 2.53:1 figure is computed from hex values in `globals.css` and Tailwind's published palette, not measured in a browser.
8. **Whether the 1,374 translation keys are *correctly* translated.** Verified: they exist, are non-empty, are structurally identical across locales, and are not English copies (7 of 1,374 excepted, all legitimately untranslatable). Not verified: semantic accuracy. A native-speaker review of `fa.json` and `ar.json` is separate work; `docs/i18n-terminology-glossary.md` was not audited against the dictionaries.
9. **Runtime RTL layout correctness.** The CSS analysis is static. Whether `fa-IR`/`ar-SA` render without overflow or clipping requires a browser; the e2e no-horizontal-overflow assertions cover only 4 routes.
10. **Whether any 2026 Dutch tax rate differs from the 2025/2024 values in code.** Not checked against Belastingdienst primary sources. The finding at §6.5 is that the system has no mechanism to know and no mechanism to warn.
11. **The precise count of mutating endpoints lacking a denial test.** A path-proximity heuristic with confirmed false positives (e.g. `/batches/{id}/approve`). Treat 40 as an upper bound on the gap and 62/102 as a lower bound on coverage.
12. **Whether the uncommitted working-tree changes were intended to ship.** The diff is reported; authorial intent is not knowable from the repository.
13. **~~Where the upload size limit is enforced relative to reading the request body.~~ RESOLVED** — `documents.py:77-79` and `batches.py:126-129` check against `settings.max_upload_size_bytes` before processing, reading the body once; batch file count is checked at `batches.py:100-104`. The residual concern at §8.10 is that the whole file still lands in memory as `bytes`, and that `openpyxl` expansion is uncapped — not that the limit is unchecked.
14. **Whether any DB collation or index makes differently-cased `users.email` values collide.** Relevant to the shadow-account path at §8.16. The migrations declare a plain case-sensitive unique index and I found no `citext` or collation override, but I did not inspect the live database. The *mechanism* is confirmed from code; whether it is exploitable end-to-end is not.
15. **Whether `backend/.dockerignore` excludes `*.bak`.** The file exists; I did not read it, so §8.12's note that `main.py.bak` would be copied into the image is unverified.

### 13.4 Files created by this audit

| Path | Note |
|---|---|
| `docs/QWEN_TECHNICAL_AUDIT_REPORT.md` | This report. **The only file created, modified or deleted by this audit.** |

No other project file was touched. No build, test, server or database operation was performed. `docs/` already existed.

### 13.5 Full endpoint inventory and authorisation matrix

**217 routes / 194 distinct paths / 26 modules**, all mounted under `/api/v1` by `app/api/v1/__init__.py`. Extracted by AST walk over every router (decorators + signature defaults + decorator-level `dependencies=`). **No router-level `dependencies=[...]` exists anywhere**, so every guard is per-function. Plus two root-level routes in `app/main.py`: `GET /health` (`:141`) and `GET /ready` (`:158`), both unauthenticated by design.

Guard key: `CU` = `get_current_user` · `RA` = `require_admin` · `RE` = `require_editor` · `RU` = `require_uploader` · `REO` = `require_editor_or_owner` · `CE` = `get_current_employee` · **—** = none

#### Per-router summary

| Router | Prefix | Routes | Guard distribution | Cross-tenant findings |
|---|---|---|---|---|
| `assistant` | `/assistant` | 6 | 6 CU | clean |
| `audit_log` | `/audit-log` | 3 | 3 RA | clean (tenant-scoped by construction) |
| `auth` | `/auth` | 11 | 3 **—**, 8 CU | §6.8, §8.21 |
| `automation` | *(none)* | 13 | 5 RE, 8 CU | clean |
| `banking` | *(none)* | 16 | 10 RE, 6 CU | **CRITICAL-2** (`:241`) |
| `batches` | `/batches` | 6 | 1 RU, 2 RE, 3 CU | clean; §8.13 (`:252`) |
| `billing` | `/billing` | 6 | 2 **—**, 2 RA, 2 CU | §8.18 (`:19`) |
| `budgets` | `/budgets` | 9 | 3 RE, 3 REO, 3 CU | clean |
| `companies` | `/companies` | 14 | 2 RA, 1 RE, 4 `_require_company_owner`, 7 CU | **CRITICAL-1** (`:196`), **HIGH-1** (`:187`), **HIGH-2** (`:307`), **HIGH-3** (`:318`), **HIGH-4** (`:353`) |
| `dashboard` | `/dashboard` | 3 | 3 CU | clean |
| `documents` | `/documents` | 10 | 1 RU, 6 RE, 3 CU | clean |
| `employee_self_service` | `/me` | 9 | 9 CE | clean ✓ |
| `employees` | *(none)* | 10 | 8 RE, 1 RA, 1 CU | §8.14 (`:207`), §8.15 (`:101`) |
| `financial_reports` | `/financial-reports` | 21 | 1 REO, 20 CU | clean, but **13 of 21 untested** (§9.4) |
| `forecasts` | *(none)* | 4 | 2 REO, 2 CU | clean |
| `kvk` | `/kvk` | 2 | 2 CU | §7.20, §8.19 |
| `legal_forms` | *(none)* | 9 | 4 RE, 5 CU | clean ✓ |
| `loonheffingen` | *(none)* | 7 | 6 RE, 1 CU | clean ✓ |
| `payroll` | *(none)* | 11 | 8 RE, 3 CU | clean ✓ |
| `reports` | `/reports` | 7 | 7 CU | clean; §2.7 duplication |
| `tax_calendar` | `/tax-calendar` | 1 | 1 CU | clean ✓ |
| `tax_centre` | `/tax-centre` | 6 | 6 CU | clean ✓ |
| `transactions` | `/transactions` | 8 | 6 RE, 2 CU | §6.2 (dead import `:8`), §4.6 (`:174` orphaned) |
| `users` | `/users` | 10 | 1 **—**, 9 RA | clean ✓ |
| `vat_returns` | `/vat-returns` | 6 | 3 RE, 3 CU | §7.9 (`:31`) |
| `workspace` | *(none)* | 4 | 2 RE, 2 CU | **MEDIUM-1** (`:102`) |

✓ = low `tenant_id` grep count is *good factoring*, not a gap — the check lives once in a shared helper that every route calls. Verified individually for `tax_centre` (all 6 routes → `_get_company_or_404` at `:66,138,157,190,220,240`), `legal_forms` (all 8 → `:41,64,75,97,111,125,139,152`), `kvk`, `tax_calendar`, `loonheffingen`, `payroll`, `employee_self_service`.

#### The 6 routes with no auth dependency

| Route | Location | Intentional? |
|---|---|---|
| `POST /auth/login` | `auth.py:45` | **Yes** — credential endpoint. Rate-limited (`:46`), lockout enforced. |
| `POST /auth/password-reset/request` | `auth.py:185` | **Yes** — rate-limited (`:193`), always 204, no enumeration. But non-functional (§6.8). |
| `POST /auth/password-reset/confirm` | `auth.py:211` | **Yes** — the 256-bit single-use token *is* the credential. Not rate-limited; infeasible to brute-force regardless. |
| `POST /users/invitations/accept` | `users.py:141` | **Yes** — signup flow, same token pattern. |
| `POST /billing/webhook` | `billing.py:67` | **Yes** — HMAC-SHA256 verified with `compare_digest` before any state change; replay blocked by `provider_event_id` uniqueness. Undermined only by the committed default secret (§6.4). |
| `GET /billing/plans` | `billing.py:19` | **Partly a bug** — calls `ensure_plans_seeded(db)` then `db.commit()` on every unauthenticated request (§8.18). |

**No route is missing an auth dependency by accident other than `/billing/plans`.** That is a good result for a 217-route surface built in four days.

#### Guard totals

| Guard | Routes |
|---|---|
| `require_editor` (owner/admin/accountant) | 62 mutating + read endpoints |
| `require_admin` (owner/admin) | 15 |
| `require_editor_or_owner` (+customer) | 5 |
| `require_uploader` (+customer) | 2 |
| `get_current_employee` | 9 |
| `get_current_user` (any authenticated role) | ~114 |
| inline `is_platform_admin` / `ADMIN_ROLES` / `_require_company_owner` | 5 |
| **none** | **6** |

Of 102 mutating endpoints (POST/PUT/PATCH/DELETE), **62 have at least one 4xx denial assertion in the test suite and 40 have none** (§9.4).

---

*End of report.*
