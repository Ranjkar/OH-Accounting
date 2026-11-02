from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class UpcomingDeadline(BaseModel):
    company_id: int
    company_name: str
    vat_period_id: int
    period_label: str
    filing_deadline: date
    payment_deadline: date
    is_overdue: bool


class CompanyAttentionFlag(BaseModel):
    company_id: int
    company_name: str
    reasons: list[str]


class DashboardSummary(BaseModel):
    company_count: int
    open_vat_periods: int
    upcoming_deadlines: list[UpcomingDeadline]

    companies_requiring_attention: list[CompanyAttentionFlag]
    vat_returns_awaiting_review: int
    vat_returns_approved: int
    overdue_vat_returns: int
    documents_awaiting_approval: int
    unmatched_payments: int
    outstanding_customer_info: int
    estimated_vat_payable: Decimal
    estimated_vat_refundable: Decimal
    generated_at: datetime
