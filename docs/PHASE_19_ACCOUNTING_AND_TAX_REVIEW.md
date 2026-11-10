# Phase 19 — Accounting and Tax Review

Every issue below was **verified in the current source** before any change was made, per rule 4. Where a fix was applied it is marked FIXED with its regression test; where it was not, the reason is stated — in three cases because fixing it correctly requires an accounting or legal decision that is not mine to make.

All monetary values are `Decimal` end to end in the ledger (`Numeric(14,2)`), rates `Numeric(6,3)`, FX `Numeric(12,6)`. No floating-point arithmetic was introduced anywhere in this phase, and no test asserts on a float.

---

## 1. FIXED — cash-based VAT companies produced permanently zero returns

**Audit 6.2. Severity: CRITICAL. Statutory output wrong.**

### Verification

`app/accounting/period_assignment.py:29-33`:
```python
if company.vat_accounting_basis == VatAccountingBasis.cash_based:
    if payment_date is None:
        return None
    anchor_date = payment_date
```
That is correct behaviour — the period for a cash-based company is the one containing the payment date, which is unknowable at posting time.

Both callers omit `payment_date`, so it defaults to `None`:
```python
# ledger_service.py:185  (post_document_to_ledger)
transaction.vat_period = determine_vat_period(db, company, financial_year.id, ledger_side, invoice_date, received_date)
# ledger_service.py:284  (create_manual_entry)
transaction.vat_period = determine_vat_period(db, company, financial_year_id, ledger_side, invoice_date, invoice_date)
```

Nothing reassigned it afterwards. `grep -rn "vat_period" app/accounting/reconciliation_service.py` returned **nothing**, and `record_payment` touched only `payment_status`.

**The smoking gun:** `app/api/v1/transactions.py:8` contained `from app.accounting.period_assignment import determine_vat_period` with `grep -c "determine_vat_period(" → 0`. The import was dead; the fix had been intended for the payment path and never written.

Since `calculate_vat_return` filters on `vat_period_id`, every cash-based transaction was excluded and **all boxes computed to `Decimal("0")` — silently, with no error and no reconciliation flag.**

### Fix

Added `period_assignment.assign_vat_period_on_payment(db, transaction, payment_date)` and called it from **both** payment paths:
- `api/v1/transactions.py::record_payment` (replacing the dead import)
- `accounting/reconciliation_service.py::approve_match`

It is a deliberate no-op when the transaction already has a period, or when the company is not cash-based — so invoice-based companies are unaffected and `determine_vat_period`'s documented contract ("payment date never moves an invoice-based transaction to another period") is preserved.

### Regression tests (9)

`tests/test_phase19_accounting_fixes.py`:
- `test_determine_vat_period_returns_none_for_an_unpaid_cash_based_transaction` — pins the pre-existing correct behaviour the fix depends on
- `test_cash_based_transaction_is_unassigned_until_a_payment_is_recorded`
- `test_cash_based_payment_lands_in_the_period_of_the_payment_not_the_invoice` — a February invoice paid in October belongs to Q4
- `test_invoice_based_period_is_never_moved_by_a_later_payment` — guards against the fix over-reaching
- `test_already_assigned_cash_based_transaction_is_not_reassigned`
- `test_cash_based_vat_return_is_zero_before_payment_and_correct_after` — asserts `box_1a_net == 0` then `1000.00`, `box_1a_vat == 210.00`, `net_payable == 210.00`
- `test_recording_a_payment_through_the_api_assigns_the_period` — the HTTP path
- `test_bank_match_approval_also_assigns_the_cash_based_period` — the reconciliation path, asserting an August booking date lands in Q3

`tests/test_phase20_e2e_scenarios.py::test_scenario_d_cash_based_company_return_follows_the_payment` — full API chain: create company → `PATCH` to `cash_based` → post a February invoice → assert `vat_period_id is None` and Q1 is zero → pay in May → assert Q1 is *still* zero and Q2 now shows `1000.00 / 210.00 / 210.00`.

---

## 2. FIXED — `previous_period()` was wrong for quarters and leap years

**Audit 7.3. Severity: HIGH. Comparison figures wrong.**

### Verification

```python
def previous_period(period: DateRange) -> DateRange:
    length = (period.end - period.start).days
    return DateRange(period.start - relativedelta(days=length + 1), period.start - relativedelta(days=1))
```

