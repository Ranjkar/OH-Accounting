# Phase 18 — Production Readiness and Deployment Validation

| | |
|---|---|
| **Date** | 2026-11-05 |
| **Branch** | `phase-16-3-complete-internationalisation` @ `97f2d84` (no commits made) |
| **Companion docs** | `PHASE_18_DEPLOYMENT_RUNBOOK.md`, `PHASE_18_TEST_RESULTS.md` |
| **Verdict** | The backend **boots and operates correctly in production mode** — verified end to end against a real server and a scratch database. The **frontend production image still cannot reach the API** (audit 6.10, unfixed, out of Phase 17/18 scope). |

---

## 1. What was verified, and how

Everything below was executed, not inferred. Exact commands and raw output are in `PHASE_18_TEST_RESULTS.md`.

| Check | Method | Result |
|---|---|---|
| Full migration chain applies to a clean database | `createdb` scratch DB → `alembic upgrade head` | **PASS** — all 23 migrations, 48 tables, version `e4f7a9c2b1d8` |
| Migration rollback is safe | `alembic downgrade -1` → verify → `upgrade head` | **PASS** — constraint dropped and re-created cleanly |
| Fail-closed on missing secrets | `ENVIRONMENT=production` with placeholder secrets | **PASS** — `RuntimeError`, exit 1, names all four offenders, leaks no value |
| Production boot with real secrets | Scratch DB + generated secrets + `uvicorn` | **PASS** — server started, no errors |
| `/health` and `/ready` | HTTP GET | **PASS** — 200 `{"status":"ok"}` / 200 `{"status":"ready"}` |
| Database connectivity | `/ready` compares DB `alembic_version` to the code head | **PASS** |
| Security headers | `curl -I` | **PASS** — `nosniff`, `DENY`, `same-origin` |
| Authentication | unauthenticated → 401; real login → 200; bad token → 401 | **PASS** |
| **Session revocation (live)** | `POST /auth/logout` → 204, then reuse the same token | **PASS** — 401. This is Phase 17.3 verified against a running server, not only in tests |
| CORS enforcement | preflight from allowed vs disallowed origin | **PASS** — allowed origin echoed; disallowed origin received **zero** `Access-Control-Allow-Origin` headers |
| Compose file validity | `yaml.safe_load` both compose files | **PASS** — see §6 for why `docker compose config` could not run |

**No Docker image was built and no container was started.** No production system was contacted. No real customer data was touched. The scratch databases (`onholland_p18_migration_check`, `onholland_p18_boot`) were created and dropped within this phase.

---

## 2. Production configuration review

### 2.1 Secrets — fail-closed, verified

`backend/app/core/config.py` guards five secrets. Outside `PERMISSIVE_ENVIRONMENTS = {development, dev, test, testing}` the application **raises at import** if any is unset, blank, or equal to a value that is public in this repository.

The actual refusal, captured verbatim (secrets were never printed; the message names variables only):

```
RuntimeError: Refusing to start: ENVIRONMENT='production' but these secrets are unset, blank,
or still a value that is public in this repository: BSN_ENCRYPTION_KEY,
OPEN_BANKING_TOKEN_ENCRYPTION_KEY, MFA_SECRET_ENCRYPTION_KEY, BILLING_WEBHOOK_SECRET.
  - BSN_ENCRYPTION_KEY: Employee BSNs would be encrypted under a key that is committed to
    this repository … Generate one with: python -c 'from cryptography.fernet import Fernet; …'
  …
```

A `grep` for every placeholder literal across the full stderr+stdout of that run returned **0 matches** — the guard does not leak the values it is checking. `JWT_SECRET` was correctly absent from the offender list because `backend/.env` sets a custom value.

Three properties worth stating explicitly, because each closes a distinct bypass:

| Property | Why it matters |
|---|---|
| **Blank is an offence** | `JWT_SECRET=` in an env file yields `""`. An empty HMAC signing key is worse than a placeholder, and a value-equality check would not catch it. |
| **The `.env.example` literal is guarded too** | The template ships `JWT_SECRET=change-me-in-production`, which is *not* the code default `dev-secret-change-in-production`. A check comparing only against the code default would let an operator copy the template into `.env.prod` and sail past it while running a publicly-known signing key. |
| **Unrecognised environments fail closed** | `PERMISSIVE_ENVIRONMENTS` is an allowlist, so `ENVIRONMENT=prodction` refuses to start rather than falling through to the permissive branch. |

`repr=False` is set on all eleven secret-bearing fields (`jwt_secret`, `database_url`, `anthropic_api_key`, `kvk_api_key`, the three encryption keys, their three `*_previous` counterparts, `billing_webhook_secret`), so `repr(settings)` — which pytest, f-strings and exception contexts all reach for — no longer dumps them. `model_dump()` and normal attribute access are unchanged, so no consumer is affected.

