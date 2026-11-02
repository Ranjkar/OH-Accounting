"""Bounded-concurrency batch processing.

No Celery/Redis: a ThreadPoolExecutor sized by settings.batch_max_concurrency
keeps us from firing every document's Claude call at once, while each worker
opens its own DB session (SQLAlchemy sessions aren't thread-safe to share).
Each document's own process_document() already isolates failures -- one bad
file never stops the rest of the batch.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import UploadBatch
from app.models.enums import BatchStatus
from app.services import document_processing

logger = logging.getLogger(__name__)


def _process_one(session_factory: Callable[[], Session], document_id: int) -> None:
    db = session_factory()
    try:
        document_processing.process_document(db, document_id)
    except Exception:
        logger.exception("Unhandled error processing document %s in batch", document_id)
    finally:
        db.close()


def process_batch(batch_id: int, session_factory: Callable[[], Session]) -> None:
    db = session_factory()
    try:
        batch = db.get(UploadBatch, batch_id)
        if batch is None:
            return
        document_ids = [d.id for d in batch.documents]
    finally:
        db.close()

    with ThreadPoolExecutor(max_workers=max(1, settings.batch_max_concurrency)) as executor:
        list(executor.map(lambda doc_id: _process_one(session_factory, doc_id), document_ids))

    db = session_factory()
    try:
        batch = db.get(UploadBatch, batch_id)
        if batch is not None:
            batch.status = BatchStatus.completed
            db.commit()
    finally:
        db.close()
