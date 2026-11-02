"""VAT-period assignment. Kept separate from the posting logic because the
rules genuinely differ by accounting basis and deserve their own tests."""

from datetime import date

from sqlalchemy.orm import Session

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
