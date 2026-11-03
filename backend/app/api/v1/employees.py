from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.accounting import hours_service
from app.api.v1._json_safe import to_json_safe
from app.core.crypto import decrypt_bsn, encrypt_bsn, mask_bsn
from app.core.deps import get_current_user, require_admin, require_company_access, require_editor
from app.core.security import hash_password
from app.db.session import get_db
from app.models.company import Company
from app.models.employee import Employee
from app.models.enums import UserRole
from app.models.timesheet import EmployeeTimesheetEntry, EntrepreneurHoursEntry
from app.models.user import User
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeInviteOut,
    EmployeeInviteRequest,
    EmployeeOut,
    EntrepreneurHoursEntryCreate,
    EntrepreneurHoursEntryOut,
    TimesheetEntryCreate,
    TimesheetEntryOut,
)

router = APIRouter(tags=["employees"])


def _get_company_or_404(db: Session, user: User, company_id: int) -> Company:
    require_company_access(company_id, user, db)
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _get_employee_or_404(db: Session, user: User, employee_id: int) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    require_company_access(employee.company_id, user, db)
    return employee


def _employee_out(employee: Employee) -> EmployeeOut:
    """Only ever exposes a masked BSN, never the plaintext -- decryption
    happens nowhere in the read path."""
    bsn_masked = None
    if employee.bsn_encrypted is not None:
        bsn_masked = mask_bsn(decrypt_bsn(employee.bsn_encrypted))
    return EmployeeOut(
        id=employee.id, company_id=employee.company_id, employee_number=employee.employee_number,
        full_name=employee.full_name, address=employee.address, bsn_masked=bsn_masked,
        employment_start_date=employee.employment_start_date, employment_end_date=employee.employment_end_date,
        employment_type=employee.employment_type, contract_type=employee.contract_type, job_title=employee.job_title,
        department=employee.department, contracted_hours_per_week=employee.contracted_hours_per_week,
        salary_basis=employee.salary_basis, hourly_rate=employee.hourly_rate, monthly_salary=employee.monthly_salary,
        holiday_allowance_pct=employee.holiday_allowance_pct, pension_scheme=employee.pension_scheme,
        is_dga=employee.is_dga, created_at=employee.created_at,
    )


