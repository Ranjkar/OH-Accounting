"""Shared document-record creation: validate, hash, detect exact duplicates,
save to storage, and persist the Document row. Used by both the single-file
upload endpoint and the bulk batch-upload endpoint so the two never drift."""

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import DocumentStatus, LedgerSide
from app.models.user import User
from app.services import storage
from app.services.file_validation import CONTENT_TYPES, UnsupportedFileType, detect_kind, secure_filename, sha256_hex


def create_document_record(
    db: Session,
    user: User,
    company_id: int,
    content: bytes,
    filename: str,
    financial_year_id: int | None = None,
    upload_batch_id: int | None = None,
    upload_category: LedgerSide | None = None,
) -> Document:
    """Raises UnsupportedFileType if the content doesn't match a supported format."""
    kind = detect_kind(filename or "upload", content)  # raises UnsupportedFileType

    file_hash = sha256_hex(content)
    duplicate = (
        db.query(Document).filter(Document.company_id == company_id, Document.sha256_hash == file_hash).first()
    )

    clean_name = secure_filename(filename or "upload")
    document = Document(
        tenant_id=user.tenant_id,
        company_id=company_id,
        financial_year_id=financial_year_id,
        uploaded_by_user_id=user.id,
        upload_batch_id=upload_batch_id,
        upload_category=upload_category,
        original_filename=filename or clean_name,
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
    db.flush()
    return document


__all__ = ["create_document_record", "UnsupportedFileType"]
