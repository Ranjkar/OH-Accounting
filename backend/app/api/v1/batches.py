import csv
import io
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.accounting import ledger_service
from app.core.config import settings
from app.core.deps import ADMIN_ROLES, get_current_user, require_company_access, require_editor, require_uploader
from app.core.rate_limit import enforce as enforce_rate_limit
from app.db.session import SessionLocal, get_db
from app.models.company import Company
from app.models.document import Document, UploadBatch
from app.models.enums import DocumentStatus, LedgerSide, UserRole
from app.models.financial_year import FinancialYear
from app.models.user import User
from app.schemas.batch import (
    BatchCounts,
    BatchDetailOut,
    BatchOut,
    BatchUploadResponse,
    BulkActionItemResult,
    BulkActionResponse,
    BulkDocumentActionRequest,
    RejectedFile,
)
from app.services import batch_processing
from app.services.document_approval import (
    DocumentAlreadyApprovedError,
    DocumentNotApprovableError,
    approve_document_record,
    reject_document_record,
)
from app.services.document_intake import create_document_record
from app.services.file_validation import UnsupportedFileType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batches", tags=["batches"])


def _counts_for(documents: list[Document]) -> BatchCounts:
    return BatchCounts(
        total=len(documents),
        extracted=sum(1 for d in documents if d.status == DocumentStatus.extracted),
        needs_review=sum(1 for d in documents if d.status == DocumentStatus.needs_review),
        duplicates=sum(1 for d in documents if d.is_duplicate),
        failed=sum(1 for d in documents if d.status == DocumentStatus.failed),
        approved=sum(1 for d in documents if d.status == DocumentStatus.approved),
        pending_or_processing=sum(1 for d in documents if d.status in (DocumentStatus.pending, DocumentStatus.processing)),
        rejected=sum(1 for d in documents if d.status == DocumentStatus.rejected),
    )


def _to_batch_out(batch: UploadBatch) -> BatchOut:
    return BatchOut(
        id=batch.id,
        company_id=batch.company_id,
        financial_year_id=batch.financial_year_id,
        category=batch.category,
        status=batch.status,
        created_at=batch.created_at,
        counts=_counts_for(batch.documents),
    )


def _get_batch_or_404(db: Session, user: User, batch_id: int) -> UploadBatch:
    batch = db.get(UploadBatch, batch_id)
    if batch is None or batch.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    require_company_access(batch.company_id, user, db)
    return batch


def _run_batch_in_background(batch_id: int) -> None:
    batch_processing.process_batch(batch_id, SessionLocal)


@router.post("/upload", response_model=BatchUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    company_id: int,
    financial_year_id: int,
    category: LedgerSide,
    files: list[UploadFile],
    db: Session = Depends(get_db),
    user: User = Depends(require_uploader),
):
    enforce_rate_limit(request, "batch-upload", settings.rate_limit_upload_per_minute)
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    fy = db.get(FinancialYear, financial_year_id)
    if fy is None or fy.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")

    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No files provided")
    if len(files) > settings.batch_max_files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Batch exceeds the maximum of {settings.batch_max_files} files",
        )

    batch = UploadBatch(
        tenant_id=user.tenant_id,
        company_id=company_id,
        financial_year_id=financial_year_id,
        category=category,
        created_by_user_id=user.id,
    )
    db.add(batch)
    db.flush()

    documents: list[Document] = []
    rejected: list[RejectedFile] = []
    for file in files:
        content = await file.read()
        if len(content) > settings.max_upload_size_bytes:
            rejected.append(RejectedFile(filename=file.filename or "unknown", reason="File too large"))
            continue
        try:
            document = create_document_record(
                db,
                user,
                company_id,
                content,
                file.filename or "upload",
                financial_year_id=financial_year_id,
                upload_batch_id=batch.id,
                upload_category=category,
            )
            documents.append(document)
        except UnsupportedFileType as exc:
            rejected.append(RejectedFile(filename=file.filename or "unknown", reason=str(exc)))

    if not documents:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No files in this batch could be accepted",
        )

    db.commit()
    for d in documents:
        db.refresh(d)
    db.refresh(batch)

    background_tasks.add_task(_run_batch_in_background, batch.id)
    return BatchUploadResponse(batch=_to_batch_out(batch), documents=documents, rejected_files=rejected)


