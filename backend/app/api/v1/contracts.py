"""Phase 26: contract administration (authenticated, tenant-scoped) and the
public token-based signing portal.

Route-ordering note: every literal path ("/settings", "/templates/...",
"/sign/{token}", "/scheduler/run") is registered BEFORE "/{contract_id}" so
Starlette never tries to parse "settings" as an integer id.

Authorisation: reads require company access (require_company_access, which
enforces tenancy for every role); drafting is editor-level; approval,
sending, cancellation, termination, templates and settings are admin-level.
The signing routes are unauthenticated by design: possession of the secret
token (hash-only storage, time-limited, single-use for signing) is the
credential, and they are rate-limited per client.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import ADMIN_ROLES, get_current_user, require_admin, require_company_access, require_editor
from app.core.rate_limit import enforce as enforce_rate_limit
from app.core.request_context import get_request_id
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.contract import Contract, ContractSigningInvitation, ContractTemplateVersion, ContractVersion
from app.models.email_outbox import EmailOutbox
from app.models.enums import ContractStatus as S, SigningInvitationStatus
from app.models.user import User
from app.schemas.contract import (
    ContractCreate,
    ContractDetailOut,
    ContractOut,
    ContractUpdate,
    ContractVersionOut,
    EventOut,
    InvitationOut,
    NonRenewalBody,
    ReasonBody,
    RenewalResult,
    SendResult,
    SettingsOut,
    SettingsUpdate,
    SignBody,
    SigningPageOut,
    TemplateVersionCreate,
    TemplateVersionOut,
    TerminateBody,
)
from app.services import contract_scheduler, contract_service as svc, contract_templates as tpl
from app.services.email_service import link as email_link

router = APIRouter(prefix="/contracts", tags=["contracts"])

ASSURANCE_NOTICE = {
    "nl": "U ondertekent met een gewone elektronische handtekening (eIDAS art. 3(10)): toegang via de e-maillink, uw ingevoerde naam en uw uitdrukkelijke instemming worden als bewijs vastgelegd. Dit is geen gekwalificeerde elektronische handtekening.",
    "en": "You sign with a simple electronic signature (eIDAS art. 3(10)): access via the emailed link, your typed name and your explicit consent are recorded as evidence. This is not a qualified electronic signature.",
}


def _feature_enabled() -> None:
    if not settings.contracts_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contracts feature is not enabled (CONTRACTS_ENABLED)")


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except svc.ContractError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _get_contract_or_404(db: Session, user: User, contract_id: int, *, for_update: bool = False) -> Contract:
    query = db.query(Contract).filter(Contract.id == contract_id, Contract.tenant_id == user.tenant_id)
    if for_update:
        query = query.with_for_update()
    contract = query.first()
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    require_company_access(contract.company_id, user, db)
    return contract


def _signing_status(contract: Contract) -> str:
    if contract.signature is not None:
        return "signed"
    if contract.status in (S.cancelled, S.terminated):
        return "withdrawn"
    if contract.status == S.viewed:
        return "viewed"
    if contract.status == S.sent:
        pending = any(i.status == SigningInvitationStatus.pending and i.expires_at > datetime.now(timezone.utc) for i in contract.invitations)
        return "awaiting" if pending else "expired"
    return "not_sent"


def _out(db: Session, contract: Contract) -> ContractOut:
    out = ContractOut.model_validate(contract)
    out.company_name = contract.company.name if contract.company else None
    out.signing_status = _signing_status(contract)
    out.days_until_expiry = (contract.end_date - date.today()).days if contract.status in (S.active, S.renewal_due, S.signed) else None
    renewal = svc.existing_renewal(db, contract)
    out.renewal_contract_id = renewal.id if renewal else None
    return out


def _detail(db: Session, contract: Contract) -> ContractDetailOut:
    base = _out(db, contract)
    outbox_status = {row.id: row.status for row in db.query(EmailOutbox).filter(EmailOutbox.id.in_([i.email_outbox_id for i in contract.invitations if i.email_outbox_id] or [0])).all()}
    invitations = []
    for inv in contract.invitations:
        item = InvitationOut.model_validate(inv)
        item.email_status = outbox_status.get(inv.email_outbox_id)
        invitations.append(item)
    actor_ids = {e.actor_user_id for e in contract.events if e.actor_user_id}
    actors = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(actor_ids or [0])).all()}
    events = []
    for e in contract.events:
        item = EventOut.model_validate(e)
        item.actor_name = actors.get(e.actor_user_id)
        events.append(item)
    renewal = svc.existing_renewal(db, contract)
    previous = db.get(Contract, contract.renews_contract_id) if contract.renews_contract_id else None
    return ContractDetailOut(
        **base.model_dump(), versions=[ContractVersionOut.model_validate(v) for v in contract.versions], invitations=invitations,
        signature=contract.signature, events=events, approval_missing=svc.validate_for_approval(contract),
        renews_reference=previous.reference if previous else None, renewal_reference=renewal.reference if renewal else None,
    )


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "no-store"})


# ---- settings (admin) ----


@router.get("/settings", response_model=SettingsOut, dependencies=[Depends(_feature_enabled)])
def get_settings(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    conf = svc.get_settings(db, user.tenant_id)
    db.commit()
    return _settings_out(conf)


def _settings_out(conf) -> SettingsOut:
    return SettingsOut(
        reminder_days=list(conf.reminder_days or []), signing_link_expire_days=conf.signing_link_expire_days, signing_reminder_days=conf.signing_reminder_days,
        auto_create_on_company_create=conf.auto_create_on_company_create, default_language=conf.default_language, notification_email=conf.notification_email,
        reply_to_email=conf.reply_to_email, feature_enabled=settings.contracts_enabled, email_automation_enabled=settings.contracts_email_automation_enabled,
        signing_provider=settings.contracts_signing_provider,
    )


@router.put("/settings", response_model=SettingsOut, dependencies=[Depends(_feature_enabled)])
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    conf = svc.get_settings(db, user.tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if "reminder_days" in updates and updates["reminder_days"] is not None:
        days = sorted({int(d) for d in updates["reminder_days"] if 1 <= int(d) <= 365}, reverse=True)
        if not days:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="reminder_days needs at least one value between 1 and 365")
        updates["reminder_days"] = days
    if "default_language" in updates and updates["default_language"] not in tpl.SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="default_language must be nl or en")
    before = {k: getattr(conf, k) for k in updates}
    for key, value in updates.items():
        setattr(conf, key, value)
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="correct", entity_type="contract_settings", entity_id=conf.id, before={k: str(v) for k, v in before.items()}, after={k: str(v) for k, v in updates.items()}, request_id=get_request_id()))
    db.commit()
    db.refresh(conf)
    return _settings_out(conf)


# ---- templates (admin) ----


@router.get("/templates", response_model=list[TemplateVersionOut], dependencies=[Depends(_feature_enabled)])
def list_template_versions(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    template = svc.ensure_default_template(db, user.tenant_id, user.id)
    db.commit()
    return db.query(ContractTemplateVersion).filter(ContractTemplateVersion.template_id == template.id).order_by(ContractTemplateVersion.version_no.desc()).all()


@router.post("/templates", response_model=TemplateVersionOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(_feature_enabled)])
def create_template_version(payload: TemplateVersionCreate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    defaults = payload.model_dump(include={"default_monthly_fee", "default_payment_terms_days", "default_notice_period_days", "default_term_months"})
    version = _handle(svc.new_template_version, db, user.tenant_id, user, payload.content, payload.default_services, defaults, payload.change_note)
    db.commit()
    db.refresh(version)
    return version


def _get_template_version_or_404(db: Session, user: User, version_id: int) -> ContractTemplateVersion:
    version = db.get(ContractTemplateVersion, version_id)
    if version is None or version.template.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template version not found")
    return version


@router.post("/templates/{version_id}/approve", response_model=TemplateVersionOut, dependencies=[Depends(_feature_enabled)])
def approve_template_version(version_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    version = _get_template_version_or_404(db, user, version_id)
    _handle(svc.approve_template_version, db, version, user)
    db.commit()
    db.refresh(version)
    return version


# ---- scheduler (admin) ----


@router.post("/scheduler/run", dependencies=[Depends(_feature_enabled)])
def run_scheduler(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Manual tick (also what an external cron would call). Processes every
    tenant -- the scheduler is a platform job -- but only an admin may
    trigger it, and the result is aggregate counts only."""
    result = contract_scheduler.run_with_lock()
    if result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scheduler is already running")
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="run_scheduler", entity_type="contract", entity_id=0, after=result, request_id=get_request_id()))
    db.commit()
    return result


