from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, LargeBinary, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import UserRole

user_companies = Table(
    "user_companies",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("company_id", ForeignKey("companies.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # ---- Phase 12: session revocation + brute-force protection ----
    # Bumped on logout/password change; embedded in every issued JWT as the
    # "ver" claim and checked on every request (app.core.deps) -- the
    # standard way to make a stateless JWT revocable without a server-side
    # session store or Redis. Any token issued before the bump is rejected.
    token_version: Mapped[int] = mapped_column(default=0)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # GDPR account deactivation: blocks login, never deletes or touches any
    # linked financial/employee/payroll record (those have their own
    # statutory retention -- see docs/gdpr-data-governance.md).
    is_active: Mapped[bool] = mapped_column(default=True)

    # ---- Phase 13: optional per-user TOTP MFA ----
    # mfa_secret_encrypted is only set once enrollment is confirmed with a
    # valid code (see app.api.v1.auth.mfa_enable); mfa_enabled gates whether
    # login requires a code at all. No backup/recovery codes in this build --
    # a lost device requires an operator to clear mfa_enabled directly, a
    # documented limitation (see docs/security.md).
    mfa_enabled: Mapped[bool] = mapped_column(default=False)
    mfa_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    companies: Mapped[list["Company"]] = relationship(
        secondary=user_companies, back_populates="users"
    )
