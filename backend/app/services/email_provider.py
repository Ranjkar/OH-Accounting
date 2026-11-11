"""Outbound email transport abstraction (Phase 22).

Three providers, one Protocol:
- NullEmailProvider: EMAIL_PROVIDER=none. Sends nothing and says so, so the
  caller can fall back to showing a link in the UI. Never pretends success.
- SmtpEmailProvider: stdlib smtplib, STARTTLS (587) or implicit TLS (465).
- ResendEmailProvider: Resend's transactional HTTP API
  (POST https://api.resend.com/emails, bearer token, JSON body) via httpx.

Credentials come exclusively from app.core.config (environment); nothing in
this module logs or returns them.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OutboundEmail:
    to_email: str
    subject: str
    html_body: str
    text_body: str
    reply_to: str | None = None


class EmailSendError(Exception):
    """Transient or permanent delivery failure; `retryable` tells the
    service whether another attempt could succeed."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class EmailProvider(Protocol):
    name: str

    def send(self, message: OutboundEmail) -> str | None:
        """Returns the provider's message id when it has one."""
        ...


def _from_header() -> str:
    return formataddr((settings.email_from_name, settings.email_from_address))


class NullEmailProvider:
    name = "none"

    def send(self, message: OutboundEmail) -> str | None:
        raise EmailSendError("No email provider is configured (EMAIL_PROVIDER=none)", retryable=False)


class SmtpEmailProvider:
    name = "smtp"

    def send(self, message: OutboundEmail) -> str | None:
        if not settings.smtp_host:
            raise EmailSendError("SMTP_HOST is not set", retryable=False)
        msg = EmailMessage()
        msg["From"] = _from_header()
        msg["To"] = message.to_email
        msg["Subject"] = message.subject
        if message.reply_to:
            msg["Reply-To"] = message.reply_to
        msg.set_content(message.text_body)
        msg.add_alternative(message.html_body, subtype="html")
        context = ssl.create_default_context()
        try:
            if settings.smtp_use_ssl:
                server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20, context=context)
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
            with server:
                server.ehlo()
                if settings.smtp_use_tls and not settings.smtp_use_ssl:
                    server.starttls(context=context)
                    server.ehlo()
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password or "")
                server.send_message(msg)
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailSendError(f"SMTP authentication failed ({exc.smtp_code})", retryable=False) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise EmailSendError("Recipient refused by SMTP server", retryable=False) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailSendError(f"SMTP error: {type(exc).__name__}", retryable=True) from exc
        return None


class ResendEmailProvider:
    name = "resend"
    _ENDPOINT = "https://api.resend.com/emails"

    def send(self, message: OutboundEmail) -> str | None:
        if not settings.resend_api_key:
            raise EmailSendError("RESEND_API_KEY is not set", retryable=False)
        payload = {
            "from": _from_header(),
            "to": [message.to_email],
            "subject": message.subject,
            "html": message.html_body,
            "text": message.text_body,
        }
        if message.reply_to:
            payload["reply_to"] = message.reply_to
        try:
            response = httpx.post(
                self._ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            raise EmailSendError(f"Resend connection error: {type(exc).__name__}", retryable=True) from exc
        if response.status_code in (401, 403):
            raise EmailSendError("Resend rejected the API key", retryable=False)
        if response.status_code == 422:
            raise EmailSendError("Resend rejected the message (invalid sender or recipient)", retryable=False)
        if response.status_code == 429 or response.status_code >= 500:
            raise EmailSendError(f"Resend temporary failure ({response.status_code})", retryable=True)
        if response.status_code >= 400:
            raise EmailSendError(f"Resend error ({response.status_code})", retryable=False)
        return (response.json() or {}).get("id")


_provider: EmailProvider | None = None


def get_email_provider() -> EmailProvider:
    global _provider
    if _provider is not None:
        return _provider
    kind = (settings.email_provider or "none").strip().lower()
    if kind == "smtp":
        _provider = SmtpEmailProvider()
    elif kind == "resend":
        _provider = ResendEmailProvider()
    elif kind == "none":
        _provider = NullEmailProvider()
    else:
        raise RuntimeError(f"EMAIL_PROVIDER={kind!r} is not supported (use none, smtp or resend)")
    return _provider


def reset_provider_cache() -> None:
    """Test hook."""
    global _provider
    _provider = None


def is_configured() -> bool:
    kind = (settings.email_provider or "none").strip().lower()
    if kind == "smtp":
        return bool(settings.smtp_host)
    if kind == "resend":
        return bool(settings.resend_api_key)
    return False
