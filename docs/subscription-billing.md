# Subscription & billing

## What exists

Plan/Subscription/BillingEvent data model (`app/models/subscription.py`),
a provider abstraction (`app/services/billing_provider.py`, Protocol +
`StubBillingProvider`, same pattern as `ai_provider.py`/
`open_banking_provider.py`/`kvk_provider.py`), and real enforcement: a
tenant's company count is checked against its plan's `company_limit` on
every `POST /companies` (`app.accounting.subscription_service.
enforce_company_limit`, HTTP 402 when exceeded).

A tenant with no `Subscription` row is lazily created on first access as
`free`/`TRIALING` (`get_or_create_subscription`) — never silently
granted a paid plan.

## Plans (seeded, no real prices)

| Code | Company limit | User limit | Monthly price |
|---|---|---|---|
| free | 5 | 10 | *(not set)* |
| starter | 10 | 20 | *(not set)* |
| professional | 25 | 50 | *(not set)* |
| business | 50 | 100 | *(not set)* |
| accountant | 200 | 500 | *(not set)* |

`monthly_price_eur` is `NULL` for every seeded plan, deliberately — no
real commercial price has been approved, per the brief's explicit "do
not hardcode commercial prices without approval." An operator would set
these once a price is approved; nothing in this codebase invents one.
`user_limit` is tracked and returned to the frontend but **not yet
enforced** — there is no self-service "invite a new teammate into my
own tenant" endpoint in this codebase to attach the check to (company
access invitations, see `docs/security.md`'s accountant-ecosystem
section, link an *existing* user from another tenant; they never
become a new user of the inviting tenant). Stated as a real limitation,
not silently assumed solved.

## Billing provider

**No payment provider account exists.** Creating one (Stripe, Mollie,
Paddle) requires a business decision and signed agreement this session
cannot make — **BLOCKED BY EXTERNAL REQUIREMENT**, same category as
SBR/Digipoort and Open Banking. What's implemented is
`StubBillingProvider`:

- `create_checkout_session` returns a sandbox URL (`billing.sandbox.
  invalid/...`) — never a real redirect target.
- Webhook signature verification is genuinely exercised, not mocked
  away: the stub signs its own test payloads with HMAC-SHA256 using
  `BILLING_WEBHOOK_SECRET`, and `POST /billing/webhook` verifies that
  exact signature before touching any state. **An unverified or missing
  signature is rejected with 400 and never applied** — tested
  (`test_webhook_with_bad_signature_is_rejected_and_never_applied`).
  A real provider signs the same way with its own secret; swapping in a
  real adapter changes zero verification logic.
- Replayed events are a no-op: `BillingEvent.provider_event_id` is
  unique, checked before any state change — tested
  (`test_webhook_is_idempotent_against_a_replayed_event`).

## SaaS administration

`User.is_platform_admin` is a privilege tier *above* tenant admin —
can see cross-tenant subscription/plan/usage counts via
`GET /billing/admin/overview` (and the `/admin` frontend page), but
**never a customer's financial records, documents, or ledger entries**
(the endpoint returns tenant name + plan + status + counts only).
There is no self-service way to grant this flag to any account — it is
only settable via a direct database update by an operator, the same
"no API ever creates this" pattern used elsewhere for privilege
escalation risks.

## What's SANDBOX VERIFIED vs. NOT IMPLEMENTED

| Capability | Status |
|---|---|
| Plan/Subscription data model + usage tracking | IMPLEMENTED, tested |
| Company-limit enforcement | IMPLEMENTED, tested (real 402 on over-limit) |
| User-limit enforcement | NOT IMPLEMENTED (no attachment point exists yet, see above) |
| Sandbox checkout + signed webhook activation | SANDBOX VERIFIED (7 tests, real HMAC verification) |
| Real payment processing | BLOCKED BY EXTERNAL REQUIREMENT (no provider account) |
| Refunds | NOT IMPLEMENTED (no real provider to refund through) |
| Cross-tenant platform admin overview | IMPLEMENTED, tested, financial-data-free by design |

## Frontend

`/billing` — current plan, usage against limits, available plans,
sandbox checkout, cancel. `/admin` — platform overview table, rendered
only when `user.is_platform_admin`; the nav item itself is only added to
the sidebar for that same flag (`navConfig.PLATFORM_ADMIN_NAV_GROUP`).
