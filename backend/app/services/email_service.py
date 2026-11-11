"""Email sending with delivery log, retry and rate limiting (Phase 22).

`queue_email` writes an email_outbox row and schedules the actual send on
FastAPI's BackgroundTasks (after the response, same process -- no Celery,
matching the rest of this codebase). `deliver` makes up to
settings.email_max_attempts provider calls with exponential backoff, only
retrying errors the provider marks retryable. A message that still fails
stays `failed` with `last_error`, visible on the admin email page, where
an admin can retry it.

Rate limits are per recipient and per tenant per rolling hour, counted
from the outbox itself (so they survive restarts, unlike the in-memory
endpoint limiter). Exceeding one records the message as failed with a
clear reason rather than raising -- a caller that just created an
invitation must not 500 because the mailbox is noisy.

Returns whether the message could be *attempted* (a provider is
configured), so callers can fall back to showing the link in the UI when
nothing can be sent. Links/tokens are never persisted here.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.email_outbox import EmailOutbox
from app.services.email_provider import EmailSendError, OutboundEmail, get_email_provider, is_configured

logger = logging.getLogger(__name__)


class EmailRateLimited(Exception):
    pass


def _check_rate_limits(db: Session, to_email: str, tenant_id: int | None) -> None:
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    per_recipient = db.query(EmailOutbox).filter(EmailOutbox.to_email == to_email.lower(), EmailOutbox.created_at >= since).count()
    if per_recipient >= settings.email_rate_limit_per_recipient_per_hour:
        raise EmailRateLimited(f"Rate limit: more than {settings.email_rate_limit_per_recipient_per_hour} emails to this address in the last hour")
    if tenant_id is not None:
        per_tenant = db.query(EmailOutbox).filter(EmailOutbox.tenant_id == tenant_id, EmailOutbox.created_at >= since).count()
        if per_tenant >= settings.email_rate_limit_per_tenant_per_hour:
            raise EmailRateLimited(f"Rate limit: more than {settings.email_rate_limit_per_tenant_per_hour} emails for this organisation in the last hour")


def queue_email(
    db: Session,
    background: BackgroundTasks | None,
    *,
    to_email: str,
    template: str,
    subject: str,
    html_body: str,
    text_body: str,
    locale: str = "nl",
    tenant_id: int | None = None,
) -> tuple[EmailOutbox, bool]:
    """Records the message and schedules delivery. Returns (row, will_send).
    `will_send` is False when no provider is configured or a rate limit
    hit -- the row then already carries status=failed + the reason.
    The caller is responsible for committing `db` (the row rides along
    with the caller's own transaction so a failed request leaves no
    orphan log entry)."""
    row = EmailOutbox(tenant_id=tenant_id, to_email=to_email.lower(), template=template, subject=subject[:255], locale=locale)
    db.add(row)
    try:
        _check_rate_limits(db, to_email, tenant_id)
    except EmailRateLimited as exc:
        row.status = "failed"
        row.last_error = str(exc)
        logger.warning("Email to %s (%s) not sent: %s", to_email, template, exc)
        db.flush()
        return row, False
    if not is_configured():
        row.status = "failed"
        row.provider_name = get_email_provider().name
        row.last_error = "No email provider configured (EMAIL_PROVIDER)"
        db.flush()
        return row, False
    db.flush()
    message = OutboundEmail(to_email=to_email, subject=subject, html_body=html_body, text_body=text_body)
    if background is not None:
        background.add_task(deliver_by_id, row.id, message)
    else:
        deliver(db, row, message)
    return row, True


def deliver(db: Session, row: EmailOutbox, message: OutboundEmail) -> None:
    provider = get_email_provider()
    row.provider_name = provider.name
    attempts_left = max(1, settings.email_max_attempts - row.attempts)
    for i in range(attempts_left):
        row.attempts += 1
        try:
            row.provider_message_id = provider.send(message)
            row.status = "sent"
            row.sent_at = datetime.now(timezone.utc)
            row.last_error = None
            db.commit()
            return
        except EmailSendError as exc:
            row.last_error = str(exc)[:1000]
            row.status = "failed"
            db.commit()
            if not exc.retryable or i == attempts_left - 1:
                logger.warning("Email %s to %s failed permanently after %d attempt(s): %s", row.id, row.to_email, row.attempts, exc)
                return
            time.sleep(settings.email_retry_base_delay_seconds * (2 ** i))
        except Exception as exc:  # never let an unexpected provider bug take the worker down
            row.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            row.status = "failed"
            db.commit()
            logger.exception("Unexpected error sending email %s", row.id)
            return


def deliver_by_id(row_id: int, message: OutboundEmail) -> None:
    """BackgroundTasks entry point: runs after the response with its own
    session (the request's session is closed by then)."""
    db = SessionLocal()
    try:
        row = db.get(EmailOutbox, row_id)
        if row is not None:
            deliver(db, row, message)
    finally:
        db.close()


def link(path: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}{path}"