Q1 2026 (1 Jan – 31 Mar) has `length = 89`, so the "previous quarter" was `1 Jan − 90 days = 3 Oct 2025` to `31 Dec 2025`. **Q4 starts on 1 October** — two days silently dropped from every quarterly comparison. For an annual period in a leap year (2024, `length = 365`) the result was `31 Dec 2022 – 31 Dec 2023` instead of `1 Jan 2023 – 31 Dec 2023`. `year_on_year_period()` three lines below already did this correctly with `relativedelta`.

### Fix

Added `_whole_calendar_months(period)`, which returns the month count when the period is calendar-aligned (starts on the 1st, ends on the last day of a month) and `None` otherwise. `previous_period` now steps back by whole months for aligned periods and falls back to the day count for arbitrary ranges — the best available answer when there is no calendar shape to preserve.

### An existing test encoded the bug

`tests/test_financial_reports.py::test_previous_period_same_length` asserted:
```python
assert (prev.end - prev.start).days == (period.end - period.start).days
```
For February 2027 that demands a 28-day predecessor ending 31 January — i.e. **4–31 January**, dropping 1–3 January. Months and quarters genuinely differ in length, so equal day counts is not the property worth pinning.

**This is the only pre-existing test modified in Phases 17–20.** It was renamed to `test_previous_period_is_the_whole_preceding_calendar_period`, its first assertion (`prev.end == date(2027, 1, 31)`) was kept unchanged because it was always correct, and a docstring records exactly what the second assertion got wrong and why. Two sibling tests were added for the quarter and leap-year cases.

### Regression tests (10)

In `test_phase19_accounting_fixes.py`: every quarter steps back to the exact previous quarter (4 parametrised); every month including February in leap and non-leap years (4 parametrised); annual periods spanning a leap year; **twelve monthly previous periods tile Dec 2025 – Nov 2026 exactly once with no gap and no overlap** and the total day count reconciles; a non-calendar range falls back to day arithmetic; and `previous_period` agrees with the independent `resolve_period` implementation for all four quarters.

**Mutation-tested:** reverting `previous_period` to day arithmetic produced **10 failures**, restore verified by SHA-256 checksum, 29 passing again.

---

## 3. FIXED — negative and zero payments were accepted

**Audit 8.8. Severity: MEDIUM. Data integrity.**

`PaymentCreate.amount: Decimal` had no bound. A negative payment was committed, fed into `payment_engine.compute_payment_status`, and inflated `remaining_balance` — able to flip a settled invoice back to `UNPAID` and corrupt debtors/creditors aging, the cash-flow statement and DSO. The correct way to undo a wrong payment already exists (`reconciliation_service` voids, never deletes).

**Fix:** `amount: Decimal = Field(gt=0)`. Precision was deliberately left to the `MONEY` column (`Numeric(14,2)`) rather than re-specified here, so the change constrains only what the finding requires.

**Tests:** schema-level rejection of `0`, `-0.01`, `-1210.00`; acceptance of a positive amount; and an API test asserting `422`, no `Payment` row created, `payment_status` still `UNPAID`, followed by a legitimate payment succeeding with `201`. Scenario A additionally fires a negative payment *after* settling an invoice and re-verifies the balance is undisturbed.

---

## 4. FIXED — no database guard against double-posting a document

**Audit 6.6. Severity: CRITICAL. Statutory figures wrong under concurrency.**

`post_document_to_ledger` guarded idempotency with a SELECT-then-INSERT:
```python
existing = db.query(AccountingTransaction).filter(
    AccountingTransaction.source_document_id == document.id).first()
if existing is not None:
    return existing
```
Single-threaded only. Two concurrent `POST /documents/{id}/approve` requests — a double-click, a browser retry, a load-balancer replay — both see no existing row and both insert. `AccountingTransaction` had **no `__table_args__` at all**; only four `UniqueConstraint`s existed in the entire model layer, and payroll had received exactly this guard in Phase 12 (`uq_payroll_run_period`).

**Fix:** `UniqueConstraint("source_document_id", name="uq_accounting_transaction_source_document")` on the model, plus migration `e4f7a9c2b1d8`, plus `IntegrityError → 409` in `documents.py::approve_document` with an explicit `db.rollback()` (an `IntegrityError` leaves the session in a failed state that would otherwise break every subsequent query on it) and a `logger.warning` naming the document and user.

