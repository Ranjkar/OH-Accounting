"""Phase 22: company setup wizard.

Drafts are tenant-scoped rows holding the wizard's answers; the frontend
PATCHes them as the user moves between steps so setup can be resumed on
any device. Validation of required / conditionally-required fields lives
in `validate_draft` (one function, used by both the preview endpoint and
completion) so the review step shows exactly what completion will enforce.

Completion is idempotent and race-safe: the draft row is locked FOR UPDATE,
and if `created_company_id` is already set the existing company is returned
with `already_completed=true` instead of creating a second one.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.accounting import subscription_service
from app.core.deps import ADMIN_ROLES, get_current_user
from app.core.dutch_identifiers import is_valid_btw, is_valid_iban, is_valid_kvk, is_valid_rsin, normalize
from app.core.email_format import is_valid_email
from app.core.request_context import get_request_id
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.banking import BankAccount
from app.models.company import Company, CompanySetupDraft
from app.models.enums import LegalFormCode, VatAccountingBasis, VatFrequency
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.legal_form import CompanyLegalForm, LegalFormDefinition
from app.models.user import User
from app.schemas.company import (
    SetupCompleteOut,
    SetupDraftData,
    SetupDraftOut,
    SetupDraftUpdate,
    SetupValidationIssue,
    SetupValidationOut,
)
from app.services import contract_service
from app.services.vat_period_generator import generate_vat_periods

router = APIRouter(prefix="/companies/setup-drafts", tags=["company-setup"])


def _require_company_creator(user: User) -> None:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


def _get_draft_or_404(db: Session, user: User, draft_id: int, *, for_update: bool = False) -> CompanySetupDraft:
    query = db.query(CompanySetupDraft).filter(CompanySetupDraft.id == draft_id, CompanySetupDraft.tenant_id == user.tenant_id)
    if for_update:
        query = query.with_for_update()
    draft = query.first()
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setup draft not found")
    return draft


def _legal_form(db: Session, code: str | None) -> LegalFormDefinition | None:
    if not code:
        return None
    try:
        enum_code = LegalFormCode(code.upper())
    except ValueError:
        return None
    return db.query(LegalFormDefinition).filter(LegalFormDefinition.code == enum_code).first()


def validate_draft(db: Session, tenant_id: int, data: SetupDraftData, *, exclude_company_id: int | None = None) -> SetupValidationOut:
    issues: list[SetupValidationIssue] = []
    warnings: list[SetupValidationIssue] = []

    def issue(field: str, code: str, message: str) -> None:
        issues.append(SetupValidationIssue(field=field, code=code, message=message))

    name = (data.name or "").strip()
    if not name:
        issue("name", "required", "Company name is required")
    form = _legal_form(db, data.legal_form_code)
    if data.legal_form_code and form is None:
        issue("legal_form_code", "invalid", "Unknown legal form")
    if not data.legal_form_code:
        issue("legal_form_code", "required", "Legal form is required")

    kvk = normalize(data.kvk_number) or None
    if form is not None and form.requires_kvk_registration and not kvk:
        issue("kvk_number", "required", "A KVK number is required for this legal form")
    if kvk and not is_valid_kvk(kvk):
        issue("kvk_number", "invalid", "KVK number must be exactly 8 digits")

    rsin = normalize(data.rsin) or None
    if form is not None and form.has_legal_personality and not rsin:
        warnings.append(SetupValidationIssue(field="rsin", code="required", message="An RSIN is normally issued to this legal form; add it when known"))
    if rsin and not is_valid_rsin(rsin):
        issue("rsin", "invalid", "RSIN must be 9 digits and pass the 11-check")

    email = (data.email or "").strip()
    if email and not is_valid_email(email):
        issue("email", "invalid", "Enter a valid email address")

    if data.vat_registered is None:
        issue("vat_registered", "required", "Indicate whether the company is registered for VAT")
    vat = normalize(data.vat_number) or None
    if data.vat_registered:
        if not vat:
            issue("vat_number", "required", "A VAT identification number (btw-id) is required for a VAT-registered company")
        if not data.vat_frequency:
            issue("vat_frequency", "required", "Choose the VAT filing frequency")
        if not data.vat_accounting_basis:
            issue("vat_accounting_basis", "required", "Choose the VAT accounting basis")
    if vat and not is_valid_btw(vat):
        issue("vat_number", "invalid", "VAT number must look like NL123456789B01 and pass the checksum")
    if data.kor_participant and data.vat_registered is False:
        issue("kor_participant", "invalid", "The KOR small-business scheme only applies to VAT-registered businesses")

    if data.financial_year is None:
        issue("financial_year", "required", "Choose the first financial year to open")
    elif not (2000 <= data.financial_year <= 2100):
        issue("financial_year", "invalid", "Financial year must be between 2000 and 2100")

    if not data.bank_skipped:
        iban = normalize(data.bank_iban) or None
        if iban and not is_valid_iban(iban):
            issue("bank_iban", "invalid", "IBAN failed its checksum")
        if iban and not (data.bank_account_name or "").strip():
            issue("bank_account_name", "required", "Give the bank account a name")

    # Duplicate protection: same KVK number, or same name, inside this tenant.
    dup_query = db.query(Company).filter(Company.tenant_id == tenant_id)
    if exclude_company_id is not None:
        dup_query = dup_query.filter(Company.id != exclude_company_id)
    if kvk and dup_query.filter(Company.kvk_number == kvk).first() is not None:
        issue("kvk_number", "duplicate", "A company with this KVK number already exists in your organisation")
    if name and dup_query.filter(func.lower(Company.name) == name.lower()).first() is not None:
        issue("name", "duplicate", "A company with this name already exists in your organisation")

    return SetupValidationOut(ok=not issues, issues=issues, warnings=warnings)


@router.post("", response_model=SetupDraftOut, status_code=status.HTTP_201_CREATED)
def create_setup_draft(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_company_creator(user)
    draft = CompanySetupDraft(tenant_id=user.tenant_id, created_by_user_id=user.id, data={}, current_step=0)
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


@router.get("", response_model=list[SetupDraftOut])
def list_setup_drafts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Open (not yet completed) drafts for the caller's tenant, so a setup
    started on a phone can be resumed from a laptop by anyone who may create
    companies."""
    _require_company_creator(user)
    return (
        db.query(CompanySetupDraft)
        .filter(CompanySetupDraft.tenant_id == user.tenant_id, CompanySetupDraft.completed_at.is_(None))
        .order_by(CompanySetupDraft.updated_at.desc())
        .all()
    )


