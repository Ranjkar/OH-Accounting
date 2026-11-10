"""Imports a bank statement file into BankTransaction rows. Synchronous --
parsing is fast and deterministic, nothing here calls an external API, so
there's no need for the background-task machinery the document pipeline
uses for OCR/Claude calls."""

from sqlalchemy.orm import Session

from app.accounting.bank_parsers import (
    BankFileParseError,
    ParsedBankTransaction,
    parse_camt053,
    parse_camt054,
    parse_csv,
    parse_mt940,
)
from app.models.banking import BankAccount, BankImportBatch, BankTransaction
from app.models.enums import BankSourceFormat, ReconciliationStatus
from app.services import storage
from app.services.file_validation import secure_filename

_PARSERS = {
    BankSourceFormat.camt053: parse_camt053,
    BankSourceFormat.camt054: parse_camt054,
    BankSourceFormat.mt940: parse_mt940,
    BankSourceFormat.csv: parse_csv,
}


class BankImportError(Exception):
    pass


def insert_rows_with_dedup(
    db: Session, bank_account: BankAccount, batch: BankImportBatch, parsed_rows: list[ParsedBankTransaction], source_format: BankSourceFormat,
) -> tuple[int, int]:
    """Shared by file import and Open Banking sync (app.services.
    open_banking_service) -- the actual duplicate-prevention logic (a
    dedupe_hash lookup, backed by the DB's own uq_bank_transaction_dedupe
    unique constraint) must not be duplicated across two call sites.
    Returns (created_count, duplicate_count)."""
    duplicate_count = 0
    created_count = 0
    for row in parsed_rows:
        dedupe_hash = row.dedupe_hash()
        existing = (
            db.query(BankTransaction)
            .filter(BankTransaction.bank_account_id == bank_account.id, BankTransaction.dedupe_hash == dedupe_hash)
            .first()
        )
        if existing is not None:
            duplicate_count += 1
            continue

        db.add(
            BankTransaction(
                tenant_id=bank_account.tenant_id,
                company_id=bank_account.company_id,
                bank_account_id=bank_account.id,
                import_batch_id=batch.id,
                external_transaction_id=row.external_transaction_id,
                dedupe_hash=dedupe_hash,
                booking_date=row.booking_date,
                value_date=row.value_date,
                amount=row.amount,
                currency=row.currency,
                counterparty_name=row.counterparty_name,
                counterparty_iban=row.counterparty_iban,
                payment_reference=row.payment_reference,
                description=row.description,
                source_format=source_format,
                raw_data=row.raw_data,
                reconciliation_status=ReconciliationStatus.imported,
            )
        )
        created_count += 1

    batch.transaction_count = created_count
    batch.duplicate_count = duplicate_count
    db.flush()
    return created_count, duplicate_count


def import_bank_file(
    db: Session,
    bank_account: BankAccount,
    content: bytes,
    filename: str,
    source_format: BankSourceFormat,
    imported_by_user_id: int,
) -> BankImportBatch:
    parser = _PARSERS[source_format]
    try:
        parsed_rows: list[ParsedBankTransaction] = parser(content)
    except BankFileParseError as exc:
        raise BankImportError(str(exc)) from exc

    batch = BankImportBatch(
        tenant_id=bank_account.tenant_id,
        company_id=bank_account.company_id,
        bank_account_id=bank_account.id,
        source_format=source_format,
        original_filename=filename,
        storage_path="",
        imported_by_user_id=imported_by_user_id,
    )
    db.add(batch)
    db.flush()

    clean_name = secure_filename(filename)
    batch.storage_path = storage.save(bank_account.tenant_id, bank_account.company_id, batch.id, clean_name, content)

    insert_rows_with_dedup(db, bank_account, batch, parsed_rows, source_format)
    return batch
