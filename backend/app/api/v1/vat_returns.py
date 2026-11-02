from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.accounting import reconciliation, vat_engine
from app.core.deps import get_current_user, require_company_access, require_editor
from app.db.session import get_db
from app.models.accounting import AccountingTransaction, VatReturn
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.enums import TransactionApprovalStatus, VatReturnStatus
from app.models.financial_year import VatPeriod
from app.models.user import User
from app.schemas.accounting import ReconciliationOut, VatReturnOut

router = APIRouter(prefix="/vat-returns", tags=["vat-returns"])


def _get_period_or_404(db: Session, user: User, company_id: int, vat_period_id: int) -> VatPeriod:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    period = db.get(VatPeriod, vat_period_id)
    if period is None or period.financial_year.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VAT period not found")
    return period


@router.get("", response_model=VatReturnOut)
def get_or_compute_vat_return(
    company_id: int, vat_period_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    period = _get_period_or_404(db, user, company_id, vat_period_id)
    vat_return = db.query(VatReturn).filter(VatReturn.vat_period_id == period.id).first()
    if vat_return is None or vat_return.status not in (VatReturnStatus.approved, VatReturnStatus.locked):
        vat_return = vat_engine.recalculate_and_store(db, company_id, user.tenant_id, period)
        db.commit()
        db.refresh(vat_return)
    return vat_return


@router.post("/{vat_return_id}/recalculate", response_model=VatReturnOut)
def recalculate(vat_return_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    vat_return = db.get(VatReturn, vat_return_id)
    if vat_return is None or vat_return.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VAT return not found")
    require_company_access(vat_return.company_id, user, db)
    try:
        vat_return = vat_engine.recalculate_and_store(db, vat_return.company_id, user.tenant_id, vat_return.vat_period)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(vat_return)
    return vat_return


@router.get("/{vat_return_id}/reconciliation", response_model=ReconciliationOut)
def get_reconciliation(vat_return_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    vat_return = db.get(VatReturn, vat_return_id)
    if vat_return is None or vat_return.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VAT return not found")
    require_company_access(vat_return.company_id, user, db)
    data = reconciliation.build_reconciliation(db, vat_return.company_id, vat_return.vat_period)
    return ReconciliationOut(vat_return=vat_return, **data)


def _transition(
    db: Session,
    user: User,
    vat_return_id: int,
    allowed_from: list[VatReturnStatus],
    to: VatReturnStatus,
    action: str,
) -> VatReturn:
    vat_return = db.get(VatReturn, vat_return_id)
    if vat_return is None or vat_return.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VAT return not found")
    require_company_access(vat_return.company_id, user, db)
    if vat_return.status not in allowed_from:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot {action} a VAT return in status {vat_return.status.value}",
        )
    vat_return.status = to
    if to == VatReturnStatus.approved:
        vat_return.approved_by_user_id = user.id
        vat_return.approved_at = datetime.now(timezone.utc)
    if to == VatReturnStatus.locked:
        vat_return.locked_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action=action,
            entity_type="vat_return",
            entity_id=vat_return.id,
        )
    )
    db.commit()
    db.refresh(vat_return)
    return vat_return


@router.post("/{vat_return_id}/submit-for-approval", response_model=VatReturnOut)
def submit_for_approval(vat_return_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    return _transition(
        db,
        user,
        vat_return_id,
        allowed_from=[VatReturnStatus.draft, VatReturnStatus.needs_review],
        to=VatReturnStatus.ready_for_approval,
        action="submit_for_approval",
    )


@router.post("/{vat_return_id}/approve", response_model=VatReturnOut)
def approve_vat_return(vat_return_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    return _transition(
        db,
        user,
        vat_return_id,
        allowed_from=[VatReturnStatus.ready_for_approval],
        to=VatReturnStatus.approved,
        action="approve",
    )


@router.post("/{vat_return_id}/lock", response_model=VatReturnOut)
def lock_vat_return(vat_return_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    vat_return = _transition(
        db,
        user,
        vat_return_id,
        allowed_from=[VatReturnStatus.approved],
        to=VatReturnStatus.locked,
        action="lock",
    )
    db.query(AccountingTransaction).filter(
        AccountingTransaction.vat_period_id == vat_return.vat_period_id
    ).update({AccountingTransaction.approval_status: TransactionApprovalStatus.locked})
    db.commit()
    return vat_return
