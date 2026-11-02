from datetime import date

from pydantic import BaseModel

CalendarEntryStatus = str  # "completed" | "upcoming" | "overdue" | "pending"


class TaxCalendarEntry(BaseModel):
    company_id: int
    company_name: str
    vat_period_id: int
    financial_year: int
    period_label: str
    vat_frequency: str
    start_date: date
    end_date: date
    filing_deadline: date
    payment_deadline: date
    calendar_status: CalendarEntryStatus
    vat_return_id: int | None
