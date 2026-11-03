from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import SubscriptionStatus


class Plan(Base):
    """A subscription tier. Seeded with a fixed, small set of plan codes
    (see app/services/billing_provider.py's SEED_PLANS) -- monthly_price_eur
    is deliberately left NULL for every seeded plan: no real commercial
    price has been approved, so none is hardcoded here. A real price would
    be set by an operator, once approved, via a direct update -- never
    invented by this code."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    monthly_price_eur: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    company_limit: Mapped[int] = mapped_column(Integer)
    user_limit: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(Base):
    """One active-or-historical subscription row per tenant. A tenant with
    no row at all is treated as the implicit free/trial default (see
    app.services.billing_provider.DEFAULT_PLAN_CODE) -- never silently
    granted a paid plan's limits."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), unique=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus, name="subscription_status"), default=SubscriptionStatus.trialing)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped["Plan"] = relationship()


class BillingEvent(Base):
    """Immutable log of every webhook event this system has processed
    (or rejected), keyed by the provider's own event id so a replayed
    webhook is a no-op, not a double-applied state change."""

    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    provider_event_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    verified: Mapped[bool] = mapped_column(Boolean)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
