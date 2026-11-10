# Phase 19 — Product Completeness

What the product is, what it is not, and the decisions that have to be made before it can be either more or less than it currently is.

Companion documents: `PHASE_19_FEATURE_MATRIX.md` (capability-by-capability status with evidence) and `PHASE_19_ACCOUNTING_AND_TAX_REVIEW.md` (calculation correctness).

---

## 1. What already works

Established first, per the brief, before anything was built. Verified against source and against executed tests, not against documentation.

**The document-to-ledger pipeline is real and complete.** Upload with magic-byte content sniffing (never trusting client MIME) → SHA-256 dedupe plus a business-duplicate heuristic → PyMuPDF text with Tesseract OCR fallback → Claude extraction behind forced tool use with a null-safe stub → a 13-rule deterministic validation engine → a status machine in which low confidence or any validation error forces manual review and **nothing auto-approves** → approval posts to the ledger. Bulk upload runs with bounded concurrency, rejects per file without aborting the batch, and shares the approval code path with the single-document route so the two cannot drift.

**Bank reconciliation is real.** Four import formats, DB-level idempotency, immutable source rows, transparent named-signal scoring, bounded 1:many search, and a reversal path that **voids** rather than deletes. Scenario C verifies the full chain including that a reversal leaves the payment row in place with `voided == True`.

**The VAT engine is mathematically sound and well tested.** 16 engine tests pin exact box values; Scenario D verifies boxes 1a, 1b, 5a, 5b and `net_payable` end to end through the API, then cross-checks them against the independently-built reconciliation view. Input-VAT eligibility is conservative by construction — it auto-assigns only `ELIGIBLE` or `REQUIRES_REVIEW`, never `INELIGIBLE`, and pro-rata defaults to 0% deducted rather than guessing. Scenario B proves a `REQUIRES_REVIEW` line contributes nothing to box 5b.

**Dutch payroll is real arithmetic, not a prototype.** Box 1 brackets, both heffingskortingen with the arbeidskorting phase-out curve, AWf with the flexible/permanent split, Aof, Whk, Zvw with the annual premium cap, the official *tabel bijzondere beloningen*, WKR free space, and the DGA `gebruikelijk_loon` norm. Expected values are recomputed from published rates inside the tests, and three official Belastingdienst table rows are parametrised within €1.00. Payslips are never edited in place; payroll-run idempotency is a DB constraint.

**Planning and analysis are real.** Budgets with an approval workflow that prevents an owner approving their own, immutable versioned revisions, forecasting that imports the cash-flow builder rather than reimplementing it, a scenario engine that stores only assumptions and recomputes on every read, and a KPI engine that returns `{value, formula, source, period, explanation, missing_data}` and yields `value: null` with an explanation rather than a misleading 0% or infinite ratio. That last design choice is rare and correct.

**Localisation is the strongest work in the repository.** 1,374 keys × 4 locales with zero drift, 55/55 routes translated, RTL CSS built on logical properties with a single deliberate and well-commented physical declaration, opt-in icon mirroring so a magnifying glass never flips, and a real Persian/Arabic PDF shaping pipeline. Phase 17 fixed the font wiring that Phase 16.3 shipped broken.

**The AI boundary is structural, not a promise.** Nothing in `app/services/ai_*.py` imports a model or a session. The assistant receives a pre-computed fact bundle and returns prose. An AI component cannot commit a financial transaction because it has no path to one.

---

## 2. What is missing, grouped by what it blocks

### 2.1 The double-entry foundation — blocks statutory reporting

No chart of accounts, no RGS mapping, no journal entries, no opening balances, no period close. `AccountingTransaction` carries net/vat/gross and a `ledger_side`; that is an invoice register, not a general ledger.

Consequences the code already admits in its own labels: `trial_balance()` is "best-effort … not a formal double-entry trial balance"; `balance_sheet()` computes an `imbalance_amount` and reports `is_balanced: false` rather than forcing a balance; `cash_flow_statement()` carries a note that accrual and cash "will not match exactly"; DIO and inventory turnover are returned as `missing_data` rather than assumed zero.

Reporting a gap instead of papering over it is admirable and applied consistently. But it means **five separate outputs declare themselves incomplete**. An accountant using this for a real Dutch BV hits the ceiling quickly: no auditable journal trail, no account-level reporting, no period close, no way to record anything the invoice pipeline does not produce.

### 2.2 Sales and purchases master data — blocks the workflows accountants expect

No `Customer` CRUD, no `Supplier` entity, no quotations, no recurring invoice *generation* (only detection), no payment reminders, no customer statements. Counterparties are free-text `counterparty_name` / `counterparty_vat_number` on each transaction, so there is no place to hang an address, a payment term, a credit limit, a dunning history or a verified IBAN.