# ---- public signing portal ----


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    return (forwarded.split(",")[0].strip() if forwarded else None) or (request.client.host if request.client else None)


@router.get("/sign/{token}", response_model=SigningPageOut, dependencies=[Depends(_feature_enabled)])
def signing_page(token: str, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "contract_sign_view", 30)
    contract, invitation, version = _handle(svc.view, db, token)
    db.commit()
    lang = tpl.normalize_language(contract.language)
    signed = contract.signature
    local, _, domain = invitation.signer_email.partition("@")
    return SigningPageOut(
        reference=contract.reference, status=contract.status, language=lang, content=version.content, signer_name=invitation.signer_name,
        signer_email_hint=f"{local[:2]}***@{domain}", consent_text=version.content["consent_text_template"].replace("{name}", invitation.signer_name),
        expires_at=invitation.expires_at, already_signed=signed is not None, signed_at=signed.signed_at if signed else None,
        signed_pdf_sha256=db.get(ContractVersion, signed.signed_version_id).pdf_sha256 if signed and signed.signed_version_id else None,
        assurance_notice=ASSURANCE_NOTICE[lang],
    )


@router.get("/sign/{token}/pdf", dependencies=[Depends(_feature_enabled)])
def signing_pdf(token: str, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "contract_sign_pdf", 30)
    version = _handle(svc.signer_download_version, db, token)
    db.commit()
    return _pdf_response(svc.version_pdf_bytes(version), f"{version.contract.reference}-v{version.version_no}.pdf")


