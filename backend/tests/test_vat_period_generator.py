from datetime import date, timedelta

from app.models.enums import VatFrequency
from app.services.vat_period_generator import generate_vat_periods


def test_quarterly_periods_cover_full_year_with_no_gaps():
    periods = generate_vat_periods(2026, VatFrequency.quarterly)
    assert [p.label for p in periods] == ["Q1", "Q2", "Q3", "Q4"]
    assert periods[0].start_date == date(2026, 1, 1)
    assert periods[-1].end_date == date(2026, 12, 31)
    for prev, nxt in zip(periods, periods[1:]):
        assert nxt.start_date == prev.end_date + timedelta(days=1)


def test_quarterly_deadline_is_end_of_following_month():
    periods = generate_vat_periods(2026, VatFrequency.quarterly)
    q1 = periods[0]
    assert q1.end_date == date(2026, 3, 31)
    assert q1.filing_deadline == date(2026, 4, 30)
    assert q1.payment_deadline == date(2026, 4, 30)


def test_monthly_periods_count_and_december_deadline_rolls_into_next_year():
    periods = generate_vat_periods(2026, VatFrequency.monthly)
    assert len(periods) == 12
    december = periods[-1]
    assert december.end_date == date(2026, 12, 31)
    assert december.filing_deadline == date(2027, 1, 31)


def test_annual_period_is_single_full_year():
    periods = generate_vat_periods(2026, VatFrequency.annual)
    assert len(periods) == 1
    assert periods[0].start_date == date(2026, 1, 1)
    assert periods[0].end_date == date(2026, 12, 31)
    assert periods[0].filing_deadline == date(2027, 1, 31)
