"""phase_12_open_banking_fields

Revision ID: 95609c015f0c
Revises: 3432aad647e8
Create Date: 2026-11-03 17:05:00.000000

Autogenerate again proposed dropping the Phase 10 performance indexes
(same known cause) -- stripped. It also did NOT pick up the new
BankConsentStatus (PENDING, EXPIRED) and BankSourceFormat (OPEN_BANKING)
enum values -- Alembic/SQLAlchemy don't diff Postgres enum values
automatically (same situation as the earlier 'employee' UserRole value,
migration 5e014e66b859) -- added manually below.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95609c015f0c'
down_revision: Union[str, None] = '3432aad647e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE bank_consent_status ADD VALUE IF NOT EXISTS 'PENDING'")
    op.execute("ALTER TYPE bank_consent_status ADD VALUE IF NOT EXISTS 'EXPIRED'")
    op.execute("ALTER TYPE bank_source_format ADD VALUE IF NOT EXISTS 'OPEN_BANKING'")

    op.add_column('bank_accounts', sa.Column('provider_name', sa.String(length=50), nullable=True))
    op.add_column('bank_accounts', sa.Column('provider_account_id', sa.String(length=255), nullable=True))
    op.add_column('bank_accounts', sa.Column('encrypted_access_token', sa.LargeBinary(), nullable=True))
    op.add_column('bank_accounts', sa.Column('encrypted_refresh_token', sa.LargeBinary(), nullable=True))
    op.add_column('bank_accounts', sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bank_accounts', sa.Column('last_sync_error', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('bank_accounts', 'last_sync_error')
    op.drop_column('bank_accounts', 'last_synced_at')
    op.drop_column('bank_accounts', 'encrypted_refresh_token')
    op.drop_column('bank_accounts', 'encrypted_access_token')
    op.drop_column('bank_accounts', 'provider_account_id')
    op.drop_column('bank_accounts', 'provider_name')
    # Postgres has no DROP VALUE for enums -- same accepted no-op as
    # migration 5e014e66b859.
