import ipaddress
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import router as api_v1_router
from app.core.config import PERMISSIVE_ENVIRONMENTS, settings
from app.core.request_context import request_id_ctx as _request_id_ctx
from app.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)

# ---- Phase 12: structured logging with request correlation ----
# contextvar definition lives in app.core.request_context (moved there in
# Phase 15 so AuditLog writers can read it too) -- imported here under its
# original local name so the rest of this file is unchanged.


class _JsonLogFormatter(logging.Formatter):
    """One JSON object per line -- structured for a log aggregator, not
    pretty-printed for a terminal. Never logs request bodies, headers, or
    anything from app.core.crypto -- BSN, tokens, and passwords are never
    passed to the logger anywhere in this codebase (grepped, not assumed)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _request_id_ctx.get(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _configure_structured_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonLogFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


_configure_structured_logging()


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
    o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://192.168.68.105:3000").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validate_cors_origins() -> None:
    """Phase 17.4 (audit 6.9/8.1): fail closed on a CORS allow-list that is
    not safe to serve credentialed requests from.

    `allow_credentials=True` means any origin on this list can make
    authenticated cross-origin calls to the API, so the list is a security
    boundary rather than a convenience. Three things are rejected outside
    local development:

      * `*` -- with credentials this is refused by browsers anyway, but it
        signals the list was never thought about;
      * a host that is a private, loopback or link-local IP address -- e.g.
        the `192.168.68.105` developer LAN address currently baked into the
        default above, which would let any device on that network make
        credentialed calls to a deployed API;
      * a plain `http://` origin -- credentialed cross-origin calls over
        cleartext are interceptable.

    In local development these are warnings, so `npm run dev` against
    `http://localhost:3000` keeps working unchanged.
    """
    # (origin, reason, worth-warning-about-in-a-permissive-environment)
    problems: list[tuple[str, str, bool]] = []
    for origin in _allowed_origins:
        if origin == "*":
            problems.append((origin, "wildcard origin with allow_credentials=True", True))
            continue
        parsed = urlparse(origin)
        if parsed.scheme not in ("http", "https"):
            problems.append((origin, "not an http(s) origin", False))
            continue
        host = parsed.hostname or ""
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None  # a DNS name, not a literal IP
        is_loopback = host in ("localhost", "[::1]") or (address is not None and address.is_loopback)
        if address is not None and (address.is_private or address.is_loopback or address.is_link_local):
            kind = "host is a private/loopback/link-local address"
        elif parsed.scheme != "https" and address is None:
            kind = "plain http:// origin carrying credentials"
        else:
            continue
        # Loopback is the documented local-dev default, so flagging it in a
        # permissive environment would print noise on every startup and train
        # people to ignore the warning that actually matters -- the LAN address.
        problems.append((origin, kind, not is_loopback))

    if not problems:
        return

    if settings.environment.strip().lower() in PERMISSIVE_ENVIRONMENTS:
        for origin, kind, worth_warning in problems:
            if worth_warning:
                logger.warning(
                    "CORS_ALLOWED_ORIGINS contains %r: %s (acceptable in local development only).",
                    origin,
                    kind,
                )
        return

    detail = "\n".join(f"  - {origin!r}: {kind}" for origin, kind, _ in problems)
    raise RuntimeError(
        "Refusing to start: CORS_ALLOWED_ORIGINS is not safe for a credentialed deployment:\n"
        + detail
        + "\n\nSet CORS_ALLOWED_ORIGINS to the public https origin(s) of the deployed frontend. "
        "See docs/QWEN_TECHNICAL_AUDIT_REPORT.md sections 6.9 and 8.1."
    )


_validate_cors_origins()

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


@app.middleware("http")
async def _request_correlation_and_timing(request: Request, call_next):
    """Every request gets an id -- the caller's own X-Request-ID if it sent
    one (so a request can be traced end-to-end from an upstream proxy),
    otherwise a generated one. Every log line emitted while handling this
    request carries it (via the contextvar _JsonLogFormatter reads), and
    it's echoed back in the response so a client/operator can correlate a
    specific response with its server-side log lines. Also logs method,
    path, status, and duration -- the "API response time monitoring" and
    "HTTP error rates" signals, without adding a metrics backend."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = _request_id_ctx.set(request_id)
    start = time.monotonic()
    try:
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.monotonic() - start) * 1000
            logger.exception("request_failed method=%s path=%s duration_ms=%.1f", request.method, request.url.path, duration_ms)
            raise
        duration_ms = (time.monotonic() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        log_level = logger.warning if response.status_code >= 500 else logger.info
        log_level("request method=%s path=%s status=%s duration_ms=%.1f", request.method, request.url.path, response.status_code, duration_ms)
        return response
    finally:
        _request_id_ctx.reset(token)


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


@app.get("/ready")
def ready():
    """Distinct from /health: readiness also confirms the DATABASE SCHEMA
    the app is running against actually matches what this code expects --
    not just that a connection can be opened. A process that boots against
    a database someone forgot to migrate would pass /health (connects
    fine) but should never receive traffic -- that's exactly what /ready
    is for. Never returns schema details, migration ids, or any other
    internal information beyond ready/not-ready in the response body."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        with engine.connect() as conn:
            db_version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

        alembic_cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
        script = ScriptDirectory.from_config(alembic_cfg)
        head_version = script.get_current_head()

        if db_version != head_version:
            logger.warning("readiness check failed: db is not migrated to head")
            return Response(content='{"status": "not_ready"}', status_code=503, media_type="application/json")
    except Exception:
        logger.exception("readiness check failed")
        return Response(content='{"status": "not_ready"}', status_code=503, media_type="application/json")
    return {"status": "ready"}
