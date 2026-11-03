"""phase_13_mfa_fields

Revision ID: d5d06a7c4472
Revises: 95609c015f0c
Create Date: 2026-11-03 21:07:28.746029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5d06a7c4472'
down_revision: Union[str, None] = '95609c015f0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('mfa_secret_encrypted', sa.LargeBinary(), nullable=True))
    op.alter_column('users', 'mfa_enabled', server_default=None)


def downgrade() -> None:
    op.drop_column('users', 'mfa_secret_encrypted')
    op.drop_column('users', 'mfa_enabled')
