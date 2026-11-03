from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.accounting import ledger_service
from app.core.security import hash_password
from app.models.company import Company
from app.models.document import Document, DocumentLineItem, ExtractedInvoiceFields
from app.models.enums import DocumentStatus, DocumentType, LedgerSide, UserRole, VatTreatment
from app.models.financial_year import FinancialYear, VatPeriod
from app.models.tenant import Tenant
from app.models.user import User


def _setup(db_session):
    tenant = Tenant(name="T")
    db_session.add(tenant)
    db_session.flush()
    company = Company(tenant_id=tenant.id, name="C")
    db_session.add(company)
    db_session.flush()
    user = User(
        tenant_id=tenant.id, email="u@t.nl", hashed_password=hash_password("x"), full_name="U", role=UserRole.admin
    )
    db_session.add(user)
    db_session.flush()
    fy = FinancialYear(company_id=company.id, year=2026, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db_session.add(fy)
    db_session.flush()
    period = VatPeriod(
        financial_year_id=fy.id,
        label="Q1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        filing_deadline=date(2026, 4, 30),
        payment_deadline=date(2026, 4, 30),
    )
    db_session.add(period)
    db_session.commit()
    return tenant, company, fy, user


_UNSET = object()


def _make_document(db_session, tenant, company, fy, user, document_type, fields_kwargs, financial_year_id=_UNSET):
    document = Document(
        tenant_id=tenant.id,
        company_id=company.id,
        financial_year_id=fy.id if financial_year_id is _UNSET else financial_year_id,
        uploaded_by_user_id=user.id,
        original_filename="f.pdf",
        secure_filename="f.pdf",
        storage_path="x",
        content_type="application/pdf",
        file_size=1,
        sha256_hash="abc",
        status=DocumentStatus.extracted,
        document_type=document_type,
        classification_confidence=0.9,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    db_session.add(document)
    db_session.flush()
    fields = ExtractedInvoiceFields(document_id=document.id, **fields_kwargs)
    db_session.add(fields)
    db_session.commit()
    return document


def test_purchase_invoice_header_only_posts_single_line(db_session):
    tenant, company, fy, user = _setup(db_session)
    document = _make_document(
        db_session, tenant, company, fy, user, DocumentType.purchase_invoice,
        {
            "invoice_number": "INV-1",
            "invoice_date": date(2026, 2, 1),
            "supplier_name": "Acme",
            "supplier_vat_number": "NL123456789B01",
            "net_amount": 100.0,
            "vat_rate": 21.0,
            "vat_amount": 21.0,
            "gross_amount": 121.0,
        },
    )
    transaction = ledger_service.post_document_to_ledger(db_session, document, user.id)
    db_session.commit()

    assert transaction.ledger_side == LedgerSide.purchases
    assert transaction.net_amount == Decimal("100.0")
    assert transaction.vat_amount == Decimal("21.0")
    assert transaction.gross_amount == Decimal("121.0")
    assert len(transaction.line_items) == 1
    line = transaction.line_items[0]
    assert line.vat_treatment == VatTreatment.domestic_standard
    assert line.input_vat_eligibility.value == "ELIGIBLE"
    assert line.deductible_vat_amount == Decimal("21.00")
    assert transaction.vat_period.label == "Q1"


def test_multi_rate_document_line_items_carry_through(db_session):
    tenant, company, fy, user = _setup(db_session)
    document = _make_document(
        db_session, tenant, company, fy, user, DocumentType.sales_invoice,
        {
            "invoice_number": "INV-2",
            "invoice_date": date(2026, 2, 1),
            "customer_name": "Client BV",
        },
    )
    db_session.add_all(
        [
            DocumentLineItem(document_id=document.id, line_number=1, description="A", net_amount=100.0, vat_rate=21.0, vat_amount=21.0, gross_amount=121.0),
            DocumentLineItem(document_id=document.id, line_number=2, description="B", net_amount=50.0, vat_rate=9.0, vat_amount=4.5, gross_amount=54.5),
        ]
    )
    db_session.commit()

    transaction = ledger_service.post_document_to_ledger(db_session, document, user.id)
    db_session.commit()

    assert transaction.net_amount == Decimal("150.0")
    assert transaction.vat_amount == Decimal("25.5")
    assert len(transaction.line_items) == 2
    assert transaction.line_items[0].vat_treatment == VatTreatment.domestic_standard
    assert transaction.line_items[1].vat_treatment == VatTreatment.domestic_low


def test_credit_note_amounts_are_negated(db_session):
    tenant, company, fy, user = _setup(db_session)
    document = _make_document(
        db_session, tenant, company, fy, user, DocumentType.credit_note,
        {
            "invoice_number": "CN-1",
            "invoice_date": date(2026, 2, 1),
            "customer_name": "Client BV",
            "net_amount": 50.0,
            "vat_rate": 21.0,
            "vat_amount": 10.5,
            "gross_amount": 60.5,
        },
    )
    transaction = ledger_service.post_document_to_ledger(db_session, document, user.id, credit_note_ledger_side=LedgerSide.sales)
    db_session.commit()

    assert transaction.net_amount == Decimal("-50.0")
    assert transaction.vat_amount == Decimal("-10.5")
    assert transaction.gross_amount == Decimal("-60.5")


def test_credit_note_without_ledger_side_raises(db_session):
    tenant, company, fy, user = _setup(db_session)
    document = _make_document(
        db_session, tenant, company, fy, user, DocumentType.credit_note,
        {"invoice_number": "CN-2", "invoice_date": date(2026, 2, 1), "net_amount": 10.0, "vat_amount": 0, "gross_amount": 10.0},
    )
    with pytest.raises(ledger_service.LedgerPostingError):
        ledger_service.post_document_to_ledger(db_session, document, user.id)


def test_posting_without_financial_year_raises(db_session):
    tenant, company, fy, user = _setup(db_session)
    document = _make_document(
        db_session, tenant, company, fy, user, DocumentType.purchase_invoice,
        {"invoice_number": "INV-3", "invoice_date": date(2026, 2, 1), "net_amount": 10.0, "vat_amount": 0, "gross_amount": 10.0},
        financial_year_id=None,
    )
    with pytest.raises(ledger_service.LedgerPostingError):
        ledger_service.post_document_to_ledger(db_session, document, user.id)


def test_reposting_the_same_document_is_idempotent(db_session):
    tenant, company, fy, user = _setup(db_session)
    document = _make_document(
        db_session, tenant, company, fy, user, DocumentType.purchase_invoice,
        {"invoice_number": "INV-4", "invoice_date": date(2026, 2, 1), "net_amount": 10.0, "vat_rate": 21.0, "vat_amount": 2.1, "gross_amount": 12.1},
    )
    first = ledger_service.post_document_to_ledger(db_session, document, user.id)
    db_session.commit()
    second = ledger_service.post_document_to_ledger(db_session, document, user.id)
    db_session.commit()
    assert first.id == second.id


def test_bank_statement_and_other_are_not_postable():
    assert ledger_service.is_postable(DocumentType.bank_statement) is False
    assert ledger_service.is_postable(DocumentType.other) is False
    assert ledger_service.is_postable(DocumentType.purchase_invoice) is True


def test_posting_to_a_locked_financial_year_is_blocked(db_session):
    tenant, company, fy, user = _setup(db_session)
    fy.is_locked = True
    db_session.commit()
    document = _make_document(
        db_session, tenant, company, fy, user, DocumentType.purchase_invoice,
        {"invoice_number": "INV-5", "invoice_date": date(2026, 2, 1), "net_amount": 10.0, "vat_rate": 21.0, "vat_amount": 2.1, "gross_amount": 12.1},
    )
    with pytest.raises(ledger_service.LedgerPostingError):
        ledger_service.post_document_to_ledger(db_session, document, user.id)


def test_manual_entry_in_a_locked_financial_year_is_blocked(db_session):
    tenant, company, fy, user = _setup(db_session)
    fy.is_locked = True
    db_session.commit()
    with pytest.raises(ledger_service.LedgerPostingError):
        ledger_service.create_manual_entry(
            db_session, tenant_id=tenant.id, company=company, financial_year_id=fy.id,
            ledger_side=LedgerSide.sales, invoice_date=date(2026, 2, 1), due_date=None,
            currency="EUR", fx_rate_to_eur=None, counterparty_name=None, counterparty_vat_number=None,
            accounting_classification=None,
            line_items=[{"net_amount": "100.00", "vat_rate": "21", "vat_amount": "21.00", "vat_treatment": VatTreatment.domestic_standard}],
            created_by_user_id=user.id,
        )
