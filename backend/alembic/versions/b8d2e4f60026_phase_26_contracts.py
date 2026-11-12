"""phase_26_contracts

Revision ID: b8d2e4f60026
Revises: a7c3e9f10022
Create Date: 2026-11-11

Phase 26: annual accounting-services agreements, electronic signatures,
renewal scheduling. Strictly additive -- nine new tables, four new enum
types, no existing table touched. `downgrade` removes only what this
revision added.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d2e4f60026"
down_revision: Union[str, None] = "a7c3e9f10022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Labels are the Python enum member NAMES (SQLAlchemy's Enum default), matching
# every earlier migration in this repo (e.g. company_invitation_status).
contract_status = sa.Enum(
    "draft", "pending_approval", "ready_to_send", "sent", "viewed", "signed", "active", "renewal_due", "expired", "cancelled", "terminated",
    name="contract_status",
)
template_version_status = sa.Enum("draft", "approved", "retired", name="contract_template_version_status")
version_kind = sa.Enum("approved", "signed", name="contract_version_kind")
invitation_status = sa.Enum("pending", "used", "revoked", "expired", name="signing_invitation_status")


def upgrade() -> None:
    op.create_table(
        "contract_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "contract_template_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("contract_templates.id"), nullable=False, index=True),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", template_version_status, nullable=False, server_default="draft"),
        sa.Column("content", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("default_services", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("default_monthly_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("default_payment_terms_days", sa.Integer(), nullable=True),
        sa.Column("default_notice_period_days", sa.Integer(), nullable=True),
        sa.Column("default_term_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("template_id", "version_no", name="uq_contract_template_version_no"),
    )
    op.create_table(
        "contract_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, unique=True),
        sa.Column("reminder_days", sa.JSON(), nullable=False, server_default="[60, 30, 14]"),
        sa.Column("signing_link_expire_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("signing_reminder_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("auto_create_on_company_create", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("default_language", sa.String(length=5), nullable=False, server_default="nl"),
        sa.Column("notification_email", sa.String(length=255), nullable=True),
        sa.Column("reply_to_email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("reference", sa.String(length=40), nullable=False, unique=True),
        sa.Column("status", contract_status, nullable=False, server_default="draft"),
        sa.Column("language", sa.String(length=5), nullable=False, server_default="nl"),
        sa.Column("template_version_id", sa.Integer(), sa.ForeignKey("contract_template_versions.id"), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("services", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("monthly_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("fee_description", sa.String(length=500), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("payment_terms_days", sa.Integer(), nullable=True),
        sa.Column("notice_period_days", sa.Integer(), nullable=True),
        sa.Column("custom_clauses", sa.JSON(), nullable=True),
        sa.Column("signer_name", sa.String(length=255), nullable=True),
        sa.Column("signer_email", sa.String(length=255), nullable=True),
        sa.Column("signer_title", sa.String(length=255), nullable=True),
        sa.Column("renews_contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=True, unique=True),
        sa.Column("renewal_disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("renewal_disabled_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_source", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_effective_date", sa.Date(), nullable=True),
        sa.Column("closure_reason", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_contracts_tenant_status", "contracts", ["tenant_id", "status"])
    op.create_index("ix_contracts_tenant_end_date", "contracts", ["tenant_id", "end_date"])
    op.create_table(
        "contract_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False, index=True),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("kind", version_kind, nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("pdf_storage_path", sa.String(length=500), nullable=False),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=False, index=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("contract_id", "version_no", name="uq_contract_version_no"),
    )
    op.create_table(
        "contract_signing_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False, index=True),
        sa.Column("contract_version_id", sa.Integer(), sa.ForeignKey("contract_versions.id"), nullable=False),
        sa.Column("signer_name", sa.String(length=255), nullable=False),
        sa.Column("signer_email", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column("status", invitation_status, nullable=False, server_default="pending"),
        sa.Column("is_renewal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("email_outbox_id", sa.Integer(), sa.ForeignKey("email_outbox.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "contract_signatures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False, unique=True),
        sa.Column("invitation_id", sa.Integer(), sa.ForeignKey("contract_signing_invitations.id"), nullable=False),
        sa.Column("contract_version_id", sa.Integer(), sa.ForeignKey("contract_versions.id"), nullable=False),
        sa.Column("signed_version_id", sa.Integer(), sa.ForeignKey("contract_versions.id"), nullable=True),
        sa.Column("signer_name_typed", sa.String(length=255), nullable=False),
        sa.Column("signer_email", sa.String(length=255), nullable=False),
        sa.Column("consent_text", sa.Text(), nullable=False),
        sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signing_method", sa.String(length=50), nullable=False),
        sa.Column("provider_name", sa.String(length=50), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("document_sha256", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
    )
    op.create_table(
        "contract_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False, index=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("actor_type", sa.String(length=10), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "contract_reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("email_outbox_id", sa.Integer(), sa.ForeignKey("email_outbox.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("contract_id", "kind", name="uq_contract_reminder_kind"),
    )


def downgrade() -> None:
    for table in ("contract_reminders", "contract_events", "contract_signatures", "contract_signing_invitations", "contract_versions"):
        op.drop_table(table)
    op.drop_index("ix_contracts_tenant_end_date", table_name="contracts")
    op.drop_index("ix_contracts_tenant_status", table_name="contracts")
    op.drop_table("contracts")
    op.drop_table("contract_settings")
    op.drop_table("contract_template_versions")
    op.drop_table("contract_templates")
    bind = op.get_bind()
    for enum in (invitation_status, version_kind, template_version_status, contract_status):
        enum.drop(bind, checkfirst=True)
