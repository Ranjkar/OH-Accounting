"""Phase 26: contract lifecycle -- drafts, approval snapshots, signing
invitations, electronic signatures, renewals, cancellation/termination.

Every function here mutates the session it is given and NEVER commits
(callers own the transaction, same convention as email_service.queue_email),
with one exception: `sign()` commits, because the row lock it takes on the
contract must be released at a well-defined point and the signature must be
durable before any notification is queued.

Status machine (ContractStatus): see ALLOWED below. Terminal states are
EXPIRED, CANCELLED, TERMINATED. Only DRAFT contracts are editable; approval
freezes the terms into an immutable ContractVersion.
"""

import hashlib
import re
import json
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit_redaction import redact
from app.core.config import settings
from app.core.request_context import get_request_id
from app.core.security import generate_password_reset_token, hash_reset_token
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.contract import (
    Contract,
    ContractEvent,
    ContractSettings,
    ContractSignature,
    ContractSigningInvitation,
    ContractTemplate,
    ContractTemplateVersion,
    ContractVersion,
)
from app.models.enums import ContractStatus, ContractTemplateVersionStatus, ContractVersionKind, SigningInvitationStatus
from app.models.legal_form import Shareholder
from app.models.user import User
from app.services import contract_templates as tpl, email_templates, storage
from app.services.contract_pdf import render_contract_pdf
from app.services.email_service import link as email_link, queue_email
from app.services.signing_provider import SignatureRequest, get_signing_provider

logger = logging.getLogger(__name__)

S = ContractStatus
TERMINAL = {S.expired, S.cancelled, S.terminated}
ALLOWED: dict[str, set[ContractStatus]] = {
    "edit": {S.draft},
    "submit": {S.draft},
    "approve": {S.draft, S.pending_approval},
    "return_to_draft": {S.pending_approval, S.ready_to_send},
    "send": {S.ready_to_send},
    "resend": {S.sent, S.viewed},
    "sign": {S.sent, S.viewed},
    "cancel": {S.draft, S.pending_approval, S.ready_to_send, S.sent, S.viewed},
    "terminate": {S.signed, S.active, S.renewal_due},
    "renew": {S.signed, S.active, S.renewal_due, S.expired},
}
SIGNED_PDF_DOWNLOAD_GRACE_DAYS = 90


class ContractError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require(contract: Contract, action: str) -> None:
    if contract.status not in ALLOWED[action]:
        raise ContractError(409, f"Cannot {action.replace('_', ' ')} a contract in status {contract.status.value}")


def canonical_hash(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()


def record_event(db: Session, contract: Contract, event_type: str, actor_type: str, actor_user_id: int | None = None, data: dict | None = None) -> ContractEvent:
    event = ContractEvent(tenant_id=contract.tenant_id, contract_id=contract.id, event_type=event_type, actor_type=actor_type, actor_user_id=actor_user_id, data=redact(data))
    db.add(event)
    return event


def _audit(db: Session, user: User | None, action: str, contract: Contract, before: dict | None = None, after: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=contract.tenant_id, user_id=user.id if user else None, action=action, entity_type="contract", entity_id=contract.id,
        before=redact(before), after=redact(after), request_id=get_request_id(),
    ))


# ---- settings & templates ----


def get_settings(db: Session, tenant_id: int) -> ContractSettings:
    row = db.query(ContractSettings).filter(ContractSettings.tenant_id == tenant_id).first()
    if row is None:
        row = ContractSettings(tenant_id=tenant_id)
        db.add(row)
        db.flush()
    return row


def ensure_default_template(db: Session, tenant_id: int, user_id: int | None = None) -> ContractTemplate:
    template = db.query(ContractTemplate).filter(ContractTemplate.tenant_id == tenant_id, ContractTemplate.is_default.is_(True)).first()
    if template is None:
        template = ContractTemplate(tenant_id=tenant_id, name="Accounting services agreement (built-in)", is_default=True)
        db.add(template)
        db.flush()
        db.add(ContractTemplateVersion(
            template_id=template.id, version_no=1, content=tpl.DEFAULT_CONTENT, default_services=tpl.DEFAULT_SERVICES,
            created_by_user_id=user_id, change_note="Built-in starting template. Must be reviewed by a Dutch legal professional and approved by an administrator before production use.",
        ))
        db.flush()
    return template


