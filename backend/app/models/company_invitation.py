from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import CompanyInvitationStatus, UserRole


class CompanyInvitation(Base):
    """One row per invitation to access a company (e.g. a business owner
    authorising their accountant). Never overwritten or reused -- same
    one-row-per-request, hash-only-token pattern as
    app.models.password_reset.PasswordResetToken. Accepting an invitation
    only adds the accepting user to the company's `user_companies` link;
    it never changes that user's own UserRole -- see docs/security.md for
    why a per-company role would be a larger schema change than this
    phase's scope."""

    __tablename__ = "company_invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    invited_email: Mapped[str] = mapped_column(String(255), index=True)
    intended_role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"))
    invited_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[CompanyInvitationStatus] = mapped_column(
        Enum(CompanyInvitationStatus, name="company_invitation_status"), default=CompanyInvitationStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship()
