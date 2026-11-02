import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_company_access, require_editor
from app.db.session import SessionLocal, get_db
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.document import Document, ExtractedInvoiceFields
from app.models.enums import DocumentStatus, UserRole
from app.models.financial_year import FinancialYear
from app.models.user import User
from app.schemas.document import (
    DocumentDetailOut,
    DocumentOut,
    ExtractedFieldsUpdate,
    ReassignRequest,
    RejectRequest,
)
from app.services import document_processing, storage
from app.services.file_validation import CONTENT_TYPES, UnsupportedFileType, detect_kind, secure_filename, sha256_hex

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
    background_tasks: BackgroundTasks,
    company_id: int,
    file: UploadFile,
    financial_year_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
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
        kind = detect_kind(file.filename or "upload", content)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    file_hash = sha256_hex(content)
    duplicate = (
        db.query(Document)
        .filter(Document.company_id == company_id, Document.sha256_hash == file_hash)
        .first()
    )

    clean_name = secure_filename(file.filename or "upload")
    document = Document(
        tenant_id=user.tenant_id,
        company_id=company_id,
        financial_year_id=financial_year_id,
        uploaded_by_user_id=user.id,
        original_filename=file.filename or clean_name,
        secure_filename=clean_name,
        storage_path="",
        content_type=CONTENT_TYPES[kind],
        file_size=len(content),
        sha256_hash=file_hash,
        status=DocumentStatus.pending,
        is_duplicate=duplicate is not None,
        duplicate_of_document_id=duplicate.id if duplicate else None,
    )
    db.add(document)
    db.flush()

    document.storage_path = storage.save(user.tenant_id, company_id, document.id, clean_name, content)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="upload",
            entity_type="document",
            entity_id=document.id,
            after={"original_filename": document.original_filename, "sha256_hash": file_hash},
        )
    )
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
    if user.role != UserRole.admin:
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
def approve_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    document = _get_document_or_404(db, user, document_id)
    if document.status not in (DocumentStatus.extracted, DocumentStatus.needs_review):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only extracted or needs-review documents can be approved",
        )
    document.status = DocumentStatus.approved
    if document.fields:
        document.fields.review_status = "approved"
        document.fields.reviewed_by_user_id = user.id
        document.fields.reviewed_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="approve",
            entity_type="document",
            entity_id=document.id,
        )
    )
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
    if document.status == DocumentStatus.approved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document already approved")
    document.status = DocumentStatus.rejected
    if document.fields:
        document.fields.review_status = "rejected"
        document.fields.reviewed_by_user_id = user.id
        document.fields.reviewed_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="reject",
            entity_type="document",
            entity_id=document.id,
            after={"reason": payload.reason},
        )
    )
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
