"""Branded, responsive HTML + plain-text email templates (Phase 22).

One base layout (table-based, inline CSS -- the only thing that renders
consistently across Outlook/Gmail/Apple Mail), rendered in nl/en/fa/ar with
`dir="rtl"` for the Arabic-script locales. Copy lives here, not in the
frontend dictionaries: these are composed server-side and must work with no
browser involved. Every link is passed in by the caller; this module never
reads tokens from anywhere itself.
"""

from html import escape

BRAND_PURPLE = "#7c3aed"
RTL_LOCALES = {"fa", "ar"}

STRINGS: dict[str, dict[str, str]] = {
    "nl": {
        "greeting": "Hallo {name},",
        "ignore": "Heeft u dit niet aangevraagd? Dan kunt u deze e-mail negeren; er is niets gewijzigd.",
        "button_fallback": "Werkt de knop niet? Kopieer deze link naar uw browser:",
        "footer": "Deze e-mail is automatisch verzonden door OnHolland Accounting. Antwoorden op dit bericht worden niet gelezen.",
        "expires": "Deze link is {minutes} minuten geldig.",
        "expires_days": "Deze link is {days} dagen geldig.",
        "password_reset.subject": "Wachtwoord opnieuw instellen",
        "password_reset.body": "Er is een verzoek ontvangen om het wachtwoord van uw OnHolland-account opnieuw in te stellen.",
        "password_reset.cta": "Nieuw wachtwoord instellen",
        "email_verification.subject": "Bevestig uw nieuwe e-mailadres",
        "email_verification.body": "U heeft gevraagd het e-mailadres van uw OnHolland-account te wijzigen naar {new_email}. Bevestig dat dit adres van u is.",
        "email_verification.cta": "E-mailadres bevestigen",
        "user_invitation.subject": "Uitnodiging voor {tenant}",
        "user_invitation.body": "{inviter} heeft u uitgenodigd om als {role} deel te nemen aan {tenant} in OnHolland Accounting. Maak uw account aan via de knop hieronder.",
        "user_invitation.cta": "Account aanmaken",
        "company_invitation.subject": "Toegang tot {company}",
        "company_invitation.body": "{inviter} geeft u toegang tot de administratie van {company} in OnHolland Accounting. Meld u aan met het account op dit e-mailadres en accepteer de uitnodiging.",
        "company_invitation.cta": "Uitnodiging accepteren",
        "security.subject": "Beveiligingsmelding: {event}",
        "security.body": "Op uw OnHolland-account heeft zojuist de volgende wijziging plaatsgevonden: {event}. Was u dit niet? Neem dan direct contact op met uw beheerder en wijzig uw wachtwoord.",
        "security.password_changed": "wachtwoord gewijzigd",
        "security.email_changed": "e-mailadres gewijzigd naar {new_email}",
        "security.mfa_enabled": "tweefactorauthenticatie ingeschakeld",
        "security.mfa_disabled": "tweefactorauthenticatie uitgeschakeld",
        "security.sessions_revoked": "alle andere sessies afgemeld",
        "test.subject": "Testbericht van OnHolland Accounting",
        "test.body": "Dit is een testbericht. Als u dit leest, is de e-mailconfiguratie ({provider}) correct.",
        "test.cta": "Open OnHolland",
    },
    "en": {
        "greeting": "Hello {name},",
        "ignore": "Didn't request this? You can safely ignore this email; nothing has changed.",
        "button_fallback": "Button not working? Copy this link into your browser:",
        "footer": "This email was sent automatically by OnHolland Accounting. Replies to this message are not read.",
        "expires": "This link is valid for {minutes} minutes.",
        "expires_days": "This link is valid for {days} days.",
        "password_reset.subject": "Reset your password",
        "password_reset.body": "We received a request to reset the password of your OnHolland account.",
        "password_reset.cta": "Set a new password",
        "email_verification.subject": "Confirm your new email address",
        "email_verification.body": "You asked to change the email address of your OnHolland account to {new_email}. Please confirm this address is yours.",
        "email_verification.cta": "Confirm email address",
        "user_invitation.subject": "Invitation to {tenant}",
        "user_invitation.body": "{inviter} has invited you to join {tenant} on OnHolland Accounting as {role}. Create your account with the button below.",
        "user_invitation.cta": "Create account",
        "company_invitation.subject": "Access to {company}",
        "company_invitation.body": "{inviter} is giving you access to the books of {company} on OnHolland Accounting. Sign in with the account on this email address and accept the invitation.",
        "company_invitation.cta": "Accept invitation",
        "security.subject": "Security notice: {event}",
        "security.body": "The following change was just made on your OnHolland account: {event}. If this wasn't you, contact your administrator immediately and change your password.",
        "security.password_changed": "password changed",
        "security.email_changed": "email address changed to {new_email}",
        "security.mfa_enabled": "two-factor authentication enabled",
        "security.mfa_disabled": "two-factor authentication disabled",
        "security.sessions_revoked": "all other sessions signed out",
        "test.subject": "Test message from OnHolland Accounting",
        "test.body": "This is a test message. If you can read it, the email configuration ({provider}) works.",
        "test.cta": "Open OnHolland",
    },
    "fa": {
        "greeting": "سلام {name}،",
        "ignore": "اگر این درخواست را نداده‌اید، می‌توانید این ایمیل را نادیده بگیرید؛ هیچ تغییری انجام نشده است.",
        "button_fallback": "دکمه کار نمی‌کند؟ این پیوند را در مرورگر خود کپی کنید:",
        "footer": "این ایمیل به‌صورت خودکار توسط OnHolland Accounting ارسال شده است. پاسخ‌ها به این پیام خوانده نمی‌شوند.",
        "expires": "این پیوند {minutes} دقیقه معتبر است.",
        "expires_days": "این پیوند {days} روز معتبر است.",
        "password_reset.subject": "بازنشانی گذرواژه",
        "password_reset.body": "درخواستی برای بازنشانی گذرواژه حساب OnHolland شما دریافت شد.",
        "password_reset.cta": "تنظیم گذرواژه جدید",
        "email_verification.subject": "تأیید آدرس ایمیل جدید",
        "email_verification.body": "شما درخواست کرده‌اید آدرس ایمیل حساب OnHolland خود را به {new_email} تغییر دهید. لطفاً تأیید کنید که این آدرس متعلق به شماست.",
        "email_verification.cta": "تأیید آدرس ایمیل",
        "user_invitation.subject": "دعوت به {tenant}",
        "user_invitation.body": "{inviter} شما را دعوت کرده است تا با نقش {role} به {tenant} در OnHolland Accounting بپیوندید. با دکمه زیر حساب خود را بسازید.",
        "user_invitation.cta": "ساخت حساب",
        "company_invitation.subject": "دسترسی به {company}",
        "company_invitation.body": "{inviter} به شما دسترسی به حسابداری {company} در OnHolland Accounting می‌دهد. با حساب مربوط به این آدرس ایمیل وارد شوید و دعوت را بپذیرید.",
        "company_invitation.cta": "پذیرش دعوت",
        "security.subject": "هشدار امنیتی: {event}",
        "security.body": "تغییر زیر هم‌اکنون در حساب OnHolland شما انجام شد: {event}. اگر این کار را شما انجام نداده‌اید، فوراً با مدیر خود تماس بگیرید و گذرواژه‌تان را تغییر دهید.",
        "security.password_changed": "گذرواژه تغییر کرد",
        "security.email_changed": "آدرس ایمیل به {new_email} تغییر کرد",
        "security.mfa_enabled": "احراز هویت دومرحله‌ای فعال شد",
        "security.mfa_disabled": "احراز هویت دومرحله‌ای غیرفعال شد",
        "security.sessions_revoked": "همه نشست‌های دیگر خارج شدند",
        "test.subject": "پیام آزمایشی از OnHolland Accounting",
        "test.body": "این یک پیام آزمایشی است. اگر آن را می‌خوانید، پیکربندی ایمیل ({provider}) درست کار می‌کند.",
        "test.cta": "باز کردن OnHolland",
    },
    "ar": {
        "greeting": "مرحباً {name}،",
        "ignore": "لم تطلب هذا؟ يمكنك تجاهل هذه الرسالة بأمان؛ لم يتغير شيء.",
        "button_fallback": "الزر لا يعمل؟ انسخ هذا الرابط في متصفحك:",
        "footer": "أُرسلت هذه الرسالة تلقائياً من OnHolland Accounting. لا تتم قراءة الردود على هذه الرسالة.",
        "expires": "هذا الرابط صالح لمدة {minutes} دقيقة.",
        "expires_days": "هذا الرابط صالح لمدة {days} أيام.",
        "password_reset.subject": "إعادة تعيين كلمة المرور",
        "password_reset.body": "تلقينا طلباً لإعادة تعيين كلمة مرور حسابك في OnHolland.",
        "password_reset.cta": "تعيين كلمة مرور جديدة",
        "email_verification.subject": "تأكيد عنوان بريدك الإلكتروني الجديد",
        "email_verification.body": "طلبت تغيير عنوان البريد الإلكتروني لحسابك في OnHolland إلى {new_email}. يرجى تأكيد أن هذا العنوان يخصك.",
        "email_verification.cta": "تأكيد عنوان البريد",
        "user_invitation.subject": "دعوة إلى {tenant}",
        "user_invitation.body": "دعاك {inviter} للانضمام إلى {tenant} في OnHolland Accounting بصفة {role}. أنشئ حسابك بالزر أدناه.",
        "user_invitation.cta": "إنشاء حساب",
        "company_invitation.subject": "الوصول إلى {company}",
        "company_invitation.body": "يمنحك {inviter} حق الوصول إلى دفاتر {company} في OnHolland Accounting. سجّل الدخول بالحساب المرتبط بهذا البريد واقبل الدعوة.",
        "company_invitation.cta": "قبول الدعوة",
        "security.subject": "تنبيه أمني: {event}",
        "security.body": "تم للتو إجراء التغيير التالي على حسابك في OnHolland: {event}. إن لم تكن أنت، فاتصل بالمسؤول فوراً وغيّر كلمة مرورك.",
        "security.password_changed": "تم تغيير كلمة المرور",
        "security.email_changed": "تم تغيير عنوان البريد إلى {new_email}",
        "security.mfa_enabled": "تم تفعيل المصادقة الثنائية",
        "security.mfa_disabled": "تم تعطيل المصادقة الثنائية",
        "security.sessions_revoked": "تم تسجيل الخروج من جميع الجلسات الأخرى",
        "test.subject": "رسالة اختبار من OnHolland Accounting",
        "test.body": "هذه رسالة اختبار. إذا كنت تقرؤها، فإن إعدادات البريد ({provider}) تعمل بشكل صحيح.",
        "test.cta": "فتح OnHolland",
    },
}


