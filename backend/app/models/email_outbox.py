from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EmailOutbox(Base):
    """Phase 22: delivery log for every email this system tries to send.
    One row per message; `status` moves queued -> sent | failed, `attempts`
    counts provider calls (bounded retry with backoff in
    app.services.email_service). Body text is deliberately NOT stored:
    password-reset / verification / invitation links are one-time
    credentials and must never sit in a log table. Only the template name,
    recipient, subject and provider message id are kept."""

    __tablename__ = "email_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    to_email: Mapped[str] = mapped_column(String(255), index=True)
    template: Mapped[str] = mapped_column(String(50))
    subject: Mapped[str] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(5), default="nl")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
