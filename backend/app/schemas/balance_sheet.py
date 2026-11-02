from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import BalanceSheetItemCategory


class ManualBalanceSheetItemCreate(BaseModel):
    company_id: int
    category: BalanceSheetItemCategory
    label: str
    amount: Decimal
    as_of_date: date


class ManualBalanceSheetItemOut(BaseModel):
    id: int
    company_id: int
    category: BalanceSheetItemCategory
    label: str
    amount: Decimal
    as_of_date: date
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
