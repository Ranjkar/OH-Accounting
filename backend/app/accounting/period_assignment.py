"""VAT-period assignment. Kept separate from the posting logic because the
rules genuinely differ by accounting basis and deserve their own tests."""

from datetime import date

from sqlalchemy.orm import Session

from app.models.accounting import AccountingTransaction
from app.models.company import Company
from app.models.enums import LedgerSide, VatAccountingBasis
from app.models.financial_year import VatPeriod


def determine_vat_period(
    db: Session,
    company: Company,
    financial_year_id: int,
    ledger_side: LedgerSide,
    invoice_date: date,
    received_date: date | None,
    payment_date: date | None = None,
) -> VatPeriod | None:
    """Invoice-based (the default): sales use the invoice date; purchases use
    the date the invoice was received (falling back to the invoice date).
    Payment date never moves an invoice-based transaction to another period.

    Cash-based: the period is the one containing the payment date. With no
    payment recorded yet, the transaction is left unassigned until one is.
    """
    if company.vat_accounting_basis == VatAccountingBasis.cash_based:
        if payment_date is None:
            return None
        anchor_date = payment_date
    else:
        anchor_date = invoice_date if ledger_side == LedgerSide.sales else (received_date or invoice_date)

    return (
        db.query(VatPeriod)
        .filter(
            VatPeriod.financial_year_id == financial_year_id,
            VatPeriod.start_date <= anchor_date,
            VatPeriod.end_date >= anchor_date,
        )
        .first()
    )


def assign_vat_period_on_payment(
    db: Session, transaction: AccountingTransaction, payment_date: date
) -> None:
    """Assigns the VAT period for a cash-based transaction once it is paid.

    Phase 19 (audit finding 6.2). For a cash-based company the period is the
    one containing the PAYMENT date, which by definition is not known when the
    transaction is posted -- so `determine_vat_period` correctly returns None
    at posting time and the transaction waits. Nothing ever came back to
    assign it afterwards: neither `record_payment` nor
    `reconciliation_service.approve_match` called this, and
    `app/api/v1/transactions.py` imported `determine_vat_period` without ever
    calling it. Every cash-based transaction therefore kept
    `vat_period = NULL` permanently, and since `calculate_vat_return` filters
    on `vat_period_id`, such a company's return computed to all zeros --
    silently, with no error and no reconciliation flag.

    Both payment paths now call this. It is deliberately a no-op when:
      * the transaction already has a period (invoice-based companies are
        assigned at posting and must never be moved by a later payment --
        see `determine_vat_period`'s own docstring); or
      * the company is not cash-based.
    """
    if transaction.vat_period_id is not None:
        return
    company = db.get(Company, transaction.company_id)
    if company is None or company.vat_accounting_basis != VatAccountingBasis.cash_based:
        return
    transaction.vat_period = determine_vat_period(
        db,
        company,
        transaction.financial_year_id,
        transaction.ledger_side,
        transaction.invoice_date,
        transaction.received_date,
        payment_date=payment_date,
    )
