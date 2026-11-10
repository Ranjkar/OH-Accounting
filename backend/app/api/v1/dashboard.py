from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.accounting import financial_forecast, financial_reports as fr
from app.api.v1._json_safe import to_json_safe
from app.core.deps import ADMIN_ROLES, get_current_user, require_company_access
from app.core.locale import resolve_locale_for_user
from app.core.messages_i18n import t
from app.db.session import get_db
from app.models.accounting import AccountingTransaction, VatReturn
from app.models.banking import BankTransaction
from app.models.budget import Budget
from app.models.company import Company
from app.models.document import Document
from app.models.enums import BudgetStatus, DocumentStatus, PaymentStatus, ReconciliationStatus, UserRole, VatPeriodStatus, VatReturnStatus
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.user import User
from app.schemas.dashboard import CompanyAttentionFlag, DashboardSummary, UpcomingDeadline

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _get_company_or_404(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


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
    if user.role not in ADMIN_ROLES:
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

    locale = resolve_locale_for_user(user)
    attention: list[CompanyAttentionFlag] = []
    for company in companies:
        reasons = []
        company_overdue = [
            p
            for p in open_periods
            if p.financial_year.company_id == company.id and _is_overdue_unresolved(p, vat_return_by_period, today)
        ]
        if company_overdue:
            reasons.append(t(locale, "dashboard.overdueVatReturns", count=len(company_overdue)))
        pending_docs = (
            db.query(Document)
            .filter(Document.company_id == company.id, Document.status.in_([DocumentStatus.needs_review, DocumentStatus.failed]))
            .count()
        )
        if pending_docs:
            reasons.append(t(locale, "dashboard.documentsNeedReview", count=pending_docs))
        overdue_tx = (
            db.query(AccountingTransaction)
            .filter(AccountingTransaction.company_id == company.id, AccountingTransaction.payment_status == PaymentStatus.overdue)
            .count()
        )
        if overdue_tx:
            reasons.append(t(locale, "dashboard.overduePayments", count=overdue_tx))
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


@router.get("/accountant")
def accountant_dashboard(reference_date: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Portfolio view across every company this user can access: current
    month profitability, VAT liability, unreconciled bank transactions, and
    missing data -- each company's own numbers, reusing financial_reports
    and the Phase 6 reconciliation status rather than a second summary
    engine."""
    companies_query = db.query(Company).filter(Company.tenant_id == user.tenant_id)
    if user.role not in ADMIN_ROLES:
        accessible_ids = [c.id for c in user.companies]
        companies_query = companies_query.filter(Company.id.in_(accessible_ids))
    companies = companies_query.all()
    today = reference_date or date.today()
    period = fr.resolve_period(fr.ReportPeriod.monthly, today)

    rows = []
    for company in companies:
        pnl = fr.profit_and_loss(db, company.id, period)
        bs = fr.balance_sheet(db, company.id, today)
        unreconciled = (
            db.query(BankTransaction)
            .filter(
                BankTransaction.company_id == company.id,
                BankTransaction.reconciliation_status.in_([ReconciliationStatus.unmatched, ReconciliationStatus.suggested_match]),
            )
            .count()
        )
        rows.append(
            {
                "company_id": company.id,
                "company_name": company.name,
                "current_month_revenue": pnl["revenue"],
                "current_month_net_profit": pnl["net_profit"],
                "vat_payable": bs["liabilities"]["vat_payable"],
                "vat_receivable": bs["assets"]["vat_receivable"],
                "unreconciled_bank_transactions": unreconciled,
                "balance_sheet_balanced": bs["is_balanced"],
                "missing_balance_sheet_data": bs["missing_opening_balance_warning"] is not None,
            }
        )

    return to_json_safe(
        {
            "period_start": period.start,
            "period_end": period.end,
            "companies_requiring_attention": sum(1 for r in rows if r["unreconciled_bank_transactions"] or not r["balance_sheet_balanced"]),
            "portfolio": rows,
            "generated_at": datetime.now(timezone.utc),
        }
    )


@router.get("/business-owner")
def business_owner_dashboard(company_id: int, reference_date: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Single-company view for the business-owner (customer-role) persona:
    revenue/expenses/profit, cash position, outstanding customer payments,
    upcoming supplier payments, tax estimates, budget performance, and a
    short-horizon forecast -- all reused from financial_reports,
    financial_forecast, and budget_service, no new computation."""
    company = _get_company_or_404(db, user, company_id)
    today = reference_date or date.today()
    period = fr.resolve_period(fr.ReportPeriod.monthly, today)

    pnl = fr.profit_and_loss(db, company_id, period)
    bs = fr.balance_sheet(db, company_id, today)
    debtors = fr.debtors(db, company_id, today)
    creditors = fr.creditors(db, company_id, today)
    forecast = financial_forecast.full_forecast(db, company_id, horizon_months=3, reference_date=today)

    latest_budget = (
        db.query(Budget)
        .filter(Budget.company_id == company_id, Budget.status == BudgetStatus.approved)
        .order_by(Budget.approved_at.desc())
        .first()
    )
    budget_summary = None
    if latest_budget is not None:
        from app.accounting import budget_service

        variance = budget_service.budget_vs_actual(db, latest_budget)
        budget_summary = {"budget_id": latest_budget.id, "budget_name": latest_budget.name, "total_budgeted": variance["total_budgeted"], "total_actual": variance["total_actual"], "total_variance": variance["total_variance"]}

    return to_json_safe(
        {
            "company_id": company_id,
            "company_name": company.name,
            "period_start": period.start,
            "period_end": period.end,
            "revenue": pnl["revenue"],
            "expenses": pnl["cost_of_sales"] + pnl["operating_expenses"] + pnl["uncategorized_expenses"] + pnl["personnel_expenses"] + pnl["depreciation"] + pnl["interest_expense"],
            "net_profit": pnl["net_profit"],
            "cash_position": bs["assets"]["cash_and_bank"],
            "outstanding_customer_payments": debtors["total_outstanding"],
            "upcoming_supplier_payments": creditors["total_outstanding"],
            "estimated_vat_position": bs["liabilities"]["vat_payable"] - bs["assets"]["vat_receivable"],
            "budget_performance": budget_summary,
            "forecast_summary": {
                "revenue_expense_profit": forecast["revenue_expense_profit"]["monthly_forecast"],
                "cash_flow_disclaimer": forecast["cash_flow"]["net_bank_transaction_movement_disclaimer"],
            },
            "generated_at": datetime.now(timezone.utc),
        }
    )
