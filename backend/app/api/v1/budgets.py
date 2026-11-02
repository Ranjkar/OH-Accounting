from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.accounting import budget_service
from app.accounting.categorization import EXPENSE_CATEGORIES
from app.api.v1._json_safe import to_json_safe
from app.core.deps import get_current_user, require_company_access, require_editor, require_editor_or_owner
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.budget import Budget
from app.models.financial_year import FinancialYear
from app.models.user import User
from app.schemas.budget import BudgetCreate, BudgetOut, BudgetRevise
from app.services import ai_budget_provider

router = APIRouter(tags=["budgets"])


def _get_company_or_404(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _get_budget_or_404(db: Session, user: User, budget_id: int) -> Budget:
    budget = db.get(Budget, budget_id)
    if budget is None or budget.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    require_company_access(budget.company_id, user, db)
    return budget


@router.post("/budgets", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
def create_budget(payload: BudgetCreate, db: Session = Depends(get_db), user: User = Depends(require_editor_or_owner)):
    company = _get_company_or_404(db, user, payload.company_id)
    fy = db.get(FinancialYear, payload.financial_year_id)
    if fy is None or fy.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")

    budget = budget_service.create_budget(
        db, tenant_id=user.tenant_id, company_id=company.id, financial_year_id=fy.id, name=payload.name,
        lines=[line.model_dump() for line in payload.lines], created_by_user_id=user.id,
    )
    db.commit()
    db.refresh(budget)
    return budget


@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(company_id: int, financial_year_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    query = db.query(Budget).filter(Budget.company_id == company_id)
    if financial_year_id is not None:
        query = query.filter(Budget.financial_year_id == financial_year_id)
    return query.order_by(Budget.created_at.desc()).all()


@router.get("/budgets/suggest")
def suggest_budget(
    company_id: int, financial_year_id: int, categories: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """AI-assisted suggestion starting from the deterministic historical
    baseline -- never applied automatically; the caller decides whether to
    use these numbers when creating or revising a budget. Registered before
    GET /budgets/{budget_id} so "suggest" is never swallowed as a budget_id."""
    company = _get_company_or_404(db, user, company_id)
    fy = db.get(FinancialYear, financial_year_id)
    if fy is None or fy.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")

    category_list = categories.split(",") if categories else (["Revenue"] + EXPENSE_CATEGORIES)
    baseline_lines = budget_service.suggest_lines_from_history(db, company.id, fy, category_list)
    baseline_by_category: dict[str, str] = {}
    for line in baseline_lines:
        baseline_by_category.setdefault(line["category"], str(line["amount"]))
    baseline = [{"category": cat, "average_monthly_amount": amount} for cat, amount in baseline_by_category.items()]

    provider = ai_budget_provider.get_budget_provider()
    suggestion = provider.suggest_budget(baseline)
    return to_json_safe({"baseline": baseline, "ai_suggestion": suggestion.model_dump()})


@router.get("/budgets/{budget_id}", response_model=BudgetOut)
def get_budget(budget_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _get_budget_or_404(db, user, budget_id)


@router.post("/budgets/{budget_id}/revise", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
def revise_budget(budget_id: int, payload: BudgetRevise, db: Session = Depends(get_db), user: User = Depends(require_editor_or_owner)):
    original = _get_budget_or_404(db, user, budget_id)
    revision = budget_service.revise_budget(db, original, lines=[line.model_dump() for line in payload.lines], created_by_user_id=user.id)
    db.commit()
    db.refresh(revision)
    return revision


@router.get("/budgets/{budget_id}/history", response_model=list[BudgetOut])
def budget_history(budget_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    budget = _get_budget_or_404(db, user, budget_id)
    return budget_service.budget_history(db, budget)


@router.post("/budgets/{budget_id}/submit", response_model=BudgetOut)
def submit_budget(budget_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor_or_owner)):
    budget = _get_budget_or_404(db, user, budget_id)
    try:
        budget_service.submit_budget(db, budget)
    except budget_service.BudgetError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(budget)
    return budget


@router.post("/budgets/{budget_id}/approve", response_model=BudgetOut)
def approve_budget(budget_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    """Approval is always a deliberate accountant/admin action -- a business
    owner can create, revise, and submit a budget, but never approve their
    own, same separation as the rest of this ledger's approval workflow."""
    budget = _get_budget_or_404(db, user, budget_id)
    try:
        budget_service.approve_budget(db, budget, user.id)
    except budget_service.BudgetError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.add(AuditLog(tenant_id=user.tenant_id, user_id=user.id, action="approve", entity_type="budget", entity_id=budget.id, after={"status": "APPROVED", "version": budget.version}))
    db.commit()
    db.refresh(budget)
    return budget


@router.get("/budgets/{budget_id}/variance")
def budget_variance(budget_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    budget = _get_budget_or_404(db, user, budget_id)
    return to_json_safe(budget_service.budget_vs_actual(db, budget))


