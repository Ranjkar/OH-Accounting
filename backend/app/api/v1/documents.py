import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import ADMIN_ROLES, get_current_user, require_company_access, require_editor, require_uploader
from app.core.rate_limit import enforce as enforce_rate_limit
from app.db.session import SessionLocal, get_db
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.document import Document, ExtractedInvoiceFields
from app.models.enums import DocumentStatus, UserRole
from app.models.financial_year import FinancialYear
from app.models.user import User
from app.schemas.document import (
    ApproveDocumentRequest,
    DocumentDetailOut,
    DocumentOut,
    ExtractedFieldsUpdate,
    ReassignRequest,
    RejectRequest,
)
from app.accounting import ledger_service
from app.services import document_processing, storage
from app.services.document_approval import (
    DocumentAlreadyApprovedError,
    DocumentNotApprovableError,
    approve_document_record,
    reject_document_record,
)
from app.services.document_intake import create_document_record
from app.services.file_validation import UnsupportedFileType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_document_or_404(db: Session, user: User, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    require_company_access(document.company_id, user, db)
    return document


def _run_processing_in_background(document_id: int) -> None:
    db = SessionLocal()
    try:
        document_processing.process_document(db, document_id)
    finally:
        db.close()


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    company_id: int,
    file: UploadFile,
    financial_year_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_uploader),
):
    enforce_rate_limit(request, "upload", settings.rate_limit_upload_per_minute)
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    if financial_year_id is not None:
        fy = db.get(FinancialYear, financial_year_id)
        if fy is None or fy.company_id != company_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")

    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    try:
        document = create_document_record(
            db, user, company_id, content, file.filename or "upload", financial_year_id=financial_year_id
        )
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    db.commit()
    db.refresh(document)

    background_tasks.add_task(_run_processing_in_background, document.id)
    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(
    company_id: int | None = None,
    status_filter: DocumentStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Document).filter(Document.tenant_id == user.tenant_id)
    if user.role not in ADMIN_ROLES:
        accessible_ids = [c.id for c in user.companies]
        query = query.filter(Document.company_id.in_(accessible_ids))
    if company_id is not None:
        require_company_access(company_id, user, db)
        query = query.filter(Document.company_id == company_id)
    if status_filter is not None:
        query = query.filter(Document.status == status_filter)
    return query.order_by(Document.created_at.desc()).all()


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _get_document_or_404(db, user, document_id)


@router.get("/{document_id}/file")
def download_document_file(
    document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    document = _get_document_or_404(db, user, document_id)
    content = storage.read(document.storage_path)
    return Response(
        content=content,
        media_type=document.content_type,
        headers={"Content-Disposition": f'inline; filename="{document.secure_filename}"'},
    )


@router.post("/{document_id}/reprocess", response_model=DocumentOut)
def reprocess_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    document = _get_document_or_404(db, user, document_id)
    if document.status == DocumentStatus.approved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot reprocess an approved document")
    document.status = DocumentStatus.pending
    document.error_message = None
    db.commit()
    background_tasks.add_task(_run_processing_in_background, document.id)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="reprocess",
            entity_type="document",
            entity_id=document.id,
        )
    )
    db.commit()
    db.refresh(document)
    return document


@router.patch("/{document_id}/fields", response_model=DocumentDetailOut)
def update_fields(
    document_id: int,
    payload: ExtractedFieldsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    document = _get_document_or_404(db, user, document_id)
    if document.status == DocumentStatus.approved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document already approved")

    fields = document.fields
    if fields is None:
        fields = ExtractedInvoiceFields(document_id=document.id)
        db.add(fields)

    before = {
        k: (v.isoformat() if hasattr(v, "isoformat") else v)
        for k, v in vars(fields).items()
        if not k.startswith("_")
    }
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(fields, key, value)
    fields.review_status = "pending"

    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="correct",
            entity_type="document",
            entity_id=document.id,
            before={k: before.get(k) for k in updates},
            after={k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in updates.items()},
        )
    )
    db.commit()
    db.refresh(document)
    return document


@router.post("/{document_id}/approve", response_model=DocumentOut)
def approve_document(
    document_id: int,
    payload: ApproveDocumentRequest = ApproveDocumentRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    document = _get_document_or_404(db, user, document_id)
    try:
        approve_document_record(db, document, user, credit_note_ledger_side=payload.credit_note_ledger_side)
    except DocumentNotApprovableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ledger_service.LedgerPostingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrityError as exc:
        # Phase 19 (audit 6.6): uq_accounting_transaction_source_document means
        # a concurrent approval of this same document won the race and already
        # posted it. Report a conflict rather than a 500, and roll back so the
        # session is usable again -- an IntegrityError leaves it in a failed
        # state that would otherwise break every subsequent query on it.
        db.rollback()
        logger.warning(
            "concurrent_approval_blocked document_id=%s user_id=%s", document_id, user.id
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has already been posted to the ledger by a concurrent request",
        ) from exc
    db.commit()
    db.refresh(document)
    return document


@router.post("/{document_id}/reject", response_model=DocumentOut)
def reject_document(
    document_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    document = _get_document_or_404(db, user, document_id)
    try:
        reject_document_record(db, document, user, payload.reason)
    except DocumentAlreadyApprovedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(document)
    return document


@router.patch("/{document_id}/assignment", response_model=DocumentOut)
def reassign_document(
    document_id: int,
    payload: ReassignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    document = _get_document_or_404(db, user, document_id)
    before = {"company_id": document.company_id, "financial_year_id": document.financial_year_id}

    if payload.company_id is not None:
        require_company_access(payload.company_id, user, db)
        new_company = db.get(Company, payload.company_id)
        if new_company is None or new_company.tenant_id != user.tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        document.company_id = payload.company_id

    if payload.financial_year_id is not None:
        fy = db.get(FinancialYear, payload.financial_year_id)
        if fy is None or fy.company_id != document.company_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")
        document.financial_year_id = payload.financial_year_id

    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="reassign",
            entity_type="document",
            entity_id=document.id,
            before=before,
            after={"company_id": document.company_id, "financial_year_id": document.financial_year_id},
        )
    )
    db.commit()
    db.refresh(document)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    """Remove an unprocessed/failed/rejected file. Never allowed once approved
    and posted to the ledger -- that requires a correction, not a deletion."""
    document = _get_document_or_404(db, user, document_id)
    if document.status == DocumentStatus.approved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot delete an approved document")

    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="delete",
            entity_type="document",
            entity_id=document.id,
            before={"original_filename": document.original_filename, "status": document.status.value},
        )
    )
    storage_path = document.storage_path
    db.delete(document)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete: another document references this one as a duplicate match",
        ) from exc
    storage.delete(storage_path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
