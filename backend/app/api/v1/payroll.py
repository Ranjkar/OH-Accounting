from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.accounting import payroll_service
from app.core.deps import get_current_user, require_company_access, require_editor
from app.db.session import get_db
from app.models.company import Company
from app.models.employee import Employee
from app.models.payroll import PayrollRun, Payslip
from app.models.user import User
from app.reporting.payslip_report import render_payslip_pdf
from app.schemas.payroll import PayrollRunCreate, PayrollRunOut, PayslipCorrectRequest, PayslipCreate, PayslipOut

router = APIRouter(tags=["payroll"])


def _get_company_or_404(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _get_run_or_404(db: Session, user: User, run_id: int) -> PayrollRun:
    run = db.get(PayrollRun, run_id)
    if run is None or run.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")
    require_company_access(run.company_id, user, db)
    return run


def _get_payslip_or_404(db: Session, user: User, payslip_id: int) -> Payslip:
    payslip = db.get(Payslip, payslip_id)
    if payslip is None or payslip.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payslip not found")
    require_company_access(payslip.company_id, user, db)
    return payslip


@router.post("/payroll-runs", response_model=PayrollRunOut, status_code=status.HTTP_201_CREATED)
def create_payroll_run(payload: PayrollRunCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    _get_company_or_404(db, user, payload.company_id)
    try:
        run = payroll_service.create_payroll_run(
            db, tenant_id=user.tenant_id, company_id=payload.company_id, period_type=payload.period_type,
            period_year=payload.period_year, period_number=payload.period_number, created_by_user_id=user.id,
            tax_year=payload.tax_year,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(run)
    return run


@router.get("/payroll-runs", response_model=list[PayrollRunOut])
def list_payroll_runs(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return db.query(PayrollRun).filter(PayrollRun.company_id == company_id).order_by(PayrollRun.period_year.desc(), PayrollRun.period_number.desc()).all()


@router.get("/payroll-runs/{run_id}", response_model=PayrollRunOut)
def get_payroll_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _get_run_or_404(db, user, run_id)


@router.get("/payroll-runs/{run_id}/payslips", response_model=list[PayslipOut])
def list_payslips(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    run = _get_run_or_404(db, user, run_id)
    return run.payslips


@router.post("/payroll-runs/{run_id}/payslips", response_model=PayslipOut, status_code=status.HTTP_201_CREATED)
def add_payslip(run_id: int, payload: PayslipCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    run = _get_run_or_404(db, user, run_id)
    employee = db.get(Employee, payload.employee_id)
    if employee is None or employee.company_id != run.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found in this company")
    try:
        payslip = payroll_service.add_payslip(
            db, run, employee, paid_hours=payload.paid_hours, overtime_hours=payload.overtime_hours,
            overtime_rate_multiplier=payload.overtime_rate_multiplier, bonus_amount=payload.bonus_amount,
            expense_reimbursement=payload.expense_reimbursement,
            pay_holiday_allowance_this_period=payload.pay_holiday_allowance_this_period,
            pension_deduction_pct=payload.pension_deduction_pct, other_deductions=payload.other_deductions,
        )
    except (payroll_service.PayrollError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(payslip)
    return payslip


@router.post("/payroll-runs/{run_id}/approve", response_model=PayrollRunOut)
def approve_payroll_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    run = _get_run_or_404(db, user, run_id)
    try:
        payroll_service.approve_payroll_run(db, run, user.id)
    except payroll_service.PayrollError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(run)
    return run


@router.post("/payroll-runs/{run_id}/mark-paid", response_model=PayrollRunOut)
def mark_payroll_run_paid(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    run = _get_run_or_404(db, user, run_id)
    try:
        payroll_service.mark_paid(db, run)
    except payroll_service.PayrollError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(run)
    return run


@router.post("/payslips/{payslip_id}/correct", response_model=PayslipOut, status_code=status.HTTP_201_CREATED)
def correct_payslip(payslip_id: int, payload: PayslipCorrectRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    original = _get_payslip_or_404(db, user, payslip_id)
    overrides = {k: v for k, v in payload.model_dump(exclude={"reason"}).items() if v is not None}
    try:
        correction = payroll_service.correct_payslip(db, original, reason=payload.reason, **overrides)
    except payroll_service.PayrollError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(correction)
    return correction


@router.get("/payslips/{payslip_id}/pdf")
def payslip_pdf(payslip_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    payslip = _get_payslip_or_404(db, user, payslip_id)
    run = db.get(PayrollRun, payslip.payroll_run_id)
    employee = db.get(Employee, payslip.employee_id)
    company = db.get(Company, payslip.company_id)
    content = render_payslip_pdf(company, employee, run, payslip)
    return Response(
        content=content, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="payslip-{payslip.id}.pdf"'},
    )
