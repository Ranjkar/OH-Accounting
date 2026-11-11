import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.mfa_crypto import decrypt_mfa_secret, encrypt_mfa_secret
from app.core.rate_limit import enforce as enforce_rate_limit
from app.core.request_context import get_request_id
from app.core.security import (
    create_access_token,
    generate_password_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.core.totp import generate_secret, provisioning_uri, verify_code
from app.core.deps import find_user_by_email
from app.services import email_templates
from app.services.email_service import link as email_link, queue_email
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.password_reset import PasswordResetToken
from app.models.timesheet import EmployeeTimesheetEntry
from app.models.user import User
from app.schemas.auth import (
    EmailChangeConfirm,
    EmailChangeRequest,
    LoginRequest,
    PasswordChangeRequest,
    PasswordChangeResponse,
    ProfileUpdate,
    SessionsRevokeResponse,
    validate_password_policy,
    MfaDisableRequest,
    MfaEnableRequest,
    MfaSetupResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    TokenResponse,
    UpdateLocaleRequest,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "login", settings.rate_limit_login_per_minute)
    normalized_email = payload.email.strip().lower()
    user = (
        db.query(User)
        .filter(func.lower(func.trim(User.email)) == normalized_email)
        .first()
    )

    # Deliberately the same generic message whether the email doesn't
    # exist, the password is wrong, or the account is locked -- except
    # for the locked case, which gets its own message below, since
    # telling a legitimate user why they're locked out has more UX value
    # than the marginal enumeration risk (their own account, not someone
    # else's).
    invalid_credentials = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user is None:
        raise invalid_credentials

    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account temporarily locked due to repeated failed login attempts. Try again after {user.locked_until.isoformat()}.",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_attempts += 1
        db.add(AuditLog(
            tenant_id=user.tenant_id, user_id=user.id, action="login_failed", entity_type="user", entity_id=user.id,
            after={"failed_login_attempts": user.failed_login_attempts}, request_id=get_request_id(),
        ))
        if user.failed_login_attempts >= settings.max_failed_login_attempts:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.account_lockout_minutes)
            user.failed_login_attempts = 0
            db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="account_locked", entity_type="user", entity_id=user.id, after={"reason": "repeated failed logins"}, request_id=get_request_id()))
        db.commit()
        raise invalid_credentials

    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    if user.mfa_enabled:
        if not payload.mfa_code:
            return TokenResponse(mfa_required=True)
        secret = decrypt_mfa_secret(user.mfa_secret_encrypted)
        if not verify_code(secret, payload.mfa_code):
            db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="login_failed", entity_type="user", entity_id=user.id, after={"reason": "invalid_mfa_code"}, request_id=get_request_id()))
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="login_success", entity_type="user", entity_id=user.id, request_id=get_request_id()))
    db.commit()
    token = create_access_token(subject=user.email, token_version=user.token_version)
    return TokenResponse(access_token=token)


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(user: User = Depends(get_current_user)):
    """Generates a new secret and its provisioning URI but does not enable
    MFA yet -- enrollment is only confirmed (and the secret persisted,
    encrypted) once the user proves they can generate a valid code via
    /mfa/enable. Calling this again before /mfa/enable simply issues a
    fresh, unsaved secret."""
    secret = generate_secret()
    return MfaSetupResponse(secret=secret, provisioning_uri=provisioning_uri(secret, user.email))