@router.post("/sign/{token}", response_model=SigningPageOut, dependencies=[Depends(_feature_enabled)])
def sign_contract(token: str, payload: SignBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "contract_sign", 10)
    _handle(svc.sign, db, background, token, typed_name=payload.full_name, typed_email=str(payload.email), consent=payload.consent, ip_address=_client_ip(request), user_agent=request.headers.get("user-agent"))
    return signing_page(token, request, db)


# ---- contracts (authenticated) ----


def _accessible_company_ids(db: Session, user: User) -> list[int] | None:
    if user.role in ADMIN_ROLES:
        return None
    return [c.id for c in user.companies]


@router.get("", response_model=list[ContractOut], dependencies=[Depends(_feature_enabled)])
def list_contracts(
    company_id: int | None = Query(None),
    status_filter: S | None = Query(None, alias="status"),
    signing_status: str | None = Query(None),
    expires_before: date | None = Query(None),
    expires_after: date | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Contract).filter(Contract.tenant_id == user.tenant_id)
    allowed = _accessible_company_ids(db, user)
    if allowed is not None:
        query = query.filter(Contract.company_id.in_(allowed or [0]))
    if company_id is not None:
        require_company_access(company_id, user, db)
        query = query.filter(Contract.company_id == company_id)
    if status_filter is not None:
        query = query.filter(Contract.status == status_filter)
    if expires_before is not None:
        query = query.filter(Contract.end_date <= expires_before)
    if expires_after is not None:
        query = query.filter(Contract.end_date >= expires_after)
    rows = [_out(db, c) for c in query.order_by(Contract.created_at.desc(), Contract.id.desc()).limit(limit).all()]
    if signing_status:
        rows = [r for r in rows if r.signing_status == signing_status]
    return rows


@router.post("", response_model=ContractDetailOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(_feature_enabled)])
def create_contract(payload: ContractCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    company = require_company_access(payload.company_id, user, db)
    version = None
    if payload.template_version_id is not None:
        version = _get_template_version_or_404(db, user, payload.template_version_id)
    if payload.language is not None and payload.language not in tpl.SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="language must be nl or en")
    contract = _handle(svc.create_draft, db, company, created_by=user, source="manual", language=payload.language, start_date=payload.start_date, template_version=version)
    db.commit()
    db.refresh(contract)
    return _detail(db, contract)


