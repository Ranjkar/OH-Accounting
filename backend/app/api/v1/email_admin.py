"""Phase 22: email configuration status + delivery log, platform admins only
(email is a system-wide setting, not a per-tenant one). Nothing here ever
returns a credential: the status reports WHICH provider is active and
whether its required variables are set, never their values."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import enforce as enforce_rate_limit
from app.core.request_context import get_request_id
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.email_outbox import EmailOutbox
from app.models.user import User
from app.services import email_templates
from app.services.email_provider import get_email_provider, is_configured
from app.services.email_service import deliver, link as email_link, queue_email
from app.services.email_provider import OutboundEmail

router = APIRouter(prefix="/admin/email", tags=["email-admin"])


def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin only")
    return user


class EmailOutboxOut(BaseModel):
    id: int
    tenant_id: int | None
    to_email: str
    template: str
    subject: str
    locale: str
    status: str
    attempts: int
    last_error: str | None
    provider_name: str | None
    provider_message_id: str | None
    created_at: datetime
    sent_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class TestEmailRequest(BaseModel):
    to_email: EmailStr | None = None


@router.get("/status")
def email_status(db: Session = Depends(get_db), user: User = Depends(require_platform_admin)):
    provider = (settings.email_provider or "none").strip().lower()
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    counts = dict(db.query(EmailOutbox.status, func.count(EmailOutbox.id)).filter(EmailOutbox.created_at >= since).group_by(EmailOutbox.status).all())
    missing: list[str] = []
    if provider == "smtp":
        if not settings.smtp_host:
            missing.append("SMTP_HOST")
        if settings.smtp_username and not settings.smtp_password:
            missing.append("SMTP_PASSWORD")
    elif provider == "resend" and not settings.resend_api_key:
        missing.append("RESEND_API_KEY")
    from_domain = settings.email_from_address.split("@")[-1] if "@" in settings.email_from_address else None
    return {
        "provider": provider,
        "configured": is_configured(),
        "missing_settings": missing,
        "from_address": settings.email_from_address,
        "from_name": settings.email_from_name,
        "app_base_url": settings.app_base_url,
        "smtp_host": settings.smtp_host if provider == "smtp" else None,
        "smtp_port": settings.smtp_port if provider == "smtp" else None,
        "smtp_security": ("ssl" if settings.smtp_use_ssl else "starttls" if settings.smtp_use_tls else "none") if provider == "smtp" else None,
        "rate_limits": {"per_recipient_per_hour": settings.email_rate_limit_per_recipient_per_hour, "per_tenant_per_hour": settings.email_rate_limit_per_tenant_per_hour},
        "last_24h": {"sent": counts.get("sent", 0), "failed": counts.get("failed", 0), "queued": counts.get("queued", 0)},
        "dns": {
            "domain": from_domain,
            "spf": f'{from_domain} TXT "v=spf1 include:<provider-spf-include> ~all"' if from_domain else None,
            "dkim": "CNAME/TXT selector records as issued by the provider (Resend: three CNAMEs under resend._domainkey; SMTP relay: your relay's DKIM selector)",
            "dmarc": f'_dmarc.{from_domain} TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@{from_domain}; adkim=s; aspf=s"' if from_domain else None,
        },
    }


@router.get("/outbox", response_model=list[EmailOutboxOut])
def list_outbox(status_filter: str | None = None, limit: int = 50, db: Session = Depends(get_db), user: User = Depends(require_platform_admin)):
    query = db.query(EmailOutbox)
    if status_filter:
        query = query.filter(EmailOutbox.status == status_filter)
    return query.order_by(EmailOutbox.created_at.desc()).limit(max(1, min(limit, 200))).all()


@router.post("/test", response_model=EmailOutboxOut)
def send_test_email(payload: TestEmailRequest, request: Request, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(require_platform_admin)):
    """Sends a harmless test message to the caller's own address (or one
    they name). Hard-limited to 3/minute per client on top of the outbox
    rate limits so the endpoint cannot be used as a mail cannon."""
    enforce_rate_limit(request, "email_test", 3)
    to_email = str(payload.to_email or user.email)
    locale = user.locale or user.tenant_default_locale or "nl"
    subject, html, text = email_templates.test_message(locale, user.full_name, get_email_provider().name, email_link("/"))
    row, _ = queue_email(db, None, to_email=to_email, template="test", subject=subject, html_body=html, text_body=text, locale=locale, tenant_id=user.tenant_id)
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="email_test_sent", entity_type="email_outbox", entity_id=row.id or 0, after={"to_email": to_email, "status": row.status}, request_id=get_request_id()))
    db.commit()
    db.refresh(row)
    return row


@router.post("/outbox/{outbox_id}/retry", response_model=EmailOutboxOut)
def retry_failed(outbox_id: int, db: Session = Depends(get_db), user: User = Depends(require_platform_admin)):
    """Re-attempts a failed TEST message only. Other templates carry one-time
    links whose tokens were never stored (by design), so they cannot be
    re-sent from the log -- the originating action (reset, invite) must be
    repeated instead, which issues a fresh token."""
    row = db.get(EmailOutbox, outbox_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outbox entry not found")
    if row.status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed messages can be retried")
    if row.template != "test":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This message carried a one-time link and cannot be re-sent; repeat the original action instead")
    if not is_configured():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No email provider is configured")
    subject, html, text = email_templates.test_message(row.locale, user.full_name, get_email_provider().name, email_link("/"))
    row.attempts = 0
    deliver(db, row, OutboundEmail(to_email=row.to_email, subject=subject, html_body=html, text_body=text))
    db.refresh(row)
    return row
