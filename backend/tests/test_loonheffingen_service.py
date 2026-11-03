from datetime import date
from decimal import Decimal

import pytest

from app.accounting import loonheffingen_service, payroll_service
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


def _approved_run_with_payslip(db_session, tenant, company, user, employee):
    run = payroll_service.create_payroll_run(
        db_session, tenant_id=tenant.id, company_id=company.id, period_type=PayrollPeriodType.monthly,
        period_year=2025, period_number=1, created_by_user_id=user.id,
    )
    payroll_service.add_payslip(db_session, run, employee)
    payroll_service.approve_payroll_run(db_session, run, user.id)
    db_session.commit()
    return run


def test_create_declaration_sums_payslip_totals(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = _approved_run_with_payslip(db_session, tenant, company, user, employee)

    declaration = loonheffingen_service.create_declaration(db_session, run)
    db_session.commit()

    assert declaration.total_gross_wages == Decimal("4000.00")
    assert declaration.total_payable == declaration.total_wage_tax_withheld + declaration.total_employer_premiums
    assert declaration.status.value == "DRAFT"


def test_cannot_create_duplicate_declaration_for_same_run(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = _approved_run_with_payslip(db_session, tenant, company, user, employee)
    loonheffingen_service.create_declaration(db_session, run)
    db_session.commit()

    with pytest.raises(loonheffingen_service.LoonheffingenError):
        loonheffingen_service.create_declaration(db_session, run)


def test_validation_fails_when_run_not_approved(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = payroll_service.create_payroll_run(
        db_session, tenant_id=tenant.id, company_id=company.id, period_type=PayrollPeriodType.monthly,
        period_year=2025, period_number=1, created_by_user_id=user.id,
    )
    payroll_service.add_payslip(db_session, run, employee)
    db_session.commit()  # run stays DRAFT -- not yet approved

    declaration = loonheffingen_service.create_declaration(db_session, run)
    db_session.commit()
    errors = loonheffingen_service.run_validation(db_session, declaration)

    assert errors
    assert declaration.status.value == "VALIDATION"
    assert declaration.validation_errors


def test_full_lifecycle_to_accepted(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = _approved_run_with_payslip(db_session, tenant, company, user, employee)
    declaration = loonheffingen_service.create_declaration(db_session, run)
    db_session.commit()

    errors = loonheffingen_service.run_validation(db_session, declaration)
    assert errors == []
    assert declaration.status.value == "ACCOUNTANT_REVIEW"

    loonheffingen_service.approve(db_session, declaration, user.id)
    assert declaration.status.value == "APPROVED"

    loonheffingen_service.mark_ready_for_submission(db_session, declaration)
    assert declaration.status.value == "READY_FOR_SUBMISSION"

    loonheffingen_service.record_submission(db_session, declaration, submission_reference="SBR-KENMERK-123", user_id=user.id)
    assert declaration.status.value == "SUBMITTED"
    assert declaration.submission_reference == "SBR-KENMERK-123"

    loonheffingen_service.record_government_response(db_session, declaration, accepted=True, response_reference="BD-ACK-456")
    db_session.commit()
    assert declaration.status.value == "ACCEPTED"
    assert declaration.government_response_reference == "BD-ACK-456"


def test_record_submission_requires_non_empty_reference(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = _approved_run_with_payslip(db_session, tenant, company, user, employee)
    declaration = loonheffingen_service.create_declaration(db_session, run)
    db_session.commit()
    loonheffingen_service.run_validation(db_session, declaration)
    loonheffingen_service.approve(db_session, declaration, user.id)
    loonheffingen_service.mark_ready_for_submission(db_session, declaration)

    with pytest.raises(loonheffingen_service.LoonheffingenError):
        loonheffingen_service.record_submission(db_session, declaration, submission_reference="   ", user_id=user.id)


def test_cannot_skip_states(db_session):
    """Submission must never be marked successful (or even attempted) without
    going through accountant review and approval first."""
    tenant, company, user, employee = _setup(db_session)
    run = _approved_run_with_payslip(db_session, tenant, company, user, employee)
    declaration = loonheffingen_service.create_declaration(db_session, run)
    db_session.commit()

    with pytest.raises(loonheffingen_service.LoonheffingenError):
        loonheffingen_service.record_submission(db_session, declaration, submission_reference="X", user_id=user.id)
    with pytest.raises(loonheffingen_service.LoonheffingenError):
        loonheffingen_service.approve(db_session, declaration, user.id)


def test_rejection_requires_reason(db_session):
    tenant, company, user, employee = _setup(db_session)
    run = _approved_run_with_payslip(db_session, tenant, company, user, employee)
    declaration = loonheffingen_service.create_declaration(db_session, run)
    db_session.commit()
    loonheffingen_service.run_validation(db_session, declaration)
    loonheffingen_service.approve(db_session, declaration, user.id)
    loonheffingen_service.mark_ready_for_submission(db_session, declaration)
    loonheffingen_service.record_submission(db_session, declaration, submission_reference="SBR-1", user_id=user.id)

    with pytest.raises(loonheffingen_service.LoonheffingenError):
        loonheffingen_service.record_government_response(db_session, declaration, accepted=False, response_reference="BD-ERR-1")

    loonheffingen_service.record_government_response(
        db_session, declaration, accepted=False, response_reference="BD-ERR-1", rejection_reason="Wrong BSN format",
    )
    db_session.commit()
    assert declaration.status.value == "REJECTED"
    assert declaration.rejection_reason == "Wrong BSN format"
