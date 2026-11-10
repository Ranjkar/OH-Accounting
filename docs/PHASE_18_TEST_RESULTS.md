# Phase 18 — Test Results

Every command actually executed during Phase 18, with its actual output. Nothing inferred or carried over from project documentation.

| | |
|---|---|
| **Date** | 2026-11-05 |
| **Environment** | darwin, CPython 3.12.16 (`backend/.venv`), Docker 29.4.0, PostgreSQL local |
| **Databases used** | Two **scratch** databases created and dropped within this phase: `onholland_p18_migration_check`, `onholland_p18_boot`. The development database and the suite's `onholland_accounting_test` were not used for boot or migration testing. |
| **Secrets** | Generated in-shell with `secrets.token_urlsafe` / `Fernet.generate_key()` and never echoed. No secret value appears in this document or was written to any tracked file. |

---

## 1. Migration chain applied to a clean database

The audit (finding 7.14) established this had **never been verified**: `tests/conftest.py:37` builds the schema with `Base.metadata.create_all`, and `grep -rn alembic tests/` returns nothing.

```
$ createdb onholland_p18_migration_check
created

$ DATABASE_URL="postgresql+psycopg://sam@localhost:5432/onholland_p18_migration_check" \
    .venv/bin/alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade 8642d7593906 -> 3432aad647e8, phase_12_payroll_run_idempotency
INFO  [alembic.runtime.migration] Running upgrade 3432aad647e8 -> 95609c015f0c, phase_12_open_banking_fields
INFO  [alembic.runtime.migration] Running upgrade 95609c015f0c -> d5d06a7c4472, phase_13_mfa_fields
INFO  [alembic.runtime.migration] Running upgrade d5d06a7c4472 -> c0f57267146a, phase_14_company_invitations
INFO  [alembic.runtime.migration] Running upgrade c0f57267146a -> 0dff1a474f44, phase_14_subscriptions_billing_platform_admin
INFO  [alembic.runtime.migration] Running upgrade 0dff1a474f44 -> 79097fec25d3, phase_15_access_governance_audit
INFO  [alembic.runtime.migration] Running upgrade 79097fec25d3 -> d90e97d4bc35, phase_16_internationalisation_locale
INFO  [alembic.runtime.migration] Running upgrade d90e97d4bc35 -> e4f7a9c2b1d8, phase_19_unique_source_document_on_ledger_posting
upgrade exit: 0
```

**Result: PASS.** All 23 migrations applied to an empty database with no error.

### Constraint, version and table count

```
$ psql -d onholland_p18_migration_check -tAc "SELECT conname FROM pg_constraint
    WHERE conrelid='accounting_transactions'::regclass AND contype='u';"
uq_accounting_transaction_source_document

$ psql -d … -tAc "SELECT version_num FROM alembic_version;"
e4f7a9c2b1d8

$ psql -d … -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
48
```

### Rollback and re-apply

```
$ .venv/bin/alembic downgrade -1
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade e4f7a9c2b1d8 -> d90e97d4bc35, phase_19_unique_source_document_on_ledger_posting

$ psql -d … -tAc "SELECT conname FROM pg_constraint WHERE … contype='u';"
(empty — constraint dropped)

$ psql -d … -tAc "SELECT version_num FROM alembic_version;"
d90e97d4bc35

$ .venv/bin/alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade d90e97d4bc35 -> e4f7a9c2b1d8, phase_19_unique_source_document_on_ledger_posting

$ psql -d … -tAc "SELECT conname FROM pg_constraint WHERE … contype='u';"
uq_accounting_transaction_source_document
```

**Result: PASS.** Down and up are both clean and idempotent.

```
$ dropdb onholland_p18_migration_check
scratch DB dropped
```

### Migration chain integrity

```
$ .venv/bin/alembic heads
e4f7a9c2b1d8 (head)                      # exactly one head

$ .venv/bin/alembic history | head -3
d90e97d4bc35 -> e4f7a9c2b1d8 (head), phase_19_unique_source_document_on_ledger_posting
79097fec25d3 -> d90e97d4bc35, phase_16_internationalisation_locale
0dff1a474f44 -> 79097fec25d3, phase_15_access_governance_audit
```

---

## 2. Fail-closed secret validation

### 2.1 Refuses to start in production with placeholder secrets