Manual entries and corrections are unaffected: they set `source_document_id = NULL` and Postgres treats NULLs as distinct. **Verified before adding the constraint** that `create_correction` routes through `create_manual_entry`, which passes `None` explicitly.

**The migration refuses rather than repairs.** If duplicate postings already exist it raises `RuntimeError` listing each `document_id`, its posting count and the transaction ids, instructing the operator to resolve each pair with a voiding correction — never a `DELETE` — and re-run. It does not modify or delete any financial record.

**Migration verified against a scratch database:** `upgrade head` (23 migrations, 48 tables) → constraint present → `downgrade -1` → constraint gone, version back to `d90e97d4bc35` → `upgrade head` → constraint present again. Full transcript in `PHASE_18_TEST_RESULTS.md` §1.

**Tests:** two transactions cannot share a source document (`IntegrityError`); many transactions may have `NULL`; and the constraint is declared on the **model**, not only in the migration — because tests build the schema with `create_all`, a migration-only constraint would never be exercised (audit 7.14).

---

## 5. NOT FIXED — and why

Each of these was verified as a real defect. None was fixed, because doing so correctly requires a decision that is not an engineering one, and guessing would change reported figures without authority.

### 5.1 `VatPeriod.status` is never assigned (audit 6.1) — CRITICAL

`grep -rn "\.status = VatPeriodStatus\|status=VatPeriodStatus" app/` returns **zero hits**. The column is only ever read:
- `financial_reports._outstanding_vat_position` filters `VatPeriod.status != paid`, so the filter never excludes anything and **every VAT return ever computed is summed into the balance sheet's VAT liability forever**. Paying a VAT bill has no effect. This corrupts `total_liabilities`, `is_balanced`, `imbalance_amount`, the current and quick ratios, ROA and the working-capital trend.
- `dashboard.py:76` computes "open VAT periods" as *all periods ever*.

**Why not fixed here:** it needs new endpoints (`mark-filed`, `mark-paid`) or a derivation from `VatReturn.status`, plus a decision about **who** may declare a period paid and whether that should be audited and reversible. That is a workflow design decision with accounting implications, not a code fix. It is the single highest-value open item in the product and should be first in any follow-up.

**Interim mitigation available without a decision:** filter `_outstanding_vat_position` on `VatReturn.status not in (approved, locked)` as the closest available proxy, and count returns rather than periods on the dashboard. Both are strictly better than today. Neither was applied, because both change reported figures and should ship with their own tests and a note to users.

### 5.2 Transaction `approval_status` affects no reported figure (audit 6.3) — CRITICAL

`grep -rn "approval_status" app/accounting/ app/reporting/` returns exactly **one** hit — the FX-rate guard at `ledger_service.py:195`. `vat_engine`, P&L, balance sheet, trial balance, GL, KPIs and every export all include `DRAFT` transactions. `POST /transactions/{id}/approve` writes an audit row and blocks later edits, but **approving changes nothing that is computed**. Scenario B confirms the edit-block works (`409` after approval); nothing makes the approval affect a figure.

**Why not fixed here:** two defensible semantics exist and they give different numbers.
- If a transaction posted from an *approved document* should be immediately effective, `post_document_to_ledger` must set `APPROVED` — but that also flips on the edit-block for every document-posted transaction, changing behaviour the current tests depend on.
- If unapproved manual entries should be excluded from returns, every report and the VAT engine need an `approval_status != DRAFT` filter — which would remove figures accountants currently see.

Either choice alters reported statutory numbers. It needs an accounting decision, then a coordinated change with a reconciliation line showing what is excluded. Documented, not guessed.

### 5.3 No FX handling outside the VAT engine (audit 7.1) — HIGH

`grep -rn "net_amount_eur\|currency"` across `financial_reports.py`, `working_capital.py`, `financial_forecast.py`, `kpi_engine.py` and `budget_service.py` returns **zero hits**. All sum `net_amount` regardless of currency. The VAT engine handles FX carefully (excludes unresolved, converts resolved, never guesses rate 1); that discipline stops at the VAT engine.

**Why not fixed here:** the correct treatment is a design choice — convert at the transaction's confirmed rate, or exclude unresolved-FX rows as the VAT engine does, or report per-currency and refuse to total. Each produces different figures. It also touches ~15 functions and every export at once, and needs its own test cycle with mixed-currency fixtures. Too large and too consequential to land safely in the remaining window alongside four other fixes.

