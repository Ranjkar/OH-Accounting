"""phase_10_add_employee_user_role

Revision ID: 5e014e66b859
Revises: ecda52e200ae
Create Date: 2026-11-03 11:28:46.242151

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e014e66b859'
down_revision: Union[str, None] = 'ecda52e200ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'employee'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums -- removing 'employee' would require
    # rebuilding the type and is not attempted here. Safe no-op: an unused
    # enum value is harmless.
    pass
