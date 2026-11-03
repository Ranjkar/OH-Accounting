from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin, require_company_access, require_editor
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.enums import UserRole
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.user import User
from app.schemas.company import (
    CompanyCreate,
    CompanyOut,
    CompanyUpdate,
    FinancialYearCreate,
    FinancialYearOut,
)
from app.services.vat_period_generator import generate_vat_periods

router = APIRouter(prefix="/companies", tags=["companies"])


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
