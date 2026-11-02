from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import NoteStatus, NoteType


class AccountantNote(Base):
    """Internal notes, customer-facing questions, and missing-document requests.
    Kept as one table with a note_type discriminator rather than three near-
    duplicate tables -- the workflow (status, author, optional link to a
    document/transaction/VAT return) is identical across all three."""

    __tablename__ = "accountant_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    note_type: Mapped[NoteType] = mapped_column(Enum(NoteType, name="note_type"))
    status: Mapped[NoteStatus] = mapped_column(Enum(NoteStatus, name="note_status"), default=NoteStatus.open)
    body: Mapped[str] = mapped_column(Text)

    related_entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship()
    author: Mapped["User"] = relationship()
