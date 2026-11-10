# Phase 19 — Feature Matrix

Evidence-based status of every capability the brief lists. Each row was verified against source, not against documentation.

**Status key**

| Code | Meaning |
|---|---|
| ✅ **REAL** | Implemented, wired end to end, and covered by a test that asserts values |
| 🟡 **PARTIAL** | Implemented but incomplete, or correct in one layer and wrong in another |
| 🟠 **CALC ONLY** | The calculation exists; there is no UI, no persistence, or no workflow around it |
| ⬜ **ABSENT** | No code path exists |
| 🔒 **BLOCKED** | Requires an external credential, registration or legal agreement |
| ⚠️ **STUB** | A deliberate, documented sandbox stand-in with no real integration |

For tax returns the brief asks for five distinct levels. They are recorded separately in §5.

---

## 1. Accounting foundation

| Capability | Status | Evidence |
|---|---|---|
| Companies | ✅ REAL | `models/company.py`, full CRUD in `api/v1/companies.py`, tenant-scoped |
| Financial years | ✅ REAL | `models/financial_year.py`, generated VAT periods, `POST /companies/{id}/financial-years` |
| **Chart of accounts** | ⬜ **ABSENT** | No `Account` model exists. `navConfig.ts:63` marks it `unavailableKey`. |
| **RGS mapping** | ⬜ **ABSENT** | No RGS reference anywhere in `app/`. |
| **Journal entries** | ⬜ **ABSENT** | No `JournalEntry`/`JournalLine`. The ledger is single-entry: `AccountingTransaction` carries net/vat/gross and a `ledger_side`. |
| General ledger | 🟡 PARTIAL | `financial_reports.general_ledger()` produces a chronological listing with running balance — real and tested — but it is a *report over the single-entry ledger*, not a double-entry GL. |
| Trial balance | 🟡 PARTIAL | Implemented and tested with exact values. Its own docstring labels it "best-effort … not a formal double-entry trial balance". Opening retained earnings is derived, not posted. |
| Profit and loss | ✅ REAL | 20 exact-value tests; `test_monthly_pnl_sums_reconcile_to_annual_pnl` is a genuine cross-check. **But not FX-aware** (§2 note). |
| Balance sheet | 🟡 PARTIAL | Implemented, reports `is_balanced` and `imbalance_amount` honestly rather than forcing a balance. Three defects: VAT liability never clears (audit 6.1), manual items summed as flows (7.2), no FX (7.1). |
| **Opening balances** | ⬜ ABSENT | Only `ManualBalanceSheetItem` rows, whose semantics are broken (audit 7.2). |
| Period locking | ✅ REAL | `_ensure_financial_year_open()` is the single choke point for postings, manual entries and corrections. Lock/unlock endpoints, `require_admin`, audit-logged. Cross-tenant access closed in Phase 17. |
| Audit trail | ✅ REAL | `AuditLog`, append-only by convention, 4 composite indexes, `request_id` correlation, 41 call sites. **Redaction applied in only 2 of 11 writing routers** (audit 8.3). |
| Reversals and corrections | ✅ REAL | Corrections are new rows (`corrects_transaction_id`), never in-place edits. Payments are voided, never deleted. Both verified end to end in `test_phase20_e2e_scenarios.py`. |

> **The single largest architectural gap.** This platform files a statutory VAT return and issues payslips while running on a single-entry invoice ledger with no chart of accounts, no journal and no period close. Everything a real GL would provide is either manually entered, derived by heuristic, or explicitly reported as unavailable. That is honest, and it is also a ceiling: no auditable journal trail, no account-level reporting, no way to record anything the invoice pipeline does not produce. See `PHASE_19_PRODUCT_COMPLETENESS.md` §3 for the two defensible paths forward.

---

## 2. Sales

| Capability | Status | Evidence |
|---|---|---|
| **Customers** | ⬜ ABSENT | A `Customer` model exists but has no CRUD surface. `navConfig.ts:74` marks it `unavailableKey`. Counterparties are free-text `counterparty_name` / `counterparty_vat_number` on the transaction. |
| **Quotations** | ⬜ ABSENT | No model, no endpoint. |
| Sales invoices | ✅ REAL | `AccountingTransaction` with `ledger_side=SALES`, line items, `TransactionType.sales_invoice`. Verified end to end (Scenario A). |
| **Recurring invoices** | 🟠 CALC ONLY | `recurring_detection.py` *detects* recurring counterparties and classifies the interval, with a `MISSING` flag. It never generates an invoice. |
| Credit notes | ✅ REAL | `TransactionType.credit_note`, sign-handled in the VAT engine, tested. |
| Payment registration | ✅ REAL | `POST /transactions/{id}/payments` + bank-match approval. **Phase 19 added `amount > 0` validation** (audit 8.8) and cash-based VAT period assignment (audit 6.2). |
| Outstanding invoices | ✅ REAL | `debtors()` with aging buckets; Scenario A asserts a fully-paid invoice leaves `total_outstanding == 0.00`. |
| **Payment reminders** | ⬜ ABSENT | No dunning logic, no reminder entity, no email provider to send one. |
| **Customer statements** | ⬜ ABSENT | No statement report. `debtors()` is an aging list, not a per-customer statement. |

