from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.accounting import bank_import, open_banking_service, reconciliation_service
from app.core.config import settings
from app.core.audit_redaction import redact
from app.core.deps import ADMIN_ROLES, get_current_user, require_company_access, require_editor
from app.core.rate_limit import enforce as enforce_rate_limit
from app.core.request_context import get_request_id
from app.db.session import get_db
from app.models.audit_log import AuditLog
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
    OpenBankingCallbackOut,
    OpenBankingCallbackRequest,
    OpenBankingConnectRequest,
    OpenBankingSelectAccountRequest,
    PaymentMatchOut,
    ReverseMatchRequest,
)
from app.services.open_banking_provider import DUTCH_BANKS, get_open_banking_provider, provider_status

router = APIRouter(tags=["banking"])


def _audit(db: Session, user: User, action: str, entity_type: str, entity_id: int, before: dict | None = None, after: dict | None = None) -> None:
    """Phase 15: this router previously wrote zero audit events -- bank
    account creation, statement imports, exclude/approve/reject/reverse on
    a reconciliation match, and Open Banking connect/sync/disconnect were
    all silent. Every mutating endpoint below now logs through here."""
    db.add(AuditLog(
        tenant_id=user.tenant_id, user_id=user.id, action=action, entity_type=entity_type, entity_id=entity_id,
        before=redact(before), after=redact(after), request_id=get_request_id(),
    ))


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
    db.flush()
    _audit(db, user, "create", "bank_account", account.id, after={"iban": account.iban, "account_name": account.account_name, "company_id": account.company_id})
    db.commit()
    db.refresh(account)
    return account


