"""Per-period completeness assessment for the company workspace. Conservative
by design: absence of evidence is reported as incomplete/needs-confirmation,
never silently treated as "nothing to report"."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.accounting import AccountingTransaction
from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType, LedgerSide, PaymentStatus, VatReturnStatus
from app.models.financial_year import VatPeriod


@dataclass(frozen=True)
class CompletenessRow:
    requirement: str
    complete: bool
    detail: str


def assess_period(db: Session, company_id: int, period: VatPeriod, vat_return_status: VatReturnStatus | None) -> list[CompletenessRow]:
    transactions = (
        db.query(AccountingTransaction)
        .filter(AccountingTransaction.company_id == company_id, AccountingTransaction.vat_period_id == period.id)
        .all()
    )
    sales_count = sum(1 for t in transactions if t.ledger_side == LedgerSide.sales)
    purchase_count = sum(1 for t in transactions if t.ledger_side == LedgerSide.purchases)
    overdue_count = sum(1 for t in transactions if t.payment_status == PaymentStatus.overdue)

    bank_statement_present = (
        db.query(Document)
        .filter(
            Document.company_id == company_id,
            Document.document_type == DocumentType.bank_statement,
            Document.status == DocumentStatus.approved,
            Document.created_at >= period.start_date,
            Document.created_at <= period.end_date,
        )
        .first()
        is not None
    )

    rows = [
        CompletenessRow(
            "Sales invoices",
            sales_count > 0,
            f"{sales_count} sales transaction(s) posted" if sales_count else "No sales transactions recorded for this period — confirm there were none",
        ),
        CompletenessRow(
            "Purchase invoices",
            purchase_count > 0,
            f"{purchase_count} purchase transaction(s) posted" if purchase_count else "No purchase transactions recorded for this period — confirm there were none",
        ),
        CompletenessRow(
            "Bank transactions",
            bank_statement_present,
            "Bank statement on file" if bank_statement_present else "No approved bank statement found for this period",
        ),
        CompletenessRow(
            "Payments reconciled",
            overdue_count == 0,
            "No overdue payments" if overdue_count == 0 else f"{overdue_count} overdue payment(s) outstanding",
        ),
        CompletenessRow(
            "VAT return reviewed",
            vat_return_status in (VatReturnStatus.approved, VatReturnStatus.locked),
            f"VAT return status: {vat_return_status.value if vat_return_status else 'not yet computed'}",
        ),
    ]
    return rows