@router.post("/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    """BSN, if given, is encrypted before it ever touches the database --
    the plaintext value in the request body is never logged or stored."""
    _get_company_or_404(db, user, payload.company_id)
    employee = Employee(
        tenant_id=user.tenant_id, company_id=payload.company_id, employee_number=payload.employee_number,
        full_name=payload.full_name, address=payload.address,
        bsn_encrypted=encrypt_bsn(payload.bsn) if payload.bsn else None,
        employment_start_date=payload.employment_start_date, employment_end_date=payload.employment_end_date,
        employment_type=payload.employment_type, contract_type=payload.contract_type, job_title=payload.job_title,
        department=payload.department, contracted_hours_per_week=payload.contracted_hours_per_week,
        salary_basis=payload.salary_basis, hourly_rate=payload.hourly_rate, monthly_salary=payload.monthly_salary,
        holiday_allowance_pct=payload.holiday_allowance_pct, pension_scheme=payload.pension_scheme,
        is_dga=payload.is_dga, created_by_user_id=user.id,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return _employee_out(employee)


@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(company_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    employees = db.query(Employee).filter(Employee.company_id == company_id).order_by(Employee.full_name).all()
    return [_employee_out(e) for e in employees]


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    """Admin/accountant only -- even the masked view is a payroll-sensitive
    record, never exposed to a plain viewer or customer role."""
    employee = _get_employee_or_404(db, user, employee_id)
    return _employee_out(employee)


@router.post("/employees/{employee_id}/invite-self-service", response_model=EmployeeInviteOut, status_code=status.HTTP_201_CREATED)
def invite_employee_self_service(employee_id: int, payload: EmployeeInviteRequest, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Admin-only. Creates a new User with role=employee and links it to
    this Employee via linked_user_id. This user is deliberately never added
    to user_companies -- require_company_access rejects it from every
    company-wide endpoint, and the only data it can reach is through the
    self-service router, scoped to this one employee_id via
    app.core.deps.get_current_employee."""
    employee = _get_employee_or_404(db, user, employee_id)
    if employee.linked_user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This employee is already linked to a self-service account")
    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")

    new_user = User(
        tenant_id=employee.tenant_id, email=payload.email, hashed_password=hash_password(payload.password),
        full_name=employee.full_name, role=UserRole.employee,
    )
    db.add(new_user)
    db.flush()
    employee.linked_user_id = new_user.id
    db.commit()
    return EmployeeInviteOut(employee_id=employee.id, linked_user_id=new_user.id, email=new_user.email)


# ---- Employee timesheets ----


@router.post("/timesheet-entries", response_model=TimesheetEntryOut, status_code=status.HTTP_201_CREATED)
def create_timesheet_entry(payload: TimesheetEntryCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    employee = _get_employee_or_404(db, user, payload.employee_id)
    entry = EmployeeTimesheetEntry(
        tenant_id=employee.tenant_id, company_id=employee.company_id, employee_id=employee.id,
        entry_date=payload.entry_date, entry_type=payload.entry_type, hours=payload.hours, description=payload.description,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/timesheet-entries", response_model=list[TimesheetEntryOut])
def list_timesheet_entries(employee_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    _get_employee_or_404(db, user, employee_id)
    return db.query(EmployeeTimesheetEntry).filter(EmployeeTimesheetEntry.employee_id == employee_id).order_by(EmployeeTimesheetEntry.entry_date.desc()).all()


@router.post("/timesheet-entries/{entry_id}/submit", response_model=TimesheetEntryOut)
def submit_timesheet_entry(entry_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    entry = db.get(EmployeeTimesheetEntry, entry_id)
    if entry is None or entry.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timesheet entry not found")
    require_company_access(entry.company_id, user, db)
    try:
        hours_service.submit_timesheet_entry(db, entry)
    except hours_service.HoursError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/timesheet-entries/{entry_id}/approve", response_model=TimesheetEntryOut)
def approve_timesheet_entry(entry_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    entry = db.get(EmployeeTimesheetEntry, entry_id)
    if entry is None or entry.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timesheet entry not found")
    require_company_access(entry.company_id, user, db)
    try:
        hours_service.approve_timesheet_entry(db, entry, user.id)
    except hours_service.HoursError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/timesheet-entries/{entry_id}/reject", response_model=TimesheetEntryOut)
def reject_timesheet_entry(entry_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    entry = db.get(EmployeeTimesheetEntry, entry_id)
    if entry is None or entry.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timesheet entry not found")
    require_company_access(entry.company_id, user, db)
    try:
        hours_service.reject_timesheet_entry(db, entry, user.id)
    except hours_service.HoursError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/employees/{employee_id}/hours-summary")
def employee_hours_summary(employee_id: int, year: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    _get_employee_or_404(db, user, employee_id)
    return to_json_safe(hours_service.employee_hours_summary(db, employee_id, year))


# ---- Entrepreneur hours ----


@router.post("/entrepreneur-hours-entries", response_model=EntrepreneurHoursEntryOut, status_code=status.HTTP_201_CREATED)
def create_entrepreneur_hours_entry(payload: EntrepreneurHoursEntryCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    _get_company_or_404(db, user, payload.company_id)
    entry = EntrepreneurHoursEntry(
        tenant_id=user.tenant_id, company_id=payload.company_id, partner_id=payload.partner_id,
        entry_date=payload.entry_date, activity_category=payload.activity_category, duration_hours=payload.duration_hours,
        description=payload.description, customer_name=payload.customer_name, project=payload.project,
        created_by_user_id=user.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/entrepreneur-hours-entries", response_model=list[EntrepreneurHoursEntryOut])
def list_entrepreneur_hours_entries(company_id: int, partner_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    query = db.query(EntrepreneurHoursEntry).filter(EntrepreneurHoursEntry.company_id == company_id)
    if partner_id is not None:
        query = query.filter(EntrepreneurHoursEntry.partner_id == partner_id)
    return query.order_by(EntrepreneurHoursEntry.entry_date.desc()).all()


@router.get("/companies/{company_id}/urencriterium-dashboard")
def urencriterium_dashboard(company_id: int, year: int, partner_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_company_or_404(db, user, company_id)
    return to_json_safe(hours_service.urencriterium_dashboard(db, company_id, year, partner_id))
