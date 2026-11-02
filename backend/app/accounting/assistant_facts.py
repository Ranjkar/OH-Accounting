"""Builds the deterministic FACTS bundle handed to the AI assistant. Every
number here comes from the database or an existing accounting service --
never from the AI itself."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting import reconciliation
from app.models.accounting import AccountingTransaction, VatReturn
from app.models.company import Company
from app.models.document import Document, DocumentValidationResult
from app.models.enums import DocumentStatus, LedgerSide, PaymentStatus, TransactionType, ValidationSeverity
from app.models.financial_year import VatPeriod


def company_facts(db: Session, company: Company) -> dict:
    transactions = db.query(AccountingTransaction).filter(AccountingTransaction.company_id == company.id).all()
    sales = [t for t in transactions if t.ledger_side == LedgerSide.sales]
    purchases = [t for t in transactions if t.ledger_side == LedgerSide.purchases]
    overdue = [t for t in transactions if t.payment_status == PaymentStatus.overdue]
    pending_documents = (
        db.query(Document)
        .filter(Document.company_id == company.id, Document.status.in_([DocumentStatus.extracted, DocumentStatus.needs_review]))
        .count()
    )
    return {
        "company_name": company.name,
        "vat_number": company.vat_number,
        "vat_frequency": company.vat_frequency.value,
        "vat_accounting_basis": company.vat_accounting_basis.value,
        "total_sales_transactions": len(sales),
        "total_sales_net": str(sum((t.net_amount for t in sales), Decimal("0"))),
        "total_purchase_transactions": len(purchases),
        "total_purchases_net": str(sum((t.net_amount for t in purchases), Decimal("0"))),
        "overdue_payment_count": len(overdue),
        "overdue_payment_transaction_ids": [t.id for t in overdue],
        "documents_awaiting_approval": pending_documents,
    }


def vat_return_facts(db: Session, vat_return: VatReturn) -> dict:
    period = vat_return.vat_period
    recon = reconciliation.build_reconciliation(db, vat_return.company_id, period)
    return {
        "period_label": period.label,
        "period_start": str(period.start_date),
        "period_end": str(period.end_date),
        "filing_deadline": str(period.filing_deadline),
        "vat_return_status": vat_return.status.value,
        "box_1a_sales_high_rate": {"net": str(vat_return.box_1a_net), "vat": str(vat_return.box_1a_vat)},
        "box_1b_sales_low_rate": {"net": str(vat_return.box_1b_net), "vat": str(vat_return.box_1b_vat)},
        "box_2a_domestic_reverse_charge": {"net": str(vat_return.box_2a_net), "vat": str(vat_return.box_2a_vat)},
        "box_3_exports_and_eu_supplies": {
            "export_non_eu_net": str(vat_return.box_3a_net),
            "eu_supply_net": str(vat_return.box_3b_net),
            "eu_distance_sale_net": str(vat_return.box_3c_net),
        },
        "box_4_imports_and_eu_acquisitions": {
            "import_net": str(vat_return.box_4a_net),
            "import_vat": str(vat_return.box_4a_vat),
            "eu_acquisition_net": str(vat_return.box_4b_net),
            "eu_acquisition_vat": str(vat_return.box_4b_vat),
        },
        "box_5a_total_vat_payable": str(vat_return.box_5a_vat),
        "box_5b_deductible_input_vat": str(vat_return.box_5b_vat),
        "net_payable_or_refundable": str(vat_return.net_payable),
        "sales_total_net": str(recon["sales_total_net"]),
        "purchases_total_net": str(recon["purchases_total_net"]),
        "pending_documents": recon["pending_documents"],
        "duplicate_documents": recon["duplicate_documents"],
        "validation_errors": recon["validation_errors"],
        "unresolved_fx_transaction_ids": recon["unresolved_fx_transaction_ids"],
        "correction_count": len(recon["corrections"]),
    }


def missing_documents_facts(db: Session, company: Company) -> dict:
    needs_review = (
        db.query(Document)
        .filter(Document.company_id == company.id, Document.status == DocumentStatus.needs_review)
        .all()
    )
    failed = db.query(Document).filter(Document.company_id == company.id, Document.status == DocumentStatus.failed).all()
    errors = (
        db.query(DocumentValidationResult)
        .join(Document, DocumentValidationResult.document_id == Document.id)
        .filter(Document.company_id == company.id, DocumentValidationResult.severity == ValidationSeverity.error)
        .all()
    )
    return {
        "documents_needing_review": [{"id": d.id, "filename": d.original_filename} for d in needs_review],
        "documents_that_failed_processing": [{"id": d.id, "filename": d.original_filename, "error": d.error_message} for d in failed],
        "validation_errors": [{"document_id": e.document_id, "rule": e.rule_code, "message": e.message} for e in errors],
    }


def period_comparison_facts(db: Session, company: Company, period_a: VatPeriod, period_b: VatPeriod) -> dict:
    def _period_summary(period: VatPeriod) -> dict:
        vat_return = db.query(VatReturn).filter(VatReturn.vat_period_id == period.id).first()
        transactions = (
            db.query(AccountingTransaction)
            .filter(AccountingTransaction.company_id == company.id, AccountingTransaction.vat_period_id == period.id)
            .all()
        )
        return {
            "label": period.label,
            "is_final": bool(vat_return and vat_return.status.value in ("approved", "locked")),
            "sales_net": str(sum((t.net_amount for t in transactions if t.ledger_side == LedgerSide.sales), Decimal("0"))),
            "purchases_net": str(sum((t.net_amount for t in transactions if t.ledger_side == LedgerSide.purchases), Decimal("0"))),
            "net_payable": str(vat_return.net_payable) if vat_return else None,
        }

    return {
        "period_a": _period_summary(period_a),
        "period_b": _period_summary(period_b),
    }
