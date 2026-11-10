# Phase 20 — Operations Handover

For whoever runs this system. Assumes no prior knowledge of the codebase.

**Read `PHASE_18_DEPLOYMENT_RUNBOOK.md` first for the deployment procedure. This document is about operating it afterwards — and about the things that will bite you.**

---

## 1. Current state in one paragraph

OnHolland Accounting is a multi-tenant Dutch VAT and accounting platform: FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL 16 backend (18.4k lines, 26 routers, 217 endpoints, 23 migrations), Next.js 16 App Router frontend (17.9k lines, 55 routes), 4 interface languages including RTL Persian and Arabic. Built in four days across 16 self-declared phases, then hardened across Phases 17–20. **662 backend tests and 175 frontend tests pass.** It boots and operates correctly in production mode — verified. **It cannot currently be deployed**, because the frontend production image hardcodes `localhost:8000` into the browser bundle (`PHASE_20_KNOWN_ISSUES.md` #1). There is no CI, no monitoring, and **no git remote**.

---

## 2. The five things that will bite you first

### 2.1 The deployment will start cleanly and not work

`/health` and `/ready` both return 200, all containers are healthy, and the login page loads — then every API call from the browser goes to `localhost:8000` on the *user's* machine. Cause and fix: known issue #1. **Always verify step 6 of the runbook's post-deployment checklist** (open DevTools → Network → confirm requests go to your API origin). No automated check covers this.

### 2.2 Ten logins a minute, for the entire platform

The rate limiter keys on `request.client.host`. Behind the reverse proxy the deployment docs prescribe, that is the proxy — so every user shares one bucket. The eleventh login attempt anywhere returns 429. Symptom: users report "I can't log in" in clusters, always with a 429, and it clears after a minute. Cause and fix: known issue #8. Until fixed, either raise `RATE_LIMIT_LOGIN_PER_MINUTE` (weakens brute-force protection) or configure uvicorn `--proxy-headers` with `--forwarded-allow-ips` and switch the limiter to the forwarded address.

### 2.3 A user who forgets their password cannot recover it

Password reset is non-functional at both ends: the backend generates the token, hashes it, and **discards it** (never emailed, logged or returned), and there is no UI. There is also no transactional email provider, so neither invitation flow can email either — both return the raw token in the HTTP response for out-of-band relay. Cause: known issue #9. **Interim procedure:** an operator resets the password directly, then forces a change. Do not paste a new password into a ticket or a chat.

### 2.4 A user who loses their authenticator is locked out

There are no MFA recovery codes. **Interim procedure**, with the user's identity verified out of band:

```sql
UPDATE users SET mfa_enabled = false, mfa_secret_encrypted = NULL,
                 token_version = token_version + 1
WHERE email = 'user@example.com';
```

The `token_version` bump revokes every outstanding session, so a stolen token cannot be used after the reset. The user then re-enrols. Log the intervention — **the application will not**, because this bypasses it.

### 2.5 The VAT liability on the balance sheet never goes away

`VatPeriod.status` is never assigned by any code path, so `_outstanding_vat_position` sums every VAT return the company has ever computed, forever. Paying a VAT bill does not reduce it. The dashboard's "open VAT periods" is likewise "all periods ever". Cause: known issue #4 — **the highest-value open defect**. Until fixed, treat the balance sheet's `vat_payable`, `total_liabilities`, `is_balanced` and every derived ratio as unreliable, and tell users so.

---

## 3. Routine operations

### 3.1 Deploy

`PHASE_18_DEPLOYMENT_RUNBOOK.md` §3. Summary: build → start Postgres and wait for healthy → start the backend and **watch the migration log** → start the frontend → run the eight-step post-deployment checklist. **One backend replica only** — the CMD runs `alembic upgrade head` and the rate limiter is per-process.

### 3.2 Health

| Endpoint | Meaning | Action on failure |
|---|---|---|
| `GET /health` | Process up **and** the database answers `SELECT 1` | 503 ⇒ check Postgres. The body includes an exception *class name* only — no message, no traceback. |
| `GET /ready` | Additionally: the DB's `alembic_version` matches the code's migration head | `{"status":"not_ready"}` ⇒ **image and database are on different revisions.** Do not route traffic. Usually an old image against a newly-migrated DB or the reverse. |

Neither endpoint is authenticated and neither leaks schema details.

### 3.3 Logs

Structured JSON, one line per request, with a `request_id` that is echoed to the client in a response header and written to `AuditLog` rows:

```json
{"timestamp":"2026-11-05T17:34:32+0100","level":"INFO","logger":"app.main",
 "message":"request method=POST path=/api/v1/auth/login status=200 duration_ms=233.9",
 "request_id":"19bf49ec-d981-40ae-8fa9-5b9e4e5d2313"}
```

- Grep a `request_id` to follow one request across log lines and audit rows.
- **No tenant or user id is attached to log lines.** To attribute a request to a tenant, use `AuditLog` (which carries both) rather than the application log.
- Startup emits one warning per guarded secret still on a placeholder value, and one per non-loopback CORS origin in development. Both name variables only; **neither ever prints a value**.
- There is no aggregation, no metrics endpoint and no alerting. Nothing pages anyone.

### 3.4 Backups

```bash
cd backend && ./scripts/backup_db.sh onholland_accounting
```

**Four caveats you must work around** (full detail in the runbook §5):

1. It does **not** read `DATABASE_URL` despite its docstring. Set `PGHOST`/`PGUSER`/`PGPASSWORD`, or `docker compose exec` into the `postgres` service.
2. The dump is **unencrypted** with default permissions and contains plaintext salaries, addresses and the whole ledger. `chmod 600`, encrypt, move off-host.
3. No retention — dumps accumulate, each a full copy of personal data.
4. **Uploaded documents are not in the database.** Back up the `backend_storage` volume separately:
   ```bash
   docker run --rm -v accounting_backend_storage:/data -v "$PWD/backups:/backup" alpine \
     tar czf /backup/storage-$(date +%F).tar.gz -C /data .
   ```

There is **no schedule**. Backups happen only when someone remembers.

### 3.5 Restore

```bash
psql -d "$DB" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"   # ALWAYS do this first
cd backend && ./scripts/restore_db.sh <dump> <db-name> --force
```

**The script's own overwrite guard is unreliable** — `|| echo "0"` means any `psql` connection error reads as "empty database" and the guard passes, after which `pg_restore --clean --if-exists --force` drops everything. Always run the count query yourself. Argument order is `<dump> <db> --force`; omitting the db name makes it `createdb -- --force`.

### 3.6 Migrations

They run automatically in the backend's `CMD`. To inspect or reverse manually:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend alembic current
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend alembic history | head
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend alembic downgrade -1
```

Single head: `e4f7a9c2b1d8`. The chain has been verified `upgrade head` → `downgrade -1` → `upgrade head` against a clean database.

**Two traps:**

- **Never run `alembic revision --autogenerate` and apply its output.** Migration `3853605281ec` creates 54 indexes that are deliberately absent from model metadata; autogenerate will propose dropping all of them. Its own docstring says so.
- Phase 19's `e4f7a9c2b1d8` **refuses to run** if any document has already been posted to the ledger twice, reporting the offending `document_id`s and transaction ids. That is intentional — it will not pick a winner or delete anything. Resolve each pair with a voiding correction (`ledger_service.create_correction`), never a `DELETE`, then re-run.

### 3.7 Encryption key rotation

Full procedure with rollback in `PHASE_17_SECURITY_REMEDIATION.md` §7. Summary: backup → generate a new key → move the current key to `*_PREVIOUS` and set the new one as current → restart → `scripts/rotate_encryption_keys.py --dry-run` → `--yes` → **verify** (a masked BSN displays, an MFA code verifies, an Open Banking sync succeeds) → only then remove the old key from `*_PREVIOUS`.

Rollback at any point before the last step is an environment change only: put the old key back. Nothing in the database needs restoring, because the old key still decrypts everything throughout.

The script refuses to migrate onto a key that is still a public placeholder, and never prints a key or a plaintext value.

**`docs/encryption-key-rotation.md` is out of date** — it still says "the only thing encrypted at rest in this system is the employee BSN". Three classes are encrypted: BSN, Open Banking tokens and MFA secrets.

### 3.8 Creating the first owner

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend python -m app.seed
```

**This creates `admin@onholland.nl` with the password `changeme123` and role `admin`, not `owner`.** Change the password immediately, and promote to `owner` if the tenant needs one — `users.py` protects the last active owner, so a tenant with zero owners cannot manage owner-level roles.

### 3.9 Onboarding an employee to the self-service portal

**There is no UI for this.** `POST /employees/{id}/invite-self-service` is the only way an `employee`-role account is created, and it has no frontend caller. It must be invoked directly, and it writes **no audit log** — so record the intervention yourself.

---

## 4. Incident playbook

### Suspicious cross-tenant access

Tenant isolation was hardened in Phase 17 and is covered by 22 mutation-verified tests. If you nevertheless suspect a leak:

1. Identify the caller's role. `owner` and `admin` bypass the *company-membership* check by design (within their own tenant) — they do **not** bypass the tenant check.
2. Query `AuditLog` for the actor: `SELECT * FROM audit_logs WHERE user_id = ? ORDER BY created_at DESC`. Note that a cross-tenant write stamps `tenant_id` with the **actor's** tenant, so search by `user_id`, not by the victim's tenant.
3. Check `request_id` correlation against the application log for the same window.
4. Revoke sessions immediately: `POST /api/v1/users/{id}/revoke-sessions`, or `UPDATE users SET token_version = token_version + 1 WHERE id = ?`.

### Suspected secret compromise

1. Do **not** paste the suspect value anywhere.
2. Rotate it via §3.7. The old key stays in `*_PREVIOUS` so nothing becomes undecryptable mid-rotation.
3. For `JWT_SECRET`, rotation invalidates **every** session platform-wide — users must log in again. Do it in a maintenance window.
4. For `BILLING_WEBHOOK_SECRET`, coordinate with the billing provider; forged webhooks can flip subscription status.

### A document is stuck in `PROCESSING`

The lifespan hook resets stuck documents on startup. Restarting the backend clears them. Background work is `BackgroundTasks` plus an in-process `ThreadPoolExecutor` — **there is no durable queue, no retry across restarts and no dead-letter store**, so a job lost to a restart is simply lost and must be re-triggered.

### A VAT return looks wrong

Work through these in order — all four are known open issues:

1. Is the company **cash-based**? Before Phase 19 such a company's return was all zeros. Verify the transactions have a `vat_period_id`.
2. Are there **DRAFT** transactions in the period? Approval status is not a filter on any calculation (known issue #5), so drafts are included.
3. Are boxes **2a, 3a, 4a or 1d** zero? They cannot be populated automatically (known issue #12).
4. Are there **foreign-currency** transactions? Reports outside the VAT engine ignore currency entirely (known issue #10). The VAT engine itself handles FX correctly.

`GET /vat-returns/{id}/reconciliation` is the diagnostic: it cross-checks ledger totals, VAT by rate, pending documents, duplicates, validation errors, unresolved FX and prior corrections.

### A payroll run looks wrong

Almost certainly the tax year. `CURRENT_TAX_YEAR = 2025` and nothing derives it from the clock, so a 2026 run silently uses 2025 brackets, rates and caps (known issue #6). The computed `tax_year` is printed in the payslip and annual-statement PDF footers — check it.

---

## 5. Escalation and ownership

There is no on-call rotation, no runbook owner and no vendor relationship recorded in this repository. **Establish all three before any production use.**

External dependencies and their status:

| Dependency | Status | Owner action |
|---|---|---|
| Anthropic API | Real, optional. Without a key, extraction and the assistant fall back to deterministic stubs that route everything to manual review. | Monitor spend. Note that two tests make real API calls unless `ANTHROPIC_API_KEY=""` is set (known issue: audit 7.13). |
| KVK API | Real, sandbox. Uses KVK's own published test key. `/kvk/lookup` is **not rate-limited**. | A production key requires a signed KVK agreement. Published pricing is €6.40/month + €0.02/query. |
| PSD2 / Open Banking | **Blocked.** No DNB/EBA-authorised TPP registration. Stub only; no network I/O. | Registration is a months-long regulatory process. |
| SBR / Digipoort | **Blocked.** No PKIoverheid certificate, no Logius registration. The old Digipoort retired **2026-04-01**, so any future work must target its replacement. | Read `docs/government-integrations.md` before starting. |
| Billing / Mollie | Stub with real HMAC verification. No provider account. | Requires a provider account and a real `BILLING_WEBHOOK_SECRET`. |
| Email | **Not configured.** Blocks password reset and both invitation flows. | Choose a provider and wire it. |

---

## 6. What to do in the first week

In this order. Items 1–4 are under a day each and remove the largest risks.

1. **Add a git remote and push.** Nothing is backed up.
2. **Fix the frontend build-time API URL** (known issue #1). Without it there is no deployment.
3. **Rotate the five secrets**, starting with a backup (known issue #2, procedure §3.7).
4. **Stand up CI** with four jobs: `alembic upgrade head && downgrade base && upgrade head`; `alembic revision --autogenerate` failing if non-empty; the full pytest suite with `ANTHROPIC_API_KEY=""`; and `tsc --noEmit && eslint && next build && vitest run`. Add `gitleaks`.
5. **Wire `VatPeriod.status`** (known issue #4) — the highest-value functional fix.
6. **Fix the rate limiter's client-key resolution** (known issue #8) before any multi-user use.
7. **Fix MFA step-up** (known issue #7).
8. **Wire a transactional email provider** (known issue #9) — unblocks password reset and both invitation flows.
9. **Make the default tax year clock-derived** so a missing 2026 rule set fails loudly instead of silently serving 2025 rates (known issue #6, first part — no new rates required).
10. **Correct the seven inaccurate documents** listed in known issue #46, so the next operator is not misled by them.

Then work down `PHASE_20_KNOWN_ISSUES.md` in priority order, and make the product decision in `PHASE_19_PRODUCT_COMPLETENESS.md` §3 — single-entry management-information tool, or a real double-entry general ledger — before investing further in features.
