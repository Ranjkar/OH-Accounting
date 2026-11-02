"""Deterministic recurring-payment detection over bank transaction history.
Detection only -- this never creates, approves, or pays an invoice. It only
ever writes RecurringPattern rows describing what it found."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.banking import BankTransaction
from app.models.enums import RecurringFrequency, RecurringStatus
from app.models.recurring import RecurringPattern

MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE_PCT = Decimal("10")

_FREQUENCY_DAY_RANGES = {
    RecurringFrequency.weekly: (5, 9),
    RecurringFrequency.monthly: (25, 35),
    RecurringFrequency.quarterly: (80, 100),
    RecurringFrequency.annual: (350, 380),
}


def _normalize(name: str) -> str:
    return name.strip().lower()


def _classify_interval(avg_gap_days: float) -> RecurringFrequency | None:
    for freq, (low, high) in _FREQUENCY_DAY_RANGES.items():
        if low <= avg_gap_days <= high:
            return freq
    return None


def detect_recurring_patterns(db: Session, company_id: int, tenant_id: int) -> list[RecurringPattern]:
    transactions = (
        db.query(BankTransaction)
        .filter(BankTransaction.company_id == company_id, BankTransaction.counterparty_name.isnot(None))
        .order_by(BankTransaction.booking_date)
        .all()
    )

    groups: dict[str, list[BankTransaction]] = defaultdict(list)
    for tx in transactions:
        groups[_normalize(tx.counterparty_name)].append(tx)

    detected: list[RecurringPattern] = []
    for name_key, group in groups.items():
        if len(group) < MIN_OCCURRENCES:
            continue

        gaps = [(group[i].booking_date - group[i - 1].booking_date).days for i in range(1, len(group))]
        avg_gap = sum(gaps) / len(gaps)
        frequency = _classify_interval(avg_gap)
        if frequency is None:
            continue

        amounts = [abs(tx.amount) for tx in group]
        avg_amount = sum(amounts, Decimal("0")) / len(amounts)
        max_deviation = max(abs(a - avg_amount) for a in amounts)
        if avg_amount > 0 and (max_deviation / avg_amount) * 100 > AMOUNT_TOLERANCE_PCT * 2:
            # too irregular in amount to be confidently called "recurring"
            continue

        last = group[-1]
        interval_days = round(avg_gap)
        next_expected = last.booking_date + timedelta(days=interval_days)
        is_overdue = next_expected < date.today() - timedelta(days=max(3, interval_days // 10))

        existing = (
            db.query(RecurringPattern)
            .filter(RecurringPattern.company_id == company_id, RecurringPattern.counterparty_name == last.counterparty_name)
            .first()
        )
        pattern = existing or RecurringPattern(
            tenant_id=tenant_id,
            company_id=company_id,
            counterparty_name=last.counterparty_name,
            counterparty_iban=last.counterparty_iban,
            frequency=frequency,
            expected_amount=avg_amount.quantize(Decimal("0.01")),
            last_transaction_date=last.booking_date,
            next_expected_date=next_expected,
        )
        pattern.frequency = frequency
        pattern.expected_amount = avg_amount.quantize(Decimal("0.01"))
        pattern.last_transaction_date = last.booking_date
        pattern.next_expected_date = next_expected
        pattern.occurrence_count = len(group)
        pattern.status = RecurringStatus.missing if is_overdue else RecurringStatus.active
        if existing is None:
            db.add(pattern)
        detected.append(pattern)

    db.flush()
    return detected
