# Phase 20 — Release Readiness Assessment

**Assessed 2026-11-05** against branch `phase-16-3-complete-internationalisation` @ `97f2d84` plus the uncommitted Phase 17–20 working tree.

Every row is backed by an executed check or by a stated reason why none exists. Nothing is marked PASS on the strength of a successful build or a documentation claim.

**Status key:** `PASS` verified by execution · `FAIL` known failure · `BLOCKED` requires manual action or an external credential · `NOT TESTED` no evidence either way.

---

## 1. Release status

# ⚠️ READY FOR INTERNAL TESTING

**Not** ready for staging, and **not** ready for a controlled production release.

### Why not staging

One hard blocker makes a staging deployment non-functional:

> **`NEXT_PUBLIC_API_URL` never reaches the browser bundle.** `frontend/lib/api.ts:1` reads it at module scope; Next.js inlines `NEXT_PUBLIC_*` at **build** time; `frontend/Dockerfile` has no matching `ARG`; `docker-compose.prod.yml:61` supplies it at **runtime**. The production bundle is therefore hardcoded to `http://localhost:8000/api/v1`, so every visitor's browser calls their own machine. The compose file's `${NEXT_PUBLIC_API_URL:?must be set}` guard fails loudly when the variable is *unset* and then silently discards it when set.

A staging deployment following the runbook exactly would start cleanly, pass `/health` and `/ready`, and be completely unusable. Audit finding 6.10. It is a one-line Dockerfile `ARG`/`ENV` plus a compose `build.args`, or better a same-origin `rewrites()` — but it was not in Phase 17's security scope and was not attempted in Phases 18–20 because it changes the build pipeline.

### Why not production

Beyond the above, four categories of open defect each independently disqualify a production release:

1. **Financial figures are wrong in known ways.** The balance sheet's VAT liability never clears because `VatPeriod.status` is never assigned (audit 6.1). No report outside the VAT engine handles FX, so currencies are summed together (7.1). Manual balance-sheet items are summed as flows though they are stocks (7.2). Transaction approval affects no reported figure (6.3).
2. **Tax rules are frozen at 2025 and VAT at `nl-2024`, in 2026.** Nothing derives the year from the clock, so a payroll run today silently computes 2025 brackets, rates and caps (6.5). Four VAT boxes cannot be populated automatically (7.11).
3. **Three security defects remain open:** MFA can be re-enrolled without proving possession of the existing factor (6.11); rate limiting is one shared bucket behind any reverse proxy, making it both ineffective against attackers and a trivial platform-wide DoS (6.9); password reset cannot deliver a token and has no UI at all (6.8).
4. **Nothing is verified automatically.** No CI, no coverage tooling, no backend linter or type checker, and **no git remote** — the entire repository exists on one machine.

### Why internal testing is supportable

- **662 backend tests pass, 0 failed, 0 skipped.** 120 of them were added in Phases 17–20.
- **The backend boots and operates correctly in production mode** — verified against a real server and a scratch database: migrations, health, readiness, security headers, authentication, live logout revocation, and CORS enforcement all confirmed (`PHASE_18_TEST_RESULTS.md` §3).
- **Tenant isolation is fixed and mutation-verified.** Seven cross-tenant endpoints, two of them writes, were closed in Phase 17; 22 regression tests were observed to **fail against the vulnerable code** and pass against the fix.
- **Four accounting defects were fixed with mutation-tested regressions** — cash-based VAT returns, comparison-period arithmetic, payment amount validation, and double-posting protection.
- **The migration chain is verified up/down/up** against a clean database for the first time in the project's history.
- The frontend builds, typechecks and lints clean, and works in **development** mode, where the API-URL fallback happens to be correct.

**Conditions on internal testing:** run it in development mode (`docker-compose.yml`, not `docker-compose.prod.yml`); treat every financial figure as provisional; and do not use it for a real VAT filing or a real payroll run.

### What would move it to STAGING

