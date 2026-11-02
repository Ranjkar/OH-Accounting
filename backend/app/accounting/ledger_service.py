"""Converts approved documents into ledger transactions, and handles manual
entries and corrections. This is the one place Phase-2 extraction data
crosses into the Phase-3 ledger -- everything downstream of here is Decimal
and deterministic."""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.accounting import vat_rules
from app.accounting.period_assignment import determine_vat_period
from app.models.accounting import AccountingTransaction, TransactionLineItem
from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentType, InputVatEligibility, LedgerSide, TransactionApprovalStatus, TransactionType
from app.models.financial_year import FinancialYear

LEDGER_SIDE_BY_DOCUMENT_TYPE = {
    DocumentType.sales_invoice: LedgerSide.sales,
    DocumentType.purchase_invoice: LedgerSide.purchases,
    DocumentType.receipt: LedgerSide.purchases,
}
TRANSACTION_TYPE_BY_DOCUMENT_TYPE = {
    DocumentType.sales_invoice: TransactionType.sales_invoice,
    DocumentType.purchase_invoice: TransactionType.purchase_invoice,
    DocumentType.receipt: TransactionType.receipt,
    DocumentType.credit_note: TransactionType.credit_note,
}


class LedgerPostingError(Exception):
    pass


def is_postable(document_type: DocumentType | None) -> bool:
    return document_type in TRANSACTION_TYPE_BY_DOCUMENT_TYPE


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def post_document_to_ledger(
    db: Session, document: Document, user_id: int, credit_note_ledger_side: LedgerSide | None = None
) -> AccountingTransaction:
    if not is_postable(document.document_type):
        raise LedgerPostingError(f"Document type {document.document_type} is not postable to the ledger")
    if document.fields is None:
        raise LedgerPostingError("Document has no extracted fields to post")

    existing = (
        db.query(AccountingTransaction).filter(AccountingTransaction.source_document_id == document.id).first()
    )
    if existing is not None:
        return existing  # idempotent: re-approving never double-posts

    if document.document_type == DocumentType.credit_note:
        if credit_note_ledger_side is None:
            raise LedgerPostingError("Credit notes require an explicit ledger side (sales or purchases)")
        ledger_side = credit_note_ledger_side
    else:
        ledger_side = LEDGER_SIDE_BY_DOCUMENT_TYPE[document.document_type]
    transaction_type = TRANSACTION_TYPE_BY_DOCUMENT_TYPE[document.document_type]

    if document.financial_year_id is None:
        raise LedgerPostingError(
            "Document has no financial year assigned; assign one before approving so it can be posted"
        )
    financial_year = db.get(FinancialYear, document.financial_year_id)
    company: Company = document.company
    fields = document.fields

    invoice_date = fields.invoice_date or document.created_at.date()
    received_date = document.created_at.date()
    sign = Decimal("-1") if document.document_type == DocumentType.credit_note else Decimal("1")

    currency = (fields.currency or "EUR").upper()
    fx_rate = Decimal("1") if currency == "EUR" else None

    counterparty_vat_number = (
        fields.supplier_vat_number if ledger_side == LedgerSide.purchases else fields.customer_vat_number
    )
    counterparty_name = fields.supplier_name if ledger_side == LedgerSide.purchases else fields.customer_name

    transaction = AccountingTransaction(
        tenant_id=document.tenant_id,
        company_id=document.company_id,
        financial_year_id=financial_year.id,
        source_document_id=document.id,
        transaction_type=transaction_type,
        ledger_side=ledger_side,
        invoice_number=fields.invoice_number,
        counterparty_name=counterparty_name,
        counterparty_vat_number=counterparty_vat_number,
        counterparty_country_code=vat_rules.country_from_vat_number(counterparty_vat_number),
        counterparty_iban=fields.iban,
        invoice_date=invoice_date,
        due_date=fields.due_date,
        received_date=received_date,
        currency=currency,
        fx_rate_to_eur=fx_rate,
        net_amount=Decimal("0"),
        vat_amount=Decimal("0"),
        gross_amount=Decimal("0"),
        net_amount_eur=None,
        vat_amount_eur=None,
        gross_amount_eur=None,
        created_by_user_id=user_id,
    )

    source_lines = list(document.line_items) or [None]
    net_total = vat_total = gross_total = Decimal("0")
    line_models: list[TransactionLineItem] = []

    for i, src in enumerate(source_lines, start=1):
        if src is not None:
            raw_rate = src.vat_rate
            net, rate, vat = _to_decimal(src.net_amount), _to_decimal(src.vat_rate), _to_decimal(src.vat_amount)
            gross = _to_decimal(src.gross_amount) or (net + vat)
            description, source_line_id = src.description, src.id
        else:
            raw_rate = fields.vat_rate
            net, rate, vat = _to_decimal(fields.net_amount), _to_decimal(fields.vat_rate), _to_decimal(fields.vat_amount)
            gross = _to_decimal(fields.gross_amount) or (net + vat)
            description, source_line_id = fields.description, None

        net, vat, gross = net * sign, vat * sign, gross * sign

        treatment = vat_rules.classify_default_treatment(
            ledger_side, Decimal(str(raw_rate)) if raw_rate is not None else None, counterparty_vat_number
        )
        eligibility = None
        deductible = None
        if ledger_side == LedgerSide.purchases:
            eligibility = vat_rules.default_input_vat_eligibility(vat, fields.invoice_number, fields.supplier_vat_number)
            deductible = vat_rules.compute_deductible_vat(vat, eligibility, company.input_vat_pro_rata_percentage)

        line_models.append(
            TransactionLineItem(
                line_number=i,
                source_document_line_item_id=source_line_id,
                description=description,
                net_amount=net,
                vat_rate=rate,
                vat_amount=vat,
                gross_amount=gross,
                vat_treatment=treatment,
                input_vat_eligibility=eligibility,
                deductible_vat_amount=deductible,
            )
        )
        net_total, vat_total, gross_total = net_total + net, vat_total + vat, gross_total + gross

    transaction.net_amount, transaction.vat_amount, transaction.gross_amount = net_total, vat_total, gross_total
    if fx_rate is not None:
        transaction.net_amount_eur = (net_total * fx_rate).quantize(Decimal("0.01"))
        transaction.vat_amount_eur = (vat_total * fx_rate).quantize(Decimal("0.01"))
        transaction.gross_amount_eur = (gross_total * fx_rate).quantize(Decimal("0.01"))
    transaction.line_items = line_models

    transaction.vat_period = determine_vat_period(
        db, company, financial_year.id, ledger_side, invoice_date, received_date
    )

    db.add(transaction)
    db.flush()
    return transaction


