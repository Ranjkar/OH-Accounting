from datetime import datetime

from pydantic import BaseModel


class AssistantResponse(BaseModel):
    facts: dict
    answer: str
    model: str
    generated_at: datetime
    disclaimer: str = (
        "AI-generated commentary for review only. It is not a verified accounting fact and "
        "has no authority to change, approve, or lock any record."
    )


class AssistantQuestion(BaseModel):
    company_id: int
    question: str
    vat_period_id: int | None = None
