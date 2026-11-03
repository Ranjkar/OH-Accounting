from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.accounting import bank_import, open_banking_service, reconciliation_service
from app.core.config import settings
from app.core.deps import get_current_user, require_company_access, require_editor
from app.core.rate_limit import enforce as enforce_rate_limit
from app.db.session import get_db
from app.models.banking import BankAccount, BankImportBatch, BankTransaction, PaymentMatch
from app.models.company import Company
from app.models.enums import BankSourceFormat, ReconciliationStatus, UserRole
from app.models.user import User
from app.schemas.banking import (
    BankAccountCreate,
    BankAccountOut,
    BankImportBatchOut,
    BankTransactionDetailOut,
    BankTransactionOut,
    OpenBankingCallbackRequest,
    OpenBankingConnectRequest,
    PaymentMatchOut,
    ReverseMatchRequest,
)
from app.services.open_banking_provider import get_open_banking_provider

router = APIRouter(tags=["banking"])


def _get_bank_account_or_404(db: Session, user: User, bank_account_id: int) -> BankAccount:
    account = db.get(BankAccount, bank_account_id)
    if account is None or account.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    require_company_access(account.company_id, user, db)
    return account


def _get_bank_transaction_or_404(db: Session, user: User, bank_transaction_id: int) -> BankTransaction:
    tx = db.get(BankTransaction, bank_transaction_id)
    if tx is None or tx.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank transaction not found")
    require_company_access(tx.company_id, user, db)
    return tx


def _get_match_or_404(db: Session, user: User, match_id: int) -> PaymentMatch:
    match = db.get(PaymentMatch, match_id)
    if match is None or match.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment match not found")
    require_company_access(match.company_id, user, db)
    return match