**FX note applying to this whole section and to §7:** `grep -rn "net_amount_eur\|currency"` across `financial_reports.py`, `working_capital.py`, `financial_forecast.py`, `kpi_engine.py` and `budget_service.py` returns **zero hits**. All of them sum `net_amount` regardless of currency, so a company with a $1,000 and a €1,000 invoice reports revenue of "2,000" with no currency label. Only the VAT engine handles FX correctly. Audit 7.1 — **open**.

---

## 3. Purchases

| Capability | Status | Evidence |
|---|---|---|
| **Suppliers** | ⬜ ABSENT | No `Supplier` entity. `navConfig.ts:75` marks it `unavailableKey`. Free-text counterparty fields only. |
| Purchase invoices | ✅ REAL | `ledger_side=PURCHASES`, per-line `input_vat_eligibility` and `deductible_vat_amount`. Scenario B verifies classification end to end. |
| **Expense management** | 🟡 PARTIAL | `expense_category` + `category_confidence` + `category_source` on the transaction, and `expense_breakdown()`. No expense claims, no per-employee expenses, no approval workflow for expenses as distinct from invoices. |
| Document attachments | ✅ REAL | `Document` with magic-byte validation, SHA-256 dedupe, per-company duplicate detection, storage under `tenant/company/`. |
| OCR and AI extraction | ✅ REAL | PyMuPDF text → Tesseract OCR fallback (Dutch pack installed) → Claude with forced tool use. Low confidence or any validation error forces `needs_review`; nothing auto-approves. |
| Approval workflows | ✅ REAL | `pending → processing → extracted/needs_review → approved/rejected/failed`; bulk approve/reject shares `document_approval.py` with the single path so they cannot drift. |
| Duplicate detection | ✅ REAL | Content hash (exact) plus a business heuristic (invoice number + counterparty VAT + date + gross across *different* files) surfaced as a warning, never an auto-reject. |
| Payment status | ✅ REAL | `payment_engine.compute_payment_status` → UNPAID/PARTIALLY_PAID/PAID/OVERDUE. **Phase 19 blocked zero and negative amounts.** |

---

## 4. Banking

| Capability | Status | Evidence |
|---|---|---|
| Bank accounts | ✅ REAL | `BankAccount`, `UniqueConstraint(company_id, iban)`, IBAN validation |
| Imported transactions | ✅ REAL | CAMT.053, CAMT.054, MT940, CSV. Idempotent via `UniqueConstraint(bank_account_id, dedupe_hash)` — verified in Scenario C (re-import gives `transaction_count=0, duplicate_count=1`). Source rows immutable. |
| Transaction matching | ✅ REAL | Deterministic named signals, transparent numeric scoring banded HIGH/MEDIUM/LOW/NONE, bounded combinatorial 1:many search, explicit overpayment signal. |
| Reconciliation | ✅ REAL | Approve creates a real `Payment`; reverse **voids** it (`voided`, `voided_by_user_id`, `voided_at`, `void_reason`) — verified in Scenario C that the row count is unchanged after reversal and exactly one payment is flagged voided. |
| Payment registration | ✅ REAL | Shared with §2. **Phase 19 added cash-based VAT period assignment to `approve_match`**, so a bank-matched payment now behaves identically to a manually recorded one. |
| **Open Banking / PSD2** | 🔒 BLOCKED / ⚠️ STUB | `StubOpenBankingProvider` is the only implementation; `get_open_banking_provider()` always returns it and it performs **no network I/O**. Requires a DNB/EBA-authorised TPP registration and bank sandbox access. Correctly documented; no fake. |
| Bank statement imports | ✅ REAL | Four formats behind an adapter-shaped boundary. **Phase 17 hardened the XML path** (DTD rejection) — audit 7.19. |

---

## 5. Dutch tax — the five levels, kept separate

The brief requires distinguishing calculation from preparation from export from submission from acceptance. This is the most important table in the document.

