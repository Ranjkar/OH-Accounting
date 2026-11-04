from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AuditLog(Base):
    """Append-only by convention: no API in this codebase ever issues an
    UPDATE or DELETE against this table (see app.api.v1.audit_log, which
    is read-only). Before/after snapshots must never contain a raw
    secret -- see app.core.audit_redaction.redact for the shared
    redaction helper every new call site should use when logging a
    dict that might contain one."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[int] = mapped_column(Integer)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Phase 15 additions, both nullable so every pre-existing call site
    # (30+ across the codebase) keeps working unmodified.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        # Covers the Audit Log page's default query (tenant-scoped, newest
        # first, optional date range) without a sequential scan.
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_logs_tenant_user", "tenant_id", "user_id"),
        Index("ix_audit_logs_tenant_action", "tenant_id", "action"),
        Index("ix_audit_logs_tenant_entity", "tenant_id", "entity_type"),
    )
