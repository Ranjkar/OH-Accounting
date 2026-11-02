"""Shared JSON-safety helper for the Phase 8 reporting/forecast/scenario
endpoints, which return deeply-nested dicts built straight from
app.accounting.financial_reports et al. rather than a bespoke Pydantic
schema per report shape. FastAPI's default dict encoder is not trusted to
preserve Decimal precision (money must never silently become a float), so
every endpoint explicitly converts Decimal/date/datetime to str before
returning."""

from dataclasses import is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


def to_json_safe(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v) for v in obj]
    if is_dataclass(obj) and not isinstance(obj, type):
        return to_json_safe(obj.__dict__)
    return obj
