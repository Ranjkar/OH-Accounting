"""AI expense-category suggestion. Same structured-output pattern as
ai_provider.py's invoice extraction: a forced tool call so the response is
always valid, parseable JSON, never free-form prose. The suggestion is
advisory only -- app/accounting/categorization.py and the API layer decide
whether/how it's applied, and it never overrides an existing rule match."""

import logging
from typing import Protocol

from app.accounting.categorization import EXPENSE_CATEGORIES
from app.core.config import settings
from app.schemas.categorization import CategorySuggestion
from app.services.retry import call_with_retry

logger = logging.getLogger(__name__)

SUGGEST_TOOL_NAME = "suggest_expense_category"

SYSTEM_PROMPT = (
    "You help a Dutch accountant categorize a business expense transaction. "
    f"Choose exactly one category from this list: {', '.join(EXPENSE_CATEGORIES)}. "
    "Base your suggestion only on the transaction details given -- counterparty name, "
    "description, and amount. If you are not confident, say so with a lower confidence "
    "score and set requires_accountant_review to true -- you are never the final decision-maker "
    "on VAT eligibility or the final ledger category, only a suggestion for review."
)


class AICategorizationProvider(Protocol):
    def suggest_category(self, counterparty_name: str | None, description: str | None, amount: str) -> CategorySuggestion: ...


class ClaudeCategorizationProvider:
    def __init__(self) -> None:
        import anthropic

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def suggest_category(self, counterparty_name: str | None, description: str | None, amount: str) -> CategorySuggestion:
        schema = CategorySuggestion.model_json_schema()
        user_message = (
            f"Counterparty: {counterparty_name or 'unknown'}\n"
            f"Description: {description or 'none'}\n"
            f"Amount: {amount}"
        )
        response = call_with_retry(
            lambda: self._client.messages.create(
                model=settings.anthropic_model,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                tools=[{"name": SUGGEST_TOOL_NAME, "description": "Record the category suggestion.", "input_schema": schema}],
                tool_choice={"type": "tool", "name": SUGGEST_TOOL_NAME},
                messages=[{"role": "user", "content": user_message}],
            )
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == SUGGEST_TOOL_NAME:
                return CategorySuggestion.model_validate(block.input)
        raise RuntimeError("Claude did not return a structured category suggestion")


class StubCategorizationProvider:
    def suggest_category(self, counterparty_name: str | None, description: str | None, amount: str) -> CategorySuggestion:
        return CategorySuggestion(
            suggested_category="Other", confidence=0.0,
            reasoning="AI categorization is unavailable (no ANTHROPIC_API_KEY configured).",
            evidence=[], requires_accountant_review=True,
        )


_provider: AICategorizationProvider | None = None


def get_categorization_provider() -> AICategorizationProvider:
    global _provider
    if _provider is not None:
        return _provider
    try:
        _provider = ClaudeCategorizationProvider()
    except Exception:
        logger.warning("No AI categorization provider configured, falling back to StubCategorizationProvider")
        _provider = StubCategorizationProvider()
    return _provider


def reset_provider_cache() -> None:
    global _provider
    _provider = None
