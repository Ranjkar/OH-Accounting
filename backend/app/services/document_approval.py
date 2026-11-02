"""Shared approve/reject logic for documents -- used by both the single-
document endpoints and the bulk batch-approval endpoint so the two workflows
can never drift (same ledger posting, same audit trail, same status rules)."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.accounting import ledger_service
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import DocumentStatus, LedgerSide
from app.models.user import User


class DocumentNotApprovableError(Exception):
    pass


class DocumentAlreadyApprovedError(Exception):
    pass


def approve_document_record(
    db: Session, document: Document, user: User, credit_note_ledger_side: LedgerSide | None = None
) -> Document:
    if document.status not in (DocumentStatus.extracted, DocumentStatus.needs_review):
        raise DocumentNotApprovableError("Only extracted or needs-review documents can be approved")

    # Bulk uploads already know which ledger a credit note belongs to --
    # the screen the accountant uploaded it through -- so default to that
    # instead of asking again.
    if credit_note_ledger_side is None and document.upload_category is not None:
        credit_note_ledger_side = document.upload_category

    transaction = None
    if ledger_service.is_postable(document.document_type):
        transaction = ledger_service.post_document_to_ledger(
            db, document, user.id, credit_note_ledger_side=credit_note_ledger_side
        )  # raises LedgerPostingError, left for the caller to handle

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
            after={"accounting_transaction_id": transaction.id} if transaction else None,
        )
    )
    db.flush()
    return document


def reject_document_record(db: Session, document: Document, user: User, reason: str) -> Document:
    if document.status == DocumentStatus.approved:
        raise DocumentAlreadyApprovedError("Document already approved")
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
            after={"reason": reason},
        )
    )
    db.flush()
    return document
