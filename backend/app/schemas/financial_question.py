from datetime import date

from pydantic import BaseModel


class FinancialQuestion(BaseModel):
    company_id: int
    question: str
    period_type: str = "MONTHLY"
    reference_date: date | None = None
    custom_start: date | None = None
    custom_end: date | None = None
    scenario_assumptions: dict | None = None
