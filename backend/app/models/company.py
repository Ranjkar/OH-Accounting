from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import VatAccountingBasis, VatFrequency
from app.models.user import user_companies


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255))
    kvk_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vat_frequency: Mapped[VatFrequency] = mapped_column(
        Enum(VatFrequency, name="vat_frequency"), default=VatFrequency.quarterly
    )
    vat_accounting_basis: Mapped[VatAccountingBasis] = mapped_column(
        Enum(VatAccountingBasis, name="vat_accounting_basis"), default=VatAccountingBasis.invoice_based
    )
    input_vat_pro_rata_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="companies")
    users: Mapped[list["User"]] = relationship(
        secondary=user_companies, back_populates="companies"
    )
    financial_years: Mapped[list["FinancialYear"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    customers: Mapped[list["Customer"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