| Return | 1. Calculated | 2. Prepared | 3. Exported | 4. Submitted | 5. Accepted |
|---|---|---|---|---|---|
| **BTW/VAT return** | ✅ REAL | ✅ REAL | ✅ REAL (PDF/XLSX/CSV, 4 locales) | ⬜ **NO** | ⬜ **NO** |
| **ICP (EU sales list)** | ⬜ NO | ⬜ NO | ⬜ NO | ⬜ NO | ⬜ NO |
| **Income tax (IB)** | 🟠 estimate only | ⬜ NO | ⬜ NO | ⬜ NO | ⬜ NO |
| **Corporate tax (VPB)** | 🟠 estimate only | ⬜ NO | ⬜ NO | ⬜ NO | ⬜ NO |
| **Loonheffingen (payroll tax)** | ✅ REAL | ✅ REAL | 🟡 PDF payslip/jaaropgave only | ⬜ **NO** | ⬜ NO |

**No return of any kind is submitted to or accepted by any authority.** There is no SBR/Digipoort connector, no XBRL generation, and no PKIoverheid certificate. `/tax-centre/overview` returns `sbr_digipoort_integration_status: "NOT_CONFIGURED"`, with `NOT_TRACKED` for ICP and OSS and `NOT_FILED` for income and corporate tax — accurate, and the code comment states this is "the honest status for every company, not a placeholder".

Level 4 and 5 are **BLOCKED**, not merely absent: they need a PKIoverheid certificate, Logius registration and their conformance suite. `docs/government-integrations.md` also records that the old Digipoort retired **2026-04-01** — already past — so any future work must target its replacement.

### VAT boxes, classifications and periods

| Item | Status | Note |
|---|---|---|
| VAT boxes 1a/1b/1c/1d/1e/2a/3a/3b/3c/4a/4b/5a/5b | 🟡 PARTIAL | The mapping table exists and is tested. **Boxes 2a, 3a, 4a and 1d are unreachable by the automatic pipeline** — `classify_default_treatment` never returns `domestic_reverse_charge_received`, `export_non_eu`, `import_non_eu` or `private_use`. That refusal to guess is correct; the consequence is not surfaced, and there is no UI to set `vat_treatment` per line. Audit 7.11 — **open**. Scenario D verifies 1a, 1b, 5a, 5b and `net_payable` exactly. |
| Input-VAT eligibility | ✅ REAL | Only ever auto-assigns `ELIGIBLE` or `REQUIRES_REVIEW`, never `INELIGIBLE`/`PARTIALLY_ELIGIBLE`. Pro-rata defaults to 0% deducted rather than guessing. Verified in Scenario B that a `REQUIRES_REVIEW` line contributes **nothing** to box 5b. **But the endpoint that resolves a review (`PATCH /transactions/{id}/line-items/{line_item_id}`) has no frontend caller** — audit 4.6, **open**. |
| VAT periods | ✅ REAL | Deterministic monthly/quarterly/annual generation with the Dutch filing-deadline rule. |
| Cash-based VAT periods | ✅ REAL **as of Phase 19** | Previously every cash-based transaction kept `vat_period = NULL` forever and the return computed to zero. Now assigned from the payment date through both payment paths, and verified end to end in `test_scenario_d_cash_based_company_return_follows_the_payment`. |
| Fiscal year calculations | ✅ REAL | |
| Tax rates and effective dates | 🟡 PARTIAL | `RULE_VERSIONS` is a real versioning mechanism — with **exactly one entry**, `"nl-2024"`. Never exercised. |
| Audit history of a return | ✅ REAL | `VatReturn` status transitions audit-logged; locking cascades to transactions. |
| Return validation | ✅ REAL | `GET /vat-returns/{id}/reconciliation` cross-checks ledger totals, VAT by rate, pending documents, duplicates, validation errors, unresolved FX and prior corrections. Scenario D asserts the box totals agree with the independently-built reconciliation view. |
| **Suppletie (correction return)** | ⬜ ABSENT | Corrections always land in the *current* period (`create_correction` uses `date.today()`). Dutch rules require a suppletie against the original period above €1,000. Audit 4.3 — **open**. |

---

## 6. Payroll and HR

**Is payroll real, partial or a prototype? — Real calculation, partial product.**