@router.post("/bank-accounts", response_model=BankAccountOut, status_code=status.HTTP_201_CREATED)
def create_bank_account(payload: BankAccountCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    require_company_access(payload.company_id, user, db)
    company = db.get(Company, payload.company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    existing = db.query(BankAccount).filter(BankAccount.company_id == payload.company_id, BankAccount.iban == payload.iban).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This IBAN is already registered for this company")

    account = BankAccount(
        tenant_id=user.tenant_id, company_id=payload.company_id, iban=payload.iban,
        account_name=payload.account_name, currency=payload.currency,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/bank-accounts", response_model=list[BankAccountOut])
def list_bank_accounts(company_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(BankAccount).filter(BankAccount.tenant_id == user.tenant_id)
    if user.role != UserRole.admin:
        accessible_ids = [c.id for c in user.companies]
        query = query.filter(BankAccount.company_id.in_(accessible_ids))
    if company_id is not None:
        require_company_access(company_id, user, db)
        query = query.filter(BankAccount.company_id == company_id)
    return query.all()


@router.post("/bank-accounts/{bank_account_id}/import", response_model=BankImportBatchOut, status_code=status.HTTP_201_CREATED)
async def import_bank_statement(
    request: Request,
    bank_account_id: int,
    source_format: BankSourceFormat,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    enforce_rate_limit(request, "upload", settings.rate_limit_upload_per_minute)
    account = _get_bank_account_or_404(db, user, bank_account_id)
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    try:
        batch = bank_import.import_bank_file(db, account, content, file.filename or "statement", source_format, user.id)
    except bank_import.BankImportError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    for bank_tx in batch.transactions:
        reconciliation_service.generate_suggestions(db, bank_tx)

    db.commit()
    db.refresh(batch)
    return batch


@router.get("/bank-accounts/{bank_account_id}/import-batches", response_model=list[BankImportBatchOut])
def list_import_batches(bank_account_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    account = _get_bank_account_or_404(db, user, bank_account_id)
    return (
        db.query(BankImportBatch)
        .filter(BankImportBatch.bank_account_id == account.id)
        .order_by(BankImportBatch.imported_at.desc())
        .all()
    )


@router.get("/bank-transactions", response_model=list[BankTransactionOut])
def list_bank_transactions(
    company_id: int | None = None,
    bank_account_id: int | None = None,
    reconciliation_status: ReconciliationStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(BankTransaction).filter(BankTransaction.tenant_id == user.tenant_id)
    if user.role != UserRole.admin:
        accessible_ids = [c.id for c in user.companies]
        query = query.filter(BankTransaction.company_id.in_(accessible_ids))
    if company_id is not None:
        require_company_access(company_id, user, db)
        query = query.filter(BankTransaction.company_id == company_id)
    if bank_account_id is not None:
        query = query.filter(BankTransaction.bank_account_id == bank_account_id)
    if reconciliation_status is not None:
        query = query.filter(BankTransaction.reconciliation_status == reconciliation_status)
    return query.order_by(BankTransaction.booking_date.desc()).all()


@router.get("/bank-transactions/{bank_transaction_id}", response_model=BankTransactionDetailOut)
def get_bank_transaction(bank_transaction_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tx = _get_bank_transaction_or_404(db, user, bank_transaction_id)
    return BankTransactionDetailOut(
        **BankTransactionOut.model_validate(tx).model_dump(),
        matches=[m for m in tx.matches if m.status != "REJECTED"],
    )


@router.post("/bank-transactions/{bank_transaction_id}/suggest-matches", response_model=list[PaymentMatchOut])
def regenerate_suggestions(bank_transaction_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    tx = _get_bank_transaction_or_404(db, user, bank_transaction_id)
    matches = reconciliation_service.generate_suggestions(db, tx)
    db.commit()
    return matches


@router.post("/bank-transactions/{bank_transaction_id}/exclude", response_model=BankTransactionOut)
def exclude_bank_transaction(bank_transaction_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    tx = _get_bank_transaction_or_404(db, user, bank_transaction_id)
    reconciliation_service.exclude_transaction(db, tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.post("/payment-matches/{match_id}/approve", response_model=PaymentMatchOut)
def approve_payment_match(match_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    match = _get_match_or_404(db, user, match_id)
    try:
        reconciliation_service.approve_match(db, match, user.id)
    except reconciliation_service.ReconciliationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(match)
    return match


@router.post("/payment-matches/{match_id}/reject", response_model=PaymentMatchOut)
def reject_payment_match(match_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    match = _get_match_or_404(db, user, match_id)
    try:
        reconciliation_service.reject_match(db, match)
    except reconciliation_service.ReconciliationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(match)
    return match


@router.post("/payment-matches/{match_id}/reverse", response_model=PaymentMatchOut)
def reverse_payment_match(
    match_id: int, payload: ReverseMatchRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    match = _get_match_or_404(db, user, match_id)
    try:
        reconciliation_service.reverse_match(db, match, user.id, payload.reason)
    except reconciliation_service.ReconciliationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(match)
    return match


@router.post("/payment-matches/bulk-approve-high-confidence", response_model=list[PaymentMatchOut])
def bulk_approve_high_confidence(
    company_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    """Automation-centre convenience: approve every still-SUGGESTED, HIGH-
    confidence match for a company in one action. Never touches MEDIUM/LOW --
    those always require individual review."""
    require_company_access(company_id, user, db)
    matches = (
        db.query(PaymentMatch)
        .filter(PaymentMatch.company_id == company_id, PaymentMatch.status == "SUGGESTED", PaymentMatch.confidence_level == "HIGH")
        .all()
    )
    approved = []
    for match in matches:
        try:
            reconciliation_service.approve_match(db, match, user.id)
            approved.append(match)
        except reconciliation_service.ReconciliationError:
            continue
    db.commit()
    return approved


# ---- Phase 12: Open Banking (PSD2 AISP) -- stub provider only, see
# docs/open-banking.md. Manual file import above remains fully available
# and untouched regardless of connection status. ----


@router.post("/bank-accounts/{bank_account_id}/open-banking/connect")
def connect_open_banking(bank_account_id: int, payload: OpenBankingConnectRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    account = _get_bank_account_or_404(db, user, bank_account_id)
    provider = get_open_banking_provider()
    authorization_url = open_banking_service.initiate_connection(db, account, provider, payload.redirect_uri)
    db.commit()
    return {"authorization_url": authorization_url, "provider": provider.name}


@router.post("/bank-accounts/{bank_account_id}/open-banking/callback", response_model=BankAccountOut)
def complete_open_banking(bank_account_id: int, payload: OpenBankingCallbackRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    account = _get_bank_account_or_404(db, user, bank_account_id)
    provider = get_open_banking_provider()
    try:
        open_banking_service.complete_connection(db, account, provider, payload.callback_params)
    except open_banking_service.OpenBankingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return account


@router.post("/bank-accounts/{bank_account_id}/open-banking/sync", response_model=BankImportBatchOut)
def sync_open_banking(bank_account_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    account = _get_bank_account_or_404(db, user, bank_account_id)
    provider = get_open_banking_provider()
    try:
        batch = open_banking_service.sync_account(db, account, provider, user.id)
    except open_banking_service.OpenBankingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/bank-accounts/{bank_account_id}/open-banking/disconnect", response_model=BankAccountOut)
def disconnect_open_banking(bank_account_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    account = _get_bank_account_or_404(db, user, bank_account_id)
    open_banking_service.disconnect(db, account)
    db.commit()
    db.refresh(account)
    return account