This is also what makes audit finding 7.15 dangerous: with no supplier master record, there is no "first-time payee" concept, so the `SUPPLIER_BANK_DETAILS_CHANGED` anomaly rule cannot fire for a new counterparty and an AI-extracted IBAN has nothing to be checked against.

Both items are marked `unavailableKey` in `navConfig.ts` rather than faked, and `navConfig.test.ts` enforces "real route XOR marked unavailable" as an invariant. That is good practice and should be kept.

### 2.3 Fixed assets, cost centres, projects, inventory — blocks management accounting

None exist. Fixed assets are manually-entered `ManualBalanceSheetItem` rows whose summation semantics are broken (audit 7.2). No cost centre or project dimension, so there is no way to answer "what did this client/job cost". No inventory beyond a manual balance.

### 2.4 Orphaned backend capabilities — working code nobody can reach

Seven endpoints have **no frontend caller** (audit 4.6). Two matter:

- `PATCH /transactions/{id}/line-items/{line_item_id}` — the mechanism for resolving an `input_vat_eligibility = REQUIRES_REVIEW` line, and therefore the mechanism that makes box 5b correct. **An accountant cannot resolve a VAT eligibility review through the product.**
- `POST /employees/{id}/invite-self-service` — the *only* way an `employee`-role account is created. **The employee portal cannot be onboarded**, despite nine working backend endpoints and a built frontend page. It is also the one privileged user-creation path with no audit log.

The remaining five: both password-reset endpoints (no UI at all), `GET /auth/me/data-export` (the GDPR Art. 15/20 right of access is not user-reachable), and `POST /auth/me/deactivate`.

### 2.5 Duplicated surface — a maintenance tax and a correctness risk

`reports.py` and `financial_reports.py` both expose P&L and balance sheet, calling the *same* engine functions, each with its **own** tenant-checking helper (`_get_company_or_404` vs `_get_company`, identical logic). Three dashboards overlap. Two cash-flow forecasts. Two period-comparison endpoints and two scenario-comparison endpoints, the latter pair calling the same engine with duplicated tenant logic.

Every duplicate is a second place where a tenant check, a role guard, an FX fix or an `approval_status` filter must be applied and can be missed. The seven cross-tenant omissions found in Phase 17 are the realised form of that risk.

---

## 3. The decision that has to be made

**Stay single-entry, or build the general ledger.** This is a product decision, not an engineering task, and it should be made before further feature work — because almost everything in §2.1 and much of §2.3 depends on which way it goes.

**Option A — reposition as a VAT-administration and management-information tool for accountants.** Cheaper, honest, and the existing code already supports it. Requires relabelling "trial balance" and "balance sheet" as management estimates rather than statutory statements, and dropping the pretence of statutory annual reporting. Compatible with everything built so far.

**Option B — build the double-entry ledger.** An `Account` model with an RGS-referenced chart, `JournalEntry` with balanced `JournalLine`s, posting of every existing transaction as a journal, an opening-balance mechanism replacing `ManualBalanceSheetItem`, and a real period close. Roughly 6–10 weeks, touching every report. This is what makes the product an accounting system rather than an invoice-and-VAT system, and it is a prerequisite for RGS compatibility and for credible annual statements.

**The current state — statutory outputs from a ledger that cannot support them, with the gaps documented but not closed — is the worst of the three options.** It is neither a clean management-information tool nor a real accounting system, and an accountant evaluating it will discover the ceiling within a day.

---

## 4. What was implemented in this phase

Deliberately narrow. Per the brief's prioritisation (incorrect financial calculations first, then data integrity), and per rule 12 (no large architectural rewrites), Phase 19 fixed the four defects that produce **wrong numbers or wrong data** and can be fixed without a product decision:

| # | Fix | Audit ref | Severity | Tests |
|---|---|---|---|---|
| 1 | Cash-based VAT period assignment on both payment paths | 6.2 | CRITICAL | 9 |
| 2 | `previous_period()` calendar arithmetic | 7.3 | HIGH | 10 + 3 updated |
| 3 | `PaymentCreate.amount > 0` | 8.8 | MEDIUM | 5 |
| 4 | DB-level uniqueness on `source_document_id` + migration + `409` mapping | 6.6 | CRITICAL | 3 |

Plus, from Phase 20's brief but landed here: **7 end-to-end API scenarios** (sales, purchases, banking, VAT lifecycle, period isolation, cash-based VAT) asserting exact figures at every step.

**Five verified defects were deliberately NOT fixed** because each requires an accounting or legal decision — `VatPeriod.status` never assigned (6.1), `approval_status` affecting no figure (6.3), no FX in reports (7.1), `ManualBalanceSheetItem` semantics (7.2), and the 2025-only tax rule set (6.5). Each is documented with its evidence, its consequence and the options in `PHASE_19_ACCOUNTING_AND_TAX_REVIEW.md` §5. Guessing at any of them would have changed reported statutory figures without authority, which rule 8 and rule 14 forbid.

