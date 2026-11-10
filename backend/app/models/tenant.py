from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # ---- Phase 16: internationalisation ----
    # Short code (nl/en/fa/ar) assigned to every new user in this tenant
    # who hasn't set a personal preference yet (User.locale is nullable;
    # null means "follow the tenant default"). Backward-compatible default
    # "nl" matches every pre-Phase-16 row via the migration's server_default.
    default_locale: Mapped[str] = mapped_column(String(5), default="nl", server_default="nl")

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    companies: Mapped[list["Company"]] = relationship(back_populates="tenant")