```
$ ENVIRONMENT=production .venv/bin/python -c "import app.main"; echo "exit code: $?"
…
  File "…/app/core/config.py", line 215, in <module>
    _enforce_secret_hygiene()
  File "…/app/core/config.py", line 204, in _enforce_secret_hygiene
    raise RuntimeError(
RuntimeError: Refusing to start: ENVIRONMENT='production' but these secrets are unset, blank,
or still a value that is public in this repository: BSN_ENCRYPTION_KEY,
OPEN_BANKING_TOKEN_ENCRYPTION_KEY, MFA_SECRET_ENCRYPTION_KEY, BILLING_WEBHOOK_SECRET.

  - BSN_ENCRYPTION_KEY: Employee BSNs would be encrypted under a key that is committed to this
    repository, so anyone with database or backup read access can decrypt every one of them.
    Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
  - OPEN_BANKING_TOKEN_ENCRYPTION_KEY: Bank access/refresh tokens would be encrypted under a
    committed key. Generate one with: …
  - MFA_SECRET_ENCRYPTION_KEY: TOTP secrets would be encrypted under a committed key, so anyone
    with database read access could decrypt them and generate valid codes -- defeating MFA
    entirely rather than weakening it. Generate one with: …
  - BILLING_WEBHOOK_SECRET: Webhook HMAC signatures could be forged, allowing any tenant's
    subscription status to be flipped at will. …

Set each one in the environment or the deployment's .env.prod. This check fails closed on purpose. …
exit code: 1
```

**Result: PASS.** `JWT_SECRET` is correctly *absent* from the offender list because `backend/.env` sets a custom value — confirming the audit's finding that only the other four are on committed defaults in this environment.

### 2.2 The refusal leaks no secret value

The full stderr and stdout of the failing start was searched for every committed placeholder literal — all five, matched exactly — and for the two known template strings:

```
$ ENVIRONMENT=production .venv/bin/python -c "import app.main" 2>&1 \
    | grep -cE "<all five placeholder literals, alternation, matched exactly>"
0
```

**Result: PASS.** Zero occurrences. The message names variables and gives generation commands only. This is also pinned permanently by `test_no_guarded_secret_value_ever_reaches_a_log_or_exception_message` and `test_settings_repr_never_renders_a_secret_value` in `tests/test_phase17_security_config.py`, which use unique canary values rather than the real placeholders so they remain conclusive if the placeholders are ever removed from source.

*The placeholder literals themselves are deliberately not reproduced in this document, per rule 7. They remain in `backend/app/core/config.py:7-12`; see `PHASE_18_PRODUCTION_READINESS.md` §2.6 and `PHASE_20_KNOWN_ISSUES.md` #2.*

### 2.3 Development mode warns instead of raising

```
$ .venv/bin/python -c "import app.core.config as c; print(c.settings.environment); \
      print([n for n,_ in c.insecure_placeholder_secrets()])"
environment = development
offending var NAMES: ['BSN_ENCRYPTION_KEY', 'OPEN_BANKING_TOKEN_ENCRYPTION_KEY',
                      'MFA_SECRET_ENCRYPTION_KEY', 'BILLING_WEBHOOK_SECRET']
OK: imported without raising
```

**Result: PASS.** The test suite and local development are unaffected.

---

## 3. Production-mode boot against a real server

Scratch database, `ENVIRONMENT=production`, freshly generated secrets, `CORS_ALLOWED_ORIGINS=https://accounting.example.nl`, uvicorn on port 8099.

```
secrets generated in-shell (never printed)

=== alembic upgrade head under ENVIRONMENT=production ===
INFO  Running upgrade 79097fec25d3 -> d90e97d4bc35, phase_16_internationalisation_locale
INFO  Running upgrade d90e97d4bc35 -> e4f7a9c2b1d8, phase_19_unique_source_document_on_ledger_posting

=== seed one tenant+owner directly into the scratch DB ===
seeded owner in tenant 1

=== start uvicorn (production mode) on :8099 ===
--- server log (startup) ---
(empty — no warnings, no errors)

=== HEALTH / READY ===
GET /health  -> 200  body: {"status":"ok"}
GET /ready   -> 200  body: {"status":"ready"}

=== SECURITY HEADERS ===
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: same-origin

=== AUTH: unauthenticated must be 401 ===
GET /api/v1/companies (no token) -> 401

=== AUTH: real login + authenticated call ===
login returned a token: yes
GET /api/v1/auth/me (with token) -> 200  email=owner@bootcheck.nl
GET /api/v1/auth/me (bad token)  -> 401

=== LOGOUT then reuse the same token (Phase 17.3, live) ===
POST /api/v1/auth/logout -> 204
GET /api/v1/auth/me after logout -> 401  (must be 401)

=== CORS: allowed vs disallowed origin ===
preflight from https://accounting.example.nl -> access-control-allow-origin: https://accounting.example.nl
preflight from https://evil.example -> 0 allow-origin headers (must be 0)

server stopped, scratch DB dropped
```

**Result: PASS on every line.** Notable:

- The startup log is **empty** — no insecure-placeholder warnings, because real secrets were supplied. That is the positive control for §2.1.
- `/ready` returning `{"status":"ready"}` proves the database's `alembic_version` matches the code's migration head, not merely that the database answers.
- **Logout revocation verified against a live server**, not only in tests: the same token that returned 200 was rejected with 401 after `POST /auth/logout` returned 204. This is Phase 17.3's fix confirmed end to end.
- **CORS verified behaviourally**: the allowed origin is echoed; a disallowed origin receives zero `Access-Control-Allow-Origin` headers, so a browser would block the response.