### 2.2 CORS — validated at startup

`app/main.py::_validate_cors_origins()` fails closed outside a permissive environment on: a wildcard origin, a private/loopback/link-local host, or a plain `http://` origin on a named host. In development it warns — but only for non-loopback origins, so the documented `localhost` defaults do not print noise on every startup.

Verified live: a preflight from `https://accounting.example.nl` was echoed back; a preflight from `https://evil.example` received **zero** `Access-Control-Allow-Origin` headers.

**Outstanding, deliberately not changed:** the default allow-list in `app/main.py` still contains `http://192.168.68.105:3000` — a developer's LAN address, present as an *uncommitted user change* that Phase 17 was required to preserve. The guard now detects and reports it in development and refuses to boot with it in production, which is a stronger control than a silent revert. Reverting it is a one-line manual action (§7).

### 2.3 Cookie, session and token settings

| Setting | Value | Assessment |
|---|---|---|
| Token transport | `Authorization: Bearer` header | No cookie is used for auth, so CSRF is genuinely not applicable. |
| Token storage (client) | `localStorage` | **Weakness.** Readable by any script on the origin. Combined with the 24h lifetime this is the main residual session risk. Audit 7.17. |
| `access_token_expire_minutes` | `60 * 24` (24 hours) | **Long.** No refresh token exists in the API contract at all, so shortening it would break sessions. Audit 7.17. |
| Revocation | `token_version` compared on every request | **Correct and now actually exercised** — `logout()` calls the endpoint as of Phase 17.3, verified live above. |
| Locale cookie | `onholland-locale` | Non-sensitive. |
| Account lockout | 5 failures / 15 minutes | Works, but keys on the account, so a known email can be locked out indefinitely by an attacker. Audit 6.9. |
| Password policy | `min_length=8` on invitation-accept only | **Gap.** No strength rule, no maximum (bcrypt truncates at 72 bytes), and password reset has no constraint at all. Audit 8.2. |

### 2.4 Database configuration

| Item | State |
|---|---|
| Driver | `postgresql+psycopg` (psycopg 3) |
| Pool | **Default `QueuePool`, no explicit sizing, no `pool_pre_ping`** — a Postgres restart surfaces as 500s rather than transparent reconnection. Audit 7.6. |
| Dev URL default | Hardcodes `sam@localhost` — a developer's username in the default config |
| Prod URL | Composed in `docker-compose.prod.yml` from `POSTGRES_USER`/`POSTGRES_PASSWORD`, on an `internal: true` network with no host route |
| Migrations at startup | `CMD alembic upgrade head && uvicorn …` — races if the service is ever scaled beyond one replica |
| Session factory | `autoflush=False`, matching the test fixture |

### 2.5 Logging

Verified in the production boot: structured JSON, one line per request, with `request_id` correlation.

```
{"timestamp": "…", "level": "INFO", "logger": "app.main",
 "message": "request method=POST path=/api/v1/auth/login status=200 duration_ms=233.9",
 "request_id": "19bf49ec-…"}
```

- Authentication failures are logged with the reason and no credential material.
- `grep` across every `logger.*` call in `app/` for `password|token|secret|bsn|iban|payload|body|header|credential` returns **zero hits**.
- The new Phase 17 guards log variable **names** only.
- `/health` exposes an exception *class name* on failure; `/ready` correctly returns only `{"status":"not_ready"}`.
- Unexpected exceptions are logged with `exc_info` and a `request_id`.

**Gaps:** no tenant/user identifier is attached to log lines, so correlating a request to a tenant requires the audit log. No metrics endpoint, no error tracking, no log shipping (audit 4.3). Background jobs (`BackgroundTasks`) log failures but have no durable queue, no retry across restarts, and no dead-letter visibility.

### 2.6 No secrets committed or embedded

| Check | Result |
|---|---|
| `git log --all -- backend/.env` | empty — never committed |
| Pickaxe for `change-me-in-production` across all history | no hits |
| `git check-ignore -v backend/.env` | covered by `.gitignore:5` |
| `backend/storage/` tracked | no |
| Secrets in the frontend bundle | `NEXT_PUBLIC_API_URL` is the only `NEXT_PUBLIC_*` reference; no API key, no secret. Verified by grep across `frontend/`. |
| Secrets introduced by this phase | none — only empty placeholders in `.env.example` / `.env.prod.example` |

**The committed placeholder literals in `config.py` remain.** They are public in git history and cannot be un-leaked; they must be treated as burned and rotated (§7 item 1). Phase 18 did not rotate them, because rotation without a backup and a tested re-encryption path is exactly what the Phase 17 brief forbade — that path now exists (`scripts/rotate_encryption_keys.py`), so rotation is unblocked but still an operator action.

