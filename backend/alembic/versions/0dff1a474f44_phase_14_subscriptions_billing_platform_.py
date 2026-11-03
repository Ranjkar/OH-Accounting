"""phase_14_subscriptions_billing_platform_admin

Revision ID: 0dff1a474f44
Revises: c0f57267146a
Create Date: 2026-11-03 22:04:35.860930

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0dff1a474f44'
down_revision: Union[str, None] = 'c0f57267146a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

plans_table = sa.table(
    "plans",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("monthly_price_eur", sa.Numeric),
    sa.column("company_limit", sa.Integer),
    sa.column("user_limit", sa.Integer),
    sa.column("is_active", sa.Boolean),
)

SEED_PLANS = [
    {"code": "free", "name": "Free / Trial", "monthly_price_eur": None, "company_limit": 5, "user_limit": 10, "is_active": True},
    {"code": "starter", "name": "Starter", "monthly_price_eur": None, "company_limit": 10, "user_limit": 20, "is_active": True},
    {"code": "professional", "name": "Professional", "monthly_price_eur": None, "company_limit": 25, "user_limit": 50, "is_active": True},
    {"code": "business", "name": "Business", "monthly_price_eur": None, "company_limit": 50, "user_limit": 100, "is_active": True},
    {"code": "accountant", "name": "Accountant", "monthly_price_eur": None, "company_limit": 200, "user_limit": 500, "is_active": True},
]


def upgrade() -> None:
    op.create_table('plans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('monthly_price_eur', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('company_limit', sa.Integer(), nullable=False),
    sa.Column('user_limit', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_plans_code'), 'plans', ['code'], unique=True)
    op.bulk_insert(plans_table, SEED_PLANS)

    op.create_table('billing_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('provider_event_id', sa.String(length=255), nullable=False),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('verified', sa.Boolean(), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_billing_events_provider_event_id'), 'billing_events', ['provider_event_id'], unique=True)

    op.create_table('subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('trialing', 'active', 'past_due', 'canceled', name='subscription_status'), nullable=False),
    sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('provider_customer_id', sa.String(length=255), nullable=True),
    sa.Column('provider_subscription_id', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id')
    )

    op.add_column('users', sa.Column('is_platform_admin', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column('users', 'is_platform_admin', server_default=None)


def downgrade() -> None:
    op.drop_column('users', 'is_platform_admin')
    op.drop_table('subscriptions')
    op.drop_index(op.f('ix_billing_events_provider_event_id'), table_name='billing_events')
    op.drop_table('billing_events')
    op.drop_index(op.f('ix_plans_code'), table_name='plans')
    op.drop_table('plans')
