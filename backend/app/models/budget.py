from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import BudgetLineSource, BudgetStatus


class Budget(Base):
    """A company's budget for one financial year. Revisions are never edited
    in place once APPROVED -- same immutable-correction pattern as
    AccountingTransaction.corrects_transaction_id: a revision is a new row
    with version = previous + 1 and supersedes_budget_id pointing back, so
    the full history of what was budgeted when is always still there."""

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    financial_year_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id"))

    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[BudgetStatus] = mapped_column(Enum(BudgetStatus, name="budget_status"), default=BudgetStatus.draft)
    version: Mapped[int] = mapped_column(default=1)
    supersedes_budget_id: Mapped[int | None] = mapped_column(ForeignKey("budgets.id"), nullable=True)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship()
    financial_year: Mapped["FinancialYear"] = relationship()
    supersedes: Mapped["Budget | None"] = relationship(remote_side=[id])
    lines: Mapped[list["BudgetLine"]] = relationship(back_populates="budget", cascade="all, delete-orphan")


class BudgetLine(Base):
    """One category/month cell of a budget. category is 'Revenue' for the
    revenue budget or one of app.accounting.categorization.EXPENSE_CATEGORIES
    for an expense budget -- never a free-form chart of accounts, so budget
    lines always line up with how actuals are categorized."""

    __tablename__ = "budget_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_id: Mapped[int] = mapped_column(ForeignKey("budgets.id"))

    category: Mapped[str] = mapped_column(String(100))
    month: Mapped[int] = mapped_column()  # 1-12, within the budget's financial year
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    source: Mapped[BudgetLineSource] = mapped_column(
        Enum(BudgetLineSource, name="budget_line_source"), default=BudgetLineSource.manual
    )

    budget: Mapped["Budget"] = relationship(back_populates="lines")
