from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import EmploymentType, SalaryBasis, TimesheetEntryType, TimesheetStatus


class EmployeeCreate(BaseModel):
    company_id: int
    employee_number: str
    full_name: str
    address: str | None = None
    bsn: str | None = None  # plaintext in the request only -- encrypted before storage, never stored or logged as-is
    employment_start_date: date
    employment_end_date: date | None = None
    employment_type: EmploymentType
    contract_type: str | None = None
    job_title: str | None = None
    department: str | None = None
    contracted_hours_per_week: Decimal | None = None
    salary_basis: SalaryBasis
    hourly_rate: Decimal | None = None
    monthly_salary: Decimal | None = None
    holiday_allowance_pct: Decimal = Decimal("8.00")
    pension_scheme: str | None = None
    is_dga: bool = False


class EmployeeOut(BaseModel):
    id: int
    company_id: int
    employee_number: str
    full_name: str
    address: str | None
    bsn_masked: str | None
    employment_start_date: date
    employment_end_date: date | None
    employment_type: EmploymentType
    contract_type: str | None
    job_title: str | None
    department: str | None
    contracted_hours_per_week: Decimal | None
    salary_basis: SalaryBasis
    hourly_rate: Decimal | None
    monthly_salary: Decimal | None
    holiday_allowance_pct: Decimal
    pension_scheme: str | None
    is_dga: bool
    created_at: datetime


class EmployeeInviteRequest(BaseModel):
    email: str
    password: str


class EmployeeInviteOut(BaseModel):
    employee_id: int
    linked_user_id: int
    email: str


class TimesheetEntryCreate(BaseModel):
    employee_id: int
    entry_date: date
    entry_type: TimesheetEntryType
    hours: Decimal
    description: str | None = None


class TimesheetEntryOut(BaseModel):
    id: int
    employee_id: int
    entry_date: date
    entry_type: TimesheetEntryType
    hours: Decimal
    description: str | None
    status: TimesheetStatus
    approved_by_user_id: int | None
    approved_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class EntrepreneurHoursEntryCreate(BaseModel):
    company_id: int
    partner_id: int | None = None
    entry_date: date
    activity_category: str
    duration_hours: Decimal
    description: str | None = None
    customer_name: str | None = None
    project: str | None = None


class EntrepreneurHoursEntryOut(BaseModel):
    id: int
    company_id: int
    partner_id: int | None
    entry_date: date
    activity_category: str
    duration_hours: Decimal
    description: str | None
    customer_name: str | None
    project: str | None

    model_config = ConfigDict(from_attributes=True)
