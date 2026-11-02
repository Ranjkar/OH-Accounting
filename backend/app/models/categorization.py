from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import CategorizationRuleType


class CategorizationRule(Base):
    """Company-specific expense categorization rule. Never applied across
    companies -- a supplier named identically for two different companies
    may legitimately mean different things to each."""

    __tablename__ = "categorization_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    rule_type: Mapped[CategorizationRuleType] = mapped_column(
        Enum(CategorizationRuleType, name="categorization_rule_type")
    )
    match_value: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    company: Mapped["Company"] = relationship()
