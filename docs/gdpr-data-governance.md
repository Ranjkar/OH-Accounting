# GDPR / data governance

## Statutory retention vs. the right to erasure

Dutch law requires business records (bookkeeping/administratie) to be retained for **7 years** (Belastingdienst, confirmed directly: *"Je moet de administratie... minimaal 7 jaar bewaren"*), and **10 years** for records touching immovable property. GDPR Article 17(3) explicitly exempts erasure where processing is necessary for compliance with a legal obligation — the fiscal retention duty **overrides** a data-subject erasure request for financial/payroll records containing personal data (e.g. BSN embedded in a payslip).

**Consequence for this system: deactivating or "deleting" an account never deletes or touches any linked Employee, Payslip, AccountingTransaction, or other financial record.** Those rows are retained for their statutory period regardless of what happens to the User account that created or is linked to them.

## What Phase 12 implements

- **Right of access / portability (Art. 15/20)**: `GET /auth/me/data-export` — returns exactly the caller's own profile, plus (if linked) their own Employee profile and timesheet entries. Never another user's or employee's data. Payslips are deliberately excluded from the bulk export (available individually via `/me/payslips`, and carry the same statutory retention noted above).
- **Account deactivation**: `POST /auth/me/deactivate` — blocks all future logins and revokes every existing session token immediately, but leaves every linked record untouched.
- **Auditability**: every security-relevant action (login lockout, logout, password reset, deactivation, data export) writes an `AuditLog` row — tenant-scoped, action, entity, timestamp.
- **Data minimisation**: BSN is encrypted at rest, never logged, never sent to the AI assistant, only ever displayed masked. Open Banking tokens are encrypted with a dedicated key, separate from BSN.

## What is not implemented

- Full erasure ("right to be forgotten") for data with **no** retention obligation (e.g. a user account with no linked financial records) — not built this phase; would be a straightforward hard-delete of the `User` row once confirmed no Employee/financial link exists, but is not wired up yet.
- A data processing register / Article 30 records — out of scope for this phase; this document is the closest equivalent.
- Automated retention-period enforcement (e.g. flagging records that have passed 7/10 years) — not implemented; retention is currently a documented policy, not an enforced one.
