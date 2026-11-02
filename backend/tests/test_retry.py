import anthropic
import pytest

from app.core.config import settings
from app.services.retry import call_with_retry


def test_succeeds_on_first_try_without_sleeping(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: pytest.fail("should not sleep on first-try success"))
    assert call_with_retry(lambda: 42) == 42


def test_retries_on_rate_limit_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise anthropic.RateLimitError("rate limited", response=_fake_response(429), body=None)
        return "ok"

    result = call_with_retry(flaky)
    assert result == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0]  # exponential backoff


def test_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(settings, "claude_max_retries", 2)

    def always_fails():
        raise anthropic.RateLimitError("rate limited", response=_fake_response(429), body=None)

    with pytest.raises(anthropic.RateLimitError):
        call_with_retry(always_fails)


def test_does_not_retry_non_transient_errors(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: pytest.fail("should not retry a non-transient error"))

    def bad_request():
        raise anthropic.BadRequestError("bad request", response=_fake_response(400), body=None)

    with pytest.raises(anthropic.BadRequestError):
        call_with_retry(bad_request)


def _fake_response(status_code: int):
    import httpx

    return httpx.Response(status_code, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
