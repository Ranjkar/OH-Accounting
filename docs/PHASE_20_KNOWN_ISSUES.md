# Phase 20 — Known Issues

Every open defect, in priority order, with the evidence that establishes it and the smallest safe fix. Audit references are to `docs/QWEN_TECHNICAL_AUDIT_REPORT.md`.

**Nothing in this list was introduced by Phases 17–20.** All were found by the audit and remain open either because they were out of scope, or because fixing them correctly requires a decision that is not an engineering one.

Priority: **P0** blocks any deployment · **P1** produces wrong statutory/financial output or breaks a security control · **P2** materially degrades correctness, security or operability · **P3** quality, performance or hygiene.

---

## P0 — blocks deployment

### 1. The production frontend cannot reach the API (audit 6.10)

```ts
// frontend/lib/api.ts:1
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
```

A module-level constant executed in the **browser**. Next.js inlines `NEXT_PUBLIC_*` at **build** time; `frontend/Dockerfile` runs `npm run build` with no matching `ARG`; `docker-compose.prod.yml:61` supplies it via `environment:`, which is **runtime** and therefore never reaches the compiled client JS.

**Consequence:** the production bundle is hardcoded to `http://localhost:8000/api/v1`, so every visitor's browser calls their own machine, and even if it resolved it would be mixed-content-blocked from an HTTPS page. The `${NEXT_PUBLIC_API_URL:?must be set}` guard makes this actively misleading — it fails loudly when unset and then silently has no effect when set. Local dev masks it because the fallback happens to be the correct dev value.

**Fix:** `ARG NEXT_PUBLIC_API_URL` + `ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL` before `RUN npm run build`, with `build.args` in compose. Better: proxy `/api` through Next via `rewrites()` so the browser only calls a same-origin relative path and the target resolves server-side at runtime — then this class of bug cannot recur. Add a smoke test that loads the built app headless and asserts no request goes to `localhost:8000`.

### 2. Five committed secrets are public and in active use (audit 6.4)

`backend/app/core/config.py:7-11` hardcodes valid Fernet keys and an HMAC secret. `.env` was never committed and no secret ever entered git history ✓ — but these are in tracked source, so they are public. `backend/.env` sets a custom `JWT_SECRET` but **not** `BSN_ENCRYPTION_KEY`, so this environment is currently encrypting employee BSNs under a public key. Same for Open Banking tokens and MFA secrets — the last of which means anyone with database read access can decrypt TOTP seeds and generate valid codes, defeating MFA entirely.

Fail-closed validation now prevents this in production (verified). It cannot fix a development database that already holds ciphertext under a burned key.

**Fix:** rotate all five. The tested procedure and its rollback path are in `PHASE_17_SECURITY_REMEDIATION.md` §7, and `backend/scripts/rotate_encryption_keys.py` now supports all three encrypted classes. **Requires a database backup first** — this is why it was not done in these phases.

### 3. No git remote

`git remote -v` is empty. 88 commits and ~36,000 lines exist only on one machine. No backup, no offsite copy, no way for anyone else to review.

**Fix:** add a remote and push. Five minutes; the highest value-to-effort item in this document.

---

## P1 — wrong output or a broken security control

### 4. `VatPeriod.status` is never assigned (audit 6.1)

`grep -rn "\.status = VatPeriodStatus\|status=VatPeriodStatus" app/` → **zero hits**. The column is only read:

- `financial_reports._outstanding_vat_position` filters `VatPeriod.status != paid`, so the filter never excludes anything and **every VAT return ever computed is summed into the balance sheet's VAT liability forever**. Paying a VAT bill has no effect. Corrupts `total_liabilities`, `is_balanced`, `imbalance_amount`, current/quick ratios, ROA and the working-capital trend.
- `dashboard.py:76` computes "open VAT periods" as *all periods ever*.

