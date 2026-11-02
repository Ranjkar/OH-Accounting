"""AI accountant-assistant provider. Strictly read-only commentary: Claude is
given a JSON bundle of facts already computed by deterministic Python
services and asked to explain/summarize them in prose. It never sees a
database connection and never writes anything -- it cannot change, approve,
or lock accounting records because it has no mechanism to do so."""

import json
import logging
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an assistant helping a Dutch accountant review a client's bookkeeping. "
    "You will be given a JSON object of FACTS, already computed by the firm's deterministic "
    "accounting software, and a question. "
    "Answer using ONLY the numbers and facts given in the FACTS JSON. "
    "Never state a monetary amount, date, or count that does not appear in FACTS -- if the "
    "answer requires information not present in FACTS, say so explicitly instead of estimating. "
    "You are not an accounting authority: you explain and summarize, you never approve, lock, "
    "or recommend silently accepting a VAT return, and you never tell the accountant to skip "
    "a review step. Be concise and use plain English."
)


class AIAssistantProvider(Protocol):
    def ask(self, facts: dict, question: str) -> str: ...


class ClaudeAssistantProvider:
    def __init__(self) -> None:
        import anthropic

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def ask(self, facts: dict, question: str) -> str:
        from app.services.retry import call_with_retry

        user_message = f"FACTS:\n{json.dumps(facts, indent=2, default=str)}\n\nQUESTION:\n{question}"
        response = call_with_retry(
            lambda: self._client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()


class StubAssistantProvider:
    """Used when no AI provider is configured. Never invents commentary."""

    def ask(self, facts: dict, question: str) -> str:
        return "AI assistant is unavailable (no ANTHROPIC_API_KEY configured). Review the facts above manually."


_provider: AIAssistantProvider | None = None


def get_assistant_provider() -> AIAssistantProvider:
    global _provider
    if _provider is not None:
        return _provider
    try:
        _provider = ClaudeAssistantProvider()
    except Exception:
        logger.warning("No AI assistant provider configured, falling back to StubAssistantProvider")
        _provider = StubAssistantProvider()
    return _provider


def reset_provider_cache() -> None:
    global _provider
    _provider = None
