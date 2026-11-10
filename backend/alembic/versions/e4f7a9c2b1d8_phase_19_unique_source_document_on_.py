"""phase_19_unique_source_document_on_ledger_posting

Revision ID: e4f7a9c2b1d8
Revises: d90e97d4bc35
Create Date: 2026-11-05

Phase 19 (audit finding 6.6): one document may post to the ledger at most once.

`ledger_service.post_document_to_ledger` already guards this with a
SELECT-then-INSERT, but that is only safe single-threaded. Two concurrent
POST /documents/{id}/approve requests -- a double-click, a browser retry, a
load-balancer replay -- both observe no existing row and both insert, so the
document is double-posted: revenue and input VAT counted twice, flowing
straight into the VAT return, the P&L, the balance sheet and every export.

Payroll received exactly this guard in Phase 12 (`uq_payroll_run_period`);
the document -> ledger path did not.

SAFETY. This migration REFUSES to run if any document has already been posted
twice. It does not pick a winner, and it never deletes or modifies a financial
record -- silently discarding a duplicate that has already flowed into a filed
VAT return would be worse than failing. On refusal it reports the offending
document ids and their transaction ids so an operator can resolve each pair
through the existing voiding-correction path and re-run.

Manual entries and corrections are unaffected: they set
`source_document_id = NULL`, and Postgres treats NULLs as distinct in a unique
constraint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f7a9c2b1d8'
down_revision: Union[str, None] = 'd90e97d4bc35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "uq_accounting_transaction_source_document"


def upgrade() -> None:
    conn = op.get_bind()
    duplicates = conn.execute(
        sa.text(
            "SELECT source_document_id, COUNT(*) AS postings, array_agg(id ORDER BY id) AS transaction_ids "
            "FROM accounting_transactions "
            "WHERE source_document_id IS NOT NULL "
            "GROUP BY source_document_id "
            "HAVING COUNT(*) > 1 "
            "ORDER BY source_document_id"
        )
    ).fetchall()

    if duplicates:
        detail = "; ".join(
            f"document_id={row[0]} posted {row[1]}x as accounting_transaction ids {list(row[2])}"
            for row in duplicates
        )
        raise RuntimeError(
            f"Cannot add {CONSTRAINT_NAME}: existing duplicate ledger postings were found -- "
            f"{detail}. Resolve each pair with a voiding correction (see "
            "ledger_service.create_correction; never a DELETE, which would destroy the audit "
            "trail), then re-run `alembic upgrade head`. This migration does not modify or "
            "delete any financial record."
        )

    op.create_unique_constraint(CONSTRAINT_NAME, "accounting_transactions", ["source_document_id"])


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "accounting_transactions", type_="unique")
