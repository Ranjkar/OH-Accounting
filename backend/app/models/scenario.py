from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import ScenarioType


class Scenario(Base):
    """A saved set of forecast assumptions. Scenarios are pure what-if
    inputs -- app/accounting/scenario_engine.py recomputes their effect from
    current ledger data on every read; nothing here is ever written back to
    the ledger, a transaction, or a budget."""

    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    name: Mapped[str] = mapped_column(String(255))
    scenario_type: Mapped[ScenarioType] = mapped_column(Enum(ScenarioType, name="scenario_type"))
    assumptions: Mapped[dict] = mapped_column(JSON)
    horizon_months: Mapped[int] = mapped_column(Integer, default=3)
    base_date: Mapped[date] = mapped_column(Date)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    company: Mapped["Company"] = relationship()
