"""phase_15_access_governance_audit

Revision ID: 79097fec25d3
Revises: 0dff1a474f44
Create Date: 2026-11-04 10:55:05.957021

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '79097fec25d3'
down_revision: Union[str, None] = '0dff1a474f44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New UserRole value, purely additive -- see app.models.enums.UserRole
    # and app.core.deps.ADMIN_ROLES. Must run in its own autocommit block:
    # Postgres does not allow a newly added enum value to be used by a
    # statement in the same transaction that added it, and Alembic runs
    # each migration in one transaction by default.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'owner' BEFORE 'admin'")

    op.create_table(
        'user_invitations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('invited_email', sa.String(length=255), nullable=False),
        sa.Column('intended_role', postgresql.ENUM('owner', 'admin', 'accountant', 'viewer', 'customer', 'employee', name='user_role', create_type=False), nullable=False),
        sa.Column('invited_by_user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'accepted', 'revoked', 'expired', name='company_invitation_status', create_type=False), nullable=False),
        sa.Column('initial_company_ids', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_user_id', sa.Integer(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['accepted_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['invited_by_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_invitations_tenant_id'), 'user_invitations', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_user_invitations_invited_email'), 'user_invitations', ['invited_email'], unique=False)
    op.create_index(op.f('ix_user_invitations_token_hash'), 'user_invitations', ['token_hash'], unique=True)

    op.add_column('audit_logs', sa.Column('request_id', sa.String(length=64), nullable=True))
    op.add_column('audit_logs', sa.Column('event_metadata', sa.JSON(), nullable=True))
    op.create_index('ix_audit_logs_tenant_created', 'audit_logs', ['tenant_id', 'created_at'], unique=False)
    op.create_index('ix_audit_logs_tenant_user', 'audit_logs', ['tenant_id', 'user_id'], unique=False)
    op.create_index('ix_audit_logs_tenant_action', 'audit_logs', ['tenant_id', 'action'], unique=False)
    op.create_index('ix_audit_logs_tenant_entity', 'audit_logs', ['tenant_id', 'entity_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_audit_logs_tenant_entity', table_name='audit_logs')
    op.drop_index('ix_audit_logs_tenant_action', table_name='audit_logs')
    op.drop_index('ix_audit_logs_tenant_user', table_name='audit_logs')
    op.drop_index('ix_audit_logs_tenant_created', table_name='audit_logs')
    op.drop_column('audit_logs', 'event_metadata')
    op.drop_column('audit_logs', 'request_id')

    op.drop_index(op.f('ix_user_invitations_token_hash'), table_name='user_invitations')
    op.drop_index(op.f('ix_user_invitations_invited_email'), table_name='user_invitations')
    op.drop_index(op.f('ix_user_invitations_tenant_id'), table_name='user_invitations')
    op.drop_table('user_invitations')

    # NOTE: Postgres cannot drop a single value from an enum type (no
    # `ALTER TYPE ... DROP VALUE`). Removing 'owner' would require
    # recreating the type and every column/table that depends on it
    # (users.role, company_invitations.intended_role,
    # user_invitations.intended_role) -- a destructive, high-risk
    # operation deliberately not automated here. If 'owner' must ever be
    # removed, it requires a hand-written migration after confirming no
    # row anywhere uses it.
