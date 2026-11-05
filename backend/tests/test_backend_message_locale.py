"""Phase 16.2: backend-generated user-facing message localisation --
resolve_locale_for_user() (personal override -> tenant default -> nl)
and its one concrete, end-to-end wired example (dashboard attention
reasons). See app/core/messages_i18n.py's module docstring for why this
is deliberately narrow in scope."""

from app.core.locale import DEFAULT_LOCALE, resolve_locale_for_user
from app.core.messages_i18n import t
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.financial_year import VatPeriodStatus
from app.models.tenant import Tenant
from app.models.user import User


def _setup(db_session, default_locale="nl", user_locale=None, email="owner@acme.nl"):
    tenant = Tenant(name="Acme Accounting", default_locale=default_locale)
    db_session.add(tenant)
    db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Owner", role=UserRole.owner, locale=user_locale)
    db_session.add(user)
    db_session.commit()
    return tenant, user


def _login(client, email, password="secret123") -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# --- resolve_locale_for_user --------------------------------------------


def test_resolve_locale_prefers_personal_override(db_session):
    _, user = _setup(db_session, default_locale="nl", user_locale="ar")
    assert resolve_locale_for_user(user) == "ar"


def test_resolve_locale_falls_back_to_tenant_default(db_session):
    _, user = _setup(db_session, default_locale="fa", user_locale=None)
    assert resolve_locale_for_user(user) == "fa"


def test_resolve_locale_falls_back_to_dutch_if_tenant_default_unsupported(db_session, monkeypatch):
    _, user = _setup(db_session, default_locale="nl", user_locale=None)
    # Simulate a corrupt/unexpected value reaching here -- resolve_locale_for_user
    # must never propagate an unsupported code to a caller.
    monkeypatch.setattr(type(user), "tenant_default_locale", property(lambda self: "xx"))
    assert resolve_locale_for_user(user) == DEFAULT_LOCALE


# --- messages_i18n.t -----------------------------------------------------


def test_t_interpolates_and_falls_back_to_dutch_for_unknown_locale():
    assert t("en", "dashboard.overdueVatReturns", count=3) == "3 overdue VAT return(s)"
    assert t("xx", "dashboard.overdueVatReturns", count=3) == "3 openstaande btw-aangifte(n)"


def test_t_covers_all_four_locales_for_every_dashboard_key():
    from app.core.messages_i18n import MESSAGES

    keys = set(MESSAGES["nl"].keys())
    for locale in ("nl", "en", "fa", "ar"):
        assert set(MESSAGES[locale].keys()) == keys, f"{locale} dashboard message keys don't match nl"
        for key in keys:
            assert MESSAGES[locale][key], f"{locale}.{key} is empty"


# --- End-to-end: dashboard attention reasons follow the user's locale ---


def test_dashboard_attention_reasons_use_tenant_default_locale(client, db_session):
    tenant, user = _setup(db_session, default_locale="ar", email="ar-owner@acme.nl")
    headers = _login(client, "ar-owner@acme.nl")
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": 2020}, headers=headers).json()
    # A financial year in the past has an already-overdue VAT period with
    # no VAT return filed -- the same setup the pre-existing
    # test_dashboard_flags_company_with_overdue_vat_return test uses.
    assert any(p["status"] == VatPeriodStatus.open.value for p in fy["vat_periods"])

    dashboard = client.get("/api/v1/dashboard", params={"company_id": company_id}, headers=headers).json()
    flagged = [c for c in dashboard["companies_requiring_attention"] if c["company_id"] == company_id]
    assert flagged
    assert any("إقرار ضريبي متأخر" in r for r in flagged[0]["reasons"]), flagged[0]["reasons"]


def test_dashboard_attention_reasons_personal_override_beats_tenant_default(client, db_session):
    tenant, user = _setup(db_session, default_locale="ar", user_locale="en", email="en-override@acme.nl")
    headers = _login(client, "en-override@acme.nl")
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": 2020}, headers=headers)

    dashboard = client.get("/api/v1/dashboard", params={"company_id": company_id}, headers=headers).json()
    flagged = [c for c in dashboard["companies_requiring_attention"] if c["company_id"] == company_id]
    assert flagged
    assert any("overdue" in r for r in flagged[0]["reasons"]), flagged[0]["reasons"]