`VatReturnStatus` has its own `approved`/`locked` states and nothing maps between the two systems. The enum, column, migration, schema field and two readers all exist; the writer does not.

**Fix:** add `mark-filed` / `mark-paid` transitions (audited, permissioned) or derive `VatPeriod.status` from `VatReturn.status` plus a recorded payment. **Needs a decision about who may declare a period paid.** Interim mitigation without a decision: filter `_outstanding_vat_position` on `VatReturn.status not in (approved, locked)` and count returns rather than periods on the dashboard.

**The single highest-value open item in the product.**

### 5. Transaction approval affects no reported figure (audit 6.3)

`grep -rn "approval_status" app/accounting/ app/reporting/` → exactly one hit, the FX guard at `ledger_service.py:195`. The VAT engine, P&L, balance sheet, trial balance, GL, KPIs and every export all include `DRAFT` transactions. `POST /transactions/{id}/approve` writes an audit row and blocks later edits — verified by Scenario B returning `409` — but **approving changes nothing that is computed**. `post_document_to_ledger` never sets `APPROVED`, so a transaction posted from an *approved document* stays `DRAFT` forever.

**Fix:** decide the semantics, then enforce. Either `post_document_to_ledger` sets `APPROVED` (and manual entries become the only `DRAFT` path), or every calculation gains an `approval_status != DRAFT` filter. Either way add a reconciliation line reporting the count and value of `DRAFT` transactions in a period being approved. **Not done because both options change reported statutory numbers.**

### 6. Tax rules are frozen at 2025 and VAT at `nl-2024` (audit 6.5)

```python
_RULE_SETS: dict[int, DutchTaxRuleSet] = {2025: RULES_2025}
CURRENT_TAX_YEAR = 2025
RULE_VERSIONS = {"nl-2024": VatRuleSet(..., standard_rate=Decimal("21"), low_rate=Decimal("9"))}
```

One entry each; neither versioning mechanism has ever been exercised. Six production call sites invoke `get_rule_set()` with no argument and nothing derives the year from the clock, so `get_rule_set(2026)` raises but `get_rule_set()` silently returns 2025. A payroll run created today for a 2026 period computes 2025 box-1 brackets, both heffingskortingen, 2025 AWf/Aof/Whk/Zvw rates, the 2025 `max_premieloon` of €75,864 and the 2025 DGA norm of €56,000 — with no error and no warning. `payroll_service.py:30`'s "fail fast, not silently" comment describes a guard that never fires on the default path.

The test suite cannot detect this: 26 of 28 `get_rule_set` calls in tests pass `2025` explicitly, every payroll test hardcodes `period_year=2025`, and nothing asserts `CURRENT_TAX_YEAR` matches the calendar year.

**Fix, in two parts:**
- *Safe and does not require new rates:* make the default year clock-derived (`current_tax_year() → date.today().year`) so `get_rule_set()` **raises** for a year nobody has loaded; add a startup check that refuses to boot outside development when the current year is missing; add a test asserting `get_rule_set(date.today().year)` succeeds — deliberately designed to fail once a year. **~1 day. Converts a silent compliance failure into a loud one.**
- *Requires authoritative sources:* write `RULES_2026` and a `nl-2026` VAT rule set with citations, exactly as `RULES_2025` was built. **Not attempted — rates were not invented.**

### 7. MFA can be re-enrolled without proving the existing factor (audit 6.11)

`POST /auth/mfa/enable` overwrites `mfa_secret_encrypted` after verifying only the **new** secret against a caller-supplied code. `mfa_disable` correctly requires a code from the *existing* secret — so disabling is protected and replacing is not. An attacker holding a session token (JWTs live in `localStorage`, 24h, no refresh, and there is no 401 handling) can call `/mfa/setup` then `/mfa/enable` with their own authenticator and permanently displace the victim's.

**Fix:** require step-up authentication — a valid code from the existing secret, ideally plus the password — before accepting a replacement. Audit-log the replacement distinctly from initial enrolment. Add MFA recovery codes (currently a lost device requires an operator to clear `mfa_enabled` in the database).

