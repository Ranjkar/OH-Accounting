"""phase_16_internationalisation_locale

Revision ID: d90e97d4bc35
Revises: 79097fec25d3
Create Date: 2026-11-04 16:55:15.335091

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd90e97d4bc35'
down_revision: Union[str, None] = '79097fec25d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default="nl" so every existing tenant row is backfilled in
    # the same statement that adds the column -- no separate UPDATE pass,
    # no row is ever left NULL (tenants.default_locale is NOT NULL).
    op.add_column('tenants', sa.Column('default_locale', sa.String(length=5), nullable=False, server_default='nl'))
    # Nullable: NULL means "follow the user's tenant default_locale" --
    # every existing user keeps this behaviour unchanged (they were all
    # implicitly "Dutch" before Phase 16 since the UI had no other
    # language; NULL now makes that explicit without forcing a value).
    op.add_column('users', sa.Column('locale', sa.String(length=5), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'locale')
    op.drop_column('tenants', 'default_locale')
