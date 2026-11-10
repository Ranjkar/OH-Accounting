from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.accounting import ledger_service, payment_engine
from app.accounting.period_assignment import assign_vat_period_on_payment
from app.core.deps import ADMIN_ROLES, get_current_user, require_company_access, require_editor
from app.db.session import get_db
from app.models.accounting import AccountingTransaction, Payment, TransactionLineItem
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.enums import PaymentStatus, TransactionApprovalStatus, TransactionType, UserRole
from app.models.financial_year import FinancialYear
from app.models.user import User
from app.schemas.accounting import (
    CorrectionCreate,
    LineItemEligibilityUpdate,
    ManualEntryCreate,
    PaymentCreate,
    PaymentOut,
    TransactionDetailOut,
    TransactionOut,
    TransactionUpdate,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _get_transaction_or_404(db: Session, user: User, transaction_id: int) -> AccountingTransaction:
    transaction = db.get(AccountingTransaction, transaction_id)
    if transaction is None or transaction.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    require_company_access(transaction.company_id, user, db)
    return transaction


def _to_detail(transaction: AccountingTransaction) -> TransactionDetailOut:
    paid = payment_engine.total_paid(transaction.payments)
    return TransactionDetailOut(
        **TransactionOut.model_validate(transaction).model_dump(),
        line_items=transaction.line_items,
        payments=transaction.payments,
        amount_paid=paid,
        remaining_balance=payment_engine.remaining_balance(transaction.gross_amount, transaction.payments),
    )


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    company_id: int | None = None,
    vat_period_id: int | None = None,
    transaction_type: TransactionType | None = None,
    payment_status: PaymentStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(AccountingTransaction).filter(AccountingTransaction.tenant_id == user.tenant_id)
    if user.role not in ADMIN_ROLES:
        accessible_ids = [c.id for c in user.companies]
        query = query.filter(AccountingTransaction.company_id.in_(accessible_ids))
    if company_id is not None:
        require_company_access(company_id, user, db)
        query = query.filter(AccountingTransaction.company_id == company_id)
    if vat_period_id is not None:
        query = query.filter(AccountingTransaction.vat_period_id == vat_period_id)
    if transaction_type is not None:
        query = query.filter(AccountingTransaction.transaction_type == transaction_type)
    if payment_status is not None:
        query = query.filter(AccountingTransaction.payment_status == payment_status)
    return query.order_by(AccountingTransaction.invoice_date.desc()).all()


@router.get("/{transaction_id}", response_model=TransactionDetailOut)
def get_transaction(transaction_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    transaction = _get_transaction_or_404(db, user, transaction_id)
    return _to_detail(transaction)


@router.post("", response_model=TransactionDetailOut, status_code=status.HTTP_201_CREATED)
def create_manual_entry(
    payload: ManualEntryCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    require_company_access(payload.company_id, user, db)
    company = db.get(Company, payload.company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    financial_year = db.get(FinancialYear, payload.financial_year_id)
    if financial_year is None or financial_year.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")

    try:
        transaction = ledger_service.create_manual_entry(
            db,
            tenant_id=user.tenant_id,
            company=company,
            financial_year_id=financial_year.id,
            ledger_side=payload.ledger_side,
            invoice_date=payload.invoice_date,
            due_date=payload.due_date,
            currency=payload.currency,
            fx_rate_to_eur=payload.fx_rate_to_eur,
            counterparty_name=payload.counterparty_name,
            counterparty_vat_number=payload.counterparty_vat_number,
            accounting_classification=payload.accounting_classification,
            line_items=[item.model_dump() for item in payload.line_items],
            created_by_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ledger_service.LedgerPostingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="create",
            entity_type="accounting_transaction",
            entity_id=transaction.id,
            after={"transaction_type": "MANUAL_ENTRY", "gross_amount": str(transaction.gross_amount)},
        )
    )
    db.commit()
    db.refresh(transaction)
    return _to_detail(transaction)


@router.patch("/{transaction_id}", response_model=TransactionDetailOut)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    transaction = _get_transaction_or_404(db, user, transaction_id)
    if transaction.approval_status != TransactionApprovalStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft transactions can be edited directly; use the corrections endpoint instead",
        )

    before = {
        "fx_rate_to_eur": str(transaction.fx_rate_to_eur) if transaction.fx_rate_to_eur else None,
        "due_date": transaction.due_date.isoformat() if transaction.due_date else None,
        "accounting_classification": transaction.accounting_classification,
    }

    if payload.fx_rate_to_eur is not None:
        ledger_service.apply_fx_rate(db, transaction, payload.fx_rate_to_eur)
    if payload.due_date is not None:
        transaction.due_date = payload.due_date
    if payload.accounting_classification is not None:
        transaction.accounting_classification = payload.accounting_classification

    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="correct",
            entity_type="accounting_transaction",
            entity_id=transaction.id,
            before=before,
            after=payload.model_dump(exclude_unset=True, mode="json"),
        )
    )
    db.commit()
    db.refresh(transaction)
    return _to_detail(transaction)


