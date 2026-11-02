from pydantic import BaseModel


class BudgetCategorySuggestion(BaseModel):
    category: str
    suggested_monthly_amount: str
    reasoning: str
    confidence: float


class BudgetSuggestionResponse(BaseModel):
    suggestions: list[BudgetCategorySuggestion]
    requires_accountant_review: bool
