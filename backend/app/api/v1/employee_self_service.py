"""Employee self-service portal: every endpoint here is scoped to the
Employee resolved by app.core.deps.get_current_employee, which looks up
the record linked to the logged-in user's own account. There is no
company_id or employee_id path/query parameter anywhere in this router --
that is deliberate, so there is no parameter to tamper with to reach
another employee's data. BSN is never returned, not even masked -- this
portal has no reason to show it to the employee themselves."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.accounting import hours_service, payroll_service
from app.api.v1._json_safe import to_json_safe
from app.core.deps import get_current_employee
from app.db.session import get_db
from app.models.company import Company
from app.models.employee import Employee
from app.models.payroll import PayrollRun, Payslip
from app.models.timesheet import EmployeeTimesheetEntry
from app.reporting.annual_statement_report import render_annual_statement_pdf
from app.reporting.payslip_report import render_payslip_pdf
from app.schemas.employee import TimesheetEntryCreate, TimesheetEntryOut
from app.schemas.payroll import PayslipOut

router = APIRouter(prefix="/me", tags=["employee-self-service"])


@router.get("/profile")
def my_profile(employee: Employee = Depends(get_current_employee)):
    return {
        "id": employee.id,
        "employee_number": employee.employee_number,
        "full_name": employee.full_name,
        "job_title": employee.job_title,
        "department": employee.department,
        "employment_start_date": employee.employment_start_date,
        "employment_end_date": employee.employment_end_date,
        "contracted_hours_per_week": employee.contracted_hours_per_week,
    }


@router.get("/payslips", response_model=list[PayslipOut])
def my_payslips(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    return (
        db.query(Payslip)
        .filter(Payslip.employee_id == employee.id)
        .order_by(Payslip.created_at.desc())
        .all()
    )


def _own_payslip_or_404(db: Session, employee: Employee, payslip_id: int) -> Payslip:
    payslip = db.get(Payslip, payslip_id)
    if payslip is None or payslip.employee_id != employee.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payslip not found")
    return payslip


@router.get("/payslips/{payslip_id}/pdf")
def my_payslip_pdf(payslip_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    payslip = _own_payslip_or_404(db, employee, payslip_id)
    run = db.get(PayrollRun, payslip.payroll_run_id)
    company = db.get(Company, payslip.company_id)
    content = render_payslip_pdf(company, employee, run, payslip)
    return Response(
        content=content, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="payslip-{payslip.id}.pdf"'},
    )


@router.get("/annual-statement")
def my_annual_statement(tax_year: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    return to_json_safe(payroll_service.build_annual_statement(db, employee, tax_year))


@router.get("/annual-statement/pdf")
def my_annual_statement_pdf(tax_year: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    company = db.get(Company, employee.company_id)
    statement = payroll_service.build_annual_statement(db, employee, tax_year)
    content = render_annual_statement_pdf(company, employee, statement)
    return Response(
        content=content, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="annual-statement-{tax_year}.pdf"'},
    )


@router.get("/timesheet-entries", response_model=list[TimesheetEntryOut])
def my_timesheet_entries(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    return (
        db.query(EmployeeTimesheetEntry)
        .filter(EmployeeTimesheetEntry.employee_id == employee.id)
        .order_by(EmployeeTimesheetEntry.entry_date.desc())
        .all()
    )


@router.post("/timesheet-entries", response_model=TimesheetEntryOut, status_code=status.HTTP_201_CREATED)
def create_my_timesheet_entry(payload: TimesheetEntryCreate, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    if payload.employee_id != employee.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot submit a timesheet entry for another employee")
    entry = EmployeeTimesheetEntry(
        tenant_id=employee.tenant_id, company_id=employee.company_id, employee_id=employee.id,
        entry_date=payload.entry_date, entry_type=payload.entry_type, hours=payload.hours, description=payload.description,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/timesheet-entries/{entry_id}/submit", response_model=TimesheetEntryOut)
def submit_my_timesheet_entry(entry_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    entry = db.get(EmployeeTimesheetEntry, entry_id)
    if entry is None or entry.employee_id != employee.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timesheet entry not found")
    try:
        hours_service.submit_timesheet_entry(db, entry)
    except hours_service.HoursError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/hours-summary")
def my_hours_summary(year: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    return to_json_safe(hours_service.employee_hours_summary(db, employee.id, year))