def t(locale: str, key: str, **params: object) -> str:
    table = STRINGS.get(locale) or STRINGS["nl"]
    return (table.get(key) or STRINGS["en"][key]).format(**params)


def render(locale: str, *, title: str, greeting_name: str | None, body: str, cta_label: str | None, cta_url: str | None, extra_lines: list[str]) -> tuple[str, str]:
    """Returns (html, text). All dynamic values are HTML-escaped; the URL is
    emitted verbatim in href and as visible text for clients without buttons."""
    locale = locale if locale in STRINGS else "nl"
    direction = "rtl" if locale in RTL_LOCALES else "ltr"
    align = "right" if direction == "rtl" else "left"
    font = "'Vazirmatn','Noto Sans Arabic',Tahoma,Arial,sans-serif" if direction == "rtl" else "-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif"

    lines_html: list[str] = []
    text_lines: list[str] = [title, ""]
    if greeting_name:
        g = t(locale, "greeting", name=greeting_name)
        lines_html.append(f'<p style="margin:0 0 16px">{escape(g)}</p>')
        text_lines += [g, ""]
    lines_html.append(f'<p style="margin:0 0 16px">{escape(body)}</p>')
    text_lines += [body, ""]
    if cta_url and cta_label:
        lines_html.append(
            f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin:24px 0"><tr><td style="background:{BRAND_PURPLE};border-radius:8px">'
            f'<a href="{escape(cta_url, quote=True)}" style="display:inline-block;padding:12px 22px;color:#ffffff;text-decoration:none;font-weight:600;font-size:15px">{escape(cta_label)}</a>'
            f"</td></tr></table>"
        )
        lines_html.append(f'<p style="margin:0 0 8px;font-size:13px;color:#666666">{escape(t(locale, "button_fallback"))}</p>')
        lines_html.append(f'<p style="margin:0 0 16px;font-size:13px;word-break:break-all" dir="ltr"><a href="{escape(cta_url, quote=True)}" style="color:{BRAND_PURPLE}">{escape(cta_url)}</a></p>')
        text_lines += [f"{cta_label}: {cta_url}", ""]
    for line in extra_lines:
        lines_html.append(f'<p style="margin:0 0 12px;font-size:13px;color:#666666">{escape(line)}</p>')
        text_lines.append(line)
    footer = t(locale, "footer")
    text_lines += ["", "--", footer]

    html = f"""<!doctype html>
<html lang="{locale}" dir="{direction}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title></head>
<body style="margin:0;padding:0;background:#f5f5f4;font-family:{font};color:#171717">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f5f5f4;padding:24px 12px">
<tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #eae7e5;border-radius:12px">
<tr><td style="padding:20px 24px;border-bottom:1px solid #eae7e5;text-align:{align}">
  <span style="display:inline-block;width:28px;height:28px;line-height:28px;border-radius:8px;background:{BRAND_PURPLE};color:#fff;font-weight:700;text-align:center;font-size:14px;vertical-align:middle">O</span>
  <span style="font-weight:600;font-size:16px;vertical-align:middle;margin:0 8px">OnHolland Accounting</span>
</td></tr>
<tr><td style="padding:24px;font-size:15px;line-height:1.55;text-align:{align}">
  <h1 style="margin:0 0 16px;font-size:20px;line-height:1.3">{escape(title)}</h1>
  {''.join(lines_html)}
</td></tr>
<tr><td style="padding:16px 24px;border-top:1px solid #eae7e5;font-size:12px;color:#929292;text-align:{align}">{escape(footer)}</td></tr>
</table>
</td></tr></table>
</body></html>"""
    return html, "\n".join(text_lines)


