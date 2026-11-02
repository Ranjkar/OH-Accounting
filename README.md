# OnHolland Accounting

AI-powered accounting and Dutch VAT administration platform. Phase 1 (Foundation),
Phase 2 (AI Document Intelligence), Phase 3 (Accounting Ledger & Dutch VAT Engine) and
Phase 4 (Accountant Assistant) complete, with a verified real Claude API integration.

## Stack
- Backend: FastAPI + SQLAlchemy + Alembic + PostgreSQL, JWT auth
- Frontend: Next.js (App Router) + TypeScript + Tailwind CSS
- Document processing: PyMuPDF (PDF text), Tesseract OCR (scanned pages/images, with a
  Dutch language pack), openpyxl/pandas (XLSX/CSV), Claude API (structured extraction)

## Local development

**Database** (via Homebrew, already running as a service):
```
brew services start postgresql@16
createdb onholland_accounting
```

**OCR** (via Homebrew):
```
brew install tesseract tesseract-lang   # tesseract-lang adds the Dutch pack
```

**Backend**:
```
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # adjust DB url; set ANTHROPIC_API_KEY to enable real AI extraction
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed   # creates admin@onholland.nl / changeme123
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Without `ANTHROPIC_API_KEY` set, document extraction falls back to a stub provider that
returns null fields and routes every document to manual review — the app still runs,
nothing crashes, but AI extraction won't populate fields until a key is configured.

**Frontend**:
```
cd frontend
npm install
npm run dev
```

App runs at http://localhost:3000, API at http://localhost:8000 (docs at /docs).

## Tests
```
cd backend
createdb onholland_accounting_test   # once
.venv/bin/python -m pytest
```

## What's implemented (Phase 1)
- Multi-tenant model: tenants -> companies -> users (role: admin/accountant/viewer), user-company access grants
- JWT auth, role-based authorization
- Financial years with deterministic VAT-period generation (monthly/quarterly/annual), Dutch filing-deadline rule (end of month following period end)
- Company CRUD, financial-year creation, dashboard summary (company count, open VAT periods, upcoming deadlines)
- Audit log table
- Next.js UI: login, dashboard, company list/create, company detail with VAT period tables

## What's implemented (Phase 2)
- Document upload (PDF/JPG/PNG/XLSX/CSV) with content-sniffed validation (magic bytes, not
  filename/MIME), secure filenames, SHA-256 hashing, duplicate detection, tenant/company/
  financial-year association, local-disk storage (swappable for Azure Blob in Phase 5)
- Async processing via FastAPI `BackgroundTasks` (no Celery/Redis — not needed at this
  volume; see `app/services/document_processing.py` docstring for the upgrade path)
- PDF text extraction (PyMuPDF) with Tesseract OCR fallback for scanned pages; OCR runs
  directly for JPG/PNG
- Structured AI extraction via Claude (`app/services/ai_provider.py`), behind a provider
  interface with a null-safe stub fallback when no API key is configured
- XLSX/CSV parsed deterministically into line items (openpyxl/pandas) — no AI call, since
  the data is already structured
- Deterministic validation engine: net+VAT=gross (rounding-tolerant), VAT-rate consistency,
  missing invoice number, due-date-before-invoice-date, duplicate flag, credit-note
  reference, currency/supplier-customer sanity checks — mathematical only, never a
  deductibility judgment
- Document statuses: `pending -> processing -> extracted/needs_review -> approved/rejected`,
  or `failed`; low-confidence or validation-error documents always land in manual review,
  nothing is ever auto-approved
- Review workflow: correct fields, approve, reject, reprocess, reassign company/financial
  year — every action audit-logged with before/after values; approved documents are locked
  (no further edits/reprocessing)
- Tenant isolation enforced on every document endpoint (list/detail/file/mutations);
  per-document file access via an authenticated streaming endpoint, never a static path
- Next.js UI: Documents nav, upload, filterable list, review screen (file preview, editable
  fields, VAT breakdown, validation warnings, confidence, approve/reject/reprocess/reassign)

## What's implemented (Phase 3)
- `app/accounting/` package (separate from AI/OCR `app/services/`): `vat_rules.py`
  (versioned Dutch rates + the sales/purchase box-mapping table), `vat_engine.py` (pure
  Decimal calculation of every declaration box), `payment_engine.py` (deterministic
  payment-status computation), `period_assignment.py` (invoice-based vs cash-based VAT
  period assignment), `ledger_service.py` (document -> transaction conversion, manual
  entries, corrections), `reconciliation.py` (the quarterly reconciliation view)
- New tables: `accounting_transactions`, `transaction_line_items` (the source of truth for
  multi-rate invoices), `payments` (manual-only, never inferred from invoice text),
  `vat_returns` (one per VAT period, with computed box totals and a reconciliation
  workflow status)
- Approving a postable document (sales/purchase invoice, credit note, receipt) now posts
  an `AccountingTransaction`, converting `DocumentLineItem`s 1:1 so multi-rate invoices
  carry through correctly; idempotent (re-approving never double-posts); requires the
  document to have a financial year assigned first (never guesses one)
- Dutch VAT box engine: 1a/1b/1c (domestic sales by rate), 1d (private use), 1e (domestic
  zero/exempt), 2a (domestic reverse-charge received), 3a/3b/3c (export/EU supply/distance
  sale), 4a/4b (import/EU acquisition), 5a (total VAT due), 5b (deductible input VAT); the
  final payable/refundable total is exposed as "5g" per this phase's brief, though the
  current official Belastingdienst form computes that total rather than labeling it as a
  box — documented in `vat_rules.py` rather than silently inventing a box that doesn't exist
- Input VAT eligibility (ELIGIBLE/INELIGIBLE/PARTIALLY_ELIGIBLE/REQUIRES_REVIEW) per line
  item; the deterministic default only ever auto-assigns ELIGIBLE (valid invoice number +
  supplier VAT number) or REQUIRES_REVIEW — never INELIGIBLE/PARTIALLY_ELIGIBLE, which
  require accountant judgment; partial deduction uses the company's configured pro-rata %
  for mixed taxable/exempt activities, defaulting to 0% deducted (never guessed) if unset
- Payment reconciliation: UNPAID/PARTIALLY_PAID/PAID/OVERDUE/UNKNOWN computed purely from
  recorded `Payment` rows + due date, never from invoice text; supports multiple partial
  payments per invoice
- Money is `Decimal` end-to-end in the ledger (Phase 1/2's `Float` columns are untouched —
  those stay AI-extraction staging data; floats are converted to Decimal once, at the
  document -> transaction boundary)
- Foreign-currency transactions without a confirmed FX rate are excluded from VAT return
  box totals (flagged, not guessed at a rate of 1); an accountant supplies the rate via
  `PATCH /transactions/{id}` while the transaction is still in draft
- VAT return workflow: `draft -> needs_review -> ready_for_approval -> approved -> locked`;
  once approved, direct transaction edits are blocked (409) and a new, audit-logged
  correction transaction is required instead; locking a period cascades to lock every
  transaction in it
- Reconciliation view: sales/purchase ledger totals, VAT-by-rate breakdown, pending
  (not-yet-approved) documents, duplicate documents, validation errors, unresolved-FX
  transactions, and prior corrections — everything an accountant needs before approving
- Tenant isolation verified on every transaction/VAT-return endpoint
- Next.js UI: Ledger (list/filter, manual-entry form, transaction detail with payments and
  corrections), VAT overview (per financial year, per period, with net payable + status),
  VAT return detail (declaration-box preview, reconciliation checks, approve/lock actions);
  company settings gained VAT accounting basis (invoice/cash-based) and pro-rata %

## Explicitly deferred (not needed yet)
- Docker for backend/frontend, Redis, Celery — single-process BackgroundTasks is enough
  at current volume; add a real queue if upload throughput or multi-worker scaling
  requires durability across restarts
- Azure Blob storage, encryption at rest, SBR integration — Phase 5
- Accountant reporting / professional PDF exports, tax calendar reminders — Phase 4
- Per-row AI extraction for XLSX/CSV (currently deterministic column-mapping only)
- A DB-editable tax-rule admin screen — rates are versioned in code (`vat_rules.py`); add
  a DB-backed version if accountants need to adjust rates without a deploy
- RECEIPT documents always post to the purchases side by default (the common case for an
  expense receipt); there's no UI yet to flag a receipt as a cash sale instead

## What's implemented (Phase 4)
- **Verified real Claude API integration.** `ANTHROPIC_API_KEY` is read from `backend/.env`
  (gitignored; `.env.example` holds only an empty placeholder). Fixed two real integration
  bugs found while testing against the live API:
  - Claude sometimes returned dates as `DD-MM-YYYY`; the prompt now explicitly requires
    ISO 8601, and `_parse_date` tolerates `DD-MM-YYYY` as a fallback rather than silently
    dropping a valid date.
  - Claude cannot tell SALES_INVOICE from PURCHASE_INVOICE from document text alone (both
    look identical structurally) — it needs to know which party is "us". The extraction
    call now receives the accounting client's company name/VAT number as context; document
    classification accuracy was confirmed to flip correctly depending on which side the
    client is on.
- Accountant dashboard: company count, companies requiring attention (computed from real
  overdue returns/pending documents/overdue payments, not a static flag), VAT returns
  awaiting review/approved/overdue, documents awaiting approval, unmatched (overdue)
  payments, outstanding customer info, estimated VAT payable/refundable across open
  periods — every figure is a live DB query, filterable by company
- Company workspace (`/companies/{id}/workspace`): financial years, transaction/document/
  payment counts, a per-VAT-period completeness table (sales/purchases/bank statements/
  payments reconciled/VAT return reviewed — absence of evidence is reported as incomplete,
  never silently assumed complete), and accountant notes
- Accountant notes: internal notes, customer-facing questions, and missing-document
  requests in one table with a status workflow (open/answered/resolved), linkable to a
  document/transaction/VAT return, fully audit-logged
- Tax calendar: all VAT periods across financial years with a computed status (completed/
  pending/upcoming/overdue) derived from the VAT return's real status and today's date —
  list and calendar (by-month) views
- AI accountant assistant (`app/accounting/assistant_facts.py` +
  `app/services/ai_assistant_provider.py`): Claude is given a JSON bundle of facts already
  computed by deterministic Python services and asked to explain/summarize them in prose.
  It has no database access and no write path, so it cannot change, approve, or lock any
  record by construction, not just by instruction. Every response carries the underlying
  facts and an explicit disclaimer. Verified live: it correctly declined to comment on data
  it wasn't given rather than inventing it, and recommended the normal review process
  rather than suggesting anything be auto-approved.
- Professional reports, generated purely from database records (never from AI output),
  in PDF (via PyMuPDF — already a dependency, no new PDF library added), XLSX (openpyxl),
  and CSV (stdlib): a VAT Return Report (box breakdown, sales/purchase overview, VAT-by-rate,
  reverse-charge overview, input VAT summary, reconciliation findings) and a Financial
  Overview Report (income/expense by period, payment status, outstanding invoices); period
  comparison reuses the same computation as a JSON endpoint for the frontend
- Next.js UI: revamped Dashboard, company Workspace tab, Tax Calendar (list + calendar
  view), Accountant Assistant chat-style page, Reports page with PDF/XLSX/CSV downloads
  (also available directly from the VAT return detail page), Settings page; nav extended
  to all 9 required sections

### Integration/security fixes made during Phase 4
- `JWT_SECRET` in `.env` was still the literal `change-me-in-production` placeholder
  (never rotated when `.env.example` was copied) — replaced with a securely generated
  random secret; added a startup warning if the insecure default is ever still active
- `POST /companies/{id}/financial-years` had no role check at all (any authenticated user
  with company access, including viewers, could create financial years) — now requires
  admin/accountant, with a regression test
- `app/api/v1/assistant.py` imported `get_assistant_provider` by name instead of importing
  the module, which silently broke the test-mocking pattern used everywhere else in the
  codebase — every assistant test was quietly hitting the real Claude API instead of the
  mock. Fixed to match the established `from app.services import x; x.get_y()` pattern;
  caught because the fake provider's test assertions on response content failed once a
  second test checked the actual `answer` field, not just the facts
- Minor: PDF reports used em-dash/middle-dot characters that don't render in PyMuPDF's
  base-14 Helvetica font (rendered as a stray glyph); replaced with plain ASCII

## Explicitly deferred (Phase 4)
- SBR/Belastingdienst submission integration — explicitly out of scope per the brief;
  nothing in this phase submits a return anywhere, only prepares and locks it internally
- A dedicated calendar-grid UI (the "calendar view" is a by-month list grouping, not a
  rendered month grid) — list view covers the same information with less UI complexity
- Customer-facing portal for answering questions/providing documents — notes/questions are
  accountant-facing only; there is no separate client login

## What's implemented (Phase 5)

**Bulk invoice upload (highest priority)** — `app/services/document_intake.py` (shared
file-validate/hash/dedupe/store logic, used by both single- and batch-upload),
`app/services/batch_processing.py` (bounded-concurrency `ThreadPoolExecutor`, no Celery/
Redis), `app/api/v1/batches.py`:
- `POST /batches/upload`: multiple files, one company/financial-year/category (SALES or
  PURCHASES) per batch; per-file validation failures are collected as `rejected_files` and
  never abort the rest of the batch
- Strict sales/purchase separation: `upload_category` is stored on every `Document` and
  checked against Claude's own classification (`UPLOAD_CATEGORY_MISMATCH`, error severity
  → forces `needs_review`) — a document is never silently posted to the wrong ledger side
  because the uploader picked the wrong screen or Claude misread the direction
  (`app/services/validation_engine.py`)
- Business-duplicate detection beyond SHA-256: same invoice number + counterparty VAT
  number + invoice date + gross amount across *different* files → `POTENTIAL_BUSINESS_DUPLICATE`
  warning, never an auto-reject
- Batch dashboard: `GET /batches`, `GET /batches/{id}` (per-file status + counts), bulk
  `approve`/`reject` (one failing document never blocks the rest — reuses
  `app/services/document_approval.py`, shared with the single-document endpoints so the two
  workflows can't drift), `DELETE /documents/{id}` (remove an unprocessed file; blocked once
  approved), CSV export
- Idempotent, restart-safe: re-approving never double-posts (existing Phase 3 guarantee,
  reused); documents stuck in `processing` at startup are reset to `pending` by a lifespan
  hook (`app/main.py`) instead of staying stuck forever after a crash/restart
- Retry with backoff for Claude API rate limits/overload (`app/services/retry.py`), used by
  both the extraction and assistant providers

**Found and fixed a real, previously-undetected Phase 2 bug while building this**: after
creating a brand-new `ExtractedInvoiceFields` row, the code never updated the in-memory
`document.fields` relationship, so `document.fields` read back as stale `None` later in the
*same* request/session. `DUPLICATE_DOCUMENT` findings (checked before fields are touched)
were never affected, which is why this went undetected since Phase 2 — but *any* validation
rule depending on `fields` (amount checks, missing-invoice-number, and now the category-
mismatch and business-duplicate checks) silently never fired on a document's first-ever
extraction. Fixed by setting `document.fields = fields` immediately after creating it.

**Customer role and permission split** — `UserRole.customer` added; `require_uploader`
(admin/accountant/customer) now gates uploads while `require_editor` (admin/accountant only)
still gates every approval/rejection/correction/lock action, so a customer can upload their
own company's invoices but can never approve them. Tenant/company isolation reuses the
existing `require_company_access` check unchanged.

**Rate limiting** — in-memory fixed-window limiter (`app/core/rate_limit.py`) on `/auth/login`
and both upload endpoints. Single-process, resets on restart; documented as the ceiling to
replace with a shared store if this is ever run with multiple worker processes.

**Security fixes made while reviewing for this phase**:
- CORS origins are now read from `CORS_ALLOWED_ORIGINS` (comma-separated) instead of being
  hardcoded to `localhost:3000`, so a real frontend domain can be configured without a code
  change — and so nobody is tempted to widen it to `*` with credentials enabled
- Added a `DELETE /documents/{id}` that's blocked once a document is approved (can't delete
  something already posted to the ledger — a correction is required instead, same rule as
  everywhere else in the ledger)

**Production infrastructure**: `backend/Dockerfile` (includes Tesseract + the Dutch
language pack), `frontend/Dockerfile`, `docker-compose.yml` extended with backend/frontend
services (Postgres service unchanged, volume never dropped by a normal `up`); real,
tested backup/restore scripts (`backend/scripts/backup_db.sh` / `restore_db.sh` — actually
run against the dev database for this report, not just written: a backup was taken,
restored into a fresh database, data verified, and the restore script's own overwrite
guard was confirmed to refuse restoring onto a non-empty database).

**SBR/Digipoort**: research and architecture only, in `docs/sbr-digipoort-integration.md` —
no submission code, no simulated acknowledgement. A real integration needs a PKIoverheid
SBR certificate, Logius registration, and passing their conformance test suite, none of
which exist in this environment; building a fake version of any of that would violate the
explicit "don't simulate submission" instruction.

**Frontend**: `/sales/upload` and `/purchases/upload` (distinct screens, drag-and-drop,
multi-file select, green/amber visual distinction), `/batches` (dashboard) and
`/batches/{id}` (per-file status table, checkbox-driven bulk approve/reject, retry, remove,
CSV export) — all built on a shared `BulkUploadScreen` component parameterized by category
so the two screens can never drift apart, while still being genuinely separate routes/URLs.

## Explicitly deferred (Phase 5)
- **Customer portal UI**: the backend fully supports it (customer role, scoped company
  access, upload permission without approval rights, all verified by tests) but there is no
  dedicated customer-facing frontend yet — a customer would currently see the same
  accountant-oriented pages, just with mutating actions correctly blocked server-side. The
  "view VAT summaries / missing documents / deadlines" customer-facing screens are not built.
- **Bank-grade production hardening** beyond what's listed above: no WAF/reverse-proxy
  config, no centralized log aggregation or error-tracking service (e.g. Sentry) wired up,
  no staged blue/green deployment config — this environment doesn't have a real
  staging/production target to configure against
- **File malware scanning** (e.g. ClamAV) — magic-byte content validation catches
  mismatched/malformed files, but nothing scans for embedded malware; would need a new
  dependency, deliberately not added without a concrete requirement
- A full nav redesign — the top nav is now 12 items and visibly dense; a collapsible
  sidebar would be the right follow-up but is a design change beyond this phase's scope

## What's implemented (Phase 6)

**No live bank integration exists.** PSD2/Open Banking requires a licensed TPP registration
and a real bank's sandbox/production API access, neither of which exist in this environment.
What's built instead is a deterministic **file-import** pipeline (CAMT.053, CAMT.054, MT940,
CSV) behind an adapter-shaped boundary (`app/accounting/bank_import.py` /
`bank_parsers.py`) so a real PSD2 adapter could be added later without touching the
reconciliation engine. Nothing ever stores a bank login credential or online-banking
password — only import files and the transaction data parsed out of them.

**Bank transaction ledger** — `app/models/banking.py` (`BankAccount`, `BankImportBatch`,
`BankTransaction`, `PaymentMatch`). Import is idempotent via a SHA-256-based `dedupe_hash`
per transaction (re-importing the same file produces zero new rows, verified by test).
`BankTransaction` rows are never edited in place except `reconciliation_status`/match
bookkeeping — the parsed source fields are immutable.

**Matching engine** (`app/accounting/matching_engine.py`) — deterministic, named-signal
scoring (exact amount, invoice number in reference, payment reference, IBAN, counterparty
name, date proximity), confidence bands HIGH/MEDIUM/LOW/NONE from a plain numeric score
(never an opaque ML score), bounded combinatorial search for combined (1 bank tx : many
invoices) matches, explicit overpayment signal (surfaced as LOW for review, never silently
dropped or silently treated as exact). `app/accounting/reconciliation_service.py` turns a
SUGGESTED match into a real `Payment` on approval, and **reverses by voiding** the payment
(`Payment.voided`/`voided_by_user_id`/`voided_at`/`void_reason`) — never deletes it, so the
full audit history survives a correction.

**Real bug found and fixed while building this**: `_refresh_bank_transaction_status`
queried the database for a `PaymentMatch`'s own just-changed `status` immediately after
changing it, relying on an implicit autoflush. The app's real session factory
(`app/db/session.py`) is `autoflush=False`, so in the running dev server a bank
transaction stayed stuck at `SUGGESTED_MATCH` forever after its match was approved — the
pytest suite never caught this because the test fixture's session was `autoflush=True` by
default, silently papering over the exact mismatch that broke the real server. Fixed by
adding an explicit `db.flush()` inside `_refresh_bank_transaction_status`, and — more
importantly — changed `tests/conftest.py`'s session fixture to `autoflush=False` to match
production exactly, so this class of bug fails a test from now on. Verified against a
live `uvicorn` instance (not just pytest) after the fix: import → suggest → approve → the
transaction now correctly shows `MATCHED`.

**AI bookkeeping assistant** — `app/services/ai_categorization_provider.py`, same
forced-tool-use structured-output pattern as the existing extraction/assistant providers.
Suggestions always carry confidence, evidence, and reasoning, and
`requires_accountant_review` is explicitly set when confidence is low; the AI never writes
`expense_category` directly — `app/api/v1/automation.py`'s `/categorize` endpoint does, and
only on explicit accountant action.

**Expense categorization rules** — `app/models/categorization.py`, scoped by `company_id`
and never cross-company (verified by test — a rule created for one company produces zero
matches when queried against another). Correcting a category can optionally create a rule
from that correction for next time.

**Recurring detection** (`app/accounting/recurring_detection.py`) — groups bank transactions
by counterparty, classifies the interval (weekly/monthly/quarterly/annual) from the average
gap, flags `MISSING` when overdue. Detection only — never creates, approves, or pays
anything.

**Anomaly detection** (`app/accounting/anomaly_detection.py`) — four transparent,
evidence-carrying rules (duplicate payment, supplier bank-detail change, unexpected expense
increase, aging unmatched bank transaction), each idempotent (re-running clears and
regenerates only that rule's own open flags). No rule or code path ever sets a "fraud"
label — flags are leads for a human, not a verdict.

**Automation Centre** — `GET /companies/{id}/automation-centre` aggregates unmatched/
suggested/high-confidence-suggested counts, categorization backlog, open anomalies,
missing recurring patterns, and failed import batches into one dashboard query, plus
action endpoints to re-run detection and a `bulk-approve-high-confidence` endpoint that
only ever touches already-HIGH-confidence SUGGESTED matches (MEDIUM/LOW always need
individual review).

**Cash-flow forecasting** (`app/accounting/cash_flow.py`) — every figure is explicitly
labeled actual (imported bank movement, with a disclaimer that it's not a live balance),
confirmed (outstanding invoice totals from the ledger), or estimated (recurring-pattern
projection, VAT-return-not-yet-locked projection); the monthly projection table is marked
`is_estimate: true` on every row. Never presents a projection as a confirmed balance.

**Frontend** (all new pages, build/lint/typecheck clean): `/banking` (accounts, statement
import, import history), `/bank-transactions` (list + detail + exclude), `/reconciliation`
(suggested-match queue with approve/reject, separate approved-match queue with reverse —
reverse is only ever offered on an APPROVED match, matching the backend's own precondition),
`/automation` (dashboard tiles linking into each workflow, re-run-detection buttons),
`/categories` (rule CRUD, AI suggestion, manual categorize-and-remember), `/anomalies`
(list, acknowledge/dismiss), `/cash-flow` (actual/confirmed/estimated broken out visually,
disclaimers inline). `npx tsc --noEmit`, `npm run lint`, and `npm run build` all pass clean.

**Verification**: 38 new backend tests (13 service-level, 25 API-level — matching engine,
parsers, and banking API already had 32 from earlier in this session) plus the existing
suite, 205 total, all passing against a real Postgres test database. Additionally smoke-
tested against a live `uvicorn` dev server (separate port, existing dev server left
untouched) end-to-end: login → create company → create bank account → import a synthetic
CAMT.053 file → automatic match suggestion → manual categorization with AI suggestion →
rule creation → approve match → payment created → bank transaction correctly shows
`MATCHED` → recurring/anomaly detection endpoints run cleanly. All test/demo data is
synthetic; no real bank credentials or real customer financial records were used anywhere.

## Explicitly deferred (Phase 6)
- **Any live PSD2/Open Banking connection** — no TPP license, no bank sandbox access exists
  in this environment. The adapter boundary is shaped to accept one later; none is wired up,
  and nothing here claims otherwise.
- **SBR/Digipoort VAT filing** — unchanged from Phase 5's explicit non-claim; this phase
  doesn't touch it.
- **Automatic payments or automatic VAT submission** — explicitly out of scope per this
  phase's own instructions; no code path anywhere sends money or files a return.
- The 17-step synthetic E2E acceptance scenario from the phase spec was exercised in pieces
  (via the smoke test above and the API test suite) rather than as one single scripted run;
  a dedicated end-to-end test file was not written for the full sequence.
- A customer-facing cut of the new screens (Banking/Reconciliation/etc. are accountant-
  oriented; no customer-role view of any of this was built, consistent with Phase 5's
  customer-portal gap).

## What's implemented (Phase 8)

**Phase 7 does not exist.** Before starting, `git log` was checked (as the phase spec itself
asked): the most recent commit was `fa85fa9` (Phase 6). There is no Dutch Tax Compliance/
Government Integration code beyond Phase 5's research-only `docs/sbr-digipoort-integration.md`.
This phase is built on Phases 1–6 only; nothing here assumes a Phase 7 capability exists.

**Financial reporting engine** (`app/accounting/financial_reports.py`) — deterministic,
Decimal-only, reused everywhere else in this phase rather than duplicated: Profit & Loss,
Balance Sheet, Cash Flow Statement, a best-effort Trial Balance (explicitly labeled as such —
this ledger is single-entry, not double-entry), General Ledger, Debtors/Creditors with aging
buckets, VAT overview, and revenue/expense breakdowns. Monthly/quarterly/annual/custom periods
all go through one `resolve_period()`; previous-period and year-on-year comparisons reuse the
same P&L function twice and diff it. Company comparison is the same function called once per
authorized company — no separate multi-company engine.

**This ledger has no chart of accounts.** Fixed assets, inventory, equity, and loans are never
derived or guessed — `ManualBalanceSheetItem` is the only source for them, entered explicitly
by an accountant. Retained earnings is computed as cumulative net profit from the P&L engine
(a genuine double-entry link, not a plug), so the balance sheet legitimately balances once
everything that should be recorded is recorded, and **honestly does not balance** otherwise —
verified by test with both an unpaid invoice alone (balances, since AR and retained earnings
move together) and the same invoice with VAT (does not balance, because the VAT portion has
nowhere to go until a VAT return is computed for that period — a real gap, correctly flagged,
never hidden).

**Budgets** (`app/accounting/budget_service.py`, `app/models/budget.py`) — annual/monthly
revenue and expense budgets, actual-vs-budget variance (reusing the P&L engine's own category
buckets so a budget line and its actual always compare like for like), draft → submitted →
approved workflow (approval is accountant/admin-only; a business-owner role can create, revise,
and submit, never approve their own), and revisions as new immutable rows (`version`,
`supersedes_budget_id`) — the same pattern as ledger corrections, never editing an approved
budget in place. AI suggestions (`app/services/ai_budget_provider.py`, same forced-tool-use
pattern as the existing providers) only ever adjust a deterministic historical-average
baseline with a stated reason, and always require explicit accountant action to apply.

**Forecasting extension** (`app/accounting/financial_forecast.py`) — explicitly imports and
calls Phase 6's `cash_flow.build_cash_flow_forecast()` for the cash component rather than
reimplementing it, and adds revenue/expense/profit trend forecasting, confirmed (not
estimated) outstanding-invoice figures, VAT payment forecasting, and an explicit
non-fabricated corporate-tax placeholder (this system calculates Dutch VAT only). Every
forecast carries its horizon, the historical data period used, its stated assumptions, and an
uncertainty band — never presented as guaranteed.

**Scenario engine** (`app/accounting/scenario_engine.py`, `app/models/scenario.py`) — base/
optimistic/conservative/custom scenarios with named assumptions (revenue/expense % change,
new-hire monthly cost, payment delay, one-off equipment investment/financing). Pure function
of the forecast plus assumptions, recomputed fresh on every read; a `Scenario` row only ever
stores the assumptions, never a cached result, so nothing can go stale. Verified by test that
creating and comparing scenarios never writes to `AccountingTransaction`.

**KPI engine** (`app/accounting/kpi_engine.py`) — profitability (gross/operating/net margin,
ROA), liquidity (current/quick/cash ratio), efficiency (AR days, AP days, inventory turnover),
and business-performance (revenue/expense growth, recurring-expense ratio, customer/supplier
concentration) KPIs. Every KPI returns `{value, formula, source, period, explanation,
missing_data}` — a KPI whose inputs don't exist (no liabilities, no inventory movement
tracking, no prior-period data) returns `value: null` with `missing_data` explaining why,
verified by test, rather than showing a misleading 0% or infinite ratio.

**Working capital & payment intelligence** (`app/accounting/working_capital.py`) — extends
Phase 6's reconciliation data: customer/supplier average days-to-pay (only counting fully-
settled invoices — a partial payment has no settlement date yet), payment-delay alerts
(newly-overdue and 90+-days-overdue), working-capital trend across periods, customer/expense-
category concentration, and an explicitly-incomplete cash-conversion-cycle (DSO and DPO are
real; DIO is reported as unavailable rather than assumed zero, since inventory movements
aren't tracked). Read-only — never initiates a payment.

**Financial AI assistant** — one new endpoint, `POST /assistant/financial-question`, reusing
the exact existing `ai_assistant_provider`/`_respond()` pattern with a new facts bundle
(`assistant_facts.financial_intelligence_facts`) built from the reporting/forecast/KPI/working-
capital engines above. The assistant's system prompt was extended (one clause) to explain that
FACTS may contain forecast/scenario figures and must always be cited as such, never as a
confirmed actual. Verified live against the real Claude API with "why did my expenses increase
and how profitable was my business" — the model correctly declined to state an expense-growth
percentage (flagged as `missing_data` in FACTS) and correctly caveated the balance-sheet
imbalance and the absence of corporate tax from the profit figure, entirely from FACTS it was
given, inventing nothing.

**Dashboards** — `GET /dashboard/accountant` (portfolio across every accessible company:
current-month revenue/profit, VAT position, unreconciled bank transactions, balance-sheet
health) and `GET /dashboard/business-owner?company_id=` (single company: revenue/expenses/
profit, cash position, outstanding customer/supplier payments, VAT position, approved-budget
variance, a 3-month forecast summary). Both reuse the reporting/forecast/budget engines; no
new computation.

**Exports** (`app/reporting/management_report.py`, extending `app/api/v1/reports.py`) — PDF/
XLSX/CSV for Profit & Loss and Balance Sheet (reusing `PdfReportBuilder` and the openpyxl/csv
pattern from Phase 1–5's `financial_report.py`/`vat_report.py`), PDF/CSV for Budget vs Actual,
CSV for Scenario comparison. A single period-width parameter (monthly/quarterly/annual) on the
P&L/Balance-Sheet export doubles as the monthly management pack / quarterly review / annual
summary the spec names as separate products — built as one parameterized report rather than
three near-identical ones.

**Data integrity** — a JSON-safety helper (`app/api/v1/_json_safe.py`) converts every
Decimal/date in these report responses to a string before they leave the API, same discipline
as the rest of this codebase (money is never silently turned into a float by a framework
default). `AuditLog` rows (the existing Phase 1 mechanism, not a new one) are written for
budget approval and manual balance-sheet-item creation. Verified by test: monthly P&L sums
reconcile exactly to the annual P&L (and quarterly to annual) for the same data, a report
recomputed twice with no ledger change is byte-identical, and a locked transaction's figures
are provably immutable. **Known limitation, stated plainly**: this ledger has no period-level
lock that blocks a brand-new transaction from being posted with a backdated `invoice_date`
into an already-filed VAT period — an individual transaction's own figures are frozen once
approved/locked (enforced since Phase 3), but nothing yet stops a new one from landing in the
past. Full period locking would be a cross-cutting Phase 3/4 change, out of scope here, and is
not claimed to exist.

**Frontend** (all new pages, build/lint/typecheck clean): Financial Overview, Profit & Loss,
Balance Sheet (with the manual-item entry form), Budgets, Forecasts, Scenario Planning,
Financial KPIs, Working Capital, and Management Reports — plus the existing Cash Flow page
extended with a second tab for the new Cash Flow Statement (actual) alongside Phase 6's
forecast tab, rather than a confusingly-named duplicate nav entry. No new chart-library
dependency was added — simple CSS bar visualizations cover the one interactive chart used
(the forecast trend); every other page is tables and numbers, consistent with the rest of the
app's visual design. `npx tsc --noEmit`, `npm run lint`, and `npm run build` all pass clean.

**Verification**: 76 new backend tests (financial-reports engine, forecasting, scenarios,
KPIs, working capital, budgets, dashboards, assistant, exports, data integrity), 281 total,
all passing against a real Postgres test database. Additionally ran the full 16-step synthetic
E2E acceptance scenario from the phase spec against a live `uvicorn` instance end to end:
create company → post sales/purchase invoices → import a CAMT.053 statement → reconcile both
payments → generate P&L → generate balance sheet → verify the balance equation (correctly
flagged an imbalance caused by malformed test XML, a good demonstration of the "never force a
balance" requirement) → generate the cash flow statement → create and approve a budget →
compute variance → generate a 3-month forecast → create optimistic/conservative scenarios →
compare them → review KPIs → ask the live AI assistant why expenses increased → export P&L and
Balance Sheet PDFs and a Budget-vs-Actual CSV → verify an audit-log row was written for the
budget approval → verify the same P&L request returns byte-identical JSON on a second call.

## Explicitly deferred (Phase 8)
- **Full period locking** at the VAT-period level (see Data integrity above) — individual
  transaction immutability exists; a ledger-wide lock preventing new backdated postings into a
  filed period does not.
- **Department budgets** — the spec says "where applicable"; no department/cost-center entity
  exists in this system, so budget lines are company+category+month only.
- **Inventory turnover and the full cash-conversion cycle** — this ledger has no tracked
  inventory movement (only a manually-entered balance), so these are reported as unavailable
  rather than computed from an assumed zero.
- **Separate named report products** (monthly management pack / quarterly review / annual
  summary) are one parameterized P&L/Balance-Sheet export, not three distinct documents.
- **Scenario adjustments to cost-of-sales specifically** — a scenario currently scales total
  revenue and total expenses; it does not yet let gross margin itself be an assumption.
- Corporate income tax estimation — explicitly never fabricated; this system calculates Dutch
  VAT only, consistent with every prior phase's own scope.