**Nothing superficial was built.** No new screens, no placeholder entities, no mock integrations. The brief was explicit that this phase is not permission to pretend, and the feature matrix records absence as absence.

---

## 5. UX and localisation review (19.4)

Reviewed; one defect fixed and the rest recorded.

**Fixed in Phase 17, re-verified here.** Persian leads with Vazirmatn, Arabic now leads with Noto Sans Arabic (previously both led with the Persian face), Dutch and English retain Geist, `:lang()` matches full BCP-47 tags, and both variables resolve to real family names in the **production CSS bundle** with all eight `@font-face` families emitted and zero `[lang=` attribute selectors.

**Locale-aware formatting is correct.** 0 of 140 `formatEUR`/`formatDate`/`formatPercent`/`formatRelativeDate` calls omit the `locale` argument.

**RTL is well executed.** Logical properties throughout; one deliberate `text-align: right` on numeric columns with an 8-line comment explaining the Excel convention; `background-position` given an explicit `[dir="rtl"]` override because CSS has no logical form for it; opt-in `.icon-directional` mirroring. One `space-x-2` is the only physical-direction utility in the app. **No RTL regression was introduced** — the 13 structural font tests and the 175-test frontend suite both pass, and `next build` succeeds.

**Open, unchanged from the audit:**

| Gap | Count | Note |
|---|---|---|
| Hardcoded English `aria-label` in shared Glass components | 6 | Screen readers announce English in all four locales. `GlassSidebar.tsx` imports `useTranslations` and translates everything else. |
| `AuthGuard.tsx:16` `Loading…` | 1 | First paint of all 53 guarded routes |
| Raw backend enum values via `.replace(/_/g," ")` | 7 | **`app/kpis/page.tsx:32` labels the entire KPI dashboard from backend JSON keys** |
| Raw backend free-text messages | 9 | English validation/anomaly strings shown to Persian and Arabic users. Correctly analysed in `docs/untranslated-backend-messages-inventory.md` as needing a schema change (store rule code + params, render at read time). |
| Backend explanatory notes | 16 | Including one in the annual-statement PDF |
| Labels with no `htmlFor` and no wrapping relationship | 24 across 13 files | The control has **no accessible name**. The project's own audit names 4 files; it is under-counted 3×. |
| `<th scope=…>` | 2 of 196 | Essentially no table header semantics across ~30 data tables — the most consequential accessibility gap for a product whose output is tabular financial data |
| `window.prompt()` used as an input dialog | 3 | Rejection/correction reasons. Unstylable, no validation, returns `null` on cancel and silently aborts the mutation. `GlassModal` exists, is focus-trapped and is axe-tested. |
| Dark-mode contrast on the error surface | 48 elements / 43 files | `bg-red-50` + `text-error` computes to **2.53:1** in dark mode against a 4.5:1 AA requirement. `scripts/contrast-check.py` cannot see it because it only compares CSS token pairs, and `test/axe.ts` disables `color-contrast` because jsdom has no layout engine. |
| Route-level tests | 0 of 55 | No `app/**/page.tsx` has a unit test |

**Form validation, loading and empty states are inconsistent.** `GlassLoadingState` is used by 13 of 55 pages and `GlassEmptyState` by 4. Error handling is uniform but shallow: `.catch(e => setError(e.message))` surfaces the backend's raw English `detail` verbatim, never distinguishes 401/403/404/422/500, and `ApiError.status` is captured but never read by any caller. Every page that calls the API does have at least one `.catch` ✓.

**Dashboard consistency:** three overlapping dashboard endpoints (§2.5) and a KPI page whose row labels are untranslated snake_case.

---

## 6. Prioritisation applied

The brief's order was: incorrect financial calculations → data integrity → security and tenant isolation → incomplete core bookkeeping → VAT and tax correctness → sales/purchase workflows → banking → reporting → payroll → AI.

Phases 17–20 followed it exactly:

1. **Incorrect financial calculations** — Phase 19 fixes 1 and 2 (cash-based VAT zeros, wrong comparison periods).
2. **Data integrity** — Phase 19 fixes 3 and 4 (negative payments, double-posting).
3. **Security and tenant isolation** — Phase 17 (8 vulnerabilities, mutation-verified) and Phase 18 (production boot validation).
4. **Incomplete core bookkeeping** — §2.1 and §3. Documented with a decision required, not partially implemented.
5. **VAT and tax correctness** — §5.5 and §5.6 of the accounting review. Documented; blocked on authoritative rate verification and on a UI for `vat_treatment`.
6–10. **Sales/purchases, banking, reporting, payroll, AI** — status recorded in the feature matrix; no changes, because each is either already real or requires the §3 decision first.

Where a feature was too large for the window, a detailed plan was written instead of an incomplete implementation — specifically for the double-entry ledger (§3), FX-aware reporting (accounting review §5.3), manual balance-sheet item semantics (§5.4) and the 2026 tax rule set (§5.5).
