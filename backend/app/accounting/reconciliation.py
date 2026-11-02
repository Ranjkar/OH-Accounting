"""Builds the quarterly VAT reconciliation view: ledger totals, box totals,
and everything an accountant needs to flag before approving a period."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.accounting import AccountingTransaction, TransactionLineItem
from app.models.document import Document, DocumentValidationResult
from app.models.enums import DocumentStatus, LedgerSide, ValidationSeverity
from app.models.financial_year import VatPeriod

ZERO = Decimal("0")


def build_reconciliation(db: Session, company_id: int, vat_period: VatPeriod) -> dict:
    transactions = (
        db.query(AccountingTransaction)
        .filter(AccountingTransaction.vat_period_id == vat_period.id, AccountingTransaction.company_id == company_id)
        .all()
    )

    sales_total_net = sum(
        (t.net_amount for t in transactions if t.ledger_side == LedgerSide.sales), ZERO
    )
    purchases_total_net = sum(
        (t.net_amount for t in transactions if t.ledger_side == LedgerSide.purchases), ZERO
    )

    sales_vat_by_rate: dict[str, Decimal] = {}
    purchase_vat_by_rate: dict[str, Decimal] = {}
    for t in transactions:
        bucket = sales_vat_by_rate if t.ledger_side == LedgerSide.sales else purchase_vat_by_rate
        for line in t.line_items:
            key = str(line.vat_rate)
            bucket[key] = bucket.get(key, ZERO) + line.vat_amount

    unresolved_fx_transaction_ids = [t.id for t in transactions if t.currency != "EUR" and t.net_amount_eur is None]

    corrections = [t for t in transactions if t.corrects_transaction_id is not None]

    pending_documents = (
        db.query(Document)
        .filter(
            Document.company_id == company_id,
            Document.status.in_(
                [
                    DocumentStatus.pending,
                    DocumentStatus.processing,
                    DocumentStatus.extracted,
                    DocumentStatus.needs_review,
                    DocumentStatus.failed,
                ]
            ),
        )
        .all()
    )
    pending_in_period = [
        d
        for d in pending_documents
        if d.fields
        and d.fields.invoice_date
        and vat_period.start_date <= d.fields.invoice_date <= vat_period.end_date
    ]

    duplicate_documents = [
        d for d in pending_documents if d.is_duplicate
    ] + [
        d
        for d in db.query(Document).filter(Document.company_id == company_id, Document.is_duplicate.is_(True)).all()
        if d not in pending_documents
    ]

    validation_errors = (
        db.query(DocumentValidationResult)
        .join(Document, DocumentValidationResult.document_id == Document.id)
        .filter(Document.company_id == company_id, DocumentValidationResult.severity == ValidationSeverity.error)
        .all()
    )

    return {
        "sales_total_net": sales_total_net,
        "purchases_total_net": purchases_total_net,
        "sales_vat_by_rate": sales_vat_by_rate,
        "purchase_vat_by_rate": purchase_vat_by_rate,
        "pending_documents": [
            {"id": d.id, "original_filename": d.original_filename, "status": d.status.value} for d in pending_in_period
        ],
        "duplicate_documents": [
            {"id": d.id, "original_filename": d.original_filename, "duplicate_of_document_id": d.duplicate_of_document_id}
            for d in duplicate_documents
        ],
        "validation_errors": [
            {"document_id": v.document_id, "rule_code": v.rule_code, "message": v.message} for v in validation_errors
        ],
        "unresolved_fx_transaction_ids": unresolved_fx_transaction_ids,
        "corrections": corrections,
    }
