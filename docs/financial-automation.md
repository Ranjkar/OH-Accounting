# Financial automation & idempotency

## Existing automation (Phase 6, preserved and reused, not duplicated)

Bank categorization rules, category suggestions, recurring-pattern detection, anomaly detection, automation-centre summary, cash-flow forecast — all in `app/accounting/*` and `app/api/v1/automation.py`, unchanged this phase. AI may *suggest* classifications and matches; it never posts a financial transaction itself — every posting path (`app/accounting/ledger_service.py`) is deterministic Decimal arithmetic with no AI involvement.

## Idempotency audit (Phase 12)

| Operation | Before this phase | After |
|---|---|---|
| Bank transaction import | Already idempotent: `dedupe_hash` application check **and** a DB-level `uq_bank_transaction_dedupe` unique constraint as the real backstop against concurrent-request races. | Unchanged — verified, not duplicated. |
| Loonheffingen declaration creation | Already idempotent: `payroll_run_id` is DB-unique on `LoonheffingenDeclaration`. | Unchanged — verified. |
| **Payroll run creation** | **Not idempotent** — a double-click/retry created a second payroll run (and therefore double payroll) for the same company+period with no guard at all. | **Fixed**: new `uq_payroll_run_period` unique constraint (company_id, period_type, period_year, period_number); `create_payroll_run` catches the resulting `IntegrityError` and raises `PayrollError` → HTTP 409. Tested (`test_create_payroll_run_is_idempotent_against_duplicate_period`). |
| Open Banking sync | New this phase. | Reuses the same `insert_rows_with_dedup` path as file import — inherits the same DB-level duplicate protection, not a parallel implementation. |
| Government submission (loonheffingen) | New this phase. | `record_submission`/`record_government_response` are one-way state transitions guarded by the declaration's current status (e.g. can't submit twice — the state machine itself prevents it). |

## What was not changed

Document upload dedup (SHA-256 content hash, Phase 2/6) and VAT return locking (Phase 4) were reviewed and found already correct — not touched.

## Approval boundaries (Phase 13)

Audited every path listed in the Phase 13 brief's "must not silently"
list against the actual code, not assumption:

| Must never happen silently | Where this is actually enforced |
|---|---|
| Post a material accounting entry from an AI suggestion | Category suggestions (`ai_categorization_provider.py`) and extracted invoice fields (`document_processing.py`) both require an explicit human action (`/transactions/{id}/categorize`, `/documents/{id}/approve`) before anything reaches the ledger. |
| Change a historical transaction | `PATCH /transactions/{id}` only accepts edits while `approval_status == draft`; any transaction past draft is rejected with 409 ("use the corrections endpoint instead") and every accepted edit is written to `AuditLog` with before/after values. Corrections to a non-draft transaction go through `reconciliation.py`'s additive `corrections` records instead of an in-place edit. |
| Submit a tax declaration | `record_submission` only transitions a declaration's own status; it is never called except from an explicit API request, and the loonheffingen lifecycle (`docs/government-integrations.md`) requires Draft→Validation→Review→Approval before Submitted is even reachable. |
| Initiate a bank payment | Not implemented at all (see `docs/open-banking.md`) -- there is no code path that could do this silently because there is no code path that does it. |
| Approve payroll | `payroll_runs.approve` (and the loonheffingen declaration's own `approve` step) are both explicit, human-triggered endpoints with their own `approved_by_user_id`. |
| Delete a legally required financial record | GDPR account deletion explicitly stops short of this (`docs/gdpr-data-governance.md`); no endpoint hard-deletes an `AccountingTransaction`, `Payslip`, or `VatReturn`. |

New this phase: two additional deterministic anomaly rules
(`DUPLICATE_INVOICE`, `UNUSUAL_CASH_WITHDRAWAL`) -- see
`docs/financial-anomaly-detection.md` -- found no new idempotency gap in
the process.