def current_template_version(db: Session, tenant_id: int, user_id: int | None = None) -> ContractTemplateVersion:
    """The approved version of the tenant's default template, else its
    newest draft (a contract built from an unapproved template is itself
    still gated by contract approval before anything is sent)."""
    template = ensure_default_template(db, tenant_id, user_id)
    versions = db.query(ContractTemplateVersion).filter(ContractTemplateVersion.template_id == template.id).order_by(ContractTemplateVersion.version_no.desc()).all()
    approved = [v for v in versions if v.status == ContractTemplateVersionStatus.approved]
    return approved[0] if approved else versions[0]


def new_template_version(db: Session, tenant_id: int, user: User, content: dict, default_services: list, defaults: dict, change_note: str | None) -> ContractTemplateVersion:
    for lang in tpl.SUPPORTED_LANGUAGES:
        block = content.get(lang)
        if not isinstance(block, dict) or not block.get("title") or not isinstance(block.get("clauses"), list) or not block["clauses"]:
            raise ContractError(422, f"Template content for '{lang}' must have a title and at least one clause")
        for clause in block["clauses"]:
            if not clause.get("heading") or not clause.get("body"):
                raise ContractError(422, f"Every clause needs a heading and a body ('{lang}')")
    template = ensure_default_template(db, tenant_id, user.id)
    last = db.query(ContractTemplateVersion).filter(ContractTemplateVersion.template_id == template.id).order_by(ContractTemplateVersion.version_no.desc()).first()
    version = ContractTemplateVersion(
        template_id=template.id, version_no=(last.version_no + 1) if last else 1, content=content, default_services=default_services,
        default_monthly_fee=defaults.get("default_monthly_fee"), default_payment_terms_days=defaults.get("default_payment_terms_days"),
        default_notice_period_days=defaults.get("default_notice_period_days"), default_term_months=defaults.get("default_term_months") or 12,
        created_by_user_id=user.id, change_note=change_note,
    )
    db.add(version)
    db.flush()
    db.add(AuditLog(tenant_id=tenant_id, user_id=user.id, action="create", entity_type="contract_template_version", entity_id=version.id, after={"version_no": version.version_no}, request_id=get_request_id()))
    return version


def approve_template_version(db: Session, version: ContractTemplateVersion, user: User) -> None:
    if version.status == ContractTemplateVersionStatus.approved:
        raise ContractError(409, "This template version is already approved")
    for other in db.query(ContractTemplateVersion).filter(ContractTemplateVersion.template_id == version.template_id, ContractTemplateVersion.status == ContractTemplateVersionStatus.approved).all():
        other.status = ContractTemplateVersionStatus.retired
    version.status = ContractTemplateVersionStatus.approved
    version.approved_by_user_id = user.id
    version.approved_at = _now()
    db.add(AuditLog(tenant_id=version.template.tenant_id, user_id=user.id, action="approve", entity_type="contract_template_version", entity_id=version.id, after={"version_no": version.version_no}, request_id=get_request_id()))


# ---- drafts ----


def _generate_reference(db: Session) -> str:
    for _ in range(10):
        candidate = f"OHA-{date.today().year}-{secrets.token_hex(3).upper()}"
        if db.query(Contract.id).filter(Contract.reference == candidate).first() is None:
            return candidate
    raise RuntimeError("Could not generate a unique contract reference")


def _term_end(start: date, months: int) -> date:
    return start + relativedelta(months=months) - timedelta(days=1)


def _default_representative(db: Session, company: Company) -> str | None:
    director = (
        db.query(Shareholder)
        .filter(Shareholder.company_id == company.id, Shareholder.is_director.is_(True), Shareholder.effective_to.is_(None))
        .order_by(Shareholder.id)
        .first()
    )
    return director.name if director else None


