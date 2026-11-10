from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_company_access, require_editor
from app.db.session import get_db
from app.models.company import Company
from app.models.legal_form import CompanyLegalForm, LegalFormDefinition, Partner, Shareholder
from app.models.user import User
from app.schemas.legal_form import (
    CompanyLegalFormCreate,
    CompanyLegalFormOut,
    LegalFormDefinitionOut,
    PartnerCreate,
    PartnerOut,
    ShareholderCreate,
    ShareholderOut,
)

router = APIRouter(tags=["legal-forms"])


def _get_company_or_404(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.get("/legal-form-definitions", response_model=list[LegalFormDefinitionOut])
def list_legal_form_definitions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(LegalFormDefinition).order_by(LegalFormDefinition.name_en).all()


@router.post("/company-legal-forms", response_model=CompanyLegalFormOut, status_code=status.HTTP_201_CREATED)
def set_company_legal_form(payload: CompanyLegalFormCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    """Closes any currently-open legal form row for this company (sets
    effective_to) and opens a new one -- history is never overwritten."""
    company = _get_company_or_404(db, user, payload.company_id)
    current = (
        db.query(CompanyLegalForm)
        .filter(CompanyLegalForm.company_id == company.id, CompanyLegalForm.effective_to.is_(None))
        .first()
    )
    if current is not None:
        if payload.effective_from <= current.effective_from:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New effective_from must be after the current legal form's effective_from")
        current.effective_to = payload.effective_from
    new_form = CompanyLegalForm(
        company_id=company.id, legal_form_code=payload.legal_form_code, effective_from=payload.effective_from,
        created_by_user_id=user.id,
    )
    db.add(new_form)
    db.commit()
    db.refresh(new_form)
    return new_form


@router.get("/company-legal-forms", response_model=list[CompanyLegalFormOut])
def list_company_legal_forms(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return (
        db.query(CompanyLegalForm)
        .filter(CompanyLegalForm.company_id == company_id)
        .order_by(CompanyLegalForm.effective_from.desc())
        .all()
    )


@router.get("/company-legal-forms/current", response_model=CompanyLegalFormOut)
def get_current_legal_form(company_id: int, as_of_date: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    as_of = as_of_date or date.today()
    current = (
        db.query(CompanyLegalForm)
        .filter(
            CompanyLegalForm.company_id == company_id,
            CompanyLegalForm.effective_from <= as_of,
        )
        .filter((CompanyLegalForm.effective_to.is_(None)) | (CompanyLegalForm.effective_to > as_of))
        .order_by(CompanyLegalForm.effective_from.desc())
        .first()
    )
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No legal form recorded for this company as of this date")
    return current


# ---- Partners (VOF/Maatschap/CV) ----


@router.post("/partners", response_model=PartnerOut, status_code=status.HTTP_201_CREATED)
def create_partner(payload: PartnerCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    _get_company_or_404(db, user, payload.company_id)
    partner = Partner(
        company_id=payload.company_id, name=payload.name, partner_type=payload.partner_type,
        profit_share_percentage=payload.profit_share_percentage, entrepreneur_hours_eligible=payload.entrepreneur_hours_eligible,
        effective_from=payload.effective_from,
    )
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


@router.get("/partners", response_model=list[PartnerOut])
def list_partners(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return (
        db.query(Partner)
        .filter(Partner.company_id == company_id, Partner.effective_to.is_(None))
        .order_by(Partner.name)
        .all()
    )


@router.patch("/partners/{partner_id}/entrepreneur-hours-eligibility", response_model=PartnerOut)
def set_partner_hours_eligibility(partner_id: int, eligible: bool, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    """Never defaulted to True elsewhere -- this is the one explicit place
    an accountant marks a partner as meeting the urencriterium."""
    partner = db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
    _get_company_or_404(db, user, partner.company_id)
    partner.entrepreneur_hours_eligible = eligible
    db.commit()
    db.refresh(partner)
    return partner


# ---- Shareholders (BV/NV) ----


@router.post("/shareholders", response_model=ShareholderOut, status_code=status.HTTP_201_CREATED)
def create_shareholder(payload: ShareholderCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    _get_company_or_404(db, user, payload.company_id)
    shareholder = Shareholder(
        company_id=payload.company_id, name=payload.name, ownership_percentage=payload.ownership_percentage,
        is_director=payload.is_director, is_dga=payload.is_dga, effective_from=payload.effective_from,
    )
    db.add(shareholder)
    db.commit()
    db.refresh(shareholder)
    return shareholder


@router.get("/shareholders", response_model=list[ShareholderOut])
def list_shareholders(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return (
        db.query(Shareholder)
        .filter(Shareholder.company_id == company_id, Shareholder.effective_to.is_(None))
        .order_by(Shareholder.name)
        .all()
    )
