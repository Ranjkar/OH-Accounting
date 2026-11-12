"""Phase 26: scheduled contract processing (activation, expiry, renewal
preparation, reminders).

`run_once(db)` is pure business logic, callable from a test or the admin
endpoint. `run_with_lock()` wraps it in a Postgres session-level advisory
lock so two backend processes (or an overlapping cron and the in-process
thread) can never process the same tick at once; `run_forever()` is the
daemon thread app.main starts when CONTRACTS_ENABLED and the interval > 0.

Deduplication is structural, not procedural: ContractReminder has UNIQUE
(contract_id, kind) and Contract.renews_contract_id is UNIQUE, so a crash
between "send" and "commit" or a double tick cannot produce a second
email or a second renewal draft.

No email leaves this module unless CONTRACTS_EMAIL_AUTOMATION_ENABLED is
true; when it is false, reminders are still recorded as `skipped_disabled`
so the state machine advances identically and nothing is sent retroactively
once the flag is flipped.
"""

import logging
import threading
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.contract import Contract, ContractReminder, ContractSigningInvitation
from app.models.enums import ContractStatus as S, SigningInvitationStatus
from app.services import contract_service as svc, contract_templates as tpl, email_templates
from app.services.email_service import queue_email

logger = logging.getLogger(__name__)

ADVISORY_LOCK_KEY = 260_026  # arbitrary, unique within this application


def _reminder(db: Session, contract: Contract, kind: str, today: date, status: str, outbox_id: int | None = None) -> bool:
    if db.query(ContractReminder.id).filter(ContractReminder.contract_id == contract.id, ContractReminder.kind == kind).first() is not None:
        return False
    db.add(ContractReminder(contract_id=contract.id, kind=kind, scheduled_for=today, status=status, email_outbox_id=outbox_id))
    db.flush()
    return True


def _automation_on() -> bool:
    return bool(settings.contracts_email_automation_enabled)


