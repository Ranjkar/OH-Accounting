from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.accounting import subscription_service
from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.enums import SubscriptionStatus
from app.models.subscription import BillingEvent, Plan, Subscription
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.billing import CheckoutRequest, CheckoutResponse, PlanOut, SubscriptionOut
from app.services.billing_provider import InvalidWebhookSignatureError, get_billing_provider

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    subscription_service.ensure_plans_seeded(db)
    db.commit()
    return db.query(Plan).filter(Plan.is_active.is_(True)).all()


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    subscription = subscription_service.get_or_create_subscription(db, user.tenant_id)
    db.commit()
    companies_used, users_used = subscription_service.usage(db, user.tenant_id)
    return SubscriptionOut(
        plan=subscription.plan, status=subscription.status, trial_ends_at=subscription.trial_ends_at,
        current_period_end=subscription.current_period_end, canceled_at=subscription.canceled_at,
        companies_used=companies_used, users_used=users_used,
    )


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(payload: CheckoutRequest, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    subscription_service.ensure_plans_seeded(db)
    db.commit()
    plan = db.query(Plan).filter(Plan.code == payload.plan_code, Plan.is_active.is_(True)).first()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or inactive plan code")
    provider = get_billing_provider()
    session = provider.create_checkout_session(user.tenant_id, payload.plan_code, payload.success_redirect)
    return CheckoutResponse(checkout_url=session.checkout_url, provider_session_id=session.provider_session_id)


@router.post("/cancel", response_model=SubscriptionOut)
def cancel_subscription(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    from datetime import datetime, timezone

    subscription = subscription_service.get_or_create_subscription(db, user.tenant_id)
    subscription.status = SubscriptionStatus.canceled
    subscription.canceled_at = datetime.now(timezone.utc)
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="cancel_subscription", entity_type="subscription", entity_id=subscription.id, after={}))
    db.commit()
    companies_used, users_used = subscription_service.usage(db, user.tenant_id)
    return SubscriptionOut(
        plan=subscription.plan, status=subscription.status, trial_ends_at=subscription.trial_ends_at,
        current_period_end=subscription.current_period_end, canceled_at=subscription.canceled_at,
        companies_used=companies_used, users_used=users_used,
    )


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def billing_webhook(request: Request, db: Session = Depends(get_db)):
    """Never treats an unverified webhook as a successful payment: an
    invalid or missing signature is rejected with 400 before any state is
    touched. A replayed (already-seen) event id is a silent no-op, not a
    re-applied state change -- idempotent by the same DB-unique-constraint
    pattern used for bank-import/payroll-run idempotency elsewhere."""
    from datetime import datetime, timedelta, timezone

    payload = await request.body()
    provider = get_billing_provider()
    try:
        event = provider.verify_and_parse_webhook(payload, request.headers.get("X-Billing-Signature"))
    except InvalidWebhookSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if db.query(BillingEvent).filter(BillingEvent.provider_event_id == event.provider_event_id).first() is not None:
        return  # already processed -- idempotent no-op

    db.add(BillingEvent(tenant_id=event.tenant_id, provider_event_id=event.provider_event_id, event_type=event.event_type, verified=True))

    if event.event_type == "checkout.completed" and event.plan_code:
        subscription_service.ensure_plans_seeded(db)
        plan = db.query(Plan).filter(Plan.code == event.plan_code).first()
        if plan is not None:
            subscription = subscription_service.get_or_create_subscription(db, event.tenant_id)
            subscription.plan_id = plan.id
            subscription.status = SubscriptionStatus.active
            subscription.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
    elif event.event_type == "payment.failed":
        subscription = subscription_service.get_or_create_subscription(db, event.tenant_id)
        subscription.status = SubscriptionStatus.past_due

    db.commit()


@router.get("/admin/overview")
def platform_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Cross-tenant SaaS administration -- platform admin only (a tier
    above tenant admin, see app.models.user.User.is_platform_admin).
    Deliberately returns only tenant/subscription/company-COUNT data,
    never a customer's financial records, documents, or ledger."""
    if not user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin only")

    tenants = db.query(Tenant).all()
    rows = []
    for tenant in tenants:
        subscription = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()
        companies_used, users_used = subscription_service.usage(db, tenant.id)
        rows.append({
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "plan_code": subscription.plan.code if subscription else None,
            "subscription_status": subscription.status.value if subscription else None,
            "companies_used": companies_used,
            "users_used": users_used,
        })
    return {"tenants": rows}
