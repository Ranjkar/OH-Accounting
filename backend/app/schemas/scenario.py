from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ScenarioType


class ScenarioCreate(BaseModel):
    company_id: int
    name: str
    scenario_type: ScenarioType
    assumptions: dict = {}
    horizon_months: int = 3
    base_date: date | None = None


class ScenarioOut(BaseModel):
    id: int
    company_id: int
    name: str
    scenario_type: ScenarioType
    assumptions: dict
    horizon_months: int
    base_date: date
    created_by_user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
