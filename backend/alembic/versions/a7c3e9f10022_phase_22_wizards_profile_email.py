"""phase_22_wizards_profile_email

Revision ID: a7c3e9f10022
Revises: e4f7a9c2b1d8
Create Date: 2026-11-11

Phase 22: company setup wizard, personal profile + verified email change,
email delivery log, Open Banking account selection. Strictly additive:
new nullable/defaulted columns and two new tables. No existing column is
altered, renamed or dropped, no data is rewritten. `downgrade` removes
only what this revision added.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9f10022"
down_revision: Union[str, None] = "e4f7a9c2b1d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Companies: wizard answers.
    op.add_column("companies", sa.Column("rsin", sa.String(length=9), nullable=True))
    op.add_column("companies", sa.Column("vat_registered", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("companies", sa.Column("kor_participant", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("companies", sa.Column("business_activity", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("phone", sa.String(length=50), nullable=True))

    op.create_table(
        "company_setup_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Users: profile + pending email change.
    for name, length in (
        ("first_name", 100), ("last_name", 100), ("display_name", 255), ("phone", 50),
        ("address_line", 255), ("postal_code", 20), ("city", 100), ("country", 2), ("pending_email", 255),
    ):
        op.add_column("users", sa.Column(name, sa.String(length=length), nullable=True))
    op.add_column("users", sa.Column("email_change_token_hash", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_users_email_change_token_hash", "users", ["email_change_token_hash"])
    op.add_column("users", sa.Column("email_change_expires_at", sa.DateTime(timezone=True), nullable=True))

    # Bank accounts: candidates awaiting selection after a multi-account consent.
    op.add_column("bank_accounts", sa.Column("pending_provider_accounts", sa.JSON(), nullable=True))

    # Email delivery log.
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("to_email", sa.String(length=255), nullable=False, index=True),
        sa.Column("template", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("locale", sa.String(length=5), nullable=False, server_default="nl"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued", index=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provider_name", sa.String(length=30), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("email_outbox")
    op.drop_column("bank_accounts", "pending_provider_accounts")
    op.drop_column("users", "email_change_expires_at")
    op.drop_constraint("uq_users_email_change_token_hash", "users", type_="unique")
    op.drop_column("users", "email_change_token_hash")
    for name in ("pending_email", "country", "city", "postal_code", "address_line", "phone", "display_name", "last_name", "first_name"):
        op.drop_column("users", name)
    op.drop_table("company_setup_drafts")
    for name in ("phone", "email", "business_activity", "kor_participant", "vat_registered", "rsin"):
        op.drop_column("companies", name)