Minimum, in order: fix the frontend build-time API URL (blocker 1); provision TLS and a reverse proxy with `--proxy-headers`; fix the rate limiter's client-key resolution; fix MFA step-up; make password reset deliverable; rotate the five committed secrets; add CI with the migration and secret-hygiene gates; add a git remote. Roughly 8–10 engineering days.

### What would move it to CONTROLLED PRODUCTION

All of the above, plus: `VatPeriod.status` wiring; `approval_status` semantics decided and enforced; FX-aware reporting; `ManualBalanceSheetItem` semantics decided; a **2026 tax rule set verified against primary Belastingdienst sources** with the default year derived from the clock; the line-item VAT-eligibility override reachable from the UI; transactional email; backup hardening and a schedule; metrics and alerting. Roughly 25–35 engineering days, of which the tax-rule verification is gated on authoritative sources rather than on effort.

---

## 2. Release checklist

### Security

| Item | Status | Evidence |
|---|---|---|
| Authentication (bcrypt, JWT, lockout) | **PASS** | Live login/logout/401 verified in production mode |
| Session revocation | **PASS** | `POST /auth/logout` → 204, same token → 401, **verified against a running server** |
| Tenant isolation | **PASS** | 22 tests, mutation-verified (14 failed against vulnerable code). All 217 routes audited. |
| Role-based authorisation | **PASS** | No escalation path to owner/admin; no self-role-change; last-owner protection; `is_platform_admin` not API-settable |
| SQL injection | **PASS** | ORM-only; 2 static `text()` literals; no string-interpolated SQL |
| XML parsing / XXE | **PASS** | DTD rejected before parsing in both CAMT parsers; 14 tests including billion-laughs and case variants |
| File upload validation | **PASS** | Magic-byte sniffing, openpyxl container check, size limits before processing, no traversal, no header injection |
| Path traversal | **PASS** | Server-side paths from integer ids; `secure_filename` charset excludes `/ \ "` |
| SSRF | **PASS** | No user-controlled URL is fetched |
| Secrets in logs | **PASS** | Zero hits across every `logger.*` call; `repr=False` on all 11 secret fields |
| Secret configuration | **PASS (fail-closed)** | Production refuses to start; names offenders; leaks no value |
| CORS | **PASS** | Allowed origin echoed; disallowed origin gets zero allow-headers — verified live |
| Security headers | **PASS** | `nosniff`, `DENY`, `same-origin` on every response |
| Audit logging | 🟡 **PARTIAL** | 41 call sites, `request_id` correlation. `redact()` used in only 2 of 11 writing routers; `invite_employee_self_service` writes none |
| **Committed encryption keys** | 🔴 **FAIL** | Five valid secrets are public in `config.py` and in git history. Four are in active use in this environment. Rotation is BLOCKED on an operator backup. |
| **MFA re-enrolment** | 🔴 **FAIL** | `/auth/mfa/enable` overwrites the secret verifying only the *new* code. A stolen session token can displace the victim's factor. Audit 6.11. |
| **Rate limiting behind a proxy** | 🔴 **FAIL** | Keys on `request.client.host` = the proxy. One shared 10/min login bucket platform-wide. Audit 6.9. |
| **Password policy** | 🔴 **FAIL** | `min_length=8` on invitation-accept only; none on reset; no maximum (bcrypt truncates at 72 bytes) |
| XSS / token storage | 🟡 **PARTIAL** | React escapes by default; no `dangerouslySetInnerHTML` in `app/` or `lib/`. But the JWT lives in `localStorage` with a 24h lifetime and no refresh token. |
| CSRF | **PASS (n/a)** | Bearer header auth, no auth cookie |
| CSV formula injection | 🔴 **FAIL** | Raw `original_filename` written unescaped in `batches.py:252`. Audit 8.13. |
| Dependency vulnerabilities | **NOT TESTED** | No `pip-audit`, no `npm audit`, no Dependabot. `python-jose` 3.3.0 and `passlib` 1.7.4 are unmaintained. |
| Frontend 401/403 handling | 🔴 **FAIL** | None anywhere. An expired token strands the user on the page with a raw English error banner. |

### Accounting correctness

