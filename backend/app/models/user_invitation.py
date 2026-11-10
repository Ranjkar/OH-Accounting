from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import CompanyInvitationStatus, UserRole


class UserInvitation(Base):
    """Phase 15: invites a brand-new person into the tenant itself (creates
    their User row on acceptance), distinct from
    app.models.company_invitation.CompanyInvitation, which only grants an
    *existing* account access to one more company. Same one-row-per-
    request, hash-only-token pattern as PasswordResetToken/
    CompanyInvitation -- the raw token is never persisted, only its
    SHA-256 hash, and is returned once to the inviting caller (no email
    provider is configured in this system, same documented limitation as
    every other invitation flow -- see docs/security.md).

    Reuses CompanyInvitationStatus (PENDING/ACCEPTED/REVOKED/EXPIRED)
    rather than defining a near-identical enum."""

    __tablename__ = "user_invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    invited_email: Mapped[str] = mapped_column(String(255), index=True)
    intended_role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"))
    invited_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[CompanyInvitationStatus] = mapped_column(
        Enum(CompanyInvitationStatus, name="company_invitation_status"), default=CompanyInvitationStatus.pending
    )
    # Optional: company IDs to grant the new account access to immediately
    # on acceptance, so an owner/admin can invite someone straight into
    # the right company(ies) in one step instead of a second round-trip.
    initial_company_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship()
