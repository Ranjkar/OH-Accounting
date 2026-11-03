"""phase_14_company_invitations

Revision ID: c0f57267146a
Revises: d5d06a7c4472
Create Date: 2026-11-03 21:51:01.067532

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c0f57267146a'
down_revision: Union[str, None] = 'd5d06a7c4472'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('company_invitations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('invited_email', sa.String(length=255), nullable=False),
    sa.Column('intended_role', postgresql.ENUM('admin', 'accountant', 'viewer', 'customer', 'employee', name='user_role', create_type=False), nullable=False),
    sa.Column('invited_by_user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('pending', 'accepted', 'revoked', 'expired', name='company_invitation_status'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_by_user_id', sa.Integer(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['accepted_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['invited_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_company_invitations_invited_email'), 'company_invitations', ['invited_email'], unique=False)
    op.create_index(op.f('ix_company_invitations_token_hash'), 'company_invitations', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_company_invitations_token_hash'), table_name='company_invitations')
    op.drop_index(op.f('ix_company_invitations_invited_email'), table_name='company_invitations')
    op.drop_table('company_invitations')
