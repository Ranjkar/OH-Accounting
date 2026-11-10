"""Subscription/usage orchestration. A tenant with no Subscription row is
treated as being on the free/trial plan (DEFAULT_PLAN_CODE) -- created
lazily on first access, never silently granted a paid plan's limits."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import SubscriptionStatus
from app.models.subscription import Plan, Subscription
from app.models.user import User
from app.services.billing_provider import DEFAULT_PLAN_CODE

TRIAL_DAYS = 14


class SubscriptionError(Exception):
    pass


class PlanLimitExceededError(SubscriptionError):
    pass


def ensure_plans_seeded(db: Session) -> None:
    """The real seed lives in the Phase 14 migration (op.bulk_insert); this
    is a resilience fallback for a database created via
    Base.metadata.create_all() without running migrations (e.g. this
    project's own test fixtures) -- idempotent, never overwrites an
    existing plan row."""
    from app.services.billing_provider import SEED_PLANS

    if db.query(Plan).first() is not None:
        return
    for seed in SEED_PLANS:
        db.add(Plan(code=seed["code"], name=seed["name"], company_limit=seed["company_limit"], user_limit=seed["user_limit"]))
    db.flush()


def get_or_create_subscription(db: Session, tenant_id: int) -> Subscription:
    subscription = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if subscription is not None:
        return subscription

    ensure_plans_seeded(db)
    plan = db.query(Plan).filter(Plan.code == DEFAULT_PLAN_CODE).first()
    if plan is None:
        raise SubscriptionError(f"Default plan '{DEFAULT_PLAN_CODE}' is not seeded -- run the plan seed migration")

    subscription = Subscription(
        tenant_id=tenant_id,
        plan_id=plan.id,
        status=SubscriptionStatus.trialing,
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS),
    )
    db.add(subscription)
    db.flush()
    return subscription


def usage(db: Session, tenant_id: int) -> tuple[int, int]:
    companies_used = db.query(Company).filter(Company.tenant_id == tenant_id).count()
    users_used = db.query(User).filter(User.tenant_id == tenant_id).count()
    return companies_used, users_used


def enforce_company_limit(db: Session, tenant_id: int) -> None:
    subscription = get_or_create_subscription(db, tenant_id)
    companies_used, _ = usage(db, tenant_id)
    if companies_used >= subscription.plan.company_limit:
        raise PlanLimitExceededError(
            f"This account's plan ({subscription.plan.name}) allows up to {subscription.plan.company_limit} "
            f"compan{'y' if subscription.plan.company_limit == 1 else 'ies'}. Upgrade the plan to add more."
        )
