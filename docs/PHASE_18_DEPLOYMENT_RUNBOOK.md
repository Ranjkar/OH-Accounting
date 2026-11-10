# Phase 18 — Deployment Runbook

Operator-facing procedure for deploying OnHolland Accounting. Written against the code as it exists at `97f2d84` plus the Phase 17–19 working-tree changes.

> **Do not follow this runbook until blocker 1 in `PHASE_18_PRODUCTION_READINESS.md` §4 is fixed.** The frontend production image currently hardcodes `http://localhost:8000/api/v1` into the browser bundle, so a deployment following these steps exactly would produce a stack that starts cleanly, passes every health check, and is completely unusable.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Docker Engine ≥ 24 with the compose plugin | 29.4.0 verified locally |
| A reverse proxy terminating TLS | nginx or Caddy. **Not** bundled — see `docs/production-deployment.md` for a worked nginx example. |
| A public DNS name for the frontend and one for the API | Both must be `https://`. |
| Postgres 16 | Provided by the compose file on an internal-only network. |
| An Anthropic API key | Optional. Without it, AI extraction and the assistant fall back to deterministic stubs that route everything to manual review — the application remains fully functional. |
| A transactional email provider | **Not integrated.** Without it, password reset and both invitation flows cannot deliver their tokens. See §7. |

---

## 2. Generate secrets

Generate each value **on the target host**, directly into `.env.prod`. Never paste a secret into a shell history, a ticket, a chat, or a commit.

```bash
cp .env.prod.example .env.prod
chmod 600 .env.prod

# JWT signing key
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
# Three independent Fernet keys -- do NOT reuse one for all three
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'   # BSN
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'   # Open Banking
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'   # MFA
# Billing webhook HMAC secret
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
# Postgres password
python3 -c 'import secrets; print(secrets.token_urlsafe(24))'
```

`.env.prod` must define **all** of:

```
POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
ENVIRONMENT=production
JWT_SECRET
BSN_ENCRYPTION_KEY
OPEN_BANKING_TOKEN_ENCRYPTION_KEY
MFA_SECRET_ENCRYPTION_KEY
BILLING_WEBHOOK_SECRET
CORS_ALLOWED_ORIGINS=https://your-frontend-origin
NEXT_PUBLIC_API_URL=https://your-api-origin/api/v1
ANTHROPIC_API_KEY            (optional)
LOG_LEVEL=INFO
```

Leave the three `*_PREVIOUS` variables **empty** unless a key rotation is in progress.

### The application will refuse to start if you get this wrong

This is intentional (Phase 17.4). With `ENVIRONMENT=production`, startup raises `RuntimeError` naming every offending variable and the command to generate it, if any guarded secret is unset, blank, or equal to a value that is public in this repository. It also refuses if `CORS_ALLOWED_ORIGINS` contains a wildcard, a private/loopback/link-local address, or a plain `http://` origin.

**Verify locally before shipping:**

```bash
cd backend
ENVIRONMENT=production \
  JWT_SECRET=… BSN_ENCRYPTION_KEY=… OPEN_BANKING_TOKEN_ENCRYPTION_KEY=… \
  MFA_SECRET_ENCRYPTION_KEY=… BILLING_WEBHOOK_SECRET=… \
  CORS_ALLOWED_ORIGINS=https://your-frontend-origin \
  DATABASE_URL=postgresql+psycopg://…/scratch_db \
  .venv/bin/python -c "import app.main; print('boots')"
```

If that prints `boots`, the configuration is acceptable. If it raises, the message tells you exactly what to fix. No secret value is ever printed by this check.

---

## 3. Startup procedure

```bash
# 1. Build
docker compose -f docker-compose.prod.yml --env-file .env.prod build

# 2. Start Postgres first and wait for it to be healthy
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d postgres
docker compose -f docker-compose.prod.yml --env-file .env.prod ps

# 3. Start the backend. Its CMD runs `alembic upgrade head` before uvicorn.
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d backend

# 4. Watch the migration log BEFORE the frontend comes up
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f backend

# 5. Start the frontend (depends_on: backend service_healthy)
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d frontend
```

**Scale the backend to exactly one replica.** `CMD alembic upgrade head && uvicorn …` races if two replicas migrate concurrently, and the in-memory rate limiter is per-process (audit 6.9, 7.6).

---

## 4. Health checks

| Endpoint | Auth | Meaning | Healthy response |
|---|---|---|---|
| `GET /health` | none | Process is up **and** the database answers `SELECT 1` | `200 {"status":"ok"}` |
| `GET /ready` | none | Additionally: the database's `alembic_version` matches the code's migration head | `200 {"status":"ready"}` |

```bash
curl -fsS https://your-api-origin/health
curl -fsS https://your-api-origin/ready
```

`/ready` returning `{"status":"not_ready"}` after a deployment means **the image and the database are on different migration revisions** — almost always an old image against a newly-migrated database, or the reverse. Do not route traffic to it. Neither endpoint leaks schema details or migration ids.

Verified during Phase 18 against a real server: both returned 200, security headers (`x-content-type-options: nosniff`, `x-frame-options: DENY`, `referrer-policy: same-origin`) were present, unauthenticated API access returned 401, login succeeded, logout returned 204 and the same token was then rejected with 401, and a CORS preflight from a disallowed origin received no `Access-Control-Allow-Origin` header.

---

## 5. Backup and restore

### 5.1 Backup

```bash
cd backend
./scripts/backup_db.sh onholland_accounting
```

**Caveats you must work around — the script's own docstring is wrong:**