def apply_fx_rate(db: Session, transaction: AccountingTransaction, fx_rate_to_eur: Decimal) -> None:
    if transaction.approval_status != TransactionApprovalStatus.draft:
        raise LedgerPostingError("Cannot change the FX rate of a transaction that is no longer in draft")
    transaction.fx_rate_to_eur = fx_rate_to_eur
    transaction.net_amount_eur = (transaction.net_amount * fx_rate_to_eur).quantize(Decimal("0.01"))
    transaction.vat_amount_eur = (transaction.vat_amount * fx_rate_to_eur).quantize(Decimal("0.01"))
    transaction.gross_amount_eur = (transaction.gross_amount * fx_rate_to_eur).quantize(Decimal("0.01"))
    db.flush()


def create_manual_entry(
    db: Session,
    *,
    tenant_id: int,
    company: Company,
    financial_year_id: int,
    ledger_side: LedgerSide,
    invoice_date: date,
    due_date: date | None,
    currency: str,
    fx_rate_to_eur: Decimal | None,
    counterparty_name: str | None,
    counterparty_vat_number: str | None,
    accounting_classification: str | None,
    line_items: list[dict],
    created_by_user_id: int,
    counterparty_iban: str | None = None,
) -> AccountingTransaction:
    transaction = AccountingTransaction(
        tenant_id=tenant_id,
        company_id=company.id,
        financial_year_id=financial_year_id,
        source_document_id=None,
        transaction_type=TransactionType.manual_entry,
        ledger_side=ledger_side,
        invoice_number=None,
        counterparty_name=counterparty_name,
        counterparty_vat_number=counterparty_vat_number,
        counterparty_country_code=vat_rules.country_from_vat_number(counterparty_vat_number),
        counterparty_iban=counterparty_iban,
        invoice_date=invoice_date,
        due_date=due_date,
        received_date=invoice_date,
        currency=currency.upper(),
        fx_rate_to_eur=fx_rate_to_eur,
        accounting_classification=accounting_classification,
        net_amount=Decimal("0"),
        vat_amount=Decimal("0"),
        gross_amount=Decimal("0"),
        created_by_user_id=created_by_user_id,
    )

    net_total = vat_total = gross_total = Decimal("0")
    line_models = []
    for i, item in enumerate(line_items, start=1):
        net, rate, vat = Decimal(str(item["net_amount"])), Decimal(str(item["vat_rate"])), Decimal(str(item["vat_amount"]))
        gross = net + vat
        treatment = vat_rules.VatTreatment(item["vat_treatment"]) if isinstance(item.get("vat_treatment"), str) else item.get("vat_treatment")
        vat_rules.box_for_line(ledger_side, treatment)  # validates it's legal for this side

        eligibility = None
        deductible = None
        if ledger_side == LedgerSide.purchases:
            eligibility = InputVatEligibility(item["input_vat_eligibility"]) if item.get("input_vat_eligibility") else InputVatEligibility.requires_review
            deductible = vat_rules.compute_deductible_vat(vat, eligibility, company.input_vat_pro_rata_percentage)

        line_models.append(
            TransactionLineItem(
                line_number=i,
                description=item.get("description"),
                net_amount=net,
                vat_rate=rate,
                vat_amount=vat,
                gross_amount=gross,
                vat_treatment=treatment,
                input_vat_eligibility=eligibility,
                deductible_vat_amount=deductible,
            )
        )
        net_total, vat_total, gross_total = net_total + net, vat_total + vat, gross_total + gross

    transaction.net_amount, transaction.vat_amount, transaction.gross_amount = net_total, vat_total, gross_total
    if fx_rate_to_eur is not None:
        transaction.net_amount_eur = (net_total * fx_rate_to_eur).quantize(Decimal("0.01"))
        transaction.vat_amount_eur = (vat_total * fx_rate_to_eur).quantize(Decimal("0.01"))
        transaction.gross_amount_eur = (gross_total * fx_rate_to_eur).quantize(Decimal("0.01"))
    elif currency.upper() == "EUR":
        transaction.net_amount_eur, transaction.vat_amount_eur, transaction.gross_amount_eur = net_total, vat_total, gross_total
    transaction.line_items = line_models
    transaction.vat_period = determine_vat_period(db, company, financial_year_id, ledger_side, invoice_date, invoice_date)

    db.add(transaction)
    db.flush()
    return transaction


def create_correction(
    db: Session,
    original: AccountingTransaction,
    delta_line_items: list[dict],
    created_by_user_id: int,
    financial_year_id: int,
) -> AccountingTransaction:
    """A correction is a brand-new transaction linked back to the original --
    the original's figures are never rewritten once approved/locked."""
    correction = create_manual_entry(
        db,
        tenant_id=original.tenant_id,
        company=original.company,
        financial_year_id=financial_year_id,
        ledger_side=original.ledger_side,
        invoice_date=date.today(),
        due_date=None,
        currency=original.currency,
        fx_rate_to_eur=original.fx_rate_to_eur,
        counterparty_name=original.counterparty_name,
        counterparty_vat_number=original.counterparty_vat_number,
        accounting_classification=f"Correction of transaction #{original.id}",
        line_items=delta_line_items,
        created_by_user_id=created_by_user_id,
    )
    correction.corrects_transaction_id = original.id
    db.flush()
    return correction
