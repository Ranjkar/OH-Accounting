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