@router.get("/{contract_id}", response_model=ContractDetailOut, dependencies=[Depends(_feature_enabled)])
def get_contract(contract_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _detail(db, _get_contract_or_404(db, user, contract_id))


@router.patch("/{contract_id}", response_model=ContractDetailOut, dependencies=[Depends(_feature_enabled)])
def update_contract(contract_id: int, payload: ContractUpdate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    contract = _get_contract_or_404(db, user, contract_id, for_update=True)
    updates = payload.model_dump(exclude_unset=True, mode="json")
    if "monthly_fee" in updates and payload.monthly_fee is not None:
        updates["monthly_fee"] = payload.monthly_fee
    if "start_date" in updates and payload.start_date is not None:
        updates["start_date"] = payload.start_date
    _handle(svc.update_draft, db, contract, user, updates)
    db.commit()
    db.refresh(contract)
    return _detail(db, contract)


@router.get("/{contract_id}/preview.pdf", dependencies=[Depends(_feature_enabled)])
def preview_contract_pdf(contract_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    contract = _get_contract_or_404(db, user, contract_id)
    return _pdf_response(svc.preview_pdf(db, contract), f"{contract.reference}-preview.pdf")


@router.get("/{contract_id}/versions/{version_id}/pdf", dependencies=[Depends(_feature_enabled)])
def download_version_pdf(contract_id: int, version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    contract = _get_contract_or_404(db, user, contract_id)
    version = db.get(ContractVersion, version_id)
    if version is None or version.contract_id != contract.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return _pdf_response(svc.version_pdf_bytes(version), f"{contract.reference}-v{version.version_no}.pdf")


@router.get("/{contract_id}/versions/{version_id}/verify", dependencies=[Depends(_feature_enabled)])
def verify_version(contract_id: int, version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    contract = _get_contract_or_404(db, user, contract_id)
    version = db.get(ContractVersion, version_id)
    if version is None or version.contract_id != contract.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return {"version_id": version.id, "pdf_sha256": version.pdf_sha256, "content_hash": version.content_hash, **svc.verify_version(version)}


def _transition(db: Session, user: User, contract_id: int, fn, *args, **kwargs) -> ContractDetailOut:
    contract = _get_contract_or_404(db, user, contract_id, for_update=True)
    _handle(fn, db, contract, user, *args, **kwargs)
    db.commit()
    db.refresh(contract)
    return _detail(db, contract)


@router.post("/{contract_id}/submit", response_model=ContractDetailOut, dependencies=[Depends(_feature_enabled)])
def submit_contract(contract_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    return _transition(db, user, contract_id, svc.submit)


@router.post("/{contract_id}/approve", response_model=ContractDetailOut, dependencies=[Depends(_feature_enabled)])
def approve_contract(contract_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return _transition(db, user, contract_id, svc.approve)


@router.post("/{contract_id}/return-to-draft", response_model=ContractDetailOut, dependencies=[Depends(_feature_enabled)])
def return_contract_to_draft(contract_id: int, payload: ReasonBody | None = None, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return _transition(db, user, contract_id, svc.return_to_draft, payload.reason if payload else None)


def _send_result(db: Session, contract: Contract, invitation: ContractSigningInvitation, raw_token: str, email_sent: bool) -> SendResult:
    return SendResult(contract=_out(db, contract), invitation=InvitationOut.model_validate(invitation), email_sent=email_sent, signing_link=None if email_sent else email_link(f"/sign/{raw_token}"))


@router.post("/{contract_id}/send", response_model=SendResult, dependencies=[Depends(_feature_enabled)])
def send_contract(contract_id: int, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    contract = _get_contract_or_404(db, user, contract_id, for_update=True)
    invitation, raw_token, email_sent = _handle(svc.send, db, background, contract, user)
    db.commit()
    db.refresh(contract)
    return _send_result(db, contract, invitation, raw_token, email_sent)


@router.post("/{contract_id}/resend", response_model=SendResult, dependencies=[Depends(_feature_enabled)])
def resend_contract(contract_id: int, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    contract = _get_contract_or_404(db, user, contract_id, for_update=True)
    invitation, raw_token, email_sent = _handle(svc.resend, db, background, contract, user)
    db.commit()
    db.refresh(contract)
    return _send_result(db, contract, invitation, raw_token, email_sent)


@router.post("/{contract_id}/cancel", response_model=ContractDetailOut, dependencies=[Depends(_feature_enabled)])
def cancel_contract(contract_id: int, background: BackgroundTasks, payload: ReasonBody | None = None, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    contract = _get_contract_or_404(db, user, contract_id, for_update=True)
    _handle(svc.cancel, db, background, contract, user, payload.reason if payload else None)
    db.commit()
    db.refresh(contract)
    return _detail(db, contract)


@router.post("/{contract_id}/terminate", response_model=ContractDetailOut, dependencies=[Depends(_feature_enabled)])
def terminate_contract(contract_id: int, background: BackgroundTasks, payload: TerminateBody | None = None, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    contract = _get_contract_or_404(db, user, contract_id, for_update=True)
    _handle(svc.terminate, db, background, contract, user, payload.reason if payload else None, payload.effective_date if payload else None)
    db.commit()
    db.refresh(contract)
    return _detail(db, contract)


@router.post("/{contract_id}/renewal", response_model=RenewalResult, dependencies=[Depends(_feature_enabled)])
def create_renewal(contract_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    contract = _get_contract_or_404(db, user, contract_id, for_update=True)
    renewal, created = _handle(svc.create_renewal, db, contract, user)
    db.commit()
    db.refresh(renewal)
    return RenewalResult(contract=_out(db, renewal), created=created)


@router.post("/{contract_id}/non-renewal", response_model=ContractDetailOut, dependencies=[Depends(_feature_enabled)])
def set_non_renewal(contract_id: int, payload: NonRenewalBody, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return _transition(db, user, contract_id, svc.set_non_renewal, payload.disabled, payload.reason)
