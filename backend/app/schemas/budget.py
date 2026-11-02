from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import BudgetStatus


class BudgetLineIn(BaseModel):
    category: str
    month: int
    amount: Decimal


class BudgetCreate(BaseModel):
    company_id: int
    financial_year_id: int
    name: str
    lines: list[BudgetLineIn] = []


class BudgetRevise(BaseModel):
    lines: list[BudgetLineIn] = []


class BudgetLineOut(BaseModel):
    id: int
    category: str
    month: int
    amount: Decimal
    source: str

    model_config = ConfigDict(from_attributes=True)


class BudgetOut(BaseModel):
    id: int
    company_id: int
    financial_year_id: int
    name: str
    status: BudgetStatus
    version: int
    supersedes_budget_id: int | None
    created_at: datetime
    submitted_at: datetime | None
    approved_by_user_id: int | None
    approved_at: datetime | None
    lines: list[BudgetLineOut]

    model_config = ConfigDict(from_attributes=True)
