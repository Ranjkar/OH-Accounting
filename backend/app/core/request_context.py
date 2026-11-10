from contextvars import ContextVar

# Phase 12 originally defined this inside app.main for structured logging;
# moved here (Phase 15) so other modules -- notably every AuditLog write
# site -- can read the current request's correlation id without importing
# app.main (which would be circular, since app.main imports every router).
# contextvars (not a global/thread-local) so each concurrent request's
# value is isolated even under asyncio concurrency on one thread.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return request_id_ctx.get()