def create_draft(
    db: Session,
    company: Company,
    *,
    created_by: User | None,
    source: str = "manual",
    language: str | None = None,
    start_date: date | None = None,
    template_version: ContractTemplateVersion | None = None,
    renews: Contract | None = None,
    copy_terms_from: Contract | None = None,
) -> Contract:
    conf = get_settings(db, company.tenant_id)
    template_version = template_version or current_template_version(db, company.tenant_id, created_by.id if created_by else None)
    lang = tpl.normalize_language(language or conf.default_language)
    start = start_date or date.today()
    months = template_version.default_term_months or 12
    src = copy_terms_from
    contract = Contract(
        tenant_id=company.tenant_id, company_id=company.id, reference=_generate_reference(db), language=lang,
        template_version_id=template_version.id, start_date=start, end_date=_term_end(start, months), term_months=months,
        services=src.services if src else [{"code": s["code"], "label": s.get(lang) or s.get("en")} for s in (template_version.default_services or [])],
        monthly_fee=src.monthly_fee if src else template_version.default_monthly_fee,
        fee_description=src.fee_description if src else None,
        payment_terms_days=src.payment_terms_days if src else template_version.default_payment_terms_days,
        notice_period_days=src.notice_period_days if src else template_version.default_notice_period_days,
        signer_name=(src.signer_name if src else None) or _default_representative(db, company),
        signer_email=(src.signer_email if src else None) or company.email,
        signer_title=src.signer_title if src else None,
        renews_contract_id=renews.id if renews else None,
        created_by_user_id=created_by.id if created_by else None, created_source=source,
    )
    db.add(contract)
    db.flush()
    record_event(db, contract, "created", "user" if created_by else "system", created_by.id if created_by else None, {"source": source, "renews_contract_id": contract.renews_contract_id})
    if created_by is not None:
        _audit(db, created_by, "create", contract, after={"reference": contract.reference, "company_id": company.id, "source": source})
    return contract


def auto_create_for_new_company(db: Session, company: Company, user: User) -> Contract | None:
    """Hook for both company-creation paths. Never raises: a failure here
    is logged and must not roll back the company registration itself."""
    if not settings.contracts_enabled:
        return None
    try:
        with db.begin_nested():  # savepoint: a failure here rolls back only the draft
            if not get_settings(db, company.tenant_id).auto_create_on_company_create:
                return None
            return create_draft(db, company, created_by=user, source="company_created")
    except Exception:  # noqa: BLE001 -- company onboarding must keep working
        logger.exception("Automatic draft agreement for company %s failed", company.id)
        return None


EDITABLE_FIELDS = ("language", "start_date", "term_months", "services", "monthly_fee", "fee_description", "payment_terms_days", "notice_period_days", "custom_clauses", "signer_name", "signer_email", "signer_title")


def update_draft(db: Session, contract: Contract, user: User, updates: dict) -> None:
    _require(contract, "edit")
    updates = {k: v for k, v in updates.items() if k in EDITABLE_FIELDS}
    if "language" in updates:
        updates["language"] = tpl.normalize_language(updates["language"])
    before = {k: getattr(contract, k) for k in updates}
    for key, value in updates.items():
        setattr(contract, key, value)
    contract.end_date = _term_end(contract.start_date, contract.term_months)
    record_event(db, contract, "terms_updated", "user", user.id, {"fields": sorted(updates)})
    _audit(db, user, "correct", contract, before={k: str(v) for k, v in before.items()}, after={k: str(v) for k, v in updates.items()})


# ---- document content ----


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _substitute(text: str, values: dict) -> str:
    """Plain {name} substitution for template/custom-clause text -- deliberately
    NOT str.format_map(). Python's format mini-language allows attribute and
    index access inside a placeholder (e.g. "{x.__class__.__mro__}"), which
    would let clause text reach into object internals. custom_clauses is only
    ever editor-authored for the editor's own tenant's own draft, but there is
    no reason to carry that capability at all -- a bare regex substitution has
    none of it, and leaves an unknown "{placeholder}" untouched rather than
    raising, matching the previous fallback behaviour."""
    return _PLACEHOLDER_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)


