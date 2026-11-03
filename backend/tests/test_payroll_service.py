from datetime import date
from decimal import Decimal

import pytest

from app.accounting import payroll_service
from app.core.security import hash_password
from app.models.company import Company
from app.models.employee import Employee
from app.models.enums import EmploymentType, PayrollPeriodType, PayrollRunStatus, SalaryBasis, UserRole
from app.models.tenant import Tenant
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
        tenant_id=tenant.id, company_id=company.id, employee_number="E001", full_name="Jan Jansen",
        employment_start_date=date(2025, 1, 1), employment_type=EmploymentType.permanent,
        salary_basis=SalaryBasis.monthly, monthly_salary=Decimal("4000.00"), created_by_user_id=user.id,
    )
    db_session.add(employee)
    db_session.flush()
    db_session.commit()
    return tenant, company, user, employee


def test_create_run_and_add_payslip(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = payroll_service.create_payroll_run(
        db_session, tenant_id=tenant.id, company_id=company.id, period_type=PayrollPeriodType.monthly,
        period_year=2025, period_number=3, created_by_user_id=user.id,
    )
    payslip = payroll_service.add_payslip(db_session, run, employee)
    db_session.commit()

    assert payslip.gross_salary == Decimal("4000.00")
    assert payslip.net_salary < payslip.gross_salary
    assert run.status == PayrollRunStatus.draft


def test_cannot_add_payslip_to_approved_run(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = payroll_service.create_payroll_run(
        db_session, tenant_id=tenant.id, company_id=company.id, period_type=PayrollPeriodType.monthly,
        period_year=2025, period_number=3, created_by_user_id=user.id,
    )
    payroll_service.add_payslip(db_session, run, employee)
    payroll_service.approve_payroll_run(db_session, run, user.id)
    db_session.commit()

    with pytest.raises(payroll_service.PayrollError):
        payroll_service.add_payslip(db_session, run, employee)


def test_cannot_approve_run_with_no_payslips(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = payroll_service.create_payroll_run(
        db_session, tenant_id=tenant.id, company_id=company.id, period_type=PayrollPeriodType.monthly,
        period_year=2025, period_number=3, created_by_user_id=user.id,
    )
    with pytest.raises(payroll_service.PayrollError):
        payroll_service.approve_payroll_run(db_session, run, user.id)


def test_correct_payslip_voids_original_and_creates_new(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = payroll_service.create_payroll_run(
        db_session, tenant_id=tenant.id, company_id=company.id, period_type=PayrollPeriodType.monthly,
        period_year=2025, period_number=3, created_by_user_id=user.id,
    )
    original = payroll_service.add_payslip(db_session, run, employee)
    payroll_service.approve_payroll_run(db_session, run, user.id)
    db_session.commit()
    original_id = original.id
    original_gross = original.gross_salary

    correction = payroll_service.correct_payslip(db_session, original, reason="Missed bonus", bonus_amount=Decimal("500"))
    db_session.commit()

    db_session.refresh(original)
    assert original.voided is True
    assert original.void_reason == "Missed bonus"
    assert original.gross_salary == original_gross  # original figures never rewritten

    assert correction.corrects_payslip_id == original_id
    assert correction.voided is False
    assert correction.gross_salary > original_gross


def test_cannot_correct_an_already_corrected_payslip(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = payroll_service.create_payroll_run(
        db_session, tenant_id=tenant.id, company_id=company.id, period_type=PayrollPeriodType.monthly,
        period_year=2025, period_number=3, created_by_user_id=user.id,
    )
    original = payroll_service.add_payslip(db_session, run, employee)
    db_session.commit()
    payroll_service.correct_payslip(db_session, original, reason="first correction")
    db_session.commit()

    with pytest.raises(payroll_service.PayrollError):
        payroll_service.correct_payslip(db_session, original, reason="second correction")