@router.post("/mfa/enable", status_code=status.HTTP_204_NO_CONTENT)
def mfa_enable(payload: MfaEnableRequest, background: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """`payload.secret` is the one just returned by /mfa/setup -- the
    frontend round-trips it here alongside the code the user typed in from
    their authenticator app, so the secret is only ever persisted once
    proven working, never stored unconfirmed."""
    if not verify_code(payload.secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code -- check your authenticator app and try again")
    user.mfa_secret_encrypted = encrypt_mfa_secret(payload.secret)
    user.mfa_enabled = True
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="mfa_enabled", entity_type="user", entity_id=user.id, request_id=get_request_id()))
    _notify_security(db, background, user, "mfa_enabled")
    db.commit()


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
def mfa_disable(payload: MfaDisableRequest, background: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled")
    secret = decrypt_mfa_secret(user.mfa_secret_encrypted)
    if not verify_code(secret, payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="mfa_disabled", entity_type="user", entity_id=user.id, request_id=get_request_id()))
    _notify_security(db, background, user, "mfa_disabled")
    db.commit()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Bumps token_version, which immediately invalidates every token ever
    issued for this account (including the one used to call this
    endpoint) -- there is no per-device session store, so this is
    "log out everywhere," not "log out this one session." A stateless JWT
    cannot otherwise be un-issued before it expires."""
    user.token_version += 1
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="logout", entity_type="user", entity_id=user.id, request_id=get_request_id()))
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# Kept in sync by hand with frontend/i18n/config.ts's LOCALES short codes --
# intentionally not shared code between the two languages/runtimes; the
# frontend's own translation-parity test (messages/__tests__/parity.test.ts)
# is what actually guards the dictionaries, this just validates the value
# going into the database.
SUPPORTED_LOCALES = {"nl", "en", "fa", "ar"}


@router.patch("/me/locale", response_model=UserOut)
def update_my_locale(payload: UpdateLocaleRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sets (or, with locale=null, clears) this user's personal language
    override. Never touches tenant.default_locale -- changing your own
    preference never changes what a brand-new teammate sees by default.
    Persisted immediately so the choice survives logout/login and follows
    the user to a new device, per the brief's explicit requirement."""
    if payload.locale is not None and payload.locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"locale must be one of {sorted(SUPPORTED_LOCALES)} or null")
    user.locale = payload.locale
    db.commit()
    db.refresh(user)
    return user


def _effective_locale(user: User) -> str:
    return user.locale or user.tenant_default_locale or "nl"


def _notify_security(db: Session, background: BackgroundTasks, user: User, event_key: str, to_email: str | None = None, **params: object) -> None:
    subject, html, text = email_templates.security_notification(_effective_locale(user), user.full_name, event_key, **params)
    queue_email(db, background, to_email=to_email or user.email, template="security_notification", subject=subject, html_body=html, text_body=text, locale=_effective_locale(user), tenant_id=user.tenant_id)