def build_content(db: Session, contract: Contract) -> dict:
    company = contract.company or db.get(Company, contract.company_id)
    lang = tpl.normalize_language(contract.language)
    version = db.get(ContractTemplateVersion, contract.template_version_id) if contract.template_version_id else None
    block = (version.content if version else tpl.DEFAULT_CONTENT).get(lang) or tpl.DEFAULT_CONTENT[lang]
    clauses_src = contract.custom_clauses or block["clauses"]
    representative = " ".join(x for x in (contract.signer_name, f"({contract.signer_title})" if contract.signer_title else None) if x) or None
    services = [s["label"] for s in contract.services]
    if contract.monthly_fee is not None:
        fee_text = tpl.label(lang, "fee_monthly", amount=tpl.format_money(Decimal(contract.monthly_fee), lang))
    else:
        fee_text = contract.fee_description or tpl.label(lang, "fee_unset")
    not_set = tpl.label(lang, "not_set")
    payment_text = tpl.label(lang, "days", n=contract.payment_terms_days) if contract.payment_terms_days is not None else not_set
    notice_text = tpl.label(lang, "days", n=contract.notice_period_days) if contract.notice_period_days is not None else not_set
    values = dict(
        provider_name=tpl.PROVIDER_NAME, client_name=company.name, client_kvk=company.kvk_number or "-", client_vat=company.vat_number or "-",
        client_address=company.address or "-", client_representative=representative or "-", start_date=tpl.format_date(contract.start_date, lang),
        end_date=tpl.format_date(contract.end_date, lang), term_months=contract.term_months, services=", ".join(services) or tpl.label(lang, "none"),
        fee=fee_text, payment_terms_days=contract.payment_terms_days if contract.payment_terms_days is not None else not_set,
        notice_period_days=contract.notice_period_days if contract.notice_period_days is not None else not_set, reference=contract.reference,
    )
    return {
        "schema": 1,
        "reference": contract.reference,
        "language": lang,
        "title": block["title"],
        "provider": {"name": tpl.PROVIDER_NAME},
        "client": {"name": company.name, "kvk_number": company.kvk_number, "vat_number": company.vat_number, "address": company.address, "representative": representative},
        "term": {"start_date": contract.start_date.isoformat(), "end_date": contract.end_date.isoformat(), "months": contract.term_months,
                 "text": tpl.label(lang, "term_value", months=contract.term_months, start=values["start_date"], end=values["end_date"])},
        "services": [dict(s) for s in contract.services],
        "fees": {"monthly_fee": str(contract.monthly_fee) if contract.monthly_fee is not None else None, "currency": contract.currency, "fee_description": contract.fee_description,
                 "fee_text": fee_text, "payment_terms_days": contract.payment_terms_days, "payment_terms_text": payment_text,
                 "notice_period_days": contract.notice_period_days, "notice_period_text": notice_text},
        "clauses": [{"key": c.get("key"), "heading": _substitute(str(c["heading"]), values), "body": _substitute(str(c["body"]), values)} for c in clauses_src],
        "signer": {"name": contract.signer_name, "email": contract.signer_email, "title": contract.signer_title},
        "consent_text_template": tpl.label(lang, "consent_text", name="{name}", client_name=company.name),
        "template_version_id": contract.template_version_id,
        "renews_reference": contract.renews_contract_id and db.get(Contract, contract.renews_contract_id).reference,
    }


def preview_pdf(db: Session, contract: Contract) -> bytes:
    return render_contract_pdf(build_content(db, contract))


def _store_version(db: Session, contract: Contract, kind: ContractVersionKind, content: dict, pdf: bytes, user_id: int | None) -> ContractVersion:
    last = db.query(ContractVersion).filter(ContractVersion.contract_id == contract.id).order_by(ContractVersion.version_no.desc()).first()
    version = ContractVersion(
        contract_id=contract.id, version_no=(last.version_no + 1) if last else 1, kind=kind, content=content, content_hash=canonical_hash(content),
        pdf_storage_path="", pdf_sha256=hashlib.sha256(pdf).hexdigest(), created_by_user_id=user_id,
    )
    db.add(version)
    db.flush()
    version.pdf_storage_path = storage.save(contract.tenant_id, contract.company_id, version.id, f"contract-{contract.reference}-v{version.version_no}.pdf", pdf)
    return version


def version_pdf_bytes(version: ContractVersion) -> bytes:
    return storage.read(version.pdf_storage_path)


def verify_version(version: ContractVersion) -> dict:
    """Recomputes both hashes from what is actually stored."""
    pdf_ok = hashlib.sha256(version_pdf_bytes(version)).hexdigest() == version.pdf_sha256
    content_ok = canonical_hash(version.content) == version.content_hash
    return {"pdf_hash_valid": pdf_ok, "content_hash_valid": content_ok, "valid": pdf_ok and content_ok}


# ---- approval ----


def validate_for_approval(contract: Contract) -> list[str]:
    problems = []
    if not contract.signer_name:
        problems.append("signer_name")
    if not contract.signer_email:
        problems.append("signer_email")
    if not contract.services:
        problems.append("services")
    if contract.monthly_fee is None and not contract.fee_description:
        problems.append("monthly_fee")
    if contract.payment_terms_days is None:
        problems.append("payment_terms_days")
    if contract.notice_period_days is None:
        problems.append("notice_period_days")
    if contract.end_date <= contract.start_date:
        problems.append("term")
    return problems


