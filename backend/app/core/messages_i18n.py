"""Phase 16.2: translations for backend-GENERATED user-facing text --
distinct from app/reporting/report_i18n.py (PDF report content) and the
frontend's next-intl dictionaries (UI chrome). This module is
deliberately small and will stay that way: most of this backend's
user-facing text already lives in the frontend (the API returns
structured data; the frontend renders and translates it). This module
exists only for the narrow case where the BACKEND itself composes a
display string server-side, e.g. the dashboard's per-company "reasons"
list (app/api/v1/dashboard.py) -- see the Phase 16.2 report's "backend
message localisation coverage" section for which call sites use this
and which ones (the many informational "note" strings across
app/accounting/*.py, app/api/v1/tax_centre.py, etc.) deliberately do
not yet: those are a separate, much larger body of work, not attempted
in this pass per the explicit instruction not to blindly translate
every backend string.

Count-dependent messages use the same "(s)"-style singular/plural
simplification as the pre-existing English text they replace (a single
template, no language-specific plural-form grammar) -- a deliberate,
documented simplification, not an attempt at full Persian/Arabic
numeral-agreement rules."""

MESSAGES = {
    "nl": {
        "dashboard.overdueVatReturns": "{count} openstaande btw-aangifte(n)",
        "dashboard.documentsNeedReview": "{count} document(en) moet(en) worden beoordeeld",
        "dashboard.overduePayments": "{count} betaling(en) te laat",
    },
    "en": {
        "dashboard.overdueVatReturns": "{count} overdue VAT return(s)",
        "dashboard.documentsNeedReview": "{count} document(s) need review",
        "dashboard.overduePayments": "{count} overdue payment(s)",
    },
    "fa": {
        "dashboard.overdueVatReturns": "{count} اظهارنامه مالیات بر ارزش افزوده معوق",
        "dashboard.documentsNeedReview": "{count} سند نیازمند بررسی",
        "dashboard.overduePayments": "{count} پرداخت معوق",
    },
    "ar": {
        "dashboard.overdueVatReturns": "{count} إقرار ضريبي متأخر",
        "dashboard.documentsNeedReview": "{count} مستند بحاجة إلى مراجعة",
        "dashboard.overduePayments": "{count} دفعة متأخرة",
    },
}

DEFAULT_LOCALE = "nl"


def t(locale: str, key: str, **params) -> str:
    strings = MESSAGES.get(locale, MESSAGES[DEFAULT_LOCALE])
    template = strings.get(key, MESSAGES[DEFAULT_LOCALE][key])
    return template.format(**params) if params else template
