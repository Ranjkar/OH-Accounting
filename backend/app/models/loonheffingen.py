from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import LoonheffingenDeclarationStatus


class LoonheffingenDeclaration(Base):
    """One wage-tax declaration (aangifte loonheffingen) for one PayrollRun.
    There is no live SBR/Digipoort integration -- submitted_at/submission_reference
    and the government_response fields are only ever set from an explicit user
    action recording what actually happened outside this system, never
    auto-filled to simulate success."""

    __tablename__ = "loonheffingen_declarations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    payroll_run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id"), unique=True)

    status: Mapped[LoonheffingenDeclarationStatus] = mapped_column(
        Enum(LoonheffingenDeclarationStatus, name="loonheffingen_declaration_status"),
        default=LoonheffingenDeclarationStatus.draft,
    )

    total_gross_wages: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_wage_tax_withheld: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_employer_premiums: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_payable: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    validation_errors: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    submission_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    government_response_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    government_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    payroll_run: Mapped["PayrollRun"] = relationship()
