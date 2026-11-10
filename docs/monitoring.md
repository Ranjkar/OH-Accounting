# Monitoring & logging (Phase 12)

## Structured logging

`app/main.py` configures the root logger with a JSON formatter — one object per line (`timestamp`, `level`, `logger`, `message`, `request_id`). Verified no call site anywhere in the codebase logs a password/BSN/token/secret (grepped, not assumed) before this was written.

Uvicorn's own `uvicorn.access` logger is untouched and still prints its default plain-text access line alongside the structured one — a known, accepted cosmetic duplication, not a bug.

## Request correlation

Every request gets an `X-Request-ID` (reuses the caller's own header if present, otherwise generates one), propagated through a `contextvars.ContextVar` so concurrent async requests' log lines don't cross-contaminate, echoed back in the response header, and logged with method/path/status/duration on every request. 5xx responses log at `warning`; everything else at `info`. Smoke-tested directly (`uvicorn` + `curl`, not just unit-tested) — confirmed the header round-trips and each request gets its own correct id in the log output.

## Health vs. readiness

- `GET /health` — real `SELECT 1` against the database. Existed since Phase 10.
- `GET /ready` — **new this phase**: additionally compares the database's `alembic_version` against this code's actual migration head (via `alembic.script.ScriptDirectory`). A process booted against an unmigrated database passes `/health` (it can connect) but fails `/ready` — point a readiness probe at this, not `/health`, to avoid routing traffic to a process whose schema doesn't match its code.

Neither endpoint returns schema details, migration ids, or stack traces in its response body — only `{"status": ...}`.

## What is not implemented

- No metrics backend (Prometheus/Datadog/etc.) — request timing is logged, not aggregated into a dashboard or alertable metric. Adding one is a reasonable next step but was out of scope given "do not introduce infrastructure without a justified need."
- No certificate-expiry monitoring — there is no certificate in this system yet to monitor (SBR/Digipoort integration is BLOCKED BY EXTERNAL REQUIREMENT, see `docs/government-integrations.md`).
- No background-job failure alerting — this system has no background job queue (Celery/etc. deliberately not introduced); the batch document-processing pool (`app/services/batch_processing.py`, Phase 6) already surfaces per-item failures in its own API response, which is where that signal lives today.
- No external-integration failure alerting beyond what's logged — Open Banking sync errors are stored on `BankAccount.last_sync_error` and surfaced via the API; there's no push notification/alert on failure yet.
