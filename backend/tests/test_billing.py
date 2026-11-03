"""Phase 14: subscription/billing sandbox workflow. No real payment
provider exists (see docs/subscription-billing.md) -- this exercises the
real signature-verification code path against the stub provider's own
signer, not a bypass of it."""

import json

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.subscription import Plan
from app.models.tenant import Tenant
from app.models.user import User
from app.services.billing_provider import StubBillingProvider


def _create_admin(db_session) -> User:
    tenant = Tenant(name="Acme Accounting")
    db_session.add(tenant)
    db_session.flush()
    admin = User(tenant_id=tenant.id, email="admin@acme.nl", hashed_password=hash_password("secret123"), full_name="Admin", role=UserRole.admin)
    db_session.add(admin)
    db_session.commit()
    return admin


def _headers(client, email="admin@acme.nl", password="secret123"):
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_new_tenant_is_on_the_free_plan_by_default(client, db_session):
    _create_admin(db_session)
    response = client.get("/api/v1/billing/subscription", headers=_headers(client))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan"]["code"] == "free"
    assert body["status"] == "TRIALING"
    assert body["plan"]["monthly_price_eur"] is None


def test_company_creation_is_blocked_once_the_plan_limit_is_reached(client, db_session):
    admin = _create_admin(db_session)
    headers = _headers(client)

    from app.accounting import subscription_service

    subscription = subscription_service.get_or_create_subscription(db_session, admin.tenant_id)
    plan = db_session.query(Plan).filter(Plan.code == "free").first()
    subscription.plan_id = plan.id
    db_session.commit()

    for i in range(plan.company_limit):
        response = client.post("/api/v1/companies", json={"name": f"Co {i}"}, headers=headers)
        assert response.status_code == 201, response.text

    over_limit = client.post("/api/v1/companies", json={"name": "One too many"}, headers=headers)
    assert over_limit.status_code == 402


def test_checkout_requires_admin(client, db_session):
    _create_admin(db_session)
    employee = User(tenant_id=db_session.query(Tenant).first().id, email="viewer@acme.nl", hashed_password=hash_password("secret123"), full_name="Viewer", role=UserRole.viewer)
    db_session.add(employee)
    db_session.commit()

    response = client.post("/api/v1/billing/checkout", json={"plan_code": "professional"}, headers=_headers(client, "viewer@acme.nl"))
    assert response.status_code == 403


def test_checkout_then_webhook_activates_the_plan(client, db_session):
    admin = _create_admin(db_session)
    headers = _headers(client)

    checkout = client.post("/api/v1/billing/checkout", json={"plan_code": "professional"}, headers=headers)
    assert checkout.status_code == 200, checkout.text

    provider = StubBillingProvider()
    payload = json.dumps({"event_id": "evt_1", "event_type": "checkout.completed", "tenant_id": admin.tenant_id, "plan_code": "professional"}).encode()
    signature = provider.sign_payload(payload)

    webhook = client.post("/api/v1/billing/webhook", content=payload, headers={"X-Billing-Signature": signature, "Content-Type": "application/json"})
    assert webhook.status_code == 204, webhook.text

    subscription = client.get("/api/v1/billing/subscription", headers=headers).json()
    assert subscription["plan"]["code"] == "professional"
    assert subscription["status"] == "ACTIVE"


def test_webhook_with_bad_signature_is_rejected_and_never_applied(client, db_session):
    admin = _create_admin(db_session)
    payload = json.dumps({"event_id": "evt_bad", "event_type": "checkout.completed", "tenant_id": admin.tenant_id, "plan_code": "professional"}).encode()

    webhook = client.post("/api/v1/billing/webhook", content=payload, headers={"X-Billing-Signature": "t=1,v1=0000", "Content-Type": "application/json"})
    assert webhook.status_code == 400

    subscription = client.get("/api/v1/billing/subscription", headers=_headers(client)).json()
    assert subscription["plan"]["code"] == "free"


def test_webhook_is_idempotent_against_a_replayed_event(client, db_session):
    admin = _create_admin(db_session)
    provider = StubBillingProvider()
    payload = json.dumps({"event_id": "evt_replay", "event_type": "checkout.completed", "tenant_id": admin.tenant_id, "plan_code": "starter"}).encode()
    signature = provider.sign_payload(payload)

    first = client.post("/api/v1/billing/webhook", content=payload, headers={"X-Billing-Signature": signature, "Content-Type": "application/json"})
    second = client.post("/api/v1/billing/webhook", content=payload, headers={"X-Billing-Signature": signature, "Content-Type": "application/json"})
    assert first.status_code == 204
    assert second.status_code == 204

    from app.models.subscription import BillingEvent

    assert db_session.query(BillingEvent).filter(BillingEvent.provider_event_id == "evt_replay").count() == 1


def test_platform_overview_requires_platform_admin(client, db_session):
    admin = _create_admin(db_session)
    response = client.get("/api/v1/billing/admin/overview", headers=_headers(client))
    assert response.status_code == 403

    admin.is_platform_admin = True
    db_session.commit()
    response2 = client.get("/api/v1/billing/admin/overview", headers=_headers(client))
    assert response2.status_code == 200
    assert any(row["tenant_id"] == admin.tenant_id for row in response2.json()["tenants"])
