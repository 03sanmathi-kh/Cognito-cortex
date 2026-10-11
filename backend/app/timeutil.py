from __future__ import annotations

import os
import re
from calendar import monthrange
from datetime import date, timedelta

_DEFAULT_AS_OF = date(2026, 9, 30)


def _configured_as_of() -> date:
    value = os.getenv("APP_AS_OF_DATE")
    if value is None:
        return _DEFAULT_AS_OF
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("APP_AS_OF_DATE must use YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("APP_AS_OF_DATE must be a valid calendar date.") from error


AS_OF = _configured_as_of()


def get_as_of() -> date:
    return AS_OF


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _month_end(value: date) -> date:
    return date(value.year, value.month, monthrange(value.year, value.month)[1])


def _quarter_start(value: date) -> date:
    month = ((value.month - 1) // 3) * 3 + 1
    return date(value.year, month, 1)


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def resolve_period(name: str, as_of: date | None = None) -> tuple[date, date]:
    anchor = as_of or get_as_of()
    period_name = (name or "").strip().lower()
    if period_name == "today":
        return anchor, anchor
    if period_name == "last_7_days":
        return anchor - timedelta(days=6), anchor
    if period_name == "last_30_days":
        return anchor - timedelta(days=29), anchor
    if period_name == "this_month":
        return _month_start(anchor), min(_month_end(anchor), anchor)
    if period_name == "last_month":
        previous_start = _add_months(_month_start(anchor), -1)
        return previous_start, _month_end(previous_start)
    if period_name == "this_quarter":
        quarter_start = _quarter_start(anchor)
        quarter_end = _month_end(_add_months(quarter_start, 2))
        return quarter_start, min(quarter_end, anchor)
    if period_name == "last_quarter":
        quarter_start = _quarter_start(anchor)
        previous_start = _add_months(quarter_start, -3)
        previous_end = _month_end(_add_months(quarter_start, -1))
        return previous_start, previous_end
    if period_name == "this_year":
        return date(anchor.year, 1, 1), anchor
    if period_name == "custom":
        return _month_start(anchor), min(_month_end(anchor), anchor)
    raise ValueError(f"Unsupported date range: {name}")


def _previous_period(start: date, end: date) -> tuple[date, date]:
    duration = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=duration - 1)
    return previous_start, previous_end


def comparison_period(name: str, start: date, end: date) -> tuple[date, date]:
    period_name = (name or "").strip().lower()
    if period_name == "this_quarter":
        return _add_months(start, -3), _add_months(end, -3)
    if period_name == "this_month":
        previous_start = _add_months(start, -1)
        return previous_start, min(_add_months(end, -1), _month_end(previous_start))
    if period_name == "this_year":
        previous_year = start.year - 1
        return date(previous_year, 1, 1), date(previous_year, end.month, end.day)
    return _previous_period(start, end)
