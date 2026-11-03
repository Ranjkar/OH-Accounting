import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

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

@app.middleware("http")
async def _security_headers(request, call_next):
    """Defense-in-depth headers that make sense regardless of what sits in
    front of this app. HTTPS itself (Strict-Transport-Security, TLS
    termination) is a reverse-proxy/load-balancer concern, not set here --
    see docs/production-deployment.md."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
def health():
    """Checks real DB connectivity, not just that the process is alive --
    an orchestrator restarting on a DB outage is more useful than one that
    keeps routing traffic to a process that can't actually serve requests."""
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as exc:
        return Response(content=f'{{"status": "error", "detail": "{exc.__class__.__name__}"}}', status_code=503, media_type="application/json")
    return {"status": "ok"}
