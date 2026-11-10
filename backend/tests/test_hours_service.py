from datetime import date
from decimal import Decimal

import pytest

from app.accounting import hours_service
from app.core.security import hash_password
from app.models.company import Company
from app.models.employee import Employee
from app.models.enums import EmploymentType, SalaryBasis, TimesheetEntryType, TimesheetStatus, UserRole
from app.models.tenant import Tenant
from app.models.timesheet import EmployeeTimesheetEntry, EntrepreneurHoursEntry
from app.models.user import User


def _setup(db_session):
    tenant = Tenant(name="T")
    db_session.add(tenant)
    db_session.flush()
    company = Company(tenant_id=tenant.id, name="C")
    db_session.add(company)
    db_session.flush()
    user = User(tenant_id=tenant.id, email="u@t.nl", hashed_password=hash_password("x"), full_name="U", role=UserRole.admin)
    db_session.add(user)
    db_session.flush()
    employee = Employee(
        tenant_id=tenant.id, company_id=company.id, employee_number="E1", full_name="Jan",
        employment_start_date=date(2025, 1, 1), employment_type=EmploymentType.permanent,
        salary_basis=SalaryBasis.monthly, monthly_salary=Decimal("4000"), created_by_user_id=user.id,
    )
    db_session.add(employee)
    db_session.flush()
    db_session.commit()
    return tenant, company, user, employee


def test_timesheet_submit_approve_workflow(db_session):
    tenant, company, user, employee = _setup(db_session)
    entry = EmployeeTimesheetEntry(
        tenant_id=tenant.id, company_id=company.id, employee_id=employee.id, entry_date=date(2025, 3, 1),
        entry_type=TimesheetEntryType.worked, hours=Decimal("8"),
    )
    db_session.add(entry)
    db_session.commit()

    with pytest.raises(hours_service.HoursError):
        hours_service.approve_timesheet_entry(db_session, entry, user.id)

    hours_service.submit_timesheet_entry(db_session, entry)
    db_session.commit()
    assert entry.status == TimesheetStatus.submitted

    hours_service.approve_timesheet_entry(db_session, entry, user.id)
    db_session.commit()
    assert entry.status == TimesheetStatus.approved
    assert entry.approved_by_user_id == user.id


def test_employee_hours_summary_groups_by_type(db_session):
    tenant, company, user, employee = _setup(db_session)
    db_session.add_all([
        EmployeeTimesheetEntry(tenant_id=tenant.id, company_id=company.id, employee_id=employee.id, entry_date=date(2025, 3, 1), entry_type=TimesheetEntryType.worked, hours=Decimal("8")),
        EmployeeTimesheetEntry(tenant_id=tenant.id, company_id=company.id, employee_id=employee.id, entry_date=date(2025, 3, 2), entry_type=TimesheetEntryType.sick, hours=Decimal("8")),
    ])
    db_session.commit()

    summary = hours_service.employee_hours_summary(db_session, employee.id, 2025)
    assert summary["hours_by_type"]["WORKED"] == Decimal("8")
    assert summary["hours_by_type"]["SICK"] == Decimal("8")


def test_urencriterium_dashboard_below_threshold(db_session):
    tenant, company, user, employee = _setup(db_session)
    db_session.add(EntrepreneurHoursEntry(
        tenant_id=tenant.id, company_id=company.id, partner_id=None, entry_date=date(2025, 3, 1),
        activity_category="business_activity", duration_hours=Decimal("100"), created_by_user_id=user.id,
    ))
    db_session.commit()

    result = hours_service.urencriterium_dashboard(db_session, company.id, 2025)
    assert result["total_recorded_hours"] == Decimal("100")
    assert result["threshold_met_by_recorded_hours_alone"] is False
    assert result["threshold_hours"] == 1225


def test_urencriterium_dashboard_above_threshold(db_session):
    tenant, company, user, employee = _setup(db_session)
    for month in range(1, 13):
        db_session.add(EntrepreneurHoursEntry(
            tenant_id=tenant.id, company_id=company.id, partner_id=None, entry_date=date(2025, month, 1),
            activity_category="business_activity", duration_hours=Decimal("110"), created_by_user_id=user.id,
        ))
    db_session.commit()

    result = hours_service.urencriterium_dashboard(db_session, company.id, 2025)
    assert result["total_recorded_hours"] == Decimal("1320")
    assert result["threshold_met_by_recorded_hours_alone"] is True
    assert "not sufficient" in result["disclaimer"]
