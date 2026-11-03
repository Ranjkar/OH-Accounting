"""phase_12_auth_security_password_reset

Revision ID: 8642d7593906
Revises: 3853605281ec
Create Date: 2026-11-03 16:25:47.186338

Autogenerate also proposed dropping all 54 company_id/tenant_id indexes
added in 3853605281ec (Phase 10 performance fix) -- expected and
documented at the time (those indexes were deliberately not mirrored as
index=True on the SQLAlchemy columns). Stripped out here; only the real
changes (password_reset_tokens table, new users columns) remain.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8642d7593906'
down_revision: Union[str, None] = '3853605281ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('password_reset_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_password_reset_tokens_token_hash'), 'password_reset_tokens', ['token_hash'], unique=True)

    # NOT NULL columns on a non-empty table: server_default to backfill
    # existing rows, then drop the default so future inserts must supply
    # a value via the ORM default instead of relying on the DB default.
    op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('users', 'token_version', server_default=None)
    op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('users', 'failed_login_attempts', server_default=None)
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column('users', 'is_active', server_default=None)


def downgrade() -> None:
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
    op.drop_column('users', 'token_version')
    op.drop_index(op.f('ix_password_reset_tokens_token_hash'), table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
