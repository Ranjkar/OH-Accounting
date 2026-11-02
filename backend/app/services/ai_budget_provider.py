"""AI budget-line suggestion. Same structured-output pattern as
ai_categorization_provider.py: a forced tool call so the response is always
valid JSON. Starts from app.accounting.budget_service's deterministic
historical-average baseline (passed in as `baseline`) rather than inventing
figures -- the AI may only adjust that baseline with a stated reason. It
never writes a Budget or BudgetLine row itself and never silently approves
anything; app/api/v1/budgets.py decides whether/how a suggestion is applied,
same as the category-suggestion flow."""

import logging
from typing import Protocol

from app.core.config import settings
from app.schemas.budget_suggestion import BudgetSuggestionResponse
from app.services.retry import call_with_retry

logger = logging.getLogger(__name__)

SUGGEST_TOOL_NAME = "suggest_budget_lines"

SYSTEM_PROMPT = (
    "You help a Dutch accountant draft next year's budget for a small business. "
    "You will be given last year's actual monthly average per category as a BASELINE. "
    "Suggest a monthly amount per category, adjusting the baseline only for a reason you state "
    "explicitly (e.g. a known planned change) -- never invent a number with no basis in the baseline. "
    "If you have no reason to adjust a category, suggest the baseline unchanged. "
    "You are never the final decision-maker: every suggestion requires accountant review and explicit "
    "approval before it becomes part of an approved budget."
)


class AIBudgetProvider(Protocol):
    def suggest_budget(self, baseline: list[dict]) -> BudgetSuggestionResponse: ...


class ClaudeBudgetProvider:
    def __init__(self) -> None:
        import anthropic

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def suggest_budget(self, baseline: list[dict]) -> BudgetSuggestionResponse:
        import json

        schema = BudgetSuggestionResponse.model_json_schema()
        user_message = f"BASELINE (category: average monthly actual over the prior year):\n{json.dumps(baseline, default=str)}"
        response = call_with_retry(
            lambda: self._client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=[{"name": SUGGEST_TOOL_NAME, "description": "Record the budget suggestions.", "input_schema": schema}],
                tool_choice={"type": "tool", "name": SUGGEST_TOOL_NAME},
                messages=[{"role": "user", "content": user_message}],
            )
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == SUGGEST_TOOL_NAME:
                return BudgetSuggestionResponse.model_validate(block.input)
        raise RuntimeError("Claude did not return a structured budget suggestion")


class StubBudgetProvider:
    """Used when no AI provider is configured -- falls back to the baseline
    unchanged rather than inventing commentary."""

    def suggest_budget(self, baseline: list[dict]) -> BudgetSuggestionResponse:
        from app.schemas.budget_suggestion import BudgetCategorySuggestion

        return BudgetSuggestionResponse(
            suggestions=[
                BudgetCategorySuggestion(
                    category=row["category"], suggested_monthly_amount=str(row["average_monthly_amount"]),
                    reasoning="AI budget suggestion is unavailable (no ANTHROPIC_API_KEY configured) -- baseline carried forward unchanged.",
                    confidence=0.0,
                )
                for row in baseline
            ],
            requires_accountant_review=True,
        )


_provider: AIBudgetProvider | None = None


def get_budget_provider() -> AIBudgetProvider:
    global _provider
    if _provider is not None:
        return _provider
    try:
        _provider = ClaudeBudgetProvider()
    except Exception:
        logger.warning("No AI budget provider configured, falling back to StubBudgetProvider")
        _provider = StubBudgetProvider()
    return _provider


def reset_provider_cache() -> None:
    global _provider
    _provider = None