---

## 3. Database and recovery readiness

### 3.1 Migration consistency — now verified for the first time

Audit finding 7.14 established that the migration chain had **zero** test coverage: `tests/conftest.py:37` builds the schema with `Base.metadata.create_all`, and `grep -rn alembic tests/` returned nothing. Phase 18 closed that gap manually:

```
createdb onholland_p18_migration_check
alembic upgrade head      → 23 migrations applied, 48 tables, version e4f7a9c2b1d8
alembic downgrade -1      → uq_accounting_transaction_source_document dropped, version d90e97d4bc35
alembic upgrade head      → constraint re-created
dropdb onholland_p18_migration_check
```

Single head throughout; no branching, no orphaned `down_revision`.

**Still outstanding:** there is no *automated* migration check, and the 54 indexes created by migration `3853605281ec` are deliberately **not** mirrored in model metadata — that migration's own docstring warns a future `alembic revision --autogenerate` "will therefore propose DROPPING these indexes". Because tests use `create_all`, they run against a schema *without* those indexes. Roadmap Tier 2.1 / 4.5.

### 3.2 Indexes and constraints

Phase 19 added `uq_accounting_transaction_source_document` (audit 6.6) with a migration that **refuses to run** if duplicate postings already exist, reporting the offending document and transaction ids rather than silently picking a winner. No financial record is deleted or modified.

Still missing on the hottest query paths (audit 7.18): `accounting_transactions(vat_period_id)`, `accounting_transactions(company_id, invoice_date)`, `transaction_line_items(transaction_id)`, `payments(transaction_id)`, `documents(company_id, sha256_hash)`, `bank_transactions(company_id, booking_date)`.

Missing uniqueness: `FinancialYear(company_id, year)`, `VatPeriod(financial_year_id, label)`, `Employee.linked_user_id`. No FK has `ondelete=`, so company deletion raises an FK violation.

### 3.3 Backup and restore — scripts reviewed, defects open

`scripts/backup_db.sh` and `scripts/restore_db.sh` exist and were drilled twice by the project against disposable databases. Defects found by the audit and **not fixed in Phase 18** (they change operational behaviour and need an operator decision):

| Defect | Consequence |
|---|---|
| `restore_db.sh:16` — `EXISTING_TABLES=$(psql … 2>/dev/null \|\| echo "0")` | The overwrite guard is **defeated by any connection error**: if `psql` fails, the guard reads "0 tables" and proceeds. |
| Dumps are unencrypted, default permissions, no `chmod 600` | The dump contains plaintext salaries, addresses and the full ledger. BSNs are encrypted, but under a committed key. |
| No retention or rotation | Full personal-data copies accumulate indefinitely — itself a GDPR minimisation concern. |
| `backup_db.sh` docstring claims it reads `DATABASE_URL`; it does not | Connects to the wrong host/user against the prod compose stack. |
| `restore_db.sh dump --force` (omitting the DB name) | Sets `DB_NAME="--force"`, then runs `createdb -- --force`. |
| No schedule, no off-host copy | A disk failure loses the database and its backups together. |

The runbook in `PHASE_18_DEPLOYMENT_RUNBOOK.md` §4 documents the correct procedure **and** these caveats, so an operator is not misled by the scripts' own docstrings.

### 3.4 Transaction handling and interrupted operations

- `_ensure_financial_year_open` is the single choke point for document posting, manual entries and corrections — verified real.
- A lifespan hook resets documents stuck in `PROCESSING` after a crash.
- `approve_match` / `reverse_match` void rather than delete, preserving the audit trail — verified end to end in `test_phase20_e2e_scenarios.py`.
- `lock_vat_return` commits **twice** (status change, then the transaction cascade), so a failure between them leaves the return locked with its transactions unlocked. Audit 7.9. **Not fixed.**
- `GET /vat-returns` still writes and recomputes on a read, with no audit row and reachable by a `viewer`. Audit 7.9. **Not fixed** — it needs a product decision about whether a GET may mutate.

---

## 4. Deployment blockers

