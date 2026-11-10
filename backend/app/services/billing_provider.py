"""Billing provider abstraction (Stripe-shaped: checkout session + signed
webhook events), same Protocol+Stub split as app/services/ai_provider.py
and app/services/open_banking_provider.py.

No payment provider account exists for this project -- creating one,
and any real card processing, requires a business decision and signed
agreement this session cannot make (see docs/subscription-billing.md).
What IS implemented: the provider interface a real adapter (Stripe,
Mollie, Paddle) would need to satisfy, and a StubBillingProvider that
signs its own webhook payloads with HMAC-SHA256 so the signature-
verification code path is genuinely exercised in tests, not mocked
away. Swapping in a real provider means writing one new class; the
verification logic in the webhook endpoint does not change.

Real commercial prices are never hardcoded here -- see app.models.
subscription.Plan's docstring."""

import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_PLAN_CODE = "free"

# Seeded once via app.db.seed_plans (see alembic data migration) --
# monthly_price_eur is deliberately absent/None for every plan: no real
# commercial price has been approved.
SEED_PLANS = [
    {"code": "free", "name": "Free / Trial", "company_limit": 5, "user_limit": 10},
    {"code": "starter", "name": "Starter", "company_limit": 10, "user_limit": 20},
    {"code": "professional", "name": "Professional", "company_limit": 25, "user_limit": 50},
    {"code": "business", "name": "Business", "company_limit": 50, "user_limit": 100},
    {"code": "accountant", "name": "Accountant", "company_limit": 200, "user_limit": 500},
]


@dataclass
class CheckoutSession:
    checkout_url: str
    provider_session_id: str


@dataclass
class WebhookEvent:
    provider_event_id: str
    event_type: str
    tenant_id: int
    plan_code: str | None


class BillingProvider(Protocol):
    name: str

    def create_checkout_session(self, tenant_id: int, plan_code: str, success_redirect: str) -> CheckoutSession: ...

    def verify_and_parse_webhook(self, payload: bytes, signature_header: str | None) -> WebhookEvent: ...


class InvalidWebhookSignatureError(Exception):
    pass


class StubBillingProvider:
    """Sandbox-only. Signs its own webhook payloads with HMAC-SHA256 using
    settings.billing_webhook_secret -- a real provider (Stripe etc.) signs
    the same way with its own secret, so this exercises the real
    verify-before-trust code path, not a bypass of it."""

    name = "stub"

    def create_checkout_session(self, tenant_id: int, plan_code: str, success_redirect: str) -> CheckoutSession:
        session_id = f"stub_cs_{secrets.token_urlsafe(16)}"
        return CheckoutSession(
            checkout_url=f"https://billing.sandbox.invalid/checkout/{session_id}?plan={plan_code}&redirect={success_redirect}",
            provider_session_id=session_id,
        )

    def sign_payload(self, payload: bytes) -> str:
        """Test/sandbox helper -- a real provider's dashboard does this for
        you; nothing in this codebase signs a real provider's payloads."""
        mac = hmac.new(settings.billing_webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        return f"t={int(time.time())},v1={mac}"

    def verify_and_parse_webhook(self, payload: bytes, signature_header: str | None) -> WebhookEvent:
        if not signature_header:
            raise InvalidWebhookSignatureError("Missing webhook signature header")
        parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
        expected = hmac.new(settings.billing_webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        if "v1" not in parts or not hmac.compare_digest(parts["v1"], expected):
            raise InvalidWebhookSignatureError("Webhook signature does not match -- event rejected, not applied")

        data = json.loads(payload)
        return WebhookEvent(
            provider_event_id=data["event_id"],
            event_type=data["event_type"],
            tenant_id=data["tenant_id"],
            plan_code=data.get("plan_code"),
        )


_provider_instance: BillingProvider | None = None


def get_billing_provider() -> BillingProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = StubBillingProvider()
    return _provider_instance


def reset_provider_cache() -> None:
    global _provider_instance
    _provider_instance = None
