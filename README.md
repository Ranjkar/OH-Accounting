# OnHolland Accounting

AI-powered accounting and Dutch VAT administration platform. Phase 1 (Foundation) complete.

## Stack
- Backend: FastAPI + SQLAlchemy + Alembic + PostgreSQL, JWT auth
- Frontend: Next.js (App Router) + TypeScript + Tailwind CSS

## Local development

**Database** (via Homebrew, already running as a service):
```
brew services start postgresql@16
createdb onholland_accounting
```

**Backend**:
```
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # adjust if your DB url differs
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed   # creates admin@onholland.nl / changeme123
.venv/bin/uvicorn app.main:app --reload --port 8000
```

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
- Audit log table (used for company creation so far; wired up further as more mutating actions are added)
- Next.js UI: login, dashboard, company list/create, company detail with VAT period tables

## Explicitly deferred (not needed yet)
- Docker for backend/frontend, Redis, Celery, Azure storage — nothing async or cloud-deployed yet (Phase 2+/5)
- Document upload, AI extraction, VAT calculation engine, reporting — later phases per CLAUDE.md
