from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import (
    InputVatEligibility,
    LedgerSide,
    PaymentStatus,
    TransactionApprovalStatus,
    TransactionType,
    VatReturnStatus,
    VatTreatment,
)

MONEY = Numeric(14, 2)
RATE = Numeric(6, 3)
FX_RATE = Numeric(12, 6)


class AccountingTransaction(Base):
    __tablename__ = "accounting_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    financial_year_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id"))
    vat_period_id: Mapped[int | None] = mapped_column(ForeignKey("vat_periods.id"), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)

    corrects_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounting_transactions.id"), nullable=True
    )

    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType, name="transaction_type"))
    ledger_side: Mapped[LedgerSide] = mapped_column(Enum(LedgerSide, name="ledger_side"))

    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    counterparty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_vat_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    counterparty_country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)

    invoice_date: Mapped[date] = mapped_column(Date)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    fx_rate_to_eur: Mapped[Decimal | None] = mapped_column(FX_RATE, nullable=True)

    net_amount: Mapped[Decimal] = mapped_column(MONEY)
    vat_amount: Mapped[Decimal] = mapped_column(MONEY)
    gross_amount: Mapped[Decimal] = mapped_column(MONEY)
    # Null when currency != EUR and no FX rate has been supplied yet. Such
    # transactions are excluded from VAT return box totals (flagged in the
    # reconciliation view) rather than guessing a rate of 1.
    net_amount_eur: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    vat_amount_eur: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    gross_amount_eur: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.unpaid
    )
    approval_status: Mapped[TransactionApprovalStatus] = mapped_column(
        Enum(TransactionApprovalStatus, name="transaction_approval_status"),
        default=TransactionApprovalStatus.draft,
    )
    accounting_classification: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company: Mapped["Company"] = relationship()
    financial_year: Mapped["FinancialYear"] = relationship()
    vat_period: Mapped["VatPeriod | None"] = relationship()
    source_document: Mapped["Document | None"] = relationship()
    corrects: Mapped["AccountingTransaction | None"] = relationship(remote_side=[id])

    line_items: Mapped[list["TransactionLineItem"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", order_by="TransactionLineItem.line_number"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="transaction", cascade="all, delete-orphan")


class TransactionLineItem(Base):
    __tablename__ = "transaction_line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("accounting_transactions.id"))
    source_document_line_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_line_items.id"), nullable=True
    )
    line_number: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    net_amount: Mapped[Decimal] = mapped_column(MONEY)
    vat_rate: Mapped[Decimal] = mapped_column(RATE)
    vat_amount: Mapped[Decimal] = mapped_column(MONEY)
    gross_amount: Mapped[Decimal] = mapped_column(MONEY)

    vat_treatment: Mapped[VatTreatment] = mapped_column(Enum(VatTreatment, name="vat_treatment"))
    input_vat_eligibility: Mapped[InputVatEligibility | None] = mapped_column(
        Enum(InputVatEligibility, name="input_vat_eligibility"), nullable=True
    )
    deductible_vat_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    transaction: Mapped["AccountingTransaction"] = relationship(back_populates="line_items")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    transaction_id: Mapped[int] = mapped_column(ForeignKey("accounting_transactions.id"))

    amount: Mapped[Decimal] = mapped_column(MONEY)
    payment_date: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    transaction: Mapped["AccountingTransaction"] = relationship(back_populates="payments")


class VatReturn(Base):
    __tablename__ = "vat_returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    vat_period_id: Mapped[int] = mapped_column(ForeignKey("vat_periods.id"), unique=True)

    status: Mapped[VatReturnStatus] = mapped_column(
        Enum(VatReturnStatus, name="vat_return_status"), default=VatReturnStatus.draft
    )
    rules_version: Mapped[str] = mapped_column(String(50))

    box_1a_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_1a_vat: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_1b_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_1b_vat: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_1c_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_1c_vat: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_1d_vat: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_1e_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_2a_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_2a_vat: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_3a_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_3b_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_3c_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_4a_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_4a_vat: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_4b_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_4b_vat: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_5a_vat: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    box_5b_vat: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    net_payable: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))

    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    vat_period: Mapped["VatPeriod"] = relationship()