| Item | Status | Evidence |
|---|---|---|
| VAT box arithmetic | **PASS** | Scenario D: 1a/1b/5a/5b/net_payable exact; cross-checked against the independently-built reconciliation view |
| VAT period isolation | **PASS** | Q2 invoice absent from the Q1 return |
| Cash-based VAT periods | **PASS** | Fixed in Phase 19; 9 tests including a full API chain |
| Return lifecycle and locking | **PASS** | `draft → ready_for_approval → approved → locked`; edits blocked with 409 after locking |
| Conservative input-VAT handling | **PASS** | `REQUIRES_REVIEW` contributes `0.00` to box 5b |
| Payment validation | **PASS** | Zero and negative rejected; ledger untouched |
| Double-posting protection | **PASS** | DB constraint + migration + 409 mapping |
| Comparison-period arithmetic | **PASS** | Fixed in Phase 19; mutation-tested (10 failures against the buggy version) |
| Corrections and voiding | **PASS** | Corrections are new rows; payments voided not deleted — verified end to end |
| Decimal discipline | **PASS** | `Numeric` end to end; money is a JSON string; no float in the API contract |
| Payroll arithmetic | **PASS** | Recomputed from published rates in tests; 3 official table rows within €1.00 |
| **Balance-sheet VAT liability** | 🔴 **FAIL** | `VatPeriod.status` never assigned; liability never clears. Audit 6.1. |
| **Approval affects reported figures** | 🔴 **FAIL** | `approval_status` is not a filter in any report or the VAT engine. Audit 6.3. |
| **FX in reports** | 🔴 **FAIL** | Zero `currency`/`_eur` references across five report modules. Audit 7.1. |
| **Manual balance-sheet items** | 🔴 **FAIL** | Stocks summed as flows. Audit 7.2. |
| VAT boxes 2a/3a/4a/1d | 🟡 **PARTIAL** | Reachable only by manual entry; no UI to set `vat_treatment`; not surfaced as a gap. Audit 7.11. |
| Suppletie (correction return) | 🔴 **FAIL** | Corrections always land in the current period. Audit 4.3. |

### Dutch tax functionality

| Item | Status | Evidence |
|---|---|---|
| VAT return calculated / prepared / exported | **PASS** | PDF, XLSX, CSV in 4 locales |
| VAT return submitted / accepted | 🔒 **BLOCKED** | No SBR/Digipoort connector, no certificate. Requires PKIoverheid + Logius registration. The old Digipoort retired 2026-04-01. |
| ICP / OSS | 🔴 **FAIL** | Not tracked. Reported honestly as `NOT_TRACKED`. |
| Income tax / corporate tax | 🟠 **ESTIMATE ONLY** | Reported as `NOT_FILED`. Never fabricated. |
| Loonheffingen lifecycle | 🟡 **PARTIAL** | Real local state machine; no transmission |
| RGS compatibility | 🔴 **FAIL** | Absent entirely |
| SBR / XBRL | 🔴 **FAIL** | Absent |
| **Tax rule currency** | 🔴 **FAIL** | One rule set (`2025`) and one VAT version (`nl-2024`), in 2026. Default year never derived from the clock. Audit 6.5. **Requires authoritative source verification — not attempted, and rates were not invented.** |
| `bewaarplicht` retention | 🟡 **PARTIAL** | Documented policy, not enforced code |

### Data integrity and database

