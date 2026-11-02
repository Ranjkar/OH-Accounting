from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.accounting import financial_forecast, scenario_engine
from app.api.v1._json_safe import to_json_safe
from app.core.deps import get_current_user, require_company_access, require_editor_or_owner
from app.db.session import get_db
from app.models.company import Company
from app.models.scenario import Scenario
from app.models.user import User
from app.schemas.scenario import ScenarioCreate, ScenarioOut

router = APIRouter(tags=["forecasts"])


def _get_company_or_404(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _get_scenario_or_404(db: Session, user: User, scenario_id: int) -> Scenario:
    scenario = db.get(Scenario, scenario_id)
    if scenario is None or scenario.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    require_company_access(scenario.company_id, user, db)
    return scenario


@router.get("/forecasts/full")
def full_forecast(company_id: int, horizon_months: int = 3, reference_date: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return to_json_safe(financial_forecast.full_forecast(db, company_id, horizon_months, reference_date))


@router.post("/scenarios", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED)
def create_scenario(payload: ScenarioCreate, db: Session = Depends(get_db), user: User = Depends(require_editor_or_owner)):
    _get_company_or_404(db, user, payload.company_id)
    scenario = Scenario(
        tenant_id=user.tenant_id, company_id=payload.company_id, name=payload.name, scenario_type=payload.scenario_type,
        assumptions=payload.assumptions, horizon_months=payload.horizon_months, base_date=payload.base_date or date.today(),
        created_by_user_id=user.id,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario


@router.get("/scenarios", response_model=list[ScenarioOut])
def list_scenarios(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return db.query(Scenario).filter(Scenario.company_id == company_id).order_by(Scenario.created_at.desc()).all()


@router.post("/scenarios/{scenario_id}/duplicate", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED)
def duplicate_scenario(scenario_id: int, name: str, db: Session = Depends(get_db), user: User = Depends(require_editor_or_owner)):
    original = _get_scenario_or_404(db, user, scenario_id)
    copy = Scenario(
        tenant_id=original.tenant_id, company_id=original.company_id, name=name, scenario_type=original.scenario_type,
        assumptions=dict(original.assumptions), horizon_months=original.horizon_months, base_date=original.base_date,
        created_by_user_id=user.id,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


@router.get("/scenarios/{scenario_id}/result")
def scenario_result(scenario_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    scenario = _get_scenario_or_404(db, user, scenario_id)
    result = scenario_engine.apply_scenario(db, scenario.company_id, scenario.assumptions, scenario.horizon_months, scenario.base_date)
    return to_json_safe({"scenario_id": scenario.id, "scenario_name": scenario.name, "scenario_type": scenario.scenario_type.value, **result})


@router.get("/scenarios/compare")
def compare_scenarios(scenario_ids: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = [int(x) for x in scenario_ids.split(",") if x.strip()]
    scenarios = [_get_scenario_or_404(db, user, sid) for sid in ids]
    if len({s.company_id for s in scenarios}) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only compare scenarios belonging to the same company")
    company_id = scenarios[0].company_id
    result = scenario_engine.compare_scenarios(
        db, company_id,
        [{"name": s.name, "assumptions": s.assumptions} for s in scenarios],
        horizon_months=scenarios[0].horizon_months, reference_date=scenarios[0].base_date,
    )
    return to_json_safe(result)