@router.patch("/{transaction_id}/line-items/{line_item_id}", response_model=TransactionDetailOut)
def update_line_item_eligibility(
    transaction_id: int,
    line_item_id: int,
    payload: LineItemEligibilityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    transaction = _get_transaction_or_404(db, user, transaction_id)
    if transaction.approval_status != TransactionApprovalStatus.draft:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transaction is no longer in draft")

    line = db.get(TransactionLineItem, line_item_id)
    if line is None or line.transaction_id != transaction.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")

    from app.accounting import vat_rules

    before = {"input_vat_eligibility": line.input_vat_eligibility.value if line.input_vat_eligibility else None}
    line.input_vat_eligibility = payload.input_vat_eligibility
    line.deductible_vat_amount = vat_rules.compute_deductible_vat(
        line.vat_amount, payload.input_vat_eligibility, transaction.company.input_vat_pro_rata_percentage
    )

    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="correct",
            entity_type="transaction_line_item",
            entity_id=line.id,
            before=before,
            after={"input_vat_eligibility": payload.input_vat_eligibility.value},
        )
    )
    db.commit()
    db.refresh(transaction)
    return _to_detail(transaction)


@router.post("/{transaction_id}/approve", response_model=TransactionDetailOut)
def approve_transaction(transaction_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    transaction = _get_transaction_or_404(db, user, transaction_id)
    if transaction.approval_status != TransactionApprovalStatus.draft:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transaction is not in draft")
    transaction.approval_status = TransactionApprovalStatus.approved
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="approve",
            entity_type="accounting_transaction",
            entity_id=transaction.id,
        )
    )
    db.commit()
    db.refresh(transaction)
    return _to_detail(transaction)


@router.post("/{transaction_id}/payments", response_model=TransactionDetailOut, status_code=status.HTTP_201_CREATED)
def record_payment(
    transaction_id: int, payload: PaymentCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    transaction = _get_transaction_or_404(db, user, transaction_id)
    payment = Payment(
        tenant_id=transaction.tenant_id,
        company_id=transaction.company_id,
        transaction_id=transaction.id,
        amount=payload.amount,
        payment_date=payload.payment_date,
        reference=payload.reference,
        created_by_user_id=user.id,
    )
    db.add(payment)
    db.flush()

    # Phase 19 (audit 6.2): for a cash-based company the VAT period is the one
    # containing the payment date, which is not knowable until now. Without
    # this the transaction keeps vat_period=NULL forever and is excluded from
    # every VAT return. No-op for invoice-based companies and for transactions
    # that already have a period.
    assign_vat_period_on_payment(db, transaction, payment.payment_date)

    transaction.payment_status = payment_engine.compute_payment_status(
        transaction.gross_amount, transaction.due_date, transaction.payments, date.today()
    )

    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="record_payment",
            entity_type="accounting_transaction",
            entity_id=transaction.id,
            after={"amount": str(payload.amount), "payment_date": payload.payment_date.isoformat()},
        )
    )
    db.commit()
    db.refresh(transaction)
    return _to_detail(transaction)


@router.post("/{transaction_id}/corrections", response_model=TransactionDetailOut, status_code=status.HTTP_201_CREATED)
def create_correction(
    transaction_id: int,
    payload: CorrectionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    original = _get_transaction_or_404(db, user, transaction_id)
    financial_year = db.get(FinancialYear, payload.financial_year_id)
    if financial_year is None or financial_year.company_id != original.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")

    try:
        correction = ledger_service.create_correction(
            db,
            original,
            [item.model_dump() for item in payload.line_items],
            created_by_user_id=user.id,
            financial_year_id=financial_year.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ledger_service.LedgerPostingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="correction",
            entity_type="accounting_transaction",
            entity_id=original.id,
            after={"correction_transaction_id": correction.id},
        )
    )
    db.commit()
    db.refresh(correction)
    return _to_detail(correction)