@router.post("/password-reset/request", status_code=status.HTTP_204_NO_CONTENT)
def request_password_reset(request: Request, payload: PasswordResetRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Always returns 204 whether or not the email exists -- never reveals
    account existence through this endpoint's response. Phase 22: the
    reset link is emailed through app.services.email_service when a
    provider is configured; with EMAIL_PROVIDER=none the attempt is
    recorded as failed in email_outbox (visible to a platform admin) and
    the raw token is never logged anywhere."""
    enforce_rate_limit(request, "password_reset", settings.rate_limit_login_per_minute)
    user = find_user_by_email(db, payload.email)
    if user is not None and user.is_active:
        raw_token, token_hash = generate_password_reset_token()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_token_expire_minutes)
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        locale = _effective_locale(user)
        subject, html, text = email_templates.password_reset(
            locale, user.full_name, email_link(f"/reset-password?token={raw_token}"), settings.password_reset_token_expire_minutes
        )
        queue_email(db, background, to_email=user.email, template="password_reset", subject=subject, html_body=html, text_body=text, locale=locale, tenant_id=user.tenant_id)
        db.commit()


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(payload: PasswordResetConfirm, background: BackgroundTasks, db: Session = Depends(get_db)):
    token_hash = hash_reset_token(payload.token)
    reset_row = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
    if reset_row is None or reset_row.used_at is not None or reset_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    user = db.get(User, reset_row.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    try:
        validate_password_policy(payload.new_password, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    user.hashed_password = hash_password(payload.new_password)
    user.token_version += 1  # revoke every existing session on password change
    user.failed_login_attempts = 0
    user.locked_until = None
    reset_row.used_at = datetime.now(timezone.utc)
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="password_reset", entity_type="user", entity_id=user.id, request_id=get_request_id()))
    _notify_security(db, background, user, "password_changed")
    db.commit()


@router.get("/me/data-export")
def export_my_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """GDPR Article 15/20 (access + portability): every piece of personal
    data this system holds about the logged-in account, in one JSON
    document -- the user's own profile plus, if their account is linked to
    an Employee record, that employee's own profile and timesheet entries
    (never another employee's, never BSN in plaintext -- see
    app.core.crypto, never decrypted here). Financial records belonging to
    the employee (payslips) are intentionally NOT included in a bulk
    export here -- they're available individually via /me/payslips and
    carry their own statutory retention obligations, documented in
    docs/gdpr-data-governance.md."""
    data: dict = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role.value, "created_at": user.created_at.isoformat()},
    }
    employee = db.query(Employee).filter(Employee.linked_user_id == user.id).first()
    if employee is not None:
        timesheet_entries = db.query(EmployeeTimesheetEntry).filter(EmployeeTimesheetEntry.employee_id == employee.id).all()
        data["employee_profile"] = {
            "employee_number": employee.employee_number,
            "full_name": employee.full_name,
            "job_title": employee.job_title,
            "department": employee.department,
            "employment_start_date": employee.employment_start_date.isoformat(),
            "employment_end_date": employee.employment_end_date.isoformat() if employee.employment_end_date else None,
        }
        data["timesheet_entries"] = [
            {"entry_date": e.entry_date.isoformat(), "entry_type": e.entry_type.value, "hours": str(e.hours), "status": e.status.value}
            for e in timesheet_entries
        ]
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="data_export", entity_type="user", entity_id=user.id, request_id=get_request_id()))
    db.commit()
    return data


@router.post("/me/deactivate", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_my_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """GDPR-adjacent "right to restrict/stop processing" for the account
    itself: blocks all future logins immediately (token_version bump +
    is_active=False). Never deletes the User row, and never touches any
    linked Employee/Payslip/AccountingTransaction/etc. -- those carry
    their own statutory retention obligations (7 years, 10 for records
    touching immovable property, per Dutch bewaarplicht) which this
    system must not override just because the account was deactivated.
    See docs/gdpr-data-governance.md."""
    user.is_active = False
    user.token_version += 1
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="account_deactivated", entity_type="user", entity_id=user.id, request_id=get_request_id()))
    db.commit()


# ---- Phase 22: personal profile, password, verified email change, sessions ----


def _sync_full_name(user: User) -> None:
    parts = " ".join(p for p in (user.first_name, user.last_name) if p and p.strip()).strip()
    if user.display_name and user.display_name.strip():
        user.full_name = user.display_name.strip()
    elif parts:
        user.full_name = parts


@router.patch("/me/profile", response_model=UserOut)
def update_my_profile(payload: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Personal details only. Email (verified flow below), role, tenant,
    platform-admin flag and MFA are never touched by this endpoint, so a
    user can never change anything that affects their own authority."""
    updates = payload.model_dump(exclude_unset=True)
    before = {k: getattr(user, k) for k in updates}
    for key, value in updates.items():
        setattr(user, key, value.strip() if isinstance(value, str) and value.strip() else (None if isinstance(value, str) else value))
    _sync_full_name(user)
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="profile_updated", entity_type="user", entity_id=user.id,
                    before={k: v for k, v in before.items()}, after={k: getattr(user, k) for k in updates}, request_id=get_request_id()))
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/password", response_model=PasswordChangeResponse)
def change_my_password(payload: PasswordChangeRequest, request: Request, background: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Requires the current password (a stolen session alone cannot set a
    new one), enforces the policy, revokes every other session by bumping
    token_version, and returns a fresh token so THIS device stays signed in."""
    enforce_rate_limit(request, "password_change", settings.rate_limit_login_per_minute)
    if not verify_password(payload.current_password, user.hashed_password):
        db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="password_change_failed", entity_type="user", entity_id=user.id, request_id=get_request_id()))
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password and confirmation do not match")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must differ from the current password")
    try:
        validate_password_policy(payload.new_password, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    user.hashed_password = hash_password(payload.new_password)
    user.token_version += 1
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="password_changed", entity_type="user", entity_id=user.id, request_id=get_request_id()))
    _notify_security(db, background, user, "password_changed")
    db.commit()
    return PasswordChangeResponse(access_token=create_access_token(subject=user.email, token_version=user.token_version))


@router.post("/me/email/request-change", response_model=UserOut)
def request_email_change(payload: EmailChangeRequest, request: Request, background: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Step 1 of 2. Re-authenticates with the password, stores the new
    address as PENDING and emails a verification link to the NEW address.
    The login email only changes once that link is used (confirm below).
    Returns 409 when the address is already taken -- unavoidable for a
    uniqueness constraint, but only after password re-auth, so it cannot be
    used anonymously to enumerate accounts."""
    enforce_rate_limit(request, "email_change", settings.rate_limit_login_per_minute)
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    new_email = payload.new_email.strip().lower()
    if new_email == user.email.lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This is already your email address")
    if find_user_by_email(db, new_email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email address is already in use")
    raw_token, token_hash = generate_password_reset_token()
    user.pending_email = new_email
    user.email_change_token_hash = token_hash
    user.email_change_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_token_expire_minutes)
    locale = _effective_locale(user)
    subject, html, text = email_templates.email_verification(
        locale, user.full_name, new_email, email_link(f"/verify-email?token={raw_token}"), settings.password_reset_token_expire_minutes
    )
    _, will_send = queue_email(db, background, to_email=new_email, template="email_verification", subject=subject, html_body=html, text_body=text, locale=locale, tenant_id=user.tenant_id)
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="email_change_requested", entity_type="user", entity_id=user.id, after={"pending_email": new_email, "email_sent": will_send}, request_id=get_request_id()))
    db.commit()
    db.refresh(user)
    return user


