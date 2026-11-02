from datetime import datetime

from pydantic import BaseModel

from app.models.enums import BatchStatus, LedgerSide
from app.schemas.document import DocumentOut


class RejectedFile(BaseModel):
    filename: str
    reason: str


class BatchCounts(BaseModel):
    total: int
    extracted: int
    needs_review: int
    duplicates: int
    failed: int
    approved: int
    pending_or_processing: int
    rejected: int


class BatchOut(BaseModel):
    id: int
    company_id: int
    financial_year_id: int
    category: LedgerSide
    status: BatchStatus
    created_at: datetime
    counts: BatchCounts


class BatchUploadResponse(BaseModel):
    batch: BatchOut
    documents: list[DocumentOut]
    rejected_files: list[RejectedFile]


class BatchDetailOut(BatchOut):
    documents: list[DocumentOut]


class BulkDocumentActionRequest(BaseModel):
    document_ids: list[int]
    reason: str | None = None  # required for reject


class BulkActionItemResult(BaseModel):
    document_id: int
    success: bool
    detail: str


class BulkActionResponse(BaseModel):
    results: list[BulkActionItemResult]
