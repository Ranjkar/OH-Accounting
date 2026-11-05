"""Phase 16.2: locale resolution for backend-generated user-facing
messages (dashboard summaries, future similar cases) -- distinct from
the PDF `document_language` param (app/reporting/report_i18n.py), which is
an explicit per-request choice independent of the viewer's own UI
language. This module answers "what language should THIS user's own
generated content show in", using the same preference chain as the
frontend: personal override, then tenant default, then Dutch."""

from app.models.user import User

SUPPORTED_LOCALES = {"nl", "en", "fa", "ar"}
DEFAULT_LOCALE = "nl"


def resolve_locale_for_user(user: User) -> str:
    code = user.locale or user.tenant_default_locale
    return code if code in SUPPORTED_LOCALES else DEFAULT_LOCALE
