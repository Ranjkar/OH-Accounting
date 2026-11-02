from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import AnomalySeverity, AnomalyStatus


class AnomalyFlag(Base):
    """A transparent, rule-based anomaly finding. Every flag names the rule
    and the evidence -- never a bare "fraud score". Never auto-labels
    anything fraudulent; that's a human judgment this only surfaces evidence
    for."""

    __tablename__ = "anomaly_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    rule_code: Mapped[str] = mapped_column(String(100))
    severity: Mapped[AnomalySeverity] = mapped_column(Enum(AnomalySeverity, name="anomaly_severity"))
    message: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON)

    related_entity_type: Mapped[str] = mapped_column(String(50))
    related_entity_id: Mapped[int] = mapped_column(Integer)

    status: Mapped[AnomalyStatus] = mapped_column(Enum(AnomalyStatus, name="anomaly_status"), default=AnomalyStatus.open)
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    company: Mapped["Company"] = relationship()