@router.delete("/me/email/request-change", response_model=UserOut)
def cancel_email_change(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.pending_email = None
    user.email_change_token_hash = None
    user.email_change_expires_at = None
    db.commit()
    db.refresh(user)
    return user


@router.post("/email/confirm-change", status_code=status.HTTP_204_NO_CONTENT)
def confirm_email_change(payload: EmailChangeConfirm, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Step 2 of 2 -- unauthenticated on purpose: the link may be opened on
    a device without a session. The single-use, expiring token is the
    credential. Swaps the address, revokes all sessions (the old email was
    the JWT subject), and notifies the OLD address so a hijack is visible."""
    token_hash = hash_reset_token(payload.token)
    user = db.query(User).filter(User.email_change_token_hash == token_hash).first()
    if user is None or user.pending_email is None or user.email_change_expires_at is None or user.email_change_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification link")
    if find_user_by_email(db, user.pending_email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email address is already in use")
    old_email, new_email = user.email, user.pending_email
    user.email = new_email
    user.pending_email = None
    user.email_change_token_hash = None
    user.email_change_expires_at = None
    user.token_version += 1
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="email_changed", entity_type="user", entity_id=user.id, before={"email": old_email}, after={"email": new_email}, request_id=get_request_id()))
    _notify_security(db, background, user, "email_changed", to_email=old_email, new_email=new_email)
    db.commit()


@router.post("/me/sessions/revoke-others", response_model=SessionsRevokeResponse)
def revoke_my_other_sessions(background: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """"Sign out everywhere else": bumps token_version (invalidating every
    token issued so far, on every device) and hands this device a new one.
    There is no per-device session list in this build -- a stateless JWT
    cannot be enumerated -- so this is the honest equivalent."""
    user.token_version += 1
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="sessions_revoked_self", entity_type="user", entity_id=user.id, request_id=get_request_id()))
    _notify_security(db, background, user, "sessions_revoked")
    db.commit()
    return SessionsRevokeResponse(access_token=create_access_token(subject=user.email, token_version=user.token_version))