@router.get("/bank-accounts", response_model=list[BankAccountOut])
def list_bank_accounts(company_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(BankAccount).filter(BankAccount.tenant_id == user.tenant_id)
    if user.role not in ADMIN_ROLES:
        accessible_ids = [c.id for c in user.companies]
        query = query.filter(BankAccount.company_id.in_(accessible_ids))
    if company_id is not None:
        require_company_access(company_id, user, db)
        query = query.filter(BankAccount.company_id == company_id)
    accounts = query.all()
    for account in accounts:
        open_banking_service.refresh_status(db, account)
    db.commit()
    return accounts


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

    _audit(db, user, "import", "bank_import_batch", batch.id, after={"bank_account_id": account.id, "filename": file.filename, "source_format": source_format.value, "transaction_count": len(batch.transactions)})
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
    if user.role not in ADMIN_ROLES:
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
    _audit(db, user, "exclude", "bank_transaction", tx.id, after={"reconciliation_status": tx.reconciliation_status.value})
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
    _audit(db, user, "approve", "payment_match", match.id, after={"status": match.status, "bank_transaction_id": match.bank_transaction_id, "accounting_transaction_id": match.accounting_transaction_id})
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
    _audit(db, user, "reject", "payment_match", match.id, after={"status": match.status})
    db.commit()
    db.refresh(match)
    return match


@router.post("/payment-matches/{match_id}/reverse", response_model=PaymentMatchOut)
def reverse_payment_match(
    match_id: int, payload: ReverseMatchRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    match = _get_match_or_404(db, user, match_id)
    before_status = match.status
    try:
        reconciliation_service.reverse_match(db, match, user.id, payload.reason)
    except reconciliation_service.ReconciliationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _audit(db, user, "reverse", "payment_match", match.id, before={"status": before_status}, after={"status": match.status, "reason": payload.reason})
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
        # Phase 17.1 (audit CRITICAL-2): the tenant predicate was missing
        # entirely, and `require_company_access` used to no-op for
        # owner/admin -- so any admin of any tenant could bulk-approve
        # every HIGH-confidence suggested match on an arbitrary company's
        # books, posting real Payment rows and flipping reconciliation
        # state on someone else's ledger in one request. The helper now
        # rejects a foreign company; this predicate is defence-in-depth so
        # the query itself can never select across a tenant boundary even
        # if a future caller reaches it another way.
        .filter(
            PaymentMatch.tenant_id == user.tenant_id,
            PaymentMatch.company_id == company_id,
            PaymentMatch.status == "SUGGESTED",
            PaymentMatch.confidence_level == "HIGH",
        )
        .all()
    )
    approved = []
    for match in matches:
        try:
            reconciliation_service.approve_match(db, match, user.id)
            approved.append(match)
        except reconciliation_service.ReconciliationError:
            continue
    _audit(db, user, "bulk_approve", "payment_match", company_id, after={"approved_count": len(approved), "approved_match_ids": [m.id for m in approved]})
    db.commit()
    return approved


# ---- Phase 12: Open Banking (PSD2 AISP) -- stub provider only, see
# docs/open-banking.md. Manual file import above remains fully available
# and untouched regardless of connection status. ----


@router.get("/open-banking/status")
def open_banking_status(user: User = Depends(get_current_user)):
    """Which adapter is active and whether it is a sandbox -- the wizard
    shows this before anyone is asked to consent to anything."""
    return provider_status()


@router.get("/open-banking/banks")
def list_supported_banks(q: str | None = None, user: User = Depends(get_current_user)):
    status_info = provider_status()
    needle = (q or "").strip().lower()
    banks = [
        {**b, "available": True, "sandbox": status_info["is_sandbox"]}
        for b in DUTCH_BANKS
        if not needle or needle in b["name"].lower() or needle in b["bic"].lower() or needle in b["id"]
    ]
    return {"banks": banks, **status_info}


@router.post("/bank-accounts/{bank_account_id}/open-banking/connect")
def connect_open_banking(bank_account_id: int, payload: OpenBankingConnectRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    """Starts (or restarts, after EXPIRED/REVOKED/ERROR) a consent flow.
    Only same-origin redirect URIs are accepted: the authorization URL is
    handed back to the browser, and an attacker-controlled redirect_uri
    would turn this into an open redirect carrying a consent id."""
    account = _get_bank_account_or_404(db, user, bank_account_id)
    if payload.bank_id and not any(b["id"] == payload.bank_id for b in DUTCH_BANKS):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown bank")
    allowed_origin = settings.app_base_url.rstrip("/")
    if not (payload.redirect_uri.startswith(allowed_origin + "/") or payload.redirect_uri == allowed_origin):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uri must be on the application's own origin")
    provider = get_open_banking_provider()
    authorization_url = open_banking_service.initiate_connection(db, account, provider, payload.redirect_uri)
    _audit(db, user, "open_banking_connect_initiated", "bank_account", account.id, after={"provider": provider.name, "bank_id": payload.bank_id})
    db.commit()
    return {"authorization_url": authorization_url, "provider": provider.name, "is_sandbox": provider.name == "stub"}


@router.post("/bank-accounts/{bank_account_id}/open-banking/callback", response_model=OpenBankingCallbackOut)
def complete_open_banking(bank_account_id: int, payload: OpenBankingCallbackRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    account = _get_bank_account_or_404(db, user, bank_account_id)
    provider = get_open_banking_provider()
    try:
        candidates = open_banking_service.complete_connection(db, account, provider, payload.callback_params)
    except open_banking_service.OpenBankingError as exc:
        account.consent_status = account.consent_status  # unchanged; recorded below
        account.last_sync_error = str(exc)[:500]
        _audit(db, user, "open_banking_connect_failed", "bank_account", account.id, after={"error": str(exc)[:200]})
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _audit(db, user, "open_banking_connected" if not candidates else "open_banking_awaiting_account_selection", "bank_account", account.id, after={"provider": provider.name, "candidate_count": len(candidates)})
    db.commit()
    db.refresh(account)
    return OpenBankingCallbackOut(account=account, candidates=candidates)


@router.post("/bank-accounts/{bank_account_id}/open-banking/select-account", response_model=BankAccountOut)
def select_open_banking_account(bank_account_id: int, payload: OpenBankingSelectAccountRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    account = _get_bank_account_or_404(db, user, bank_account_id)
    try:
        open_banking_service.select_account(db, account, payload.provider_account_id)
    except open_banking_service.OpenBankingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _audit(db, user, "open_banking_connected", "bank_account", account.id, after={"provider_account_id": payload.provider_account_id})
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
    _audit(db, user, "open_banking_sync", "bank_import_batch", batch.id, after={"bank_account_id": account.id, "transaction_count": len(batch.transactions)})
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/bank-accounts/{bank_account_id}/open-banking/disconnect", response_model=BankAccountOut)
def disconnect_open_banking(bank_account_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    account = _get_bank_account_or_404(db, user, bank_account_id)
    open_banking_service.disconnect(db, account)
    _audit(db, user, "open_banking_disconnected", "bank_account", account.id)
    db.commit()
    db.refresh(account)
    return account
