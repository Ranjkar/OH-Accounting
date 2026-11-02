# OnHolland Accounting

AI-powered accounting and Dutch VAT administration platform. Phase 1 (Foundation) and
Phase 2 (AI Document Intelligence) complete.

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

## Explicitly deferred (not needed yet)
- Docker for backend/frontend, Redis, Celery — single-process BackgroundTasks is enough
  at current volume (Phase 2); add a real queue if upload throughput or multi-worker
  scaling requires durability across restarts
- Azure Blob storage, encryption at rest, SBR integration — Phase 5
- VAT box calculation, the deterministic accounting/ledger engine, accountant reporting — Phase 3/4
- Per-row AI extraction for XLSX/CSV (currently deterministic column-mapping only)