| Item | Status | Evidence |
|---|---|---|
| Migration chain applies cleanly | **PASS** | 23 migrations, 48 tables, single head — first time ever verified |
| Migration rollback | **PASS** | `downgrade -1` → `upgrade head` round-trip clean |
| Schema/migration parity | 🔴 **FAIL** | 54 indexes from `3853605281ec` are deliberately absent from model metadata; `autogenerate` would propose dropping them. Tests use `create_all`, so they run without those indexes. |
| Automated migration testing | 🔴 **FAIL** | `grep -rn alembic tests/` → 0 |
| Idempotency constraints | 🟡 **PARTIAL** | Bank transactions, bank accounts, payroll runs, VAT returns, and (new) ledger postings. **Missing:** `FinancialYear(company_id, year)`, `VatPeriod(financial_year_id, label)`, `Employee.linked_user_id` |
| Hot-path indexes | 🔴 **FAIL** | No index on `accounting_transactions.vat_period_id`, `.invoice_date`, `transaction_line_items.transaction_id`, `payments.transaction_id`, `documents.sha256_hash`. Audit 7.18. |
| FK delete behaviour | 🔴 **FAIL** | No `ondelete=` anywhere; company deletion raises an FK violation |
| Connection pool | 🟡 **PARTIAL** | Default `QueuePool`, no `pool_pre_ping`, no sizing |
| Transaction atomicity | 🟡 **PARTIAL** | `lock_vat_return` commits twice; `GET /vat-returns` writes on a read with no audit row. Audit 7.9. |
| Query performance | **NOT TESTED** | No benchmark, no `EXPLAIN ANALYZE`, no slow-query log. Zero eager loading anywhere; all aggregation in Python. Audit 7.4. |

### Backup and recovery

| Item | Status | Evidence |
|---|---|---|
| Backup script exists | **PASS** | `scripts/backup_db.sh`, drilled twice by the project |
| Restore script exists | **PASS** | `scripts/restore_db.sh` |
| **Restore overwrite guard** | 🔴 **FAIL** | `\|\| echo "0"` means any `psql` connection error reads as "empty database" and the guard passes. Audit 7.12. |
| Dump encryption / permissions | 🔴 **FAIL** | Plaintext, default umask, contains salaries and addresses |
| Retention / rotation | 🔴 **FAIL** | None |
| Schedule | 🔴 **FAIL** | None — backups happen only when someone remembers |
| Off-host copy | 🔴 **FAIL** | None |
| Storage-volume backup | 🔴 **FAIL** | Uploaded documents are not in the database and no procedure covers them |
| Encryption-key rotation | 🟡 **PARTIAL** | Tooling now exists for all three classes and the procedure is tested; **rotation not performed** and `docs/encryption-key-rotation.md` still wrongly says BSN is the only encrypted data |
| Restore executed | **NOT TESTED** | Explicitly out of bounds |

### Monitoring and operations

| Item | Status | Evidence |
|---|---|---|
| Structured logging with correlation | **PASS** | JSON, `request_id` propagated via `ContextVar` and echoed to the client |
| Health vs readiness separation | **PASS** | `/health` does `SELECT 1`; `/ready` additionally compares DB revision to code head |
| Auth failures logged safely | **PASS** | Reason logged, no credential material |
| Background job failure reporting | 🟡 **PARTIAL** | Logged, but no durable queue, no retry across restarts, no dead-letter visibility |
| Metrics | 🔴 **FAIL** | None |
| Alerting | 🔴 **FAIL** | None |
| Error tracking | 🔴 **FAIL** | None |
| Log aggregation | 🔴 **FAIL** | None |
| Runbook | **PASS** | `PHASE_18_DEPLOYMENT_RUNBOOK.md`, including its own caveats |

### Production configuration

| Item | Status | Evidence |
|---|---|---|
| Fail-closed secret validation | **PASS** | Verified raising, verified leaking no value |
| CORS validation | **PASS** | Verified live |
| No secrets committed to `.env` files | **PASS** | Never in history; templates hold empty placeholders only |
| No secrets in the frontend bundle | **PASS** | `NEXT_PUBLIC_API_URL` is the only `NEXT_PUBLIC_*` reference |
| Postgres not host-exposed in prod | **PASS** | `internal: true`, no `ports:` |
| Non-root containers | **PASS** | Both Dockerfiles use `appuser` |
| **Frontend API URL at build time** | 🔴 **FAIL** | Blocker 1 above |
| **Frontend image hygiene** | 🔴 **FAIL** | `npm install` not `npm ci`; full devDependency tree copied to runtime; `npm` as PID 1 |
| **TLS / reverse proxy** | 🔒 **BLOCKED** | Documented, never provisioned; environment-specific by design |
| Compose validated by the compose parser | **NOT TESTED** | `.env.prod` does not exist; validated structurally instead |
| Docker image built | **NOT TESTED** | No image was built in any phase |
| **`ENVIRONMENT` default in prod compose** | **PASS** | `${ENVIRONMENT:-production}` — fails safe if `.env.prod` omits it |