@router.get("", response_model=list[BatchOut])
def list_batches(
    company_id: int | None = None,
    category: LedgerSide | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(UploadBatch).filter(UploadBatch.tenant_id == user.tenant_id)
    if user.role not in ADMIN_ROLES:
        accessible_ids = [c.id for c in user.companies]
        query = query.filter(UploadBatch.company_id.in_(accessible_ids))
    if company_id is not None:
        require_company_access(company_id, user, db)
        query = query.filter(UploadBatch.company_id == company_id)
    if category is not None:
        query = query.filter(UploadBatch.category == category)
    batches = query.order_by(UploadBatch.created_at.desc()).all()
    return [_to_batch_out(b) for b in batches]


@router.get("/{batch_id}", response_model=BatchDetailOut)
def get_batch(batch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = _get_batch_or_404(db, user, batch_id)
    out = _to_batch_out(batch)
    return BatchDetailOut(**out.model_dump(), documents=batch.documents)


@router.post("/{batch_id}/approve", response_model=BulkActionResponse)
def bulk_approve(
    batch_id: int,
    payload: BulkDocumentActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    batch = _get_batch_or_404(db, user, batch_id)
    valid_ids = {d.id for d in batch.documents}
    results = []
    for document_id in payload.document_ids:
        if document_id not in valid_ids:
            results.append(BulkActionItemResult(document_id=document_id, success=False, detail="Not in this batch"))
            continue
        document = db.get(Document, document_id)
        try:
            approve_document_record(db, document, user)
            db.commit()
            results.append(BulkActionItemResult(document_id=document_id, success=True, detail="Approved"))
        except (DocumentNotApprovableError, ledger_service.LedgerPostingError) as exc:
            db.rollback()
            results.append(BulkActionItemResult(document_id=document_id, success=False, detail=str(exc)))
        except Exception:  # one bad document must never abort the rest of the bulk action
            logger.exception("Unexpected error approving document %s in batch %s", document_id, batch_id)
            db.rollback()
            results.append(BulkActionItemResult(document_id=document_id, success=False, detail="Unexpected error"))
    return BulkActionResponse(results=results)


@router.post("/{batch_id}/reject", response_model=BulkActionResponse)
def bulk_reject(
    batch_id: int,
    payload: BulkDocumentActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    batch = _get_batch_or_404(db, user, batch_id)
    valid_ids = {d.id for d in batch.documents}
    reason = payload.reason or "Rejected in bulk review"
    results = []
    for document_id in payload.document_ids:
        if document_id not in valid_ids:
            results.append(BulkActionItemResult(document_id=document_id, success=False, detail="Not in this batch"))
            continue
        document = db.get(Document, document_id)
        try:
            reject_document_record(db, document, user, reason)
            db.commit()
            results.append(BulkActionItemResult(document_id=document_id, success=True, detail="Rejected"))
        except DocumentAlreadyApprovedError as exc:
            db.rollback()
            results.append(BulkActionItemResult(document_id=document_id, success=False, detail=str(exc)))
    return BulkActionResponse(results=results)


@router.get("/{batch_id}/export")
def export_batch(batch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Headers are stable, untranslated snake_case identifiers (this is
    for re-import/scripting, not reading) -- same convention as every
    other CSV exporter in app/reporting/, see financial_report.render_csv's
    docstring. UTF-8 BOM so Excel correctly decodes non-ASCII content in
    filenames/error messages regardless of the viewer's locale."""
    batch = _get_batch_or_404(db, user, batch_id)
    buf = io.StringIO()
    buf.write("﻿")
    writer = csv.writer(buf)
    writer.writerow(["document_id", "filename", "category", "document_type", "status", "is_duplicate", "error_message"])
    for d in batch.documents:
        writer.writerow(
            [d.id, d.original_filename, d.upload_category.value if d.upload_category else "", d.document_type.value if d.document_type else "", d.status.value, d.is_duplicate, d.error_message or ""]
        )
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="batch-{batch_id}.csv"'},
    )