def submit(db: Session, contract: Contract, user: User) -> None:
    _require(contract, "submit")
    contract.status = S.pending_approval
    contract.submitted_at = _now()
    record_event(db, contract, "submitted_for_approval", "user", user.id)
    _audit(db, user, "submit", contract, after={"status": contract.status.value})


def approve(db: Session, contract: Contract, user: User) -> ContractVersion:
    _require(contract, "approve")
    missing = validate_for_approval(contract)
    if missing:
        raise ContractError(422, "Contract is not complete; set: " + ", ".join(missing))
    content = build_content(db, contract)
    version = _store_version(db, contract, ContractVersionKind.approved, content, render_contract_pdf(content), user.id)
    contract.status = S.ready_to_send
    contract.approved_at = _now()
    contract.approved_by_user_id = user.id
    record_event(db, contract, "approved", "user", user.id, {"version_id": version.id, "pdf_sha256": version.pdf_sha256})
    _audit(db, user, "approve", contract, after={"status": contract.status.value, "version_id": version.id, "pdf_sha256": version.pdf_sha256})
    return version


def return_to_draft(db: Session, contract: Contract, user: User, reason: str | None = None) -> None:
    _require(contract, "return_to_draft")
    before = contract.status.value
    contract.status = S.draft
    contract.approved_at = None
    contract.approved_by_user_id = None
    record_event(db, contract, "returned_to_draft", "user", user.id, {"from": before, "reason": reason})
    _audit(db, user, "return_to_draft", contract, before={"status": before}, after={"status": "DRAFT", "reason": reason})


# ---- sending & invitations ----


def _latest_approved_version(db: Session, contract: Contract) -> ContractVersion:
    version = db.query(ContractVersion).filter(ContractVersion.contract_id == contract.id, ContractVersion.kind == ContractVersionKind.approved).order_by(ContractVersion.version_no.desc()).first()
    if version is None:
        raise ContractError(409, "Contract has no approved document version")
    return version


def _issue_invitation(db: Session, background: BackgroundTasks | None, contract: Contract, actor: User | None, *, reminder: bool = False) -> tuple[ContractSigningInvitation, str, bool]:
    conf = get_settings(db, contract.tenant_id)
    version = _latest_approved_version(db, contract)
    now = _now()
    for old in db.query(ContractSigningInvitation).filter(ContractSigningInvitation.contract_id == contract.id, ContractSigningInvitation.status == SigningInvitationStatus.pending).all():
        old.status = SigningInvitationStatus.revoked
        old.revoked_at = now
    raw_token, token_hash = generate_password_reset_token()
    invitation = ContractSigningInvitation(
        tenant_id=contract.tenant_id, contract_id=contract.id, contract_version_id=version.id, signer_name=contract.signer_name, signer_email=contract.signer_email.lower(),
        token_hash=token_hash, is_renewal=contract.renews_contract_id is not None, created_by_user_id=actor.id if actor else None,
        expires_at=now + timedelta(days=conf.signing_link_expire_days),
    )
    db.add(invitation)
    db.flush()
    sender = actor.full_name if actor else tpl.PROVIDER_NAME
    link = email_link(f"/sign/{raw_token}")
    if reminder:
        subject, html, text = email_templates.contract_reminder(contract.language, contract.company.name, contract.reference, link, tpl.format_date(invitation.expires_at.date(), contract.language))
        template_name = "contract_reminder"
    else:
        previous = db.get(Contract, contract.renews_contract_id) if contract.renews_contract_id else None
        subject, html, text = email_templates.contract_invitation(
            contract.language, sender, contract.company.name, contract.reference, link, conf.signing_link_expire_days,
            renewal=previous is not None, end_date=tpl.format_date(previous.end_date, contract.language) if previous else "",
        )
        template_name = "contract_renewal_signing" if previous else "contract_invitation"
    row, will_send = queue_email(db, background, to_email=invitation.signer_email, template=template_name, subject=subject, html_body=html, text_body=text, locale=contract.language, tenant_id=contract.tenant_id)
    invitation.email_outbox_id = row.id
    return invitation, raw_token, will_send


