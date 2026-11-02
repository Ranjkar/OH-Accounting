from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.accounting import financial_reports as fr
from app.accounting import kpi_engine, working_capital
from app.api.v1._json_safe import to_json_safe
from app.core.deps import get_current_user, require_company_access, require_editor_or_owner
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.balance_sheet import ManualBalanceSheetItem
from app.models.company import Company
from app.models.enums import LedgerSide
from app.models.user import User
from app.schemas.balance_sheet import ManualBalanceSheetItemCreate, ManualBalanceSheetItemOut

router = APIRouter(prefix="/financial-reports", tags=["financial-reports"])


def _get_company_or_404(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _resolve_period(period_type: fr.ReportPeriod, reference_date: date | None, custom_start: date | None, custom_end: date | None) -> fr.DateRange:
    try:
        return fr.resolve_period(period_type, reference_date or date.today(), custom_start, custom_end)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/profit-and-loss")
def profit_and_loss(
    company_id: int,
    period_type: fr.ReportPeriod = fr.ReportPeriod.monthly,
    reference_date: date | None = None,
    custom_start: date | None = None,
    custom_end: date | None = None,
    compare: str | None = Query(None, description="previous | year_on_year"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    current = fr.profit_and_loss(db, company_id, period)

    result = {"current": current}
    if compare == "previous":
        previous = fr.profit_and_loss(db, company_id, fr.previous_period(period))
        result["previous"] = previous
        result["comparison"] = fr.compare_periods(current, previous)
    elif compare == "year_on_year":
        yoy = fr.profit_and_loss(db, company_id, fr.year_on_year_period(period))
        result["year_on_year"] = yoy
        result["comparison"] = fr.compare_periods(current, yoy)
    return to_json_safe(result)


@router.get("/balance-sheet")
def balance_sheet(company_id: int, as_of_date: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return to_json_safe(fr.balance_sheet(db, company_id, as_of_date or date.today()))


@router.get("/cash-flow-statement")
def cash_flow_statement(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.monthly, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(fr.cash_flow_statement(db, company_id, period))


@router.get("/trial-balance")
def trial_balance(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.monthly, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(fr.trial_balance(db, company_id, period))


@router.get("/general-ledger")
def general_ledger(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.monthly, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None, ledger_side: LedgerSide | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(fr.general_ledger(db, company_id, period, ledger_side))


@router.get("/debtors")
def debtors(company_id: int, as_of_date: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return to_json_safe(fr.debtors(db, company_id, as_of_date or date.today()))


@router.get("/creditors")
def creditors(company_id: int, as_of_date: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return to_json_safe(fr.creditors(db, company_id, as_of_date or date.today()))


@router.get("/vat-overview")
def vat_overview(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.annual, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(fr.vat_overview(db, company_id, period))


@router.get("/revenue-breakdown")
def revenue_breakdown(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.monthly, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(fr.revenue_breakdown(db, company_id, period))


@router.get("/expense-breakdown")
def expense_breakdown(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.monthly, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(fr.expense_breakdown(db, company_id, period))


@router.get("/company-comparison")
def company_comparison(
    company_ids: str = Query(..., description="Comma-separated company ids"),
    period_type: fr.ReportPeriod = fr.ReportPeriod.monthly, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    ids = [int(x) for x in company_ids.split(",") if x.strip()]
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    rows = []
    for company_id in ids:
        company = _get_company_or_404(db, user, company_id)
        pnl = fr.profit_and_loss(db, company_id, period)
        rows.append({"company_id": company_id, "company_name": company.name, "profit_and_loss": pnl})
    return to_json_safe({"period_start": period.start, "period_end": period.end, "companies": rows})


@router.get("/kpis")
def kpis(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.monthly, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(kpi_engine.all_kpis(db, company_id, period))


# ---- Working capital ----


@router.get("/working-capital/customer-payment-behavior")
def customer_payment_behavior(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.annual, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(working_capital.customer_payment_behavior(db, company_id, period))


@router.get("/working-capital/supplier-payment-trends")
def supplier_payment_trends(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.annual, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(working_capital.supplier_payment_trends(db, company_id, period))


@router.get("/working-capital/payment-delay-alerts")
def payment_delay_alerts(company_id: int, as_of_date: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return to_json_safe(working_capital.payment_delay_alerts(db, company_id, as_of_date or date.today()))


@router.get("/working-capital/trend")
def working_capital_trend(
    company_id: int, months: int = 6, reference_date: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    reference = reference_date or date.today()
    periods = []
    for i in range(months, 0, -1):
        from dateutil.relativedelta import relativedelta

        month_ref = reference.replace(day=1) - relativedelta(months=i - 1)
        periods.append(fr.resolve_period(fr.ReportPeriod.monthly, month_ref))
    return to_json_safe(working_capital.working_capital_trend(db, company_id, periods))


@router.get("/working-capital/cash-conversion-cycle")
def cash_conversion_cycle(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.monthly, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(working_capital.cash_conversion_cycle(db, company_id, period))


@router.get("/working-capital/customer-concentration")
def customer_concentration(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.annual, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(working_capital.customer_concentration(db, company_id, period))


@router.get("/working-capital/supplier-dependency")
def supplier_dependency(
    company_id: int, period_type: fr.ReportPeriod = fr.ReportPeriod.annual, reference_date: date | None = None,
    custom_start: date | None = None, custom_end: date | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _get_company_or_404(db, user, company_id)
    period = _resolve_period(period_type, reference_date, custom_start, custom_end)
    return to_json_safe(working_capital.supplier_dependency(db, company_id, period))


# ---- Manual balance-sheet items ----


@router.post("/balance-sheet-items", response_model=ManualBalanceSheetItemOut, status_code=status.HTTP_201_CREATED)
def create_balance_sheet_item(
    payload: ManualBalanceSheetItemCreate, db: Session = Depends(get_db), user: User = Depends(require_editor_or_owner)
):
    _get_company_or_404(db, user, payload.company_id)
    item = ManualBalanceSheetItem(
        tenant_id=user.tenant_id, company_id=payload.company_id, category=payload.category,
        label=payload.label, amount=payload.amount, as_of_date=payload.as_of_date, created_by_user_id=user.id,
    )
    db.add(item)
    db.flush()
    db.add(
        AuditLog(
            tenant_id=user.tenant_id, user_id=user.id, action="create", entity_type="manual_balance_sheet_item",
            entity_id=item.id, after=payload.model_dump(mode="json"),
        )
    )
    db.commit()
    db.refresh(item)
    return item


@router.get("/balance-sheet-items", response_model=list[ManualBalanceSheetItemOut])
def list_balance_sheet_items(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return db.query(ManualBalanceSheetItem).filter(ManualBalanceSheetItem.company_id == company_id).order_by(ManualBalanceSheetItem.as_of_date).all()
