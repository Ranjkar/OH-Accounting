from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_company_access
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.enums import UserRole
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.user import User
from app.schemas.company import (
    CompanyCreate,
    CompanyOut,
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


@router.post(
    "/{company_id}/financial-years",
    response_model=FinancialYearOut,
    status_code=status.HTTP_201_CREATED,
)
def create_financial_year(
    company_id: int,
    payload: FinancialYearCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