def send(db: Session, background: BackgroundTasks | None, contract: Contract, user: User) -> tuple[ContractSigningInvitation, str, bool]:
    _require(contract, "send")
    invitation, raw_token, will_send = _issue_invitation(db, background, contract, user)
    contract.status = S.sent
    contract.sent_at = _now()
    record_event(db, contract, "sent", "user", user.id, {"invitation_id": invitation.id, "email_queued": will_send, "signer_email": invitation.signer_email})
    _audit(db, user, "send", contract, after={"status": "SENT", "invitation_id": invitation.id, "email_queued": will_send})
    return invitation, raw_token, will_send


def resend(db: Session, background: BackgroundTasks | None, contract: Contract, user: User | None, *, reminder: bool = False) -> tuple[ContractSigningInvitation, str, bool]:
    _require(contract, "resend")
    invitation, raw_token, will_send = _issue_invitation(db, background, contract, user, reminder=reminder)
    record_event(db, contract, "reminder_sent" if reminder else "resent", "user" if user else "system", user.id if user else None, {"invitation_id": invitation.id, "email_queued": will_send})
    if user is not None:
        _audit(db, user, "resend", contract, after={"invitation_id": invitation.id, "email_queued": will_send})
    return invitation, raw_token, will_send


# ---- signer-side (token) ----


def lookup_invitation(db: Session, raw_token: str, *, for_update: bool = False) -> ContractSigningInvitation:
    """Resolves a raw signing token. 404 unknown, 410 expired/revoked. A
    USED invitation is returned (the signer may still view/download the
    signed agreement for a grace period); callers decide what it may do."""
    if not raw_token or len(raw_token) > 128:
        raise ContractError(404, "Unknown signing link")
    query = db.query(ContractSigningInvitation).filter(ContractSigningInvitation.token_hash == hash_reset_token(raw_token))
    if for_update:
        query = query.with_for_update()
    invitation = query.first()
    if invitation is None:
        raise ContractError(404, "Unknown signing link")
    now = _now()
    if invitation.status == SigningInvitationStatus.revoked:
        raise ContractError(410, "This signing link has been replaced by a newer one; please use the most recent email")
    if invitation.status == SigningInvitationStatus.used:
        if invitation.used_at and now > invitation.used_at + timedelta(days=SIGNED_PDF_DOWNLOAD_GRACE_DAYS):
            raise ContractError(410, "This signing link has expired")
        return invitation
    if invitation.expires_at < now or invitation.status == SigningInvitationStatus.expired:
        if invitation.status == SigningInvitationStatus.pending:
            invitation.status = SigningInvitationStatus.expired
            db.commit()  # bookkeeping only; persisted even though the request itself fails (same as company invitation accept)
        raise ContractError(410, "This signing link has expired; ask your accountant for a new one")
    return invitation


def view(db: Session, raw_token: str) -> tuple[Contract, ContractSigningInvitation, ContractVersion]:
    invitation = lookup_invitation(db, raw_token)
    contract = db.get(Contract, invitation.contract_id)
    if contract.status in (S.cancelled, S.terminated):
        raise ContractError(410, "This agreement has been withdrawn")
    if invitation.status == SigningInvitationStatus.pending:
        now = _now()
        if invitation.first_viewed_at is None:
            invitation.first_viewed_at = now
            record_event(db, contract, "viewed", "signer", None, {"invitation_id": invitation.id})
        if contract.status == S.sent:
            contract.status = S.viewed
            contract.viewed_at = now
    version = db.get(ContractVersion, invitation.contract_version_id)
    return contract, invitation, version


def signer_download_version(db: Session, raw_token: str) -> ContractVersion:
    invitation = lookup_invitation(db, raw_token)
    contract = db.get(Contract, invitation.contract_id)
    if contract.signature and contract.signature.signed_version_id:
        return db.get(ContractVersion, contract.signature.signed_version_id)
    if contract.status in (S.cancelled, S.terminated):
        raise ContractError(410, "This agreement has been withdrawn")
    return db.get(ContractVersion, invitation.contract_version_id)


