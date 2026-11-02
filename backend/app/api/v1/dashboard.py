from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.company import Company
from app.models.enums import UserRole, VatPeriodStatus
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class UpcomingDeadline(BaseModel):
    company_id: int
    company_name: str
    period_label: str
    filing_deadline: date
    payment_deadline: date


class DashboardSummary(BaseModel):
    company_count: int
    open_vat_periods: int
    upcoming_deadlines: list[UpcomingDeadline]


@router.get("", response_model=DashboardSummary)
def dashboard_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    companies_query = db.query(Company).filter(Company.tenant_id == user.tenant_id)
    if user.role != UserRole.admin:
        company_ids = [c.id for c in user.companies]
        companies_query = companies_query.filter(Company.id.in_(company_ids))
    companies = companies_query.all()
    company_by_id = {c.id: c for c in companies}

    open_periods = (
        db.query(VatPeriod)
        .join(FinancialYear, VatPeriod.financial_year_id == FinancialYear.id)
        .filter(
            FinancialYear.company_id.in_(company_by_id.keys()),
            VatPeriod.status == VatPeriodStatus.open,
        )
        .order_by(VatPeriod.filing_deadline)
        .all()
    )

    upcoming = [
        UpcomingDeadline(
            company_id=period.financial_year.company_id,
            company_name=company_by_id[period.financial_year.company_id].name,
            period_label=period.label,
            filing_deadline=period.filing_deadline,
            payment_deadline=period.payment_deadline,
        )
        for period in open_periods[:10]
    ]

    return DashboardSummary(
        company_count=len(companies),
        open_vat_periods=len(open_periods),
        upcoming_deadlines=upcoming,
    )