### Documentation and process

| Item | Status | Evidence |
|---|---|---|
| Phase documentation | **PASS** | 31 pre-existing docs plus 9 from Phases 17–20 |
| Documentation accuracy | 🟡 **PARTIAL** | Five docs make claims this audit found false: `production-readiness.md`, `security.md`, `encryption-key-rotation.md`, `gdpr-data-governance.md`, `untranslated-backend-messages-inventory.md`. Listed for correction. |
| `README.md` currency | 🔴 **FAIL** | Stops at Phase 9; understates the test count by 291 (358 claimed, 662 actual) |
| Original requirements committed | 🔴 **FAIL** | No specification exists in the repository, so "done" is unfalsifiable |
| **CI** | 🔴 **FAIL** | None. No `.github/workflows`, no GitLab CI, no Jenkinsfile, no Makefile. |
| **Git remote** | 🔴 **FAIL** | None. The repository exists on one machine only. |
| Code review gate | 🔴 **FAIL** | `main` is 81 commits behind HEAD; nothing has ever passed through a PR |
| Coverage measurement | 🔴 **FAIL** | No tooling installed |
| Backend linting / typing | 🔴 **FAIL** | No ruff, mypy, flake8, black or pylint; no config file |

---

## 3. Score summary

| Area | PASS | PARTIAL | FAIL | BLOCKED | NOT TESTED |
|---|---|---|---|---|---|
| Security | 13 | 3 | 6 | 0 | 1 |
| Accounting correctness | 11 | 1 | 5 | 0 | 0 |
| Dutch tax | 1 | 2 | 5 | 1 | 0 |
| Data integrity / DB | 2 | 3 | 5 | 0 | 1 |
| Backup and recovery | 2 | 1 | 7 | 0 | 1 |
| Monitoring | 3 | 1 | 4 | 0 | 0 |
| Production configuration | 7 | 0 | 2 | 1 | 2 |
| Documentation and process | 1 | 1 | 7 | 0 | 0 |
| **Total** | **40** | **12** | **41** | **2** | **5** |

Forty-one FAIL rows is a large number, but it is concentrated: **28 of the 41 are absent operational infrastructure** (CI, metrics, alerting, backup automation, linting, coverage, git remote, documentation currency) rather than defects in the application. Those are days of work, not weeks, and none requires a design decision.

The 13 that are genuine application defects are the ones that gate a release, and they are listed in `PHASE_20_KNOWN_ISSUES.md` in priority order.

---

## 4. What changed the assessment during Phases 17–20

Recorded so the delta is visible rather than buried.

| Before Phase 17 | After Phase 20 |
|---|---|
| Any admin of any tenant could lock another tenant's financial year and bulk-approve payments against their ledger | Closed, mutation-verified |
| "Log out" did not revoke the session; tokens lived 24h | Closed, verified against a running server |
| A production deployment could boot with public encryption keys and pass `/health` | Refuses to start, names the offenders, leaks no value |
| `repr(settings)` dumped every secret | `repr=False` on all 11 secret fields, test-pinned |
| XML bank parsing depended on the interpreter's expat build | DTD rejected before parsing, 14 tests |
| Cash-based VAT companies got all-zero returns | Fixed on both payment paths, 9 tests |
| Quarterly comparisons dropped 2 days; leap-year annual comparisons shifted by one | Fixed, mutation-tested |
| Negative payments were accepted | Rejected with 422 |
| A document could be double-posted by a concurrent approval | DB constraint + migration + 409 |
| The migration chain had never been executed | Verified up/down/up on a clean database |
| RTL fonts were loaded but never applied | Fixed and verified in the production CSS bundle |
| Test count | 542 → **662** |