def run_once(db: Session, today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    now = datetime.now(timezone.utc)
    counts = {"invitations_expired": 0, "activated": 0, "expired": 0, "renewals_created": 0, "renewal_reminders": 0, "signing_reminders": 0, "errors": 0}

    # 1. Lapsed signing links.
    for inv in db.query(ContractSigningInvitation).filter(ContractSigningInvitation.status == SigningInvitationStatus.pending, ContractSigningInvitation.expires_at < now).all():
        inv.status = SigningInvitationStatus.expired
        counts["invitations_expired"] += 1
    db.commit()

    # 2. Signed agreements whose term has started.
    for contract in db.query(Contract).filter(Contract.status == S.signed, Contract.start_date <= today).all():
        contract.status = S.active
        contract.activated_at = now
        svc.record_event(db, contract, "activated", "system", None, {"start_date": contract.start_date.isoformat()})
        counts["activated"] += 1
    db.commit()

    # 3. Expiry (never auto-renews: an unsigned renewal is NOT acceptance).
    for contract in db.query(Contract).filter(Contract.status.in_([S.active, S.renewal_due]), Contract.end_date < today).all():
        try:
            contract.status = S.expired
            contract.expired_at = now
            svc.record_event(db, contract, "expired", "system", None, {"end_date": contract.end_date.isoformat()})
            outbox_id = None
            if _automation_on() and contract.signer_email:
                subject, html, txt = email_templates.contract_expired(contract.language, contract.company.name, contract.reference, tpl.format_date(contract.end_date, contract.language))
                row, _ = queue_email(db, None, to_email=contract.signer_email, template="contract_expired", subject=subject, html_body=html, text_body=txt, locale=contract.language, tenant_id=contract.tenant_id)
                outbox_id = row.id
            _reminder(db, contract, "expired", today, "sent" if outbox_id else "skipped_disabled", outbox_id)
            counts["expired"] += 1
            db.commit()
        except Exception:  # noqa: BLE001 -- one bad contract must not stop the tick
            logger.exception("Expiry processing failed for contract %s", contract.id)
            db.rollback()
            counts["errors"] += 1

    # 4. Renewal window: prepare the next agreement and remind.
    for contract in db.query(Contract).filter(Contract.status.in_([S.active, S.renewal_due]), Contract.renewal_disabled.is_(False)).all():
        try:
            conf = svc.get_settings(db, contract.tenant_id)
            days = sorted({int(d) for d in (conf.reminder_days or [60, 30, 14]) if int(d) > 0}, reverse=True)
            days_left = (contract.end_date - today).days
            if not days or days_left > days[0]:
                continue
            if contract.status == S.active:
                contract.status = S.renewal_due
                svc.record_event(db, contract, "renewal_due", "system", None, {"days_left": days_left})
            renewal, created = svc.create_renewal(db, contract, None)
            if created:
                counts["renewals_created"] += 1
            due = [d for d in days if days_left <= d]  # thresholds already crossed, largest first
            for d in due[:-1]:  # older thresholds crossed in the same tick: never send a burst
                _reminder(db, contract, f"renewal_{d}", today, "skipped_superseded")
            kind = f"renewal_{due[-1]}"
            if db.query(ContractReminder.id).filter(ContractReminder.contract_id == contract.id, ContractReminder.kind == kind).first() is None:
                outbox_id = None
                if _automation_on() and contract.signer_email:
                    subject, html, txt = email_templates.contract_renewal_upcoming(contract.language, contract.company.name, contract.reference, tpl.format_date(contract.end_date, contract.language), days_left)
                    row, _ = queue_email(db, None, to_email=contract.signer_email, template="contract_renewal_upcoming", subject=subject, html_body=html, text_body=txt, locale=contract.language, tenant_id=contract.tenant_id)
                    outbox_id = row.id
                _reminder(db, contract, kind, today, "sent" if outbox_id else "skipped_disabled", outbox_id)
                svc.record_event(db, contract, "renewal_reminder", "system", None, {"kind": kind, "email_queued": outbox_id is not None, "renewal_contract_id": renewal.id})
                counts["renewal_reminders"] += 1
            db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Renewal processing failed for contract %s", contract.id)
            db.rollback()
            counts["errors"] += 1

    # 5. Unsigned agreements: one reminder per invitation after N days (re-issues the link).
    for contract in db.query(Contract).filter(Contract.status.in_([S.sent, S.viewed])).all():
        try:
            conf = svc.get_settings(db, contract.tenant_id)
            pending = next((i for i in contract.invitations if i.status == SigningInvitationStatus.pending), None)
            if pending is None or (now - pending.created_at).days < conf.signing_reminder_days:
                continue
            kind = f"signing_reminder_{pending.id}"
            if db.query(ContractReminder.id).filter(ContractReminder.contract_id == contract.id, ContractReminder.kind == kind).first() is not None:
                continue
            if not _automation_on():
                _reminder(db, contract, kind, today, "skipped_disabled")
                db.commit()
                continue
            new_inv, _, queued = svc.resend(db, None, contract, None, reminder=True)
            _reminder(db, contract, kind, today, "sent" if queued else "failed", new_inv.email_outbox_id)
            counts["signing_reminders"] += 1
            db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Signing reminder failed for contract %s", contract.id)
            db.rollback()
            counts["errors"] += 1

    return counts


def run_with_lock(session_factory=None, today: date | None = None) -> dict[str, int] | None:
    """Returns None when another process holds the lock (skipped tick)."""
    db = (session_factory or SessionLocal)()
    try:
        if not db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar():
            logger.info("contract scheduler: another process holds the lock, skipping tick")
            return None
        try:
            return run_once(db, today)
        finally:
            db.rollback()
            db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
            db.commit()
    finally:
        db.close()


def run_forever(stop: threading.Event, interval_minutes: int) -> None:
    logger.info("contract scheduler thread started (every %d min)", interval_minutes)
    while not stop.is_set():
        try:
            result = run_with_lock()
            if result:
                logger.info("contract scheduler tick: %s", result)
        except Exception:  # noqa: BLE001 -- the thread must survive a DB hiccup
            logger.exception("contract scheduler tick failed")
        stop.wait(interval_minutes * 60)


def start_background_thread() -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=run_forever, args=(stop, settings.contracts_scheduler_interval_minutes), name="contract-scheduler", daemon=True).start()
    return stop