### 8. Rate limiting is ineffective behind any reverse proxy (audit 6.9)

```python
client_host = request.client.host if request.client else "unknown"
```

Under the nginx/Caddy topology the deployment docs prescribe, that is the **proxy's** address for every user. One shared 10-request/minute login bucket platform-wide: the eleventh legitimate login anywhere returns 429, and an attacker can lock out the entire platform with 10 requests. Conversely an attacker rotating source IPs is not individually limited either. `_buckets` is also an unbounded `defaultdict` that is never pruned.

It correctly does **not** trust `X-Forwarded-For` ✓ — the failure is the opposite: it trusts the peer too much.

Also: `documents.py:68` and `banking.py:111` share the `"upload"` scope, so a bank-import session blocks the user's own invoice uploads; and `GET /kvk/lookup/{kvk_number}` is unrate-limited, letting any authenticated user including an `employee` burn the operator's KVK quota at €0.02/query.

**Fix:** uvicorn `--proxy-headers` with `forwarded_allow_ips`, then read the leftmost untrusted-trimmed `X-Forwarded-For` only when the peer is a trusted proxy. Bound `_buckets`. Give bank imports their own scope. Rate-limit `/kvk/lookup` and validate `kvk_number` against `^\d{8}$`. Longer term, Redis.

### 9. Password reset cannot work (audit 6.8, 4.6)

`request_password_reset` generates the raw token, stores only its SHA-256 hash, then discards it (`_ = raw_token`). It is not emailed, not logged, not returned. The docstring claims "the reset link is logged server-side instead of emailed"; the code explicitly does not log it. **No human or system can ever obtain a valid token.** Both reset endpoints also have **no frontend caller**, so there is no UI either.

`PasswordResetConfirm.new_password` has no strength constraint (invitation-accept requires `min_length=8`), and the lookup uses `User.email == payload.email` exact match, contradicting `find_user_by_email`'s own docstring. `test_password_reset_full_flow` never submits a *valid* token, which is why this was never caught.

**Fix:** return `raw_token` once to an authenticated operator (mirroring the invitation flow, which does exactly this) or wire a transactional email provider. Then write the missing happy-path test. Share one password policy across both paths.

### 10. No FX handling outside the VAT engine (audit 7.1)

`grep -rn "net_amount_eur\|currency"` across `financial_reports.py`, `working_capital.py`, `financial_forecast.py`, `kpi_engine.py` and `budget_service.py` → **zero hits**. All sum `net_amount` regardless of currency. A company with a $1,000 and a €1,000 invoice reports revenue of "2,000" with no currency label. The VAT engine excludes unresolved-FX transactions and converts resolved ones; that discipline stops there.

**Fix:** one shared helper returning the EUR equivalent or flagging unresolved, used in every aggregation; exclude and surface unresolved-FX rows as the VAT engine does; a mixed-currency test asserting revenue equals the EUR-equivalent total, not the naive sum. Touches ~15 functions and every export, so it needs its own cycle.

### 11. `ManualBalanceSheetItem` sums stocks as though they were flows (audit 7.2)

`_manual_items_total` adds **every** row with `as_of_date <= X`. A balance-sheet item is a point-in-time stock, so recording "Fixed assets €50,000" twice yields €100,000. No `version`, no `supersedes_item_id`, no unique constraint, and no UI convention saying whether a row is a balance or a signed delta. Feeds `total_assets`, `total_liabilities`, `total_equity`, `is_balanced`, the trial balance, the cash-flow statement's investing and financing sections, and every liquidity and ROA KPI.

Budgets solved the analogous problem correctly with `version`/`supersedes_budget_id`.

**Fix:** decide the semantics. Either make rows movements (rename, document, require signed amounts) or keep them balances and query "latest row per `(category, label)` with `as_of_date <= X`" plus a unique constraint. Add `supersedes_item_id` either way.

