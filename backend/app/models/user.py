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

    # ---- Phase 14: SaaS platform administration ----
    # A privilege tier ABOVE tenant admin -- can see cross-tenant
    # subscription/usage/system-health data (app.api.v1.admin) but never a
    # customer's financial records. Deliberately has no self-service way
    # to grant itself: only settable via direct DB/seed by an operator, the
    # same "no API ever creates this" pattern as choosing not to expose a
    # self-signup-to-admin path.
    is_platform_admin: Mapped[bool] = mapped_column(default=False)

    # ---- Phase 16: internationalisation ----
    # Short code (nl/en/fa/ar), nullable -- null means "use this user's
    # tenant's default_locale" (app.models.tenant.Tenant.default_locale),
    # non-null means an explicit personal override that always wins over
    # the tenant default. This is how "a default language for new users"
    # and "override the organisation's default with a personal
    # preference" both work from a single nullable column instead of
    # needing a separate has_custom_locale flag.
    locale: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # ---- Phase 22: personal profile ----
    # full_name stays the display value every existing screen reads; the
    # profile endpoint keeps it in sync (display_name, else "first last").
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # Email change is two-step: the new address is held here until the
    # verification link (hash-only token, same pattern as password reset)
    # sent TO THAT ADDRESS is clicked. `email` itself never changes before.
    pending_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_change_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    email_change_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    companies: Mapped[list["Company"]] = relationship(
        secondary=user_companies, back_populates="users"
    )

    @property
    def tenant_default_locale(self) -> str:
        """Convenience passthrough so UserOut (Pydantic, from_attributes)
        can read `user.tenant_default_locale` directly without every
        caller needing to join/select Tenant separately."""
        return self.tenant.default_locale