The access token was captured into a shell variable and never printed; only `yes`/`NO` for its presence appears above.

---

## 4. Compose file validation

`docker compose -f docker-compose.prod.yml config` **could not be run**:

```
$ POSTGRES_PASSWORD=dummy NEXT_PUBLIC_API_URL=https://x.example/api/v1 \
    docker compose -f docker-compose.prod.yml config
env file /Users/sam/Projects/Accounting/.env.prod not found: stat …: no such file or directory
---exit: 1---

$ which docker && docker version --format '{{.Server.Version}}'
/usr/local/bin/docker
29.4.0
```

Docker is available; the failure is the compose file's pre-existing `env_file: .env.prod`, which is gitignored and operator-created. Creating it was out of scope. Validated structurally instead:

```
$ python -c "import yaml; …"
docker-compose.prod.yml: valid YAML, services = ['backend', 'frontend', 'postgres']
docker-compose.yml:      valid YAML, services = ['backend', 'frontend', 'postgres']
backend.environment keys: ['DATABASE_URL', 'ENVIRONMENT']
ENVIRONMENT value: ${ENVIRONMENT:-production}
env_file preserved: ['.env.prod']
postgres still has no published ports: OK
networks: {'internal': {'internal': True}, 'public': {}}
```

**Result: PASS (structural).** The `ENVIRONMENT` default lands under the backend service, `env_file` is untouched, and Postgres remains internal-only with no host publishing. **No image was built and no container was started**, so the Dockerfiles themselves are unverified by execution.

---

## 5. Configuration review checks

| Check | Command | Result |
|---|---|---|
| `.env` never committed | `git log --all -- backend/.env` | empty ✓ |
| No secret ever entered history | `git log --all -p -S "change-me-in-production" -- backend/.env` | no hits ✓ |
| `backend/.env` gitignored | `git check-ignore -v backend/.env` | `.gitignore:5` ✓ |
| `backend/storage/` untracked | `git ls-files backend/storage` | empty ✓ |
| Backup files untracked | `git ls-files \| grep -i 'backup\|\.bak'` | empty ✓ |
| No secrets in the frontend bundle source | `grep -rn NEXT_PUBLIC frontend/` | only `NEXT_PUBLIC_API_URL` ✓ |
| No secret in any log call | `grep` every `logger.*` for `password\|token\|secret\|bsn\|iban\|payload\|body\|header\|credential` | zero hits ✓ |
| No raw SQL | `grep -rn "text(\|\.execute(" backend/app` | 2 static `text()` literals (`SELECT 1`, `alembic_version`); all other `.execute(` are PyMuPDF `pdf.text()` ✓ |
| Env templates cover all guarded secrets | `test_env_templates_document_every_guarded_variable` | PASS ✓ |

---

## 6. Regression suites re-run

Phase 18 changed no application code — only verification. The suites were nevertheless re-run because Phase 19's changes landed in the same window:

| Suite | Result |
|---|---|
| Backend full (`pytest tests/`) | see `PHASE_19_TEST_RESULTS.md` §1 and `PHASE_20_FINAL_QA_REPORT.md` §1 for the authoritative post-Phase-19 numbers |
| Frontend `vitest run` | **175 passed / 11 files** |
| `tsc --noEmit` | **exit 0** |
| `next build` | **exit 0**, 55 routes |
| `eslint .` | **0 errors**, 4 pre-existing warnings in untouched files |

---

## 7. What was NOT tested

Stated plainly rather than left implicit.

1. **No Docker image was built and no container was started.** The Dockerfiles, the `alembic upgrade head && uvicorn` CMD, the healthchecks and the non-root user are all unverified by execution. Audit finding 6.10 (the frontend cannot reach the API) would only surface here.
2. **No reverse proxy / TLS.** The documented nginx topology was not provisioned, so the rate-limiter behaviour *behind* a proxy — the actual production failure mode from audit 6.9 — was not observed. The verification in §3 ran uvicorn directly, where `request.client.host` is the real client.
3. **`docker compose config` did not run** (§4).
4. **No load, soak or concurrency test.** The double-posting race that Phase 19's unique constraint defends against was verified at the database level (`test_two_transactions_cannot_share_a_source_document` asserts `IntegrityError`), not by firing concurrent HTTP requests.
5. **Backup and restore scripts were not executed.** Reviewing them is what produced the defects listed in `PHASE_18_PRODUCTION_READINESS.md` §3.3; running a restore against any database was explicitly out of bounds.
6. **No coverage measurement exists** — `pytest-cov`/`coverage` are in neither `requirements.txt` nor the venv, so no coverage figure can be given.
7. **No backend linter or type checker exists.** `ruff`, `mypy`, `flake8`, `black` and `pylint` are all absent from the venv, and there is no config file anywhere in the repository. "Backend static checks" could therefore only mean `py_compile` plus import verification, both of which passed for every changed file.