def password_reset(locale: str, name: str, link: str, minutes: int) -> tuple[str, str, str]:
    subject = t(locale, "password_reset.subject")
    html, text = render(locale, title=subject, greeting_name=name, body=t(locale, "password_reset.body"), cta_label=t(locale, "password_reset.cta"), cta_url=link, extra_lines=[t(locale, "expires", minutes=minutes), t(locale, "ignore")])
    return subject, html, text


def email_verification(locale: str, name: str, new_email: str, link: str, minutes: int) -> tuple[str, str, str]:
    subject = t(locale, "email_verification.subject")
    html, text = render(locale, title=subject, greeting_name=name, body=t(locale, "email_verification.body", new_email=new_email), cta_label=t(locale, "email_verification.cta"), cta_url=link, extra_lines=[t(locale, "expires", minutes=minutes), t(locale, "ignore")])
    return subject, html, text


def user_invitation(locale: str, inviter: str, tenant: str, role: str, link: str, days: int) -> tuple[str, str, str]:
    subject = t(locale, "user_invitation.subject", tenant=tenant)
    html, text = render(locale, title=subject, greeting_name=None, body=t(locale, "user_invitation.body", inviter=inviter, tenant=tenant, role=role), cta_label=t(locale, "user_invitation.cta"), cta_url=link, extra_lines=[t(locale, "expires_days", days=days), t(locale, "ignore")])
    return subject, html, text


def company_invitation(locale: str, inviter: str, company: str, link: str, days: int) -> tuple[str, str, str]:
    subject = t(locale, "company_invitation.subject", company=company)
    html, text = render(locale, title=subject, greeting_name=None, body=t(locale, "company_invitation.body", inviter=inviter, company=company), cta_label=t(locale, "company_invitation.cta"), cta_url=link, extra_lines=[t(locale, "expires_days", days=days), t(locale, "ignore")])
    return subject, html, text


def security_notification(locale: str, name: str, event_key: str, **params: object) -> tuple[str, str, str]:
    event = t(locale, f"security.{event_key}", **params)
    subject = t(locale, "security.subject", event=event)
    html, text = render(locale, title=subject, greeting_name=name, body=t(locale, "security.body", event=event), cta_label=None, cta_url=None, extra_lines=[])
    return subject, html, text


def test_message(locale: str, name: str, provider: str, link: str) -> tuple[str, str, str]:
    subject = t(locale, "test.subject")
    html, text = render(locale, title=subject, greeting_name=name, body=t(locale, "test.body", provider=provider), cta_label=t(locale, "test.cta"), cta_url=link, extra_lines=[])
    return subject, html, text
