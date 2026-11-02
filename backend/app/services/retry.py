"""Retry-with-backoff for Claude API calls. Only retries the transient error
classes (rate limit, overloaded, connection) -- never retries on a bad
request or auth failure, which won't succeed on retry and would just burn
through the attempt budget."""

import logging
import random
import time
from typing import Callable, TypeVar

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def call_with_retry(fn: Callable[[], T]) -> T:
    import anthropic

    retryable = (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError)
    last_exc: Exception | None = None
    for attempt in range(1, settings.claude_max_retries + 1):
        try:
            return fn()
        except retryable as exc:
            last_exc = exc
            if attempt == settings.claude_max_retries:
                break
            delay = settings.claude_retry_base_delay_seconds * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning("Claude API call failed (%s), retrying in %.1fs (attempt %d/%d)", type(exc).__name__, delay, attempt, settings.claude_max_retries)
            time.sleep(delay)
    raise last_exc
