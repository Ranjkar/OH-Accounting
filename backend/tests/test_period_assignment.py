from datetime import date

from app.accounting.period_assignment import determine_vat_period
from app.core.security import hash_password
from app.models.company import Company
from app.models.enums import LedgerSide, UserRole, VatAccountingBasis, VatFrequency
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.tenant import Tenant
from app.models.user import User


def _setup_company_with_quarters(db_session, basis=VatAccountingBasis.invoice_based):
    tenant = Tenant(name="T")
    db_session.add(tenant)
    db_session.flush()
    company = Company(tenant_id=tenant.id, name="C", vat_frequency=VatFrequency.quarterly, vat_accounting_basis=basis)
    db_session.add(company)
    db_session.flush()
    fy = FinancialYear(company_id=company.id, year=2026, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db_session.add(fy)
    db_session.flush()
    q1 = VatPeriod(
        financial_year_id=fy.id,
        label="Q1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        filing_deadline=date(2026, 4, 30),
        payment_deadline=date(2026, 4, 30),
    )
    q2 = VatPeriod(
        financial_year_id=fy.id,
        label="Q2",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 6, 30),
        filing_deadline=date(2026, 7, 31),
        payment_deadline=date(2026, 7, 31),
    )
    db_session.add_all([q1, q2])
    db_session.commit()
    return company, fy, q1, q2


def test_invoice_based_sales_uses_invoice_date(db_session):
    company, fy, q1, q2 = _setup_company_with_quarters(db_session)
    period = determine_vat_period(
        db_session, company, fy.id, LedgerSide.sales, invoice_date=date(2026, 1, 15), received_date=date(2026, 4, 2)
    )
    assert period.label == "Q1"  # invoice date governs sales, not received date


def test_invoice_based_purchase_uses_received_date(db_session):
    company, fy, q1, q2 = _setup_company_with_quarters(db_session)
    period = determine_vat_period(
        db_session, company, fy.id, LedgerSide.purchases, invoice_date=date(2026, 1, 15), received_date=date(2026, 4, 2)
    )
    assert period.label == "Q2"  # received date governs purchases


def test_invoice_based_purchase_without_received_date_falls_back_to_invoice_date(db_session):
    company, fy, q1, q2 = _setup_company_with_quarters(db_session)
    period = determine_vat_period(
        db_session, company, fy.id, LedgerSide.purchases, invoice_date=date(2026, 1, 15), received_date=None
    )
    assert period.label == "Q1"


def test_invoice_based_payment_date_never_moves_the_period(db_session):
    company, fy, q1, q2 = _setup_company_with_quarters(db_session)
    period = determine_vat_period(
        db_session,
        company,
        fy.id,
        LedgerSide.sales,
        invoice_date=date(2026, 1, 15),
        received_date=None,
        payment_date=date(2026, 6, 1),  # paid much later, in Q2
    )
    assert period.label == "Q1"  # still Q1 -- payment date is irrelevant under invoice-based accounting


def test_cash_based_uses_payment_date(db_session):
    company, fy, q1, q2 = _setup_company_with_quarters(db_session, basis=VatAccountingBasis.cash_based)
    period = determine_vat_period(
        db_session,
        company,
        fy.id,
        LedgerSide.sales,
        invoice_date=date(2026, 1, 15),
        received_date=None,
        payment_date=date(2026, 5, 1),
    )
    assert period.label == "Q2"


def test_cash_based_without_payment_is_unassigned(db_session):
    company, fy, q1, q2 = _setup_company_with_quarters(db_session, basis=VatAccountingBasis.cash_based)
    period = determine_vat_period(
        db_session, company, fy.id, LedgerSide.sales, invoice_date=date(2026, 1, 15), received_date=None
    )
    assert period is None
