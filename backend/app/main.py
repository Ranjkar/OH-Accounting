import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_v1_router
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def _recover_stuck_processing_documents() -> None:
    """A document (or batch document) stuck in PROCESSING means the process
    died mid-flight on the last run -- nothing could legitimately still be
    processing at startup. Reset to PENDING so it gets picked up on the next
    reprocess rather than staying stuck forever."""
    from app.models.document import Document
    from app.models.enums import DocumentStatus

    db = SessionLocal()
    try:
        stuck = db.query(Document).filter(Document.status == DocumentStatus.processing).all()
        for doc in stuck:
            doc.status = DocumentStatus.pending
        if stuck:
            db.commit()
            logger.warning("Reset %d document(s) stuck in PROCESSING after restart to PENDING", len(stuck))
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _recover_stuck_processing_documents()
    yield


app = FastAPI(title="OnHolland Accounting API", lifespan=lifespan)

# Comma-separated allowed origins via CORS_ALLOWED_ORIGINS, defaulting to the
# local dev frontend. Production deployments must set this explicitly --
# never widen this to "*" once credentials are allowed.
_allowed_origins = [
    o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