| # | Blocker | Severity | Status |
|---|---|---|---|
| 1 | **`NEXT_PUBLIC_API_URL` never reaches the browser bundle.** `frontend/lib/api.ts:1` reads it at module scope; Next.js inlines `NEXT_PUBLIC_*` at *build* time; `frontend/Dockerfile` has no matching `ARG`; compose supplies it at *runtime*. The production bundle is hardcoded to `http://localhost:8000/api/v1`, so every visitor's browser calls their own machine. | **Critical** | **OPEN.** Audit 6.10. Out of Phase 17 scope (not a security-config item) and not attempted in Phase 18 because the fix changes the build pipeline. One-line Dockerfile `ARG`/`ENV` plus a compose `build.args`, or better a same-origin `rewrites()`. |
| 2 | Five committed placeholder secrets must be rotated. | **Critical** | **BLOCKED on operator** — requires a backup first. Tooling and procedure now exist. |
| 3 | No TLS / reverse proxy provisioned. | High | **BLOCKED on operator** — environment-specific by design. |
| 4 | Rate limiting is one shared bucket behind any proxy (`request.client.host` is the proxy). Ten logins/minute platform-wide, and a trivial unauthenticated DoS. | High | **OPEN.** Audit 6.9. |
| 5 | MFA can be re-enrolled without proving possession of the existing factor. | High | **OPEN.** Audit 6.11. |
| 6 | Password reset cannot deliver a token (generated, hashed, discarded). | High | **OPEN.** Audit 6.8. |
| 7 | No transactional email provider. | High | **BLOCKED on operator** — needs a provider account. |
| 8 | Frontend image ships the full dev-dependency tree; `npm install` not `npm ci`; `npm` as PID 1. | Medium | **OPEN.** Audit 7.6. |
| 9 | No CI, no coverage tooling, no backend linter or type checker. | High | **OPEN.** Audit 11.1. |
| 10 | **No git remote.** The entire repository exists only on this machine. | High | **OPEN** — five minutes of work, highest ratio of value to effort in this document. |

---

## 5. Known risks accepted for now

- `VatPeriod.status` is still never assigned, so the balance sheet's VAT liability never clears and the dashboard's "open periods" counts every period ever. **Audit 6.1 — the highest-value open functional defect.** Not fixed in Phase 19 because it needs new endpoints and a decision about who may mark a period filed or paid.
- Transaction `approval_status` is still never used as a filter by any report or VAT calculation. Audit 6.3. Not fixed because it needs a product decision about whether a `DRAFT` manual entry belongs in a return — changing it unilaterally would alter every reported figure.
- No FX handling outside the VAT engine; reports sum `net_amount` across currencies. Audit 7.1. Not fixed: it changes many reported numbers at once and needs its own test cycle.
- `ManualBalanceSheetItem` sums point-in-time balances as though they were flows. Audit 7.2. Not fixed: the correct semantics (movements vs. latest-balance) is an accounting decision.
- Tax rules are frozen at 2025 (`CURRENT_TAX_YEAR`) and VAT at `nl-2024`, with the default path never deriving the year from the clock. **Audit 6.5 — a live compliance risk in 2026.** Not fixed: adding a 2026 rule set requires authoritative source verification, and inventing rates is explicitly forbidden.
- No eager loading anywhere; all aggregation in Python. Audit 7.4.
- `python-jose` 3.3.0 and `passlib` 1.7.4 are unmaintained. Audit 7.16.

Each is recorded in `PHASE_20_KNOWN_ISSUES.md` with its evidence and a recommended fix.

---

## 6. Note on `docker compose config`

Docker 29.4.0 is installed, but `docker compose -f docker-compose.prod.yml config` exits 1 with `env file .env.prod not found`. That file is gitignored and operator-created, and `env_file: .env.prod` is a pre-existing requirement of the compose file, not something introduced by these phases. Creating it was out of scope. Both compose files were validated structurally instead (valid YAML, correct service set, `ENVIRONMENT` under the backend service, `env_file` preserved, Postgres still internal-only with no published ports) — output in `PHASE_18_TEST_RESULTS.md`.

---

## 7. Manual operations required

1. **Rotate all five secrets.** Take a database backup first, then follow the procedure in `PHASE_17_SECURITY_REMEDIATION.md` §7 (which `scripts/rotate_encryption_keys.py` now supports for all three encrypted classes, with rollback).
2. **Set `BSN_ENCRYPTION_KEY` in `backend/.env`.** This development environment is currently encrypting employee BSNs under the committed public key, and `backend/storage/` contains what appear to be real uploaded invoices. Treat the local database as holding real personal data.
3. **Revert the CORS default** in `backend/app/main.py` to `http://localhost:3000` and move the LAN origin into `backend/.env`.
4. **Fix the frontend build-time API URL** (blocker 1) before any deployment.
5. **Provision TLS and the reverse proxy**, and set uvicorn `--proxy-headers` / `--forwarded-allow-ips` so the rate limiter sees real client addresses.
6. **Configure a transactional email provider** — unblocks password reset and both invitation flows.
7. **Add a git remote and push.**
8. **Delete the three stray backup files** once the `globals.css` fix is committed.
9. **Harden the backup scripts** (fail-closed restore guard, `chmod 600`, encryption, retention, off-host copy) and schedule them.
10. **Stand up CI** — the migration up/down/up check and an "autogenerate must be empty" gate are the two highest-value jobs.
