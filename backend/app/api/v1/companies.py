from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin, require_company_access, require_editor
from app.core.security import generate_password_reset_token, hash_reset_token
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.company_invitation import CompanyInvitation
from app.models.enums import CompanyInvitationStatus, UserRole
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.user import User
from app.schemas.company import (
    AcceptInvitationRequest,
    CompanyAccessOut,
    CompanyCreate,
    CompanyInvitationCreate,
    CompanyInvitationCreateResult,
    CompanyInvitationOut,
    CompanyOut,
    CompanyUpdate,
    FinancialYearCreate,
    FinancialYearOut,
)
from app.services.vat_period_generator import generate_vat_periods

router = APIRouter(prefix="/companies", tags=["companies"])

INVITATION_EXPIRE_DAYS = 14


def _require_company_owner(company_id: int, user: User, db: Session) -> None:
    """Who may manage who has access to a company: an admin, or the
    company's own business-owner persona (customer role) -- not every
    accountant who happens to have access, since inviting further access
    is a company-ownership decision, not a bookkeeping one."""
    require_company_access(company_id, user, db)
    if user.role not in (UserRole.admin, UserRole.customer):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin or the company owner can manage company access")


def _accessible_companies_query(db: Session, user: User):
    query = db.query(Company).filter(Company.tenant_id == user.tenant_id)
    if user.role != UserRole.admin:
        company_ids = [c.id for c in user.companies]
        query = query.filter(Company.id.in_(company_ids))
    return query


@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _accessible_companies_query(db, user).all()


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    company = Company(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="create",
            entity_type="company",
            entity_id=company.id,
            after=payload.model_dump(mode="json"),
        )
    )
    db.commit()
    return company


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    updates = payload.model_dump(exclude_unset=True)
    before = {k: getattr(company, k) for k in updates}
    for key, value in updates.items():
        setattr(company, key, value)

    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="correct",
            entity_type="company",
            entity_id=company.id,
            before={k: str(v) for k, v in before.items()},
            after={k: str(v) for k, v in updates.items()},
        )
    )
    db.commit()
    db.refresh(company)
    return company


