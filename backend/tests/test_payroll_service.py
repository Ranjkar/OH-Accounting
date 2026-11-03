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


def test_add_payslip_tracks_cumulative_wage_across_periods_for_premium_cap(db_session):
    """Each add_payslip call must look at the employee's already-added payslips
    earlier in the same calendar year so the annual premieloon cap (tested in
    isolation in test_dutch_tax_rules.py) actually applies across periods, not
    just within a single call with a hardcoded cumulative wage of 0."""
    tenant, company, user, employee = _setup(db_session)
    employee.monthly_salary = Decimal("70000.00")
    db_session.flush()
    db_session.commit()

    run1 = payroll_service.create_payroll_run(
        db_session, tenant_id=tenant.id, company_id=company.id, period_type=PayrollPeriodType.monthly,
        period_year=2025, period_number=1, created_by_user_id=user.id,
    )
    payslip1 = payroll_service.add_payslip(db_session, run1, employee)
    db_session.commit()

    run2 = payroll_service.create_payroll_run(
        db_session, tenant_id=tenant.id, company_id=company.id, period_type=PayrollPeriodType.monthly,
        period_year=2025, period_number=2, created_by_user_id=user.id,
    )
    payslip2 = payroll_service.add_payslip(db_session, run2, employee)
    db_session.commit()

    premiums1 = payslip1.employer_costs_total - payslip1.gross_salary
    premiums2 = payslip2.employer_costs_total - payslip2.gross_salary
    # Period 1: full EUR 70,000 is below the EUR 75,864 cap -- premiums computed on the full wage.
    # Period 2: cumulative wage is already 70,000, so only ~5,864 of this period's wage is still
    # subject to premiums -- period 2's premiums must be much smaller than period 1's.
    assert premiums1 > premiums2
    assert premiums2 < premiums1 / 5