### 5.4 `ManualBalanceSheetItem` sums stocks as though they were flows (audit 7.2) — HIGH

`_manual_items_total` adds **every** row with `as_of_date <= X`. A balance-sheet item is a point-in-time stock, so recording "Fixed assets €50,000" twice yields €100,000. There is no `version`, no `supersedes_item_id`, no unique constraint, and no UI convention telling an accountant whether a row is a balance or a signed delta. Feeds `total_assets`, `total_liabilities`, `total_equity`, `is_balanced`, the trial balance, the cash-flow statement's investing and financing sections, and every liquidity and ROA KPI.

**Why not fixed here:** the fix is a semantics decision — make rows *movements* (rename, document, require signed amounts) or keep them *balances* and change the query to "latest row per `(category, label)` with `as_of_date <= X`" plus a unique constraint. Budgets solved the analogous problem correctly with `version`/`supersedes_budget_id`; balance-sheet items need the same treatment. Either choice changes reported balances.

### 5.5 Tax rules are frozen at 2025 (audit 6.5) — CRITICAL compliance risk

```python
_RULE_SETS: dict[int, DutchTaxRuleSet] = {2025: RULES_2025}
CURRENT_TAX_YEAR = 2025
```
and `RULE_VERSIONS = {"nl-2024": …}` — **one entry each; neither versioning mechanism has ever been exercised.** Six production call sites invoke `get_rule_set()` with no argument and nothing derives the year from the clock, so `get_rule_set(2026)` would raise but `get_rule_set()` silently returns 2025.

**Why not fixed here:** rule 8 forbids inventing tax rules or rates, and rule 3.19.3 requires marking anything unverified as needing authoritative confirmation. Adding a 2026 rule set means transcribing box-1 brackets, heffingskortingen, AWf/Aof/Whk/Zvw rates, `max_premieloon`, the DGA norm, zelfstandigenaftrek and the KOR threshold from primary Belastingdienst sources, and the reduced VAT rate for 2026. **I did not verify any 2026 figure against an authoritative source in this session, and I will not write numbers I cannot cite.** The finding is that the system has no mechanism to know and no mechanism to warn — which is true regardless of whether any specific rate changed.

**The safe part of the fix, which does not require new rates, is recorded as the top recommendation:** make the default year clock-derived (`current_tax_year()` returning `date.today().year`) so `get_rule_set()` *raises* for a year nobody has loaded instead of silently serving last year's, add a startup check that refuses to boot outside development when the current year is missing, and add a test asserting `get_rule_set(date.today().year)` succeeds — a test deliberately designed to fail once a year, forcing the annual update. That is ~1 day of work and converts a silent compliance failure into a loud one.

### 5.6 Four VAT boxes are unreachable automatically (audit 7.11) — HIGH

`classify_default_treatment` can never return `domestic_reverse_charge_received` (2a), `export_non_eu` (3a), `import_non_eu` (4a) or `private_use` (1d). The refusal to guess is correct. The consequence is not surfaced: those boxes are always `0.00` unless an accountant creates a manual entry with the right treatment, and `PATCH /transactions/{id}/line-items/{line_item_id}` — which updates only `input_vat_eligibility`, not `vat_treatment` — has **no frontend caller at all**. Box 2a is doubly affected, since reverse-charge VAT belongs in both 5a and 5b and `box_5b_vat` accumulates only `deductible_vat_amount`, which is `0` for a `REQUIRES_REVIEW` line by design.

**Not fixed:** adding `vat_treatment` to the line-item PATCH is straightforward, but doing so without a UI and without a reconciliation warning would create a field nobody can set. Recorded as a paired backend+frontend item.

---

## 6. Verified correct — no change needed

Recorded so this review is not read as uniformly negative. Each was checked in source and, where applicable, by an executed test.