def _normalize_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def sign(
    db: Session,
    background: BackgroundTasks | None,
    raw_token: str,
    *,
    typed_name: str,
    typed_email: str,
    consent: bool,
    ip_address: str | None,
    user_agent: str | None,
) -> ContractSignature:
    """Commits. Concurrency: the contract row is locked FOR UPDATE for the
    duration, and contract_signatures.contract_id is UNIQUE, so two
    simultaneous sign requests cannot both succeed."""
    if not consent:
        raise ContractError(422, "You must confirm that you agree to sign electronically")
    typed_name = " ".join((typed_name or "").split())
    if len(typed_name) < 2:
        raise ContractError(422, "Enter your full legal name")
    invitation = lookup_invitation(db, raw_token, for_update=True)
    if invitation.status != SigningInvitationStatus.pending:
        raise ContractError(409, "This agreement has already been signed")
    contract = db.query(Contract).filter(Contract.id == invitation.contract_id).with_for_update().one()
    if contract.signature is not None or contract.status not in ALLOWED["sign"]:
        raise ContractError(409, "This agreement can no longer be signed" if contract.status in TERMINAL else "This agreement has already been signed")
    if (typed_email or "").strip().lower() != invitation.signer_email:
        raise ContractError(403, "The email address does not match the address this agreement was sent to")
    if _normalize_name(typed_name) != _normalize_name(invitation.signer_name):
        raise ContractError(422, "The name entered does not match the authorised representative named in the agreement")

    version = db.get(ContractVersion, invitation.contract_version_id)
    now = _now()
    consent_text = version.content["consent_text_template"].replace("{name}", typed_name)
    result = get_signing_provider().sign(SignatureRequest(contract.reference, version.pdf_sha256, typed_name, invitation.signer_email, consent_text))
    signature = ContractSignature(
        contract_id=contract.id, invitation_id=invitation.id, contract_version_id=version.id, signer_name_typed=typed_name, signer_email=invitation.signer_email,
        consent_text=consent_text, consent_given_at=now, signed_at=now, signing_method=result.signing_method, provider_name=result.provider_name,
        provider_reference=result.provider_reference, document_sha256=version.pdf_sha256, ip_address=(ip_address or None) and ip_address[:64], user_agent=(user_agent or None) and user_agent[:255],
    )
    db.add(signature)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ContractError(409, "This agreement has already been signed") from exc

    evidence = {
        "signer_name_typed": typed_name, "signer_email": invitation.signer_email, "signed_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"), "consent_text": consent_text,
        "signing_method": result.signing_method, "provider_name": result.provider_name, "assurance_level": result.assurance_level, "document_sha256": version.pdf_sha256,
        "ip_address": signature.ip_address,
    }
    signed_content = dict(version.content, signature=evidence)
    signed_version = _store_version(db, contract, ContractVersionKind.signed, signed_content, render_contract_pdf(signed_content, evidence), None)
    signature.signed_version_id = signed_version.id
    invitation.status = SigningInvitationStatus.used
    invitation.used_at = now
    contract.status = S.signed
    contract.signed_at = now
    if contract.start_date <= date.today():
        contract.status = S.active
        contract.activated_at = now
    record_event(db, contract, "signed", "signer", None, {"signature_id": signature.id, "signed_version_id": signed_version.id, "signed_pdf_sha256": signed_version.pdf_sha256, "signing_method": result.signing_method})
    if contract.status == S.active:
        record_event(db, contract, "activated", "system", None, {"start_date": contract.start_date.isoformat()})
    db.add(AuditLog(tenant_id=contract.tenant_id, user_id=None, action="sign", entity_type="contract", entity_id=contract.id,
                    after={"signer_email": invitation.signer_email, "signed_version_id": signed_version.id, "pdf_sha256": signed_version.pdf_sha256}, request_id=get_request_id()))
    db.commit()
    _notify_signed(db, background, contract, signature, raw_token)
    db.commit()
    return signature


def _notify_signed(db: Session, background: BackgroundTasks | None, contract: Contract, signature: ContractSignature, raw_token: str) -> None:
    if not settings.contracts_email_automation_enabled:
        record_event(db, contract, "notification_skipped", "system", None, {"kind": "signed", "reason": "CONTRACTS_EMAIL_AUTOMATION_ENABLED is false"})
        return
    conf = get_settings(db, contract.tenant_id)
    signed_at = signature.signed_at.strftime("%Y-%m-%d %H:%M UTC")
    subject, html, text = email_templates.contract_signed(contract.language, contract.company.name, contract.reference, signature.signer_name_typed, signed_at, email_link(f"/sign/{raw_token}"))
    queue_email(db, background, to_email=signature.signer_email, template="contract_signed", subject=subject, html_body=html, text_body=text, locale=contract.language, tenant_id=contract.tenant_id)
    admin_email = conf.notification_email or (db.get(User, contract.approved_by_user_id).email if contract.approved_by_user_id else None)
    if admin_email:
        subject, html, text = email_templates.contract_signed("nl" if conf.default_language == "nl" else "en", contract.company.name, contract.reference, signature.signer_name_typed, signed_at, email_link(f"/contracts/{contract.id}"))
        queue_email(db, background, to_email=admin_email, template="contract_signed", subject=subject, html_body=html, text_body=text, locale=conf.default_language, tenant_id=contract.tenant_id)
    record_event(db, contract, "notification_sent", "system", None, {"kind": "signed"})


