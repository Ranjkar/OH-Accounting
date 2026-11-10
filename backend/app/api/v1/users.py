from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit_redaction import redact
from app.core.deps import ADMIN_ROLES, get_current_user, require_admin
from app.core.request_context import get_request_id
from app.core.security import (
    generate_password_reset_token,
    hash_password,
    hash_reset_token,
)
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.enums import CompanyInvitationStatus, UserRole
from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.schemas.user import (
    ASSIGNABLE_ROLES,
    AcceptUserInvitationRequest,
    TenantUserOut,
    UserInvitationCreate,
    UserInvitationCreateResult,
    UserInvitationOut,
    UserRoleUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])

INVITATION_EXPIRE_DAYS = 14


def _count_active_owners(db: Session, tenant_id: int, exclude_user_id: int | None = None) -> int:
    query = db.query(User).filter(
        User.tenant_id == tenant_id, User.role == UserRole.owner, User.is_active.is_(True)
    )
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.count()


def _get_tenant_user_or_404(db: Session, actor: User, user_id: int) -> User:
    target = db.get(User, user_id)
    if target is None or target.tenant_id != actor.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return target


def _audit(db: Session, actor: User, action: str, entity_id: int, before: dict | None = None, after: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=actor.tenant_id, user_id=actor.id, action=action, entity_type="user", entity_id=entity_id,
        before=redact(before), after=redact(after), request_id=get_request_id(),
    ))


