"""Bank transaction ledger. Transactions arrive by file import (CAMT.053/054,
MT940, CSV) -- there is no live Open Banking provider connection in this
build (see docs/bank-integration.md for the adapter architecture and what a
real connection would require). Source rows are treated as immutable once
imported: only reconciliation_status and match bookkeeping ever change."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import BankConsentStatus, BankSourceFormat, ReconciliationStatus

MONEY = Numeric(14, 2)


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (UniqueConstraint("company_id", "iban", name="uq_bank_account_company_iban"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    iban: Mapped[str] = mapped_column(String(34))
    account_name: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Open Banking groundwork -- never actually connected in this build.
    consent_status: Mapped[BankConsentStatus] = mapped_column(
        Enum(BankConsentStatus, name="bank_consent_status"), default=BankConsentStatus.not_connected
    )
    consent_granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    company: Mapped["Company"] = relationship()
    import_batches: Mapped[list["BankImportBatch"]] = relationship(back_populates="bank_account")
    transactions: Mapped[list["BankTransaction"]] = relationship(back_populates="bank_account")


class BankImportBatch(Base):
    """One row per file import -- the audit trail of what was imported, when,
    by whom, and how many rows were new vs. duplicates vs. errored."""

    __tablename__ = "bank_import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))

    source_format: Mapped[BankSourceFormat] = mapped_column(Enum(BankSourceFormat, name="bank_source_format"))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))

    transaction_count: Mapped[int] = mapped_column(default=0)
    duplicate_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    imported_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    bank_account: Mapped["BankAccount"] = relationship(back_populates="import_batches")
    transactions: Mapped[list["BankTransaction"]] = relationship(back_populates="import_batch")


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (UniqueConstraint("bank_account_id", "dedupe_hash", name="uq_bank_transaction_dedupe"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("bank_import_batches.id"))

    external_transaction_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), index=True)

    booking_date: Mapped[date] = mapped_column(Date)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)  # signed: positive = incoming, negative = outgoing
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    counterparty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_format: Mapped[BankSourceFormat] = mapped_column(Enum(BankSourceFormat, name="bank_source_format"))
    raw_data: Mapped[dict] = mapped_column(JSON)

    reconciliation_status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, name="reconciliation_status"), default=ReconciliationStatus.imported
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    bank_account: Mapped["BankAccount"] = relationship(back_populates="transactions")
    import_batch: Mapped["BankImportBatch"] = relationship(back_populates="transactions")
    matches: Mapped[list["PaymentMatch"]] = relationship(back_populates="bank_transaction", cascade="all, delete-orphan")


class PaymentMatch(Base):
    """A proposed or confirmed allocation of (part of) a bank transaction to
    an accounting transaction. One bank transaction can have several rows
    (combined payment covering multiple invoices, or a partial allocation);
    one accounting transaction can likewise be matched by several bank
    transactions (several partial payments)."""

    __tablename__ = "payment_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    bank_transaction_id: Mapped[int] = mapped_column(ForeignKey("bank_transactions.id"))
    accounting_transaction_id: Mapped[int] = mapped_column(ForeignKey("accounting_transactions.id"))

    allocated_amount: Mapped[Decimal] = mapped_column(MONEY)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    confidence_level: Mapped[str] = mapped_column(String(10))
    match_signals: Mapped[dict] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(String(20), default="SUGGESTED")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)

    bank_transaction: Mapped["BankTransaction"] = relationship(back_populates="matches")
    accounting_transaction: Mapped["AccountingTransaction"] = relationship()
