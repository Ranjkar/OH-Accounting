from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.company import Company
from app.models.employee import Employee
from app.models.enums import UserRole
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def find_user_by_email(db: Session, email: str) -> User | None:
    """Case-insensitive, whitespace-trimmed email lookup -- the one place
    this comparison happens, used by every endpoint that looks a user up
    by an email address someone typed (login, password reset, invitation/
    signup uniqueness checks) or that was issued in a token.

    Root-caused a real login failure to this: the previous `User.email ==
    payload.email` exact match meant a browser auto-capitalizing the first
    letter (or any other casing difference) produced a clean, silently
    correct-looking 401 "Invalid email or password" -- indistinguishable
    from an actually wrong password, with zero audit trail (failed_login_
    attempts never incremented, since the code path that does that is
    AFTER this lookup and never reached). Fixed at the lookup, once, rather
    than normalizing in every caller."""
    normalized = email.strip().lower()
    return db.query(User).filter(func.lower(User.email) == normalized).first()

# Phase 15: `owner` (UserRole.owner, the new tenant super-role) is treated
# identically to `admin` everywhere `admin` previously meant "full tenant
# access, bypasses company-membership checks" -- purely additive, no
# existing admin's privileges change. Not to be confused with
# `require_editor_or_owner` below, whose "owner" means the pre-existing
# `customer` role (the "business owner of one company" persona) -- a
# different, older concept kept under its original name for backward
# compatibility.
ADMIN_ROLES = (UserRole.owner, UserRole.admin)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
    )
    decoded = decode_access_token(token)
    if decoded is None:
        raise credentials_error
    email, token_version = decoded
    user = find_user_by_email(db, email)
    if user is None:
        raise credentials_error
    # Revocation check: a token issued before the user's last logout/
    # password-change (which bumps token_version) is rejected even though
    # it's still cryptographically valid and unexpired.
    if token_version != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked, please sign in again")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def require_editor(user: User = Depends(get_current_user)) -> User:
    if user.role not in (*ADMIN_ROLES, UserRole.accountant):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin or accountant role required"
        )
    return user


def require_uploader(user: User = Depends(get_current_user)) -> User:
    """Who may upload documents: accountants/admins for any company they can
    access, plus customers uploading their own company's invoices. Approval,
    rejection, locking, and every other mutating accounting action stay
    require_editor-only -- customers can upload, never approve."""
    if user.role not in (*ADMIN_ROLES, UserRole.accountant, UserRole.customer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin, accountant, or customer role required"
        )
    return user


def require_editor_or_owner(user: User = Depends(get_current_user)) -> User:
    """Who may create/approve budgets and manual balance-sheet items:
    accountants/admins for any company they can access, plus a customer
    (the business-owner persona in this system) for their own company --
    checked separately via require_company_access. Viewers can still read
    every Phase 8 report through get_current_user + require_company_access,
    just never mutate one. NOTE: "owner" in this function's name predates
    Phase 15's UserRole.owner and refers to UserRole.customer -- see the
    ADMIN_ROLES comment above."""
    if user.role not in (*ADMIN_ROLES, UserRole.accountant, UserRole.customer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin, accountant, or business-owner role required"
        )
    return user


def get_current_employee(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Resolves the Employee record this logged-in user is allowed to act
    as themselves -- never any other employee's record. An 'employee'-role
    user is deliberately never added to user_companies, so
    require_company_access already rejects them from every company-wide
    endpoint; this is the only way such a user reaches employee data, and
    it is always scoped to their own linked_user_id."""
    employee = db.query(Employee).filter(Employee.linked_user_id == user.id).first()
    if employee is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is not linked to an employee record")
    return employee


def require_company_access(company_id: int, user: User, db: Session) -> Company:
    """Authoritative company-scope check for EVERY role, including owner/admin.

    Phase 17.1 (audit finding 6.7): this previously returned immediately
    for ADMIN_ROLES without comparing tenants, so cross-tenant isolation
    depended entirely on each of the 61 call sites remembering to write
    its own `tenant_id != user.tenant_id` filter. Seven did not -- two of
    them cross-tenant WRITES (financial-year lock/unlock, which halts a
    victim's bookkeeping, and bulk payment-match approval, which posts to
    a victim's ledger). The tenant check now lives here, once, and cannot
    be skipped by a new endpoint that trusts this function's name.

    A company in another tenant (or no such company) is a 404, not a 403,
    matching the convention every per-endpoint check this replaces already
    used: a caller from another tenant learns neither that the company
    exists nor anything about its id space. A same-tenant user who simply
    is not a member keeps the original 403, so existing behaviour and
    tests for the non-admin roles are unchanged.

    Returns the Company so a caller can drop its own now-redundant
    re-fetch; the 61 existing callers that ignore the return value are
    unaffected.
    """
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        )
    if user.role not in ADMIN_ROLES:
        has_access = any(c.id == company_id for c in user.companies)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No access to this company"
            )
    return company