| Capability | Status | Evidence |
|---|---|---|
| Employees | ✅ REAL | `Employee`, BSN Fernet-encrypted at rest, returned masked only; `employee_self_service` returns **no** BSN at all. |
| Payroll records | ✅ REAL | `PayrollRun` + `Payslip`, DB-level idempotency (`uq_payroll_run_period`) with `IntegrityError → 409`. Payslips never edited in place — a correction voids and re-links. |
| Payroll tax (loonheffing) | ✅ REAL | Box 1 brackets, algemene heffingskorting with its phase-out curve, all four arbeidskorting brackets, the official *tabel bijzondere beloningen*. `test_special_remuneration_tax_matches_official_worked_example` pins `Decimal("1021.44")` against a cited Belastingdienst PDF; `test_payroll_validation.py:45` parametrises three official table rows within €1.00. |
| Employer premiums | ✅ REAL | AWf (flexible/permanent split), Aof, Whk, Zvw with the annual `max_premieloon` cap. |
| DGA support | ✅ REAL | `gebruikelijk_loon` norm, `Shareholder.is_dga`, a DGA position endpoint. Every consumer returns `requires_accountant_confirmation: True`. |
| WKR | 🟠 CALC ONLY | Free space is computed. There is no `WKR`-scoped expense register to feed it, so the calculation has nothing real to work on. |
| **Leave and absence** | ⬜ ABSENT | Not modelled. `navConfig.ts:100` marks it `unavailableKey`. |
| Employer costs | ✅ REAL | Total employer cost is part of the payroll calculation. |
| Payroll reporting | ✅ REAL | Payslip and jaaropgave PDFs, 4 locales, RTL-mirrored with a real shaping pipeline. |
| Loonheffingen declaration lifecycle | 🟡 PARTIAL | A real local state machine (`draft → validated → approved → ready_for_submission → submitted → accepted/rejected`) with six endpoints. **No transmission** — `record_submission` and `record_government_response` record what an operator did elsewhere. Correctly labelled. |
| Time registration | ✅ REAL | Timesheets with submit/approve/reject, plus entrepreneur-hours logging feeding a 1,225-hour urencriterium dashboard that states meeting the threshold is *necessary but not sufficient* and never auto-grants the deduction. |
| **Employee self-service onboarding** | 🟡 BROKEN UX | The router (9 endpoints) and `frontend/app/employee-portal/` are real and tested. But `POST /employees/{id}/invite-self-service` — the **only** way an `employee`-role account is ever created — has **no frontend caller**, and writes **no audit log**. Audit 4.6, 8.15 — **open**. |

**Tax-year staleness applies to this entire section.** `_RULE_SETS = {2025: RULES_2025}` and `CURRENT_TAX_YEAR = 2025`; six production call sites invoke `get_rule_set()` with no argument and nothing derives the year from the clock. A payroll run created today for a 2026 period computes 2025 brackets, 2025 premium rates, the 2025 `max_premieloon` (€75,864) and the 2025 DGA norm (€56,000). Audit 6.5 — **open, and the most serious compliance risk in the product.**

---

## 7. Business management

| Capability | Status | Evidence |
|---|---|---|
| **Fixed assets and depreciation** | ⬜ ABSENT | No asset register, no depreciation schedule. Fixed assets exist only as manually-entered `ManualBalanceSheetItem` rows — whose summation semantics are broken (audit 7.2, **open**). |
| Budgets | ✅ REAL | Draft → submitted → approved, with approval restricted so an owner cannot approve their own. Revisions are new immutable rows (`version`, `supersedes_budget_id`). Variance endpoint. |
| **Cost centres** | ⬜ ABSENT | No entity. |
| **Projects** | ⬜ ABSENT | No entity. |
| Time registration | ✅ REAL | See §6. |
| **Inventory** | ⬜ ABSENT | Manual balance only, so inventory turnover and the full cash-conversion cycle are reported as `missing_data` rather than assumed zero — correct behaviour, documented. |
| Reports and dashboards | ✅ REAL | P&L, balance sheet, cash flow, trial balance, GL, debtors/creditors, VAT overview, revenue/expense breakdowns, KPIs, working capital (7 routes), forecasts, scenarios, tax centre. Exported as PDF/XLSX/CSV in 4 locales. **13 of the 21 `financial-reports` API endpoints have no test** (audit 9.4). |
| KPI engine | ✅ REAL | Returns `{value, formula, source, period, explanation, missing_data}` and yields `value: null` with an explanation rather than a misleading 0% or infinite ratio. Genuinely good design. **But `app/kpis/page.tsx:32` labels the whole dashboard with `key.replace(/_/g," ")` from backend JSON keys — untranslated in all four locales** (audit 4.5). |
| Scenarios | ✅ REAL | Stores only assumptions, recomputed fresh on every read — nothing cached, nothing staleable. Verified never to write to `AccountingTransaction`. |

---

## 8. AI features