@router.post(
    "/{company_id}/financial-years",
    response_model=FinancialYearOut,
    status_code=status.HTTP_201_CREATED,
)
def create_financial_year(
    company_id: int,
    payload: FinancialYearCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    existing = (
        db.query(FinancialYear)
        .filter(FinancialYear.company_id == company_id, FinancialYear.year == payload.year)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Financial year {payload.year} already exists for this company",
        )

    specs = generate_vat_periods(payload.year, company.vat_frequency)
    financial_year = FinancialYear(
        company_id=company_id,
        year=payload.year,
        start_date=specs[0].start_date,
        end_date=specs[-1].end_date,
    )
    financial_year.vat_periods = [
        VatPeriod(
            label=spec.label,
            start_date=spec.start_date,
            end_date=spec.end_date,
            filing_deadline=spec.filing_deadline,
            payment_deadline=spec.payment_deadline,
        )
        for spec in specs
    ]
    db.add(financial_year)
    db.commit()
    db.refresh(financial_year)
    return financial_year


@router.get("/{company_id}/financial-years", response_model=list[FinancialYearOut])
def list_financial_years(
    company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    require_company_access(company_id, user, db)
    return (
        db.query(FinancialYear)
        .filter(FinancialYear.company_id == company_id)
        .order_by(FinancialYear.year)
        .all()
    )


def _get_financial_year_or_404(db: Session, user: User, company_id: int, financial_year_id: int) -> FinancialYear:
    require_company_access(company_id, user, db)
    financial_year = db.get(FinancialYear, financial_year_id)
    if financial_year is None or financial_year.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")
    return financial_year


@router.post("/{company_id}/financial-years/{financial_year_id}/lock", response_model=FinancialYearOut)
def lock_financial_year(
    company_id: int, financial_year_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    """Locking blocks any new or corrected ledger transaction dated within
    this financial year (see ledger_service._ensure_financial_year_open) --
    it never touches transactions already posted."""
    financial_year = _get_financial_year_or_404(db, user, company_id, financial_year_id)
    if financial_year.is_locked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Financial year is already locked")
    financial_year.is_locked = True
    financial_year.locked_at = datetime.now(timezone.utc)
    financial_year.locked_by_user_id = user.id
    db.add(AuditLog(
        tenant_id=user.tenant_id, user_id=user.id, action="lock", entity_type="financial_year",
        entity_id=financial_year.id, after={"year": financial_year.year, "is_locked": True},
    ))
    db.commit()
    db.refresh(financial_year)
    return financial_year


@router.post("/{company_id}/financial-years/{financial_year_id}/unlock", response_model=FinancialYearOut)
def unlock_financial_year(
    company_id: int, financial_year_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    """Unlocking is deliberate and audit-logged -- never automatic. It does
    not retroactively validate or re-check anything already posted; it only
    re-opens the period to new postings and corrections."""
    financial_year = _get_financial_year_or_404(db, user, company_id, financial_year_id)
    if not financial_year.is_locked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Financial year is not locked")
    financial_year.is_locked = False
    db.add(AuditLog(
        tenant_id=user.tenant_id, user_id=user.id, action="unlock", entity_type="financial_year",
        entity_id=financial_year.id, before={"locked_by_user_id": financial_year.locked_by_user_id, "locked_at": str(financial_year.locked_at)},
        after={"year": financial_year.year, "is_locked": False},
    ))
    financial_year.locked_at = None
    financial_year.locked_by_user_id = None
    db.commit()
    db.refresh(financial_year)
    return financial_year


# ---- Phase 14: company access / accountant invitations ----
# No email provider is configured (same documented limitation as password
# reset, see docs/security.md) -- the raw invitation token is returned in
# the create response for the inviting party to relay out-of-band, and
# only its SHA-256 hash is ever persisted.


@router.get("/{company_id}/access", response_model=list[CompanyAccessOut])
def list_company_access(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return [CompanyAccessOut(user_id=u.id, email=u.email, full_name=u.full_name, role=u.role) for u in company.users]


@router.post("/{company_id}/access/{user_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_company_access(company_id: int, user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_company_owner(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    target = next((u for u in company.users if u.id == user_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This user does not have access to this company")
    company.users.remove(target)
    db.add(AuditLog(
        tenant_id=user.tenant_id, user_id=user.id, action="revoke_access", entity_type="company",
        entity_id=company.id, before={"revoked_user_id": user_id}, after={},
    ))
    db.commit()


@router.post("/{company_id}/invitations", response_model=CompanyInvitationCreateResult, status_code=status.HTTP_201_CREATED)
def create_invitation(company_id: int, payload: CompanyInvitationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_company_owner(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    raw_token, token_hash = generate_password_reset_token()
    invitation = CompanyInvitation(
        tenant_id=user.tenant_id, company_id=company_id, invited_email=payload.invited_email,
        intended_role=payload.intended_role, invited_by_user_id=user.id, token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITATION_EXPIRE_DAYS),
    )
    db.add(invitation)
    db.add(AuditLog(
        tenant_id=user.tenant_id, user_id=user.id, action="invite", entity_type="company",
        entity_id=company.id, after={"invited_email": payload.invited_email, "intended_role": payload.intended_role.value},
    ))
    db.commit()
    db.refresh(invitation)
    return CompanyInvitationCreateResult(invitation=invitation, raw_token=raw_token)


@router.get("/{company_id}/invitations", response_model=list[CompanyInvitationOut])
def list_invitations(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_company_owner(company_id, user, db)
    return (
        db.query(CompanyInvitation)
        .filter(CompanyInvitation.company_id == company_id)
        .order_by(CompanyInvitation.created_at.desc())
        .all()
    )


@router.post("/{company_id}/invitations/{invitation_id}/revoke", response_model=CompanyInvitationOut)
def revoke_invitation(company_id: int, invitation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_company_owner(company_id, user, db)
    invitation = db.get(CompanyInvitation, invitation_id)
    if invitation is None or invitation.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.status != CompanyInvitationStatus.pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Invitation is {invitation.status.value}, not pending")
    invitation.status = CompanyInvitationStatus.revoked
    invitation.revoked_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        tenant_id=user.tenant_id, user_id=user.id, action="revoke_invitation", entity_type="company_invitation",
        entity_id=invitation.id, after={},
    ))
    db.commit()
    db.refresh(invitation)
    return invitation


@router.post("/invitations/accept", response_model=CompanyAccessOut)
def accept_invitation(payload: AcceptInvitationRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The accepting user must already have an account, and it must match
    the invited email -- this is deliberately access-grant-only, never a
    signup flow, to avoid creating accounts from an unauthenticated token."""
    token_hash = hash_reset_token(payload.token)
    invitation = db.query(CompanyInvitation).filter(CompanyInvitation.token_hash == token_hash).first()
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or unknown invitation token")
    if invitation.status != CompanyInvitationStatus.pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Invitation is {invitation.status.value}, not pending")
    if invitation.expires_at < datetime.now(timezone.utc):
        invitation.status = CompanyInvitationStatus.expired
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This invitation has expired")
    if invitation.invited_email.lower() != user.email.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This invitation was issued to a different email address")

    company = db.get(Company, invitation.company_id)
    if user not in company.users:
        company.users.append(user)

    invitation.status = CompanyInvitationStatus.accepted
    invitation.accepted_at = datetime.now(timezone.utc)
    invitation.accepted_by_user_id = user.id
    db.add(AuditLog(
        tenant_id=user.tenant_id, user_id=user.id, action="accept_invitation", entity_type="company",
        entity_id=company.id, after={"accepted_by_user_id": user.id},
    ))
    db.commit()
    return CompanyAccessOut(user_id=user.id, email=user.email, full_name=user.full_name, role=user.role)
