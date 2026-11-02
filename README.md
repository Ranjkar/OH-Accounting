# OnHolland Accounting

AI-powered accounting and Dutch VAT administration platform. Phase 1 (Foundation),
Phase 2 (AI Document Intelligence) and Phase 3 (Accounting Ledger & Dutch VAT Engine)
complete.

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
