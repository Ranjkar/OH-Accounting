"""phase_12_payroll_run_idempotency

Revision ID: 3432aad647e8
Revises: 8642d7593906
Create Date: 2026-11-03 16:41:50.243749

Autogenerate again proposed dropping the 54 Phase 10 performance
indexes (same known, documented cause as 8642d7593906) -- stripped out.
Only the real change (a unique constraint preventing duplicate payroll
runs for the same period) remains. Checked for existing violating rows
before writing this migration: none found.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3432aad647e8'
down_revision: Union[str, None] = '8642d7593906'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint('uq_payroll_run_period', 'payroll_runs', ['company_id', 'period_type', 'period_year', 'period_number'])


def downgrade() -> None:
    op.drop_constraint('uq_payroll_run_period', 'payroll_runs', type_='unique')
