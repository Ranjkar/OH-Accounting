"""In-memory fixed-window rate limiting for sensitive endpoints.

ponytail: single-process, in-memory counters -- resets on restart and isn't
shared across worker processes. That's fine at current scale (one uvicorn
process, no Redis per the architecture constraint); if this is ever run with
multiple workers or needs to survive restarts, swap this module for a
Redis-backed limiter without touching call sites.
"""

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

_WINDOW_SECONDS = 60
_buckets: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def _client_key(request: Request, scope: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{scope}:{client_host}"


def enforce(request: Request, scope: str, limit_per_minute: int) -> None:
    key = _client_key(request, scope)
    now = time.monotonic()
    with _lock:
        hits = _buckets[key]
        cutoff = now - _WINDOW_SECONDS
        while hits and hits[0] < cutoff:
            hits.pop(0)
        if len(hits) >= limit_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, please slow down.",
            )
        hits.append(now)


def reset_all() -> None:
    """Test hook."""
    with _lock:
        _buckets.clear()