# ---- closure ----


def _notify_closed(db: Session, background: BackgroundTasks | None, contract: Contract, state: str, reason: str | None) -> None:
    if not settings.contracts_email_automation_enabled or not contract.signer_email or contract.sent_at is None:
        return
    subject, html, text = email_templates.contract_closed(contract.language, contract.company.name, contract.reference, state, reason)
    queue_email(db, background, to_email=contract.signer_email, template="contract_closed", subject=subject, html_body=html, text_body=text, locale=contract.language, tenant_id=contract.tenant_id)


def cancel(db: Session, background: BackgroundTasks | None, contract: Contract, user: User, reason: str | None) -> None:
    _require(contract, "cancel")
    before = contract.status.value
    now = _now()
    for inv in contract.invitations:
        if inv.status == SigningInvitationStatus.pending:
            inv.status = SigningInvitationStatus.revoked
            inv.revoked_at = now
    contract.status = S.cancelled
    contract.cancelled_at = now
    contract.closure_reason = reason
    record_event(db, contract, "cancelled", "user", user.id, {"from": before, "reason": reason})
    _audit(db, user, "cancel", contract, before={"status": before}, after={"status": "CANCELLED", "reason": reason})
    _notify_closed(db, background, contract, "cancelled", reason)


def terminate(db: Session, background: BackgroundTasks | None, contract: Contract, user: User, reason: str | None, effective_date: date | None) -> None:
    _require(contract, "terminate")
    before = contract.status.value
    contract.status = S.terminated
    contract.terminated_at = _now()
    contract.termination_effective_date = effective_date or date.today()
    contract.closure_reason = reason
    contract.renewal_disabled = True
    contract.renewal_disabled_reason = contract.renewal_disabled_reason or "terminated"
    record_event(db, contract, "terminated", "user", user.id, {"from": before, "reason": reason, "effective_date": contract.termination_effective_date.isoformat()})
    _audit(db, user, "terminate", contract, before={"status": before}, after={"status": "TERMINATED", "reason": reason, "effective_date": str(contract.termination_effective_date)})
    _notify_closed(db, background, contract, "terminated", reason)


def set_non_renewal(db: Session, contract: Contract, user: User, disabled: bool, reason: str | None) -> None:
    if contract.status in TERMINAL:
        raise ContractError(409, f"Contract is {contract.status.value}")
    contract.renewal_disabled = disabled
    contract.renewal_disabled_reason = reason if disabled else None
    record_event(db, contract, "non_renewal_set" if disabled else "non_renewal_cleared", "user", user.id, {"reason": reason})
    _audit(db, user, "non_renewal" if disabled else "renewal_enabled", contract, after={"renewal_disabled": disabled, "reason": reason})


# ---- renewals ----


def existing_renewal(db: Session, contract: Contract) -> Contract | None:
    return db.query(Contract).filter(Contract.renews_contract_id == contract.id).first()


def create_renewal(db: Session, contract: Contract, user: User | None) -> tuple[Contract, bool]:
    """Idempotent: returns (renewal, created). The UNIQUE constraint on
    renews_contract_id is the race guard; the pre-check is the fast path."""
    _require(contract, "renew")
    if contract.renewal_disabled and user is None:
        raise ContractError(409, "Renewal has been disabled for this contract")
    existing = existing_renewal(db, contract)
    if existing is not None:
        return existing, False
    company = contract.company or db.get(Company, contract.company_id)
    try:
        with db.begin_nested():
            renewal = create_draft(
                db, company, created_by=user, source="renewal", language=contract.language, start_date=contract.end_date + timedelta(days=1),
                template_version=current_template_version(db, contract.tenant_id, user.id if user else None), renews=contract, copy_terms_from=contract,
            )
    except IntegrityError:
        return existing_renewal(db, contract), False
    record_event(db, contract, "renewal_prepared", "user" if user else "system", user.id if user else None, {"renewal_contract_id": renewal.id, "renewal_reference": renewal.reference})
    return renewal, True