| Capability | Status | Evidence |
|---|---|---|
| Invoice extraction | ✅ REAL | Claude with forced tool use against a Pydantic-derived schema, retry with backoff, and a null-safe stub that routes everything to manual review when no key is set. |
| Transaction classification | ✅ REAL | Provider-shaped, `requires_accountant_review: True` on stub output. |
| Financial explanations | ✅ REAL | Narrates a deterministic fact bundle. |
| Accounting assistance | ✅ REAL | `POST /assistant/ask`, `/financial-question`. |
| Anomaly detection | ✅ REAL | **Deterministic, not AI.** Six evidence-carrying, idempotent rules; none ever applies a "fraud" label. |
| AI-generated reports | 🟡 PARTIAL | The assistant narrates; report *figures* are always computed deterministically. No AI-generated numbers reach a report. |
| **Can AI commit a financial transaction?** | **NO — structurally** | Nothing in `app/services/ai_*.py` imports a model or a session. The assistant receives a pre-computed JSON fact bundle and returns prose. This is an architectural control, not a prompt instruction, and it holds. |

**Residual AI risks (audit 7.15, open):** document text is truncated at 50,000 characters with **no flag** when truncation occurs, so a long invoice's totals block can be dropped while confidence stays high. Untrusted document text is concatenated into the prompt; forced tool use constrains output *shape* but not *values*, so an injected IBAN can reach the ledger. `SUPPLIER_BANK_DETAILS_CHANGED` mitigates this for a known counterparty but **cannot fire for a first-time payee** — there is no first-payee control.

---

## 9. Platform

| Capability | Status | Evidence |
|---|---|---|
| Multi-tenancy | 🟡 PARTIAL → **improved** | `tenant_id` on nearly every table. Phase 17 made `require_company_access` tenant-authoritative for all roles, closing 7 endpoints (2 of them cross-tenant writes). 22 mutation-verified regression tests. **The cross-tenant accountant-delegation feature was withdrawn** — it never worked, and real delegation needs a `CompanyAccess` grant model (audit 6.7b). |
| Roles and permissions | ✅ REAL | Six roles, five guard dependencies, `require_admin` on all user management, no privilege-escalation path to owner/admin, last-active-owner protection, no self-role-change. Verified. |
| **Per-company roles** | ⬜ ABSENT | `User.role` is one value for the whole account. An accountant with 40 clients has the same role in all of them. `intended_role` is recorded on an invitation but never applied. |
| Accountant access | 🟡 WITHDRAWN | Same-tenant grants work and are tested. Cross-tenant grants are now refused (Phase 17) rather than silently broken. |
| Multiple companies | ✅ REAL | Within a tenant. `CompanyProvider` exists but 38 of 55 pages re-fetch the list themselves. |
| API | ✅ REAL | 217 routes, 26 routers, all mounted, OpenAPI at `/docs`. No router-level dependencies — every guard is per-function. |
| **Webhooks** | ⚠️ STUB | Inbound billing webhook with real HMAC-SHA256 verification and replay protection. **No outbound webhooks.** |
| Imports and exports | ✅ REAL | Bank imports (4 formats), bulk document upload, PDF/XLSX/CSV exports in 4 locales. **CSV export is vulnerable to formula injection** via raw `original_filename` (audit 8.13, open). |
| **Data migration** | ⬜ ABSENT | No importer for an existing ledger. Opening balances are manual entries only. |
| Localization | ✅ REAL | 4 locales, **1,374 keys × 4 files with zero drift**, 55/55 routes translated, RTL CSS with logical properties, real Persian/Arabic PDF shaping. Residual gaps: 6 hardcoded `aria-label`s, 7 raw enum renderings, 16 backend notes. |
| Mobile responsiveness | 🟡 PARTIAL | Tables wrapped in `overflow-x-auto`; responsive e2e viewport tests exist for 4 routes. No route-level tests for the other 51. |
| **`is_platform_admin`** | ✅ REAL | Not settable through any API — verified across all 8 occurrences. `/billing/admin/overview` exposes counts only. |

---

## 10. Summary counts

| Status | Count |
|---|---|
| ✅ REAL | 41 |
| 🟡 PARTIAL | 15 |
| 🟠 CALC ONLY | 3 |
| ⬜ ABSENT | 14 |
| 🔒 BLOCKED | 2 |
| ⚠️ STUB | 2 |

**The absent items cluster in exactly two places:** the double-entry foundation (chart of accounts, RGS, journal, opening balances) and the sales/purchases master data plus workflows around it (customers, suppliers, quotations, recurring invoices, reminders, statements). Everything else is either real or honestly labelled.

Nothing in this matrix claims submission to or acceptance by a Dutch authority, because none exists.
