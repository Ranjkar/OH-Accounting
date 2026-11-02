from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_company_access
from app.db.session import get_db
from app.models.accounting import VatReturn
from app.models.company import Company
from app.models.enums import UserRole, VatReturnStatus
from app.models.financial_year import FinancialYear
from app.models.user import User
from app.schemas.tax_calendar import TaxCalendarEntry

router = APIRouter(prefix="/tax-calendar", tags=["tax-calendar"])


@router.get("", response_model=list[TaxCalendarEntry])
def get_tax_calendar(
    company_id: int | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    companies_query = db.query(Company).filter(Company.tenant_id == user.tenant_id)
    if user.role != UserRole.admin:
        accessible_ids = [c.id for c in user.companies]
        companies_query = companies_query.filter(Company.id.in_(accessible_ids))
    if company_id is not None:
        require_company_access(company_id, user, db)
        companies_query = companies_query.filter(Company.id == company_id)
    companies = companies_query.all()
    company_by_id = {c.id: c for c in companies}

    fy_query = db.query(FinancialYear).filter(FinancialYear.company_id.in_(company_by_id.keys()))
    if year is not None:
        fy_query = fy_query.filter(FinancialYear.year == year)
    financial_years = fy_query.all()

    today = date.today()
    entries: list[TaxCalendarEntry] = []
    for fy in financial_years:
        company = company_by_id[fy.company_id]
        for period in fy.vat_periods:
            vat_return = db.query(VatReturn).filter(VatReturn.vat_period_id == period.id).first()
            if vat_return and vat_return.status in (VatReturnStatus.approved, VatReturnStatus.locked):
                calendar_status = "completed"
            elif period.filing_deadline < today:
                calendar_status = "overdue"
            elif vat_return and vat_return.status in (VatReturnStatus.needs_review, VatReturnStatus.ready_for_approval):
                calendar_status = "pending"
            else:
                calendar_status = "upcoming"

            entries.append(
                TaxCalendarEntry(
                    company_id=company.id,
                    company_name=company.name,
                    vat_period_id=period.id,
                    financial_year=fy.year,
                    period_label=period.label,
                    vat_frequency=company.vat_frequency.value,
                    start_date=period.start_date,
                    end_date=period.end_date,
                    filing_deadline=period.filing_deadline,
                    payment_deadline=period.payment_deadline,
                    calendar_status=calendar_status,
                    vat_return_id=vat_return.id if vat_return else None,
                )
            )

    entries.sort(key=lambda e: e.filing_deadline)
    return entries
