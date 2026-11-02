from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import BalanceSheetItemCategory


class ManualBalanceSheetItem(Base):
    """Fixed assets, inventory, equity, and loans are never derivable from
    this ledger (no chart of accounts) -- so they are only ever what an
    accountant explicitly records here, never computed or guessed by
    app/accounting/financial_reports.py."""

    __tablename__ = "manual_balance_sheet_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    category: Mapped[BalanceSheetItemCategory] = mapped_column(
        Enum(BalanceSheetItemCategory, name="balance_sheet_item_category")
    )
    label: Mapped[str] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    as_of_date: Mapped[date] = mapped_column(Date)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    company: Mapped["Company"] = relationship()