@router.get("/{draft_id}", response_model=SetupDraftOut)
def get_setup_draft(draft_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_company_creator(user)
    return _get_draft_or_404(db, user, draft_id)


@router.patch("/{draft_id}", response_model=SetupDraftOut)
def update_setup_draft(draft_id: int, payload: SetupDraftUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_company_creator(user)
    draft = _get_draft_or_404(db, user, draft_id)
    if draft.completed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This setup has already been completed")
    draft.data = payload.data.model_dump(mode="json", exclude_none=True)
    draft.current_step = max(0, min(payload.current_step, 10))
    db.commit()
    db.refresh(draft)
    return draft


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_setup_draft(draft_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_company_creator(user)
    draft = _get_draft_or_404(db, user, draft_id)
    if draft.completed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A completed setup cannot be deleted")
    db.delete(draft)
    db.commit()


@router.post("/{draft_id}/validate", response_model=SetupValidationOut)
def validate_setup_draft(draft_id: int, payload: SetupDraftUpdate | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Dry run of completion's checks, for the review step. Accepts the
    not-yet-saved answers in the body so the review is always of what is
    on screen."""
    _require_company_creator(user)
    draft = _get_draft_or_404(db, user, draft_id)
    data = payload.data if payload is not None else SetupDraftData(**(draft.data or {}))
    return validate_draft(db, user.tenant_id, data, exclude_company_id=draft.created_company_id)


@router.post("/{draft_id}/complete", response_model=SetupCompleteOut)
def complete_setup_draft(draft_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_company_creator(user)
    draft = _get_draft_or_404(db, user, draft_id, for_update=True)

    if draft.created_company_id is not None:
        company = db.get(Company, draft.created_company_id)
        fy = db.query(FinancialYear).filter(FinancialYear.company_id == company.id).order_by(FinancialYear.year).first()
        acct = db.query(BankAccount).filter(BankAccount.company_id == company.id).order_by(BankAccount.id).first()
        return SetupCompleteOut(company=company, financial_year_id=fy.id if fy else None, bank_account_id=acct.id if acct else None, already_completed=True)

    data = SetupDraftData(**(draft.data or {}))
    validation = validate_draft(db, user.tenant_id, data)
    if not validation.ok:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Setup is incomplete", "issues": [i.model_dump() for i in validation.issues]},
        )
    try:
        subscription_service.enforce_company_limit(db, user.tenant_id)
    except subscription_service.PlanLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc

    vat_registered = bool(data.vat_registered)
    company = Company(
        tenant_id=user.tenant_id,
        name=data.name.strip(),
        kvk_number=normalize(data.kvk_number) or None,
        vat_number=normalize(data.vat_number) or None if vat_registered else None,
        rsin=normalize(data.rsin) or None,
        address=(data.address or "").strip() or None,
        business_activity=(data.business_activity or "").strip() or None,
        email=(data.email or "").strip().lower() or None,
        phone=(data.phone or "").strip() or None,
        vat_registered=vat_registered,
        kor_participant=bool(data.kor_participant) if vat_registered else False,
        vat_frequency=data.vat_frequency or VatFrequency.quarterly,
        vat_accounting_basis=data.vat_accounting_basis or VatAccountingBasis.invoice_based,
    )
    db.add(company)
    db.flush()

    db.add(CompanyLegalForm(
        company_id=company.id, legal_form_code=LegalFormCode(data.legal_form_code.upper()),
        effective_from=datetime(data.financial_year, 1, 1).date(), created_by_user_id=user.id,
    ))

    specs = generate_vat_periods(data.financial_year, company.vat_frequency)
    financial_year = FinancialYear(company_id=company.id, year=data.financial_year, start_date=specs[0].start_date, end_date=specs[-1].end_date)
    financial_year.vat_periods = [
        VatPeriod(label=s.label, start_date=s.start_date, end_date=s.end_date, filing_deadline=s.filing_deadline, payment_deadline=s.payment_deadline)
        for s in specs
    ]
    db.add(financial_year)
    db.flush()

    bank_account_id: int | None = None
    iban = normalize(data.bank_iban) or None
    if iban and not data.bank_skipped:
        account = BankAccount(tenant_id=user.tenant_id, company_id=company.id, iban=iban, account_name=(data.bank_account_name or "").strip(), currency="EUR")
        db.add(account)
        db.flush()
        bank_account_id = account.id

    draft.created_company_id = company.id
    draft.completed_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        tenant_id=user.tenant_id, user_id=user.id, action="create", entity_type="company", entity_id=company.id,
        after={"via": "setup_wizard", "draft_id": draft.id, "name": company.name, "kvk_number": company.kvk_number, "legal_form": data.legal_form_code,
               "vat_registered": vat_registered, "kor_participant": company.kor_participant, "financial_year": data.financial_year},
        request_id=get_request_id(),
    ))
    contract_service.auto_create_for_new_company(db, company, user)  # Phase 26, no-op unless CONTRACTS_ENABLED
    db.commit()
    db.refresh(company)
    return SetupCompleteOut(company=company, financial_year_id=financial_year.id, bank_account_id=bank_account_id, already_completed=False)
