"""Deterministic generation of Dutch VAT periods for a financial year.

Belastingdienst standard deadlines: filing and payment are due by the end of
the month following the period's end (e.g. Q1 ends Mar 31 -> deadline Apr 30).
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from app.models.enums import VatFrequency


@dataclass(frozen=True)
class VatPeriodSpec:
    label: str
    start_date: date
    end_date: date
    filing_deadline: date
    payment_deadline: date


def _last_day_of_month(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def _deadline_one_month_after(end_date: date) -> date:
    month = end_date.month + 1
    year = end_date.year
    if month > 12:
        month = 1
        year += 1
    return _last_day_of_month(year, month)


def generate_vat_periods(year: int, frequency: VatFrequency) -> list[VatPeriodSpec]:
    """Generate ordered, non-overlapping VAT periods covering a full calendar year."""
    if frequency is VatFrequency.annual:
        spans = [("Year", 1, 12)]
    elif frequency is VatFrequency.quarterly:
        spans = [("Q1", 1, 3), ("Q2", 4, 6), ("Q3", 7, 9), ("Q4", 10, 12)]
    elif frequency is VatFrequency.monthly:
        spans = [(f"{m:02d}", m, m) for m in range(1, 13)]
    else:
        raise ValueError(f"Unsupported VAT frequency: {frequency}")

    periods = []
    for label, start_month, end_month in spans:
        start_date = date(year, start_month, 1)
        end_date = _last_day_of_month(year, end_month)
        deadline = _deadline_one_month_after(end_date)
        periods.append(
            VatPeriodSpec(
                label=label,
                start_date=start_date,
                end_date=end_date,
                filing_deadline=deadline,
                payment_deadline=deadline,
            )
        )
    return periods