### 12. Four VAT boxes are unreachable automatically (audit 7.11)

`classify_default_treatment` can never return `domestic_reverse_charge_received` (2a), `export_non_eu` (3a), `import_non_eu` (4a) or `private_use` (1d). The refusal to guess is correct; the consequence is not surfaced. Boxes are always `0.00` unless an accountant creates a manual entry with the right treatment, and `PATCH /transactions/{id}/line-items/{line_item_id}` — which updates only `input_vat_eligibility`, not `vat_treatment` — has **no frontend caller**. A company that exports outside the EU or receives reverse-charge services will under-declare and the platform will not tell them.

**Fix:** add `vat_treatment` to `LineItemEligibilityUpdate` (guarded, audited, draft-only) **and** wire the endpoint into the UI **and** add a reconciliation finding listing transactions defaulted to `domestic_zero_or_exempt` with a non-NL counterparty. The three parts only work together.

---

## P2 — material degradation

| # | Issue | Audit | Evidence / fix |
|---|---|---|---|
| 13 | Cross-tenant accountant delegation withdrawn | 6.7(b) | `accept_invitation` now refuses cross-tenant acceptance. `docs/accountant-ecosystem.md` and Phase 14's "IMPLEMENTED, tested (7 tests)" are now inaccurate. Real delegation needs a `CompanyAccess` grant (per-company role, revocable, expiring) that queries authorise against **instead of** `tenant_id` — which also delivers per-company roles. |
| 14 | No frontend 401/403 handling | 7.17 | `lib/api.ts:22-26` throws on any `!res.ok`; `ApiError.status` is captured and **never read**. An expired token strands the user with a raw English error banner. Fix: a response interceptor branching on status, `AuthGuard` moved into `app/layout.tsx`, shorter tokens plus a refresh token, and `httpOnly` `SameSite=Strict` cookies with a CSRF token. |
| 15 | Dark-mode contrast 2.53:1 on the primary error surface | 7.7 | 48 elements across 43 files combine `bg-red-50` (fixed `#fef2f2`) with `text-error` (`#f87171` in dark mode) against a 4.5:1 AA requirement; light mode is fine at 5.91:1. 228 hardcoded palette colours, `dark:` used in single digits. Invisible to `contrast-check.py` (token pairs only) and to `test/axe.ts` (`color-contrast` disabled — jsdom has no layout engine). Fix: semantic tokens, then run axe with `color-contrast` **enabled** in a real browser in both themes. |
| 16 | CSV formula injection | 8.13 | `batches.py:252` writes raw `original_filename`; `csv.writer` does not neutralise a leading `=`, `+`, `-` or `@`. Reachable by the `customer` role. Fix: one shared helper prefixing such cells, applied to every CSV writer. |
| 17 | Zero eager loading; all aggregation in Python | 7.4 | 0 hits for `selectinload`/`joinedload`/`subqueryload`. `_ar_ap` and `general_ledger` walk `transaction.payments` per row. Fix: `selectinload` on those two queries (one line, large win), then push aggregation into SQL. |
| 18 | Missing indexes on hot paths | 7.18 | `accounting_transactions.vat_period_id` (the VAT engine's primary filter), `.invoice_date`, `transaction_line_items.transaction_id`, `payments.transaction_id`, `documents(company_id, sha256_hash)`, `bank_transactions(company_id, booking_date)`. |
| 19 | Schema/migration divergence | 7.14 | 54 indexes from `3853605281ec` are absent from model metadata; `autogenerate` would propose dropping them. Tests use `create_all`, so they run **without** those indexes and the chain has no automated coverage. Fix: declare them in `__table_args__`, then CI jobs for `upgrade/downgrade/upgrade` and "autogenerate must be empty". |
| 20 | Missing uniqueness constraints | 8.7 | `FinancialYear(company_id, year)` — duplicates make `determine_vat_period(...).first()` non-deterministic across overlapping periods; `VatPeriod(financial_year_id, label)`; `Employee.linked_user_id` — `get_current_employee` uses an unordered `.first()`, so two rows sharing it could show one employee another's payslips. No FK has `ondelete=`. |
| 21 | `GET /vat-returns` writes on a read | 7.9 | Recomputes and commits for any status other than approved/locked, reachable by a `viewer`, with **no audit row** — while the explicit `POST /recalculate` does audit. A return in `ready_for_approval` can change underneath its approver. `lock_vat_return` also commits twice. |
| 22 | AI extraction: silent truncation and no first-payee control | 7.15 | `(preamble + text)[:50_000]` drops the **end** of a document — where totals and the IBAN block sit — with no flag. Untrusted text is concatenated into the prompt; forced tool use constrains shape, not values, so an injected IBAN reaches the ledger. `SUPPLIER_BANK_DETAILS_CHANGED` cannot fire for a first-time payee. |
| 23 | Case-sensitive email uniqueness | 8.16 | `users.py:89/159`, `employees.py:110` and `auth.py:191` compare exactly while `login` and `get_current_user` normalise. The unique index is case-sensitive, so `victim@corp.com` and `Victim@Corp.com` can coexist and `find_user_by_email(...).first()` has no deterministic `ORDER BY`. |
| 24 | Backup and restore defects | 7.12 | `restore_db.sh:16`'s `\|\| echo "0"` defeats the overwrite guard on any `psql` error. Dumps are unencrypted with default permissions and contain plaintext salaries. No retention, no schedule, no off-host copy, no storage-volume backup. `backup_db.sh` ignores `DATABASE_URL` despite its docstring. |
| 25 | No CI | 11.1 | No `.github/workflows`, GitLab CI, Jenkinsfile or Makefile. Every guarantee in these documents rests on a test someone must remember to run. |
| 26 | `invite_employee_self_service` writes no audit log | 8.15 | The only endpoint that creates a `User`, sets a password and links an employee — with zero audit trail. It also has **no frontend caller**, so the employee portal cannot be onboarded at all. |
| 27 | Unmaintained security dependencies | 7.16 | `python-jose` 3.3.0 (2021; CVE-2024-33663/33664) and `passlib` 1.7.4 (2020). `pytest`/`httpx` ship in the production `requirements.txt`. No `pip-audit`, `npm audit` or Dependabot. bcrypt truncates at 72 bytes with no maximum enforced. |

---

## P3 — quality, performance, hygiene

| # | Issue | Audit |
|---|---|---|
| 28 | `CompanyProvider` is dead weight: 38 of 55 pages re-fetch `/companies` themselves; the header switcher is disconnected from them | 2.3 |
| 29 | No data-fetching library: 38 copies of the same `useEffect` + `.then/.catch`, no `AbortController`, so rapid filter changes can paint a stale response | 2.3 |
| 30 | Accessibility: 24 labels with no `htmlFor` and no wrapping relationship (control has no accessible name) across 13 files — the project's own audit names 4; 2 of 196 `<th>` carry `scope`; 1 `<caption>`; 4 live regions across 55 routes; 3 `window.prompt()` calls where an axe-tested `GlassModal` exists | 7.8 |
| 31 | i18n residuals: 6 hardcoded English `aria-label`s in shared Glass components, `AuthGuard`'s `Loading…`, 7 raw enum renderings (including `kpis/page.tsx:32`, which labels the whole KPI dashboard from backend JSON keys), 9 raw backend free-text messages, 16 backend notes | 4.5 |
| 32 | Three translation stores and four hardcoded copies of the supported-locale list; the two backend `t()` helpers disagree on robustness (one falls back to Dutch, one raises `KeyError`); no automated guard against new hardcoded strings | 4.5, 8.12 |
| 33 | `lib/api.ts` is 1,513 lines with ~750 hand-maintained interfaces mirroring the Pydantic schemas; ~43 of 210 methods unused; no `typecheck` script despite the docs referencing one | 2.3, 11.5 |
| 34 | Duplicated API surface: `reports.py` vs `financial_reports.py` call the same engine functions behind two separately-defined tenant helpers; three dashboards; two cash-flow forecasts; two scenario-comparison endpoints | 2.7 |
| 35 | Seven endpoints with no frontend caller, including the GDPR data export and self-service deactivation | 4.6 |
| 36 | `Float` for money in the extraction staging tables; `_to_decimal` swallows `InvalidOperation` and returns `Decimal("0")`, turning a malformed amount into a zero-value line item | 8.6 |
| 37 | Frontend Dockerfile: `npm install` not `npm ci`, `package-lock.json*` wildcard, full devDependency tree copied into the runtime image, `npm` as PID 1, no `output: "standalone"`, healthcheck accepts any status < 500 | 7.6 |
| 38 | `storage.read()` uses a string-prefix check rather than `Path.is_relative_to`; uploads are read wholly into memory with no cap on openpyxl zip expansion | 8.9, 8.10 |
| 39 | Unauthenticated write + commit on `GET /billing/plans`; unvalidated `redirect_uri`/`success_redirect` echoed by the stub providers (latent open redirects); reset tokens not revoked on re-request; `/password-reset/confirm` unrate-limited | 8.18–8.21 |
| 40 | `seed.py` hardcodes `admin@onholland.nl` / `changeme123` and creates an `admin`, not an `owner` — so a seeded tenant has zero owners | 8.5 |
| 41 | Stray backups: `backend/app/main.py.bak` and two `frontend/app/globals.css.backup-*`. Now gitignored, not deleted — the CSS backups are currently the only record of the intermediate `:root[lang="fa"]` bug | 8.1 |
| 42 | The uncommitted CORS default still contains `http://192.168.68.105:3000`. Guarded now, not reverted (it is a user change) | 8.1 |
| 43 | `frontend/README.md` is unmodified `create-next-app` boilerplate; `frontend/AGENTS.md` is an auto-generated rules block; `next.config.ts:12` commits a developer LAN IP | 11.5 |
| 44 | `models/user.py:56` and `billing.py:105` reference `app.api.v1.admin`, which does not exist | 8.22 |
| 45 | No locale-prefixed routing: all four languages share one URL per page (cookie-only), so none is shareable or indexable per language | 4.3 |
| 46 | Documentation accuracy: `production-readiness.md` (Docker images, tenant isolation, session revocation, password reset), `security.md` (rate limiting, CSRF framing, "every company-scoped query goes through `require_company_access`"), `encryption-key-rotation.md` ("the only thing encrypted at rest is the BSN" — false since Phase 12/13), `gdpr-data-governance.md` (data export is not user-reachable), `untranslated-backend-messages-inventory.md` (enum values are not all translated), `README.md` (stops at Phase 9; understates the test count by 291), `accountant-ecosystem.md` (cross-tenant delegation withdrawn) | 11.6 |

---

## Absent capabilities that are not defects

Recorded so they are not mistaken for bugs. Each is either honestly surfaced in the UI as `unavailableKey` or documented as blocked on an external requirement.

Chart of accounts · RGS mapping · journal entries · opening balances · period close · customers · suppliers · quotations · recurring invoice generation · payment reminders · customer statements · fixed assets and depreciation · cost centres · projects · inventory · leave and absence · suppletie · ICP/OSS · SBR/Digipoort · XBRL · live PSD2/Open Banking · payment initiation · real payment processing · transactional email · outbound webhooks · data migration/import · per-company roles · customer portal screens · GDPR hard erasure · automated retention enforcement · MFA recovery codes.

**No return of any kind is submitted to or accepted by any authority, and nothing in these phases changed that.**
