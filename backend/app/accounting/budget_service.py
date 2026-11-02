"""Company budgeting. Revisions are new, immutable Budget rows (version N+1,
supersedes_budget_id pointing back), the same pattern used for ledger
corrections elsewhere -- an approved budget is never edited in place."""

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting import financial_reports as fr
from app.models.budget import Budget, BudgetLine
from app.models.enums import BudgetStatus

ZERO = Decimal("0")


class BudgetError(Exception):
    pass


def create_budget(db: Session, *, tenant_id: int, company_id: int, financial_year_id: int, name: str,
                   lines: list[dict], created_by_user_id: int) -> Budget:
    budget = Budget(tenant_id=tenant_id, company_id=company_id, financial_year_id=financial_year_id,
                     name=name, created_by_user_id=created_by_user_id)
    db.add(budget)
    db.flush()
    for line in lines:
        db.add(BudgetLine(budget_id=budget.id, category=line["category"], month=line["month"], amount=Decimal(str(line["amount"]))))
    db.flush()
    return budget


def revise_budget(db: Session, original: Budget, lines: list[dict], created_by_user_id: int) -> Budget:
    """A revision is always a new DRAFT budget; the original (even if
    APPROVED) is left untouched for history."""
    revision = Budget(
        tenant_id=original.tenant_id, company_id=original.company_id, financial_year_id=original.financial_year_id,
        name=original.name, version=original.version + 1, supersedes_budget_id=original.id,
        created_by_user_id=created_by_user_id,
    )
    db.add(revision)
    db.flush()
    for line in lines:
        db.add(BudgetLine(budget_id=revision.id, category=line["category"], month=line["month"], amount=Decimal(str(line["amount"]))))
    db.flush()
    return revision


def submit_budget(db: Session, budget: Budget) -> None:
    if budget.status != BudgetStatus.draft:
        raise BudgetError(f"Budget is {budget.status.value}, not DRAFT")
    budget.status = BudgetStatus.submitted
    budget.submitted_at = datetime.now(timezone.utc)
    db.flush()


def approve_budget(db: Session, budget: Budget, user_id: int) -> None:
    if budget.status != BudgetStatus.submitted:
        raise BudgetError(f"Budget is {budget.status.value}, not SUBMITTED")
    budget.status = BudgetStatus.approved
    budget.approved_by_user_id = user_id
    budget.approved_at = datetime.now(timezone.utc)
    db.flush()


def budget_history(db: Session, budget: Budget) -> list[Budget]:
    """Walks the supersedes_budget_id chain both ways to return every
    version of this budget, oldest first."""
    chain = [budget]
    current = budget
    while current.supersedes_budget_id:
        current = db.get(Budget, current.supersedes_budget_id)
        chain.append(current)
    chain.reverse()
    newest = budget
    all_budgets = db.query(Budget).filter(Budget.company_id == budget.company_id, Budget.financial_year_id == budget.financial_year_id, Budget.name == budget.name).all()
    by_supersedes = {b.supersedes_budget_id: b for b in all_budgets if b.supersedes_budget_id}
    while newest.id in by_supersedes:
        newest = by_supersedes[newest.id]
        chain.append(newest)
    return chain


def actual_for_category_month(db: Session, company_id: int, financial_year, category: str, month: int) -> Decimal:
    """Actual spend/revenue for one budget line's category+month, reusing
    the same category buckets as the P&L engine so a budget line and its
    actual always compare apples to apples."""
    from calendar import monthrange

    year = financial_year.year
    period = fr.DateRange(date(year, month, 1), date(year, month, monthrange(year, month)[1]))
    if category == "Revenue":
        return sum((t.net_amount for t in fr.transactions_in_period(db, company_id, period, fr.LedgerSide.sales)), ZERO)
    purchases = fr.transactions_in_period(db, company_id, period, fr.LedgerSide.purchases)
    return sum((t.net_amount for t in purchases if t.expense_category == category), ZERO)


def budget_vs_actual(db: Session, budget: Budget) -> dict:
    rows = []
    totals_budget = ZERO
    totals_actual = ZERO
    for line in budget.lines:
        actual = actual_for_category_month(db, budget.company_id, budget.financial_year, line.category, line.month)
        variance = actual - line.amount
        variance_pct = (variance / abs(line.amount) * 100).quantize(Decimal("0.1")) if line.amount else None
        rows.append(
            {
                "category": line.category,
                "month": line.month,
                "budgeted": line.amount,
                "actual": actual,
                "variance": variance,
                "variance_pct": variance_pct,
            }
        )
        totals_budget += line.amount
        totals_actual += actual
    return {
        "budget_id": budget.id,
        "budget_name": budget.name,
        "status": budget.status.value,
        "version": budget.version,
        "lines": rows,
        "total_budgeted": totals_budget,
        "total_actual": totals_actual,
        "total_variance": totals_actual - totals_budget,
    }


def suggest_lines_from_history(db: Session, company_id: int, financial_year, categories: list[str]) -> list[dict]:
    """Deterministic (non-AI) fallback/baseline: average of the same
    category's actuals over the prior financial year, repeated across all
    12 months. AI suggestions (app.services.ai_budget_provider) start from
    this baseline rather than inventing figures with no historical basis."""
    prior_year_start = date(financial_year.year - 1, 1, 1)
    prior_year_end = date(financial_year.year - 1, 12, 31)
    period = fr.DateRange(prior_year_start, prior_year_end)

    monthly_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    if "Revenue" in categories:
        sales = fr.transactions_in_period(db, company_id, period, fr.LedgerSide.sales)
        monthly_totals["Revenue"] = sum((t.net_amount for t in sales), ZERO) / 12
    purchases = fr.transactions_in_period(db, company_id, period, fr.LedgerSide.purchases)
    for category in categories:
        if category == "Revenue":
            continue
        monthly_totals[category] = sum((t.net_amount for t in purchases if t.expense_category == category), ZERO) / 12

    lines = []
    for category in categories:
        avg = monthly_totals[category].quantize(Decimal("0.01"))
        for month in range(1, 13):
            lines.append({"category": category, "month": month, "amount": avg})
    return lines
