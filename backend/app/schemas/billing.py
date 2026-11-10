from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import SubscriptionStatus


class PlanOut(BaseModel):
    code: str
    name: str
    monthly_price_eur: Decimal | None
    company_limit: int
    user_limit: int

    model_config = ConfigDict(from_attributes=True)


class SubscriptionOut(BaseModel):
    plan: PlanOut
    status: SubscriptionStatus
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    canceled_at: datetime | None
    companies_used: int
    users_used: int

    model_config = ConfigDict(from_attributes=True)


class CheckoutRequest(BaseModel):
    plan_code: str
    success_redirect: str = "/billing"


class CheckoutResponse(BaseModel):
    checkout_url: str
    provider_session_id: str
