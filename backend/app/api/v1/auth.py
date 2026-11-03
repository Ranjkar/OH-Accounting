import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.mfa_crypto import decrypt_mfa_secret, encrypt_mfa_secret
from app.core.rate_limit import enforce as enforce_rate_limit
from app.core.security import (
    create_access_token,
    generate_password_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.core.totp import generate_secret, provisioning_uri, verify_code
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.password_reset import PasswordResetToken
from app.models.timesheet import EmployeeTimesheetEntry
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MfaDisableRequest,
    MfaEnableRequest,
    MfaSetupResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    TokenResponse,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "login", settings.rate_limit_login_per_minute)
    user = db.query(User).filter(User.email == payload.email).first()

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
        if user.failed_login_attempts >= settings.max_failed_login_attempts:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.account_lockout_minutes)
            user.failed_login_attempts = 0
            db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="account_locked", entity_type="user", entity_id=user.id, after={"reason": "repeated failed logins"}))
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
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

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
def mfa_enable(payload: MfaEnableRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """`payload.secret` is the one just returned by /mfa/setup -- the
    frontend round-trips it here alongside the code the user typed in from
    their authenticator app, so the secret is only ever persisted once
    proven working, never stored unconfirmed."""
    if not verify_code(payload.secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code -- check your authenticator app and try again")
    user.mfa_secret_encrypted = encrypt_mfa_secret(payload.secret)
    user.mfa_enabled = True
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="mfa_enabled", entity_type="user", entity_id=user.id))
    db.commit()


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
def mfa_disable(payload: MfaDisableRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled")
    secret = decrypt_mfa_secret(user.mfa_secret_encrypted)
    if not verify_code(secret, payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="mfa_disabled", entity_type="user", entity_id=user.id))
    db.commit()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Bumps token_version, which immediately invalidates every token ever
    issued for this account (including the one used to call this
    endpoint) -- there is no per-device session store, so this is
    "log out everywhere," not "log out this one session." A stateless JWT
    cannot otherwise be un-issued before it expires."""
    user.token_version += 1
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="logout", entity_type="user", entity_id=user.id))
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/password-reset/request", status_code=status.HTTP_204_NO_CONTENT)
def request_password_reset(request: Request, payload: PasswordResetRequest, db: Session = Depends(get_db)):
    """Always returns 204 whether or not the email exists -- never reveals
    account existence through this endpoint's response. No email-sending
    provider is configured in this system (see docs/gdpr-data-governance.md
    and docs/security.md) -- the reset link is logged server-side instead
    of emailed, which is safe for development but is NOT a production
    delivery mechanism; wiring a real transactional-email provider is a
    documented prerequisite before this endpoint is exposed publicly."""
    enforce_rate_limit(request, "password_reset", settings.rate_limit_login_per_minute)
    user = db.query(User).filter(User.email == payload.email).first()
    if user is not None:
        raw_token, token_hash = generate_password_reset_token()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_token_expire_minutes)
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        db.commit()
        logger.warning(
            "Password reset requested for user %s. No email provider is configured -- "
            "reset token (not logged here) must be delivered out-of-band by an operator "
            "until a real email provider is wired up. Token expires at %s.",
            user.id, expires_at.isoformat(),
        )
        # Deliberately never logged: the raw token is as sensitive as a password.
        _ = raw_token


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    token_hash = hash_reset_token(payload.token)
    reset_row = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
    if reset_row is None or reset_row.used_at is not None or reset_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    user = db.get(User, reset_row.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    user.hashed_password = hash_password(payload.new_password)
    user.token_version += 1  # revoke every existing session on password change
    user.failed_login_attempts = 0
    user.locked_until = None
    reset_row.used_at = datetime.now(timezone.utc)
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="password_reset", entity_type="user", entity_id=user.id))
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
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="data_export", entity_type="user", entity_id=user.id))
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
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="account_deactivated", entity_type="user", entity_id=user.id))
    db.commit()