| Area | Evidence |
|---|---|
| VAT box mapping and arithmetic | Scenario D asserts `box_1a_net 1000.00`, `box_1a_vat 210.00`, `box_1b_net 500.00`, `box_1b_vat 45.00`, `box_5a_vat 255.00`, `box_5b_vat 42.00`, `net_payable 213.00` — all exact. 16 pre-existing engine tests also pin exact box values. |
| Return-to-ledger reconciliation | Scenario D cross-checks the box totals against the *independently built* reconciliation view: `sales_total_net 1500.00`, `purchases_total_net 200.00`, `sum(sales_vat_by_rate) == box_5a_vat`, `sum(purchase_vat_by_rate) == box_5b_vat`, `box_1a_vat + box_1b_vat == sales VAT`, and all five "unsafe to file" lists empty. |
| Period isolation | `test_scenario_d_vat_return_excludes_other_periods` — an April invoice appears in Q2 (`900.00 / 189.00`) and Q1 stays `0.00`. |
| Return lifecycle and locking | `draft → ready_for_approval → approved → locked` walked through the API; after locking, a direct transaction edit returns `409` and a plain `GET` does not silently recompute a locked return. |
| Conservative input-VAT handling | `test_scenario_b_unresolved_eligibility_contributes_nothing_to_box_5b` — a `REQUIRES_REVIEW` line yields `deductible_vat_amount == 0.00` and `box_5b_vat == 0.00`. It never guesses a deduction. |
| Approved-transaction immutability | Scenario B: `PATCH` after approval → `409`. |
| Payment voiding preserves the audit trail | Scenario C: after reversal the `Payment` row count is unchanged and exactly one row has `voided == True`. |
| Bank import idempotency | Scenario C: re-importing the identical file gives `transaction_count == 0`, `duplicate_count == 1`. |
| Decimal discipline | Every assertion above compares `Decimal` to `Decimal` on **string** JSON values. Money is never a float in the API contract. |
| Financial-year locking | `_ensure_financial_year_open` is the single choke point; cross-tenant lock/unlock closed in Phase 17 and mutation-verified. |
| Payroll and tax-rule arithmetic | 27 pre-existing tests recompute expected values from published rates in the test itself; three official Belastingdienst table rows are parametrised within €1.00. All still pass. |
| Monthly P&L reconciles to annual | `test_monthly_pnl_sums_reconcile_to_annual_pnl` — 12 monthly figures sum to the annual one and to `Decimal("1200.00")`. Still passes after the `previous_period` change. |

---

## 7. Dutch compliance position

**This application is not legally compliant, and nothing in this phase makes it so.** It contains tax calculations. Compliance is a different claim and requires verification against primary sources by a qualified Dutch tax professional.

| Requirement | Position |
|---|---|
| VAT rates | 21% / 9% under rule version **`nl-2024`** — the only version that exists. **Requires authoritative confirmation for 2026.** |
| VAT return periods and deadlines | Generated deterministically with the Dutch filing rule. Correct in structure; the deadline offsets were not re-derived from primary sources in this session. |
| VAT return completeness | Boxes 2a, 3a, 4a and 1d cannot be populated automatically (§5.6). A company that exports outside the EU or receives reverse-charge services will under-declare and **the platform will not tell them**. |
| ICP (EU sales list) | Not tracked. Reported as `NOT_TRACKED`, honestly. |
| RGS compatibility | **Absent entirely.** No RGS reference in the codebase. |
| SBR / XBRL | **Absent.** No XBRL generation, no SBR connector, no certificate. `NOT_CONFIGURED`. The old Digipoort retired 2026-04-01, so any future work must target its replacement. |
| Financial-year handling | Real and enforced. But `FinancialYear` has **no unique constraint on `(company_id, year)`**, so duplicate years with overlapping VAT periods are possible, and `determine_vat_period` uses `.first()` — making period assignment non-deterministic in that state. Audit 8.7, **open**. |
| Payroll tax | Real and validated against official tables — **for tax year 2025 only** (§5.5). |
| WKR | Free space is computed, but there is no WKR-scoped expense register to feed it. |
| DGA | `gebruikelijk_loon` norm and a DGA position endpoint, both returning `requires_accountant_confirmation: True`. Correct posture; **2025 norm only**. |
| `bewaarplicht` (7/10-year retention) | A documented policy, not enforced code. |

**Every tax figure the platform produces should be treated as requiring professional verification until the rule sets are versioned by tax year and confirmed against primary sources.** The codebase already says this in many places (`requires_accountant_confirmation: True`, `confidence: "requires_data_not_tracked"`, "best-effort" labels) — that honesty is a genuine strength and should be preserved, not papered over.
