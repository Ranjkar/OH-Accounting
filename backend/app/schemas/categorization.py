from pydantic import BaseModel, Field


class CategorySuggestion(BaseModel):
    suggested_category: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence: list[str] = Field(default_factory=list)
    requires_accountant_review: bool = True