@router.get("", response_model=list[TenantUserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Owner/admin only -- every user in the caller's own tenant, full stop.
    Tenant isolation is the query filter itself, not require_company_access
    (user management is tenant-wide, not company-scoped)."""
    return db.query(User).filter(User.tenant_id == user.tenant_id).order_by(User.created_at).all()


# ---- Phase 15: tenant invitations (creates a brand-new account) ----
# Distinct from app.api.v1.companies' company-access invitations, which
# only grant an *existing* account access to one more company. No email
# provider is configured in this system (same documented limitation as
# every other invitation flow here) -- the raw token is returned once, for
# the inviting party to relay out-of-band.
#
# IMPORTANT: every literal "/invitations..." route below must stay
# registered before the parameterized "/{user_id}..." routes further down
# this file -- FastAPI/Starlette matches routes in registration order, and
# "/{user_id}" would otherwise greedily match the literal segment
# "invitations" as a (non-numeric, 422-rejected) user_id. This bit a real
# manual-testing pass: GET /users/invitations returned a 422 from the
# wrong route until the invitation routes were moved up here.


@router.post("/invitations", response_model=UserInvitationCreateResult, status_code=status.HTTP_201_CREATED)
def create_user_invitation(payload: UserInvitationCreate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if payload.intended_role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Role must be one of {[r.value for r in ASSIGNABLE_ROLES]}")
    if payload.intended_role in (UserRole.owner, UserRole.admin) and user.role != UserRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an owner can invite someone as owner or admin")
    if db.query(User).filter(User.email == payload.invited_email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")

    if payload.initial_company_ids:
        owned_count = db.query(Company).filter(
            Company.id.in_(payload.initial_company_ids), Company.tenant_id == user.tenant_id
        ).count()
        if owned_count != len(set(payload.initial_company_ids)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more company IDs do not belong to this tenant")

    raw_token, token_hash = generate_password_reset_token()
    invitation = UserInvitation(
        tenant_id=user.tenant_id, invited_email=payload.invited_email, intended_role=payload.intended_role,
        invited_by_user_id=user.id, token_hash=token_hash, initial_company_ids=payload.initial_company_ids,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITATION_EXPIRE_DAYS),
    )
    db.add(invitation)
    db.flush()  # assigns invitation.id before the audit row references it
    db.add(AuditLog(
        tenant_id=user.tenant_id, user_id=user.id, action="invite_user", entity_type="user_invitation", entity_id=invitation.id,
        after={"invited_email": payload.invited_email, "intended_role": payload.intended_role.value}, request_id=get_request_id(),
    ))
    db.commit()
    db.refresh(invitation)
    return UserInvitationCreateResult(invitation=invitation, raw_token=raw_token)


@router.get("/invitations", response_model=list[UserInvitationOut])
def list_user_invitations(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return (
        db.query(UserInvitation)
        .filter(UserInvitation.tenant_id == user.tenant_id)
        .order_by(UserInvitation.created_at.desc())
        .all()
    )


@router.post("/invitations/{invitation_id}/revoke", response_model=UserInvitationOut)
def revoke_user_invitation(invitation_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    invitation = db.get(UserInvitation, invitation_id)
    if invitation is None or invitation.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.status != CompanyInvitationStatus.pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Invitation is {invitation.status.value}, not pending")
    invitation.status = CompanyInvitationStatus.revoked
    invitation.revoked_at = datetime.now(timezone.utc)
    _audit(db, user, "revoke_user_invitation", invitation.id)
    db.commit()
    db.refresh(invitation)
    return invitation


@router.post("/invitations/accept")
def accept_user_invitation(payload: AcceptUserInvitationRequest, db: Session = Depends(get_db)):
    """Deliberately unauthenticated -- the whole point is that this person
    does not have an account yet. The token itself (expiring, single-use,
    hash-only-stored) is the credential that authorizes account creation,
    exactly like app.api.v1.companies.accept_invitation's token but for a
    brand-new account instead of extra access on an existing one."""
    token_hash = hash_reset_token(payload.token)
    invitation = db.query(UserInvitation).filter(UserInvitation.token_hash == token_hash).first()
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or unknown invitation token")
    if invitation.status != CompanyInvitationStatus.pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Invitation is {invitation.status.value}, not pending")
    if invitation.expires_at < datetime.now(timezone.utc):
        invitation.status = CompanyInvitationStatus.expired
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This invitation has expired")
    if db.query(User).filter(User.email == invitation.invited_email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")

    new_user = User(
        tenant_id=invitation.tenant_id, email=invitation.invited_email, hashed_password=hash_password(payload.password),
        full_name=payload.full_name, role=invitation.intended_role,
    )
    db.add(new_user)
    db.flush()

    if invitation.initial_company_ids:
        companies = db.query(Company).filter(
            Company.id.in_(invitation.initial_company_ids), Company.tenant_id == invitation.tenant_id
        ).all()
        new_user.companies = companies

    invitation.status = CompanyInvitationStatus.accepted
    invitation.accepted_at = datetime.now(timezone.utc)
    invitation.accepted_user_id = new_user.id
    db.add(AuditLog(
        tenant_id=invitation.tenant_id, user_id=new_user.id, action="accept_user_invitation", entity_type="user",
        entity_id=new_user.id, after={"role": new_user.role.value}, request_id=get_request_id(),
    ))
    db.commit()
    db.refresh(new_user)
    return TenantUserOut.model_validate(new_user)


# ---- Phase 15: individual user administration (parameterized routes --
# must stay below every literal "/invitations..." route above) ----


@router.get("/{user_id}", response_model=TenantUserOut)
def get_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return _get_tenant_user_or_404(db, user, user_id)


@router.patch("/{user_id}/role", response_model=TenantUserOut)
def update_user_role(user_id: int, payload: UserRoleUpdate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Role-change escalation rules (never trust the frontend for these --
    re-checked here on every call):
    - A user can never change their own role (self-escalation).
    - A plain admin may only move a target BETWEEN accountant and viewer --
      touching anyone who currently is, or would become, an owner or admin
      requires an owner actor. (Not just granting upward: an admin cannot
      demote an owner or another admin either -- that would let one admin
      strip another admin's or an owner's privileges, itself a form of
      unauthorized escalation of the acting admin's own effective power.)
    - The last active owner in a tenant can never be demoted away from
      owner -- a tenant must always retain at least one.
    - `customer`/`employee` are not assignable here -- they have their own
      dedicated flows and are intentionally out of this endpoint's scope."""
    if payload.role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Role must be one of {[r.value for r in ASSIGNABLE_ROLES]}")

    target = _get_tenant_user_or_404(db, user, user_id)

    if target.id == user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot change your own role")

    privileged = (UserRole.owner, UserRole.admin)
    if user.role != UserRole.owner and (payload.role in privileged or target.role in privileged):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an owner can grant, revoke, or change an owner's or admin's role")

    if target.role == UserRole.owner and payload.role != UserRole.owner:
        if _count_active_owners(db, user.tenant_id, exclude_user_id=target.id) == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot change the role of the last owner -- promote another user to owner first")

    before_role = target.role
    target.role = payload.role
    _audit(db, user, "role_change", target.id, before={"role": before_role.value}, after={"role": payload.role.value})
    db.commit()
    db.refresh(target)
    return target


@router.post("/{user_id}/activate", response_model=TenantUserOut)
def activate_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    target = _get_tenant_user_or_404(db, user, user_id)
    if target.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already active")
    target.is_active = True
    target.failed_login_attempts = 0
    target.locked_until = None
    _audit(db, user, "user_activated", target.id, after={"is_active": True})
    db.commit()
    db.refresh(target)
    return target


@router.post("/{user_id}/deactivate", response_model=TenantUserOut)
def deactivate_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Blocks login immediately (is_active=False) and revokes every
    existing session (token_version bump) -- never deletes the row or
    touches any linked financial/employee/payroll record, same principle
    as the existing self-service /auth/me/deactivate."""
    target = _get_tenant_user_or_404(db, user, user_id)
    if target.id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use /auth/me/deactivate to deactivate your own account")
    if not target.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already inactive")
    if target.role == UserRole.owner and _count_active_owners(db, user.tenant_id, exclude_user_id=target.id) == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot deactivate the last owner -- promote another user to owner first")

    target.is_active = False
    target.token_version += 1
    _audit(db, user, "user_deactivated", target.id, after={"is_active": False})
    db.commit()
    db.refresh(target)
    return target


@router.post("/{user_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
def revoke_user_sessions(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Force-logout everywhere for the target user, without deactivating
    the account -- bumps token_version, same mechanism as
    /auth/logout and password reset."""
    target = _get_tenant_user_or_404(db, user, user_id)
    target.token_version += 1
    _audit(db, user, "sessions_revoked", target.id)
    db.commit()