- It does **not** read `DATABASE_URL` despite claiming to. It defaults to the literal database name `onholland_accounting` and takes host/user/password from `PGHOST`/`PGUSER`/`PGPASSWORD`. Against the prod compose stack, set those explicitly, or `docker compose exec` into the `postgres` service and run `pg_dump` there.
- The dump is **unencrypted** and written with default permissions. It contains plaintext employee names, addresses, salaries and the entire financial ledger. Immediately `chmod 600` it, encrypt it (`age`/`gpg`), and move it off-host.
- There is **no retention policy**. Old dumps accumulate, each a full copy of personal data — a GDPR minimisation problem in its own right. Delete or rotate them deliberately.
- Verify the dump is non-empty before trusting it: `ls -l backups/ && pg_restore --list <file> | head`.

Also back up the `backend_storage` volume — uploaded source documents are not in the database:

```bash
docker run --rm -v accounting_backend_storage:/data -v "$PWD/backups:/backup" alpine \
  tar czf /backup/storage-$(date +%F).tar.gz -C /data .
```

### 5.2 Restore

```bash
cd backend
./scripts/restore_db.sh <dump-file> <db-name> --force
```

**The overwrite guard is not reliable.** `restore_db.sh:16` is:

```bash
EXISTING_TABLES=$(psql -d "$DB_NAME" -tAc "…" 2>/dev/null || echo "0")
```

If `psql` fails for *any* reason — wrong host, bad credentials, database absent, server down — `EXISTING_TABLES` becomes `"0"` and the guard passes, after which `pg_restore --clean --if-exists --force` drops everything. **Always confirm manually before restoring:**

```bash
psql -d "$DB_NAME" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
```

Argument order matters: `restore_db.sh <dump> <db> --force`. Passing `restore_db.sh <dump> --force` sets `DB_NAME="--force"`.

### 5.3 There is no schedule

No cron, systemd timer or other automation exists. Until one is added, backups happen only when someone remembers. This is a genuine operational gap, not a documentation one.

---

## 6. Rollback

### Application rollback (no schema change)

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod down
git checkout <previous-tag>
docker compose -f docker-compose.prod.yml --env-file .env.prod build
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### Rollback involving a migration

Migrations run automatically in the backend's `CMD`. To reverse the most recent one:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend alembic downgrade -1
```

Then start the **previous** image, or `/ready` will report a revision mismatch.

**Check before rolling back** that the migration is reversible. Phase 19's `e4f7a9c2b1d8` is (verified: `downgrade -1` dropped the constraint, `upgrade head` re-created it). A migration that drops a column or data is not recoverable without a restore — take a backup before any deploy that includes one.

### Encryption key rollback

If a key rotation goes wrong: put the old key back as the current one and remove the new one. **Nothing in the database needs restoring**, because the retired key stays in `*_PREVIOUS` throughout the procedure and still decrypts everything. This is why `*_PREVIOUS` must not be cleared until a rotation is verified.

---

## 7. Known operational gaps

| Gap | Impact | Workaround |
|---|---|---|
| No email provider | Password reset cannot deliver a token at all (it is generated, hashed, then discarded — audit 6.8). Both invitation flows return the raw token in the HTTP response for out-of-band relay. | An operator must relay invitation tokens manually. Password reset is **non-functional**; reset passwords directly in the database as a last resort. |
| Rate limiting keys on `request.client.host` | Behind the reverse proxy this is the proxy's address, so all users share one 10-request/minute login bucket. Ten logins from anywhere returns 429 for everyone. | Until fixed, either raise `RATE_LIMIT_LOGIN_PER_MINUTE` (weakens brute-force protection) or configure `--proxy-headers` with `--forwarded-allow-ips` and switch the limiter to read the forwarded address. |
| In-memory rate limiter | Resets on restart; not shared across workers. | Keep one replica. Move to Redis for more. |
| No metrics or alerting | Request timings are logged, never aggregated. Nothing pages anyone. | Ship logs to an aggregator and alert on 5xx rate and on `/ready` failures. |
| No MFA recovery codes | A lost authenticator device requires an operator to clear `mfa_enabled` in the database. | Documented DB intervention. |
| Background jobs are `BackgroundTasks` | No durability, no retry across restarts, no visibility into failures beyond logs. | Acceptable at current volume. Grep logs for `document_processing` failures. |
| No git remote | The repository exists only on one machine. | Fix immediately. |

---

## 8. Post-deployment verification checklist

```bash
# 1. Both health endpoints
curl -fsS https://api/health && curl -fsS https://api/ready

# 2. Security headers present
curl -sI https://api/health | grep -iE 'x-content-type|x-frame|referrer'

# 3. Unauthenticated access is refused
curl -s -o /dev/null -w '%{http_code}\n' https://api/api/v1/companies     # expect 401

# 4. Login works for a real operator account, and logout revokes
#    (do this with a throwaway account, not an admin)

# 5. CORS: a foreign origin gets no allow-header
curl -s -D - -o /dev/null -X OPTIONS https://api/api/v1/companies \
  -H 'Origin: https://evil.example' -H 'Access-Control-Request-Method: GET' \
  | grep -ci 'access-control-allow-origin'                                # expect 0

# 6. The frontend actually reaches the API -- open the deployed site, log in,
#    and confirm in DevTools Network that requests go to your API origin and
#    NOT to localhost:8000. This is blocker 1 and no automated check covers it.

# 7. Migration revision matches
docker compose -f docker-compose.prod.yml exec backend alembic current
```

Step 6 is the one that cannot be skipped and cannot be automated with the current build pipeline.
