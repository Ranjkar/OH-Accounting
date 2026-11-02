from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.accounting import AccountingTransaction, VatReturn
from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentStatus, PaymentStatus, UserRole, VatPeriodStatus, VatReturnStatus
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.user import User
from app.schemas.dashboard import CompanyAttentionFlag, DashboardSummary, UpcomingDeadline

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _is_overdue_unresolved(period: VatPeriod, vat_return_by_period: dict, today: date) -> bool:
    """Past its filing deadline with no VAT return yet, or one that hasn't been approved/locked."""
    if period.filing_deadline >= today:
        return False
    vat_return = vat_return_by_period.get(period.id)
    return vat_return is None or vat_return.status not in (VatReturnStatus.approved, VatReturnStatus.locked)


@router.get("", response_model=DashboardSummary)
def dashboard_summary(
    company_id: int | None = None,
    financial_year_id: int | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    companies_query = db.query(Company).filter(Company.tenant_id == user.tenant_id)
    if user.role != UserRole.admin:
        accessible_ids = [c.id for c in user.companies]
        companies_query = companies_query.filter(Company.id.in_(accessible_ids))
    if company_id is not None:
        companies_query = companies_query.filter(Company.id == company_id)
    companies = companies_query.all()
    company_by_id = {c.id: c for c in companies}
    company_ids = list(company_by_id.keys())
    today = date.today()

    periods_query = (
        db.query(VatPeriod)
        .join(FinancialYear, VatPeriod.financial_year_id == FinancialYear.id)
        .filter(FinancialYear.company_id.in_(company_ids))
    )
    if financial_year_id is not None:
        periods_query = periods_query.filter(FinancialYear.id == financial_year_id)
    if period_start is not None:
        periods_query = periods_query.filter(VatPeriod.end_date >= period_start)
    if period_end is not None:
        periods_query = periods_query.filter(VatPeriod.start_date <= period_end)
    periods = periods_query.all()
    period_ids = [p.id for p in periods]

    open_periods = [p for p in periods if p.status == VatPeriodStatus.open]
    upcoming = sorted(open_periods, key=lambda p: p.filing_deadline)[:10]
    upcoming_deadlines = [
        UpcomingDeadline(
            company_id=p.financial_year.company_id,
            company_name=company_by_id[p.financial_year.company_id].name,
            vat_period_id=p.id,
            period_label=p.label,
            filing_deadline=p.filing_deadline,
            payment_deadline=p.payment_deadline,
            is_overdue=p.filing_deadline < today,
        )
        for p in upcoming
    ]

    vat_returns = db.query(VatReturn).filter(VatReturn.vat_period_id.in_(period_ids)).all() if period_ids else []
    vat_returns_awaiting_review = sum(
        1 for r in vat_returns if r.status in (VatReturnStatus.draft, VatReturnStatus.needs_review, VatReturnStatus.ready_for_approval)
    )
    vat_returns_approved = sum(1 for r in vat_returns if r.status in (VatReturnStatus.approved, VatReturnStatus.locked))
    vat_return_by_period = {r.vat_period_id: r for r in vat_returns}
    overdue_vat_returns = sum(1 for p in open_periods if _is_overdue_unresolved(p, vat_return_by_period, today))

    estimated_vat_payable = sum(
        (r.net_payable for r in vat_returns if r.status not in (VatReturnStatus.approved, VatReturnStatus.locked) and r.net_payable > 0),
        Decimal("0"),
    )
    estimated_vat_refundable = -sum(
        (r.net_payable for r in vat_returns if r.status not in (VatReturnStatus.approved, VatReturnStatus.locked) and r.net_payable < 0),
        Decimal("0"),
    )

    documents_awaiting_approval = (
        db.query(Document)
        .filter(
            Document.company_id.in_(company_ids),
            Document.status.in_([DocumentStatus.extracted, DocumentStatus.needs_review]),
        )
        .count()
        if company_ids
        else 0
    )

    unmatched_payments = (
        db.query(AccountingTransaction)
        .filter(AccountingTransaction.company_id.in_(company_ids), AccountingTransaction.payment_status == PaymentStatus.overdue)
        .count()
        if company_ids
        else 0
    )

    outstanding_customer_info = (
        db.query(Document)
        .filter(
            Document.company_id.in_(company_ids),
            Document.status == DocumentStatus.needs_review,
        )
        .count()
        if company_ids
        else 0
    )

    attention: list[CompanyAttentionFlag] = []
    for company in companies:
        reasons = []
        company_overdue = [
            p
            for p in open_periods
            if p.financial_year.company_id == company.id and _is_overdue_unresolved(p, vat_return_by_period, today)
        ]
        if company_overdue:
            reasons.append(f"{len(company_overdue)} overdue VAT return(s)")
        pending_docs = (
            db.query(Document)
            .filter(Document.company_id == company.id, Document.status.in_([DocumentStatus.needs_review, DocumentStatus.failed]))
            .count()
        )
        if pending_docs:
            reasons.append(f"{pending_docs} document(s) need review")
        overdue_tx = (
            db.query(AccountingTransaction)
            .filter(AccountingTransaction.company_id == company.id, AccountingTransaction.payment_status == PaymentStatus.overdue)
            .count()
        )
        if overdue_tx:
            reasons.append(f"{overdue_tx} overdue payment(s)")
        if reasons:
            attention.append(CompanyAttentionFlag(company_id=company.id, company_name=company.name, reasons=reasons))

    return DashboardSummary(
        company_count=len(companies),
        open_vat_periods=len(open_periods),
        upcoming_deadlines=upcoming_deadlines,
        companies_requiring_attention=attention,
        vat_returns_awaiting_review=vat_returns_awaiting_review,
        vat_returns_approved=vat_returns_approved,
        overdue_vat_returns=overdue_vat_returns,
        documents_awaiting_approval=documents_awaiting_approval,
        unmatched_payments=unmatched_payments,
        outstanding_customer_info=outstanding_customer_info,
        estimated_vat_payable=estimated_vat_payable,
        estimated_vat_refundable=estimated_vat_refundable,
        generated_at=datetime.now(timezone.utc),
    )
