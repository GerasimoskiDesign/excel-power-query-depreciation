"""Month arithmetic used everywhere.

Months are represented by their first day (``date(2024, 3, 1)``) and by an
integer *month index* ``year * 12 + month - 1``. The index makes "number of
whole months between two dates" a subtraction, which is exactly how the M
scripts do it too (``Date.Year(d) * 12 + Date.Month(d) - 1``).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def from_month_index(idx: int) -> date:
    return date(idx // 12, idx % 12 + 1, 1)


def days_in_month(d: date) -> int:
    return calendar.monthrange(d.year, d.month)[1]


def month_end(d: date) -> date:
    return date(d.year, d.month, days_in_month(d))


def add_months(d: date, n: int) -> date:
    return from_month_index(month_index(d) + n)


def parse_month(text: str) -> date:
    """Parse ``YYYY-MM`` (CLI input) into the first day of that month."""
    year, month = text.strip().split("-")[:2]
    return date(int(year), int(month), 1)


def report_months(start: date, n_months: int) -> list[date]:
    """First days of the ``n_months`` reporting months beginning at ``start``."""
    first = month_index(start)
    return [from_month_index(first + i) for i in range(n_months)]


def random_day_between(lo: date, hi: date, u: float) -> date:
    """Map ``u`` in [0, 1) to a day in [lo, hi] - keeps randomness in the caller's RNG."""
    span = (hi - lo).days
    return lo + timedelta(days=min(int(u * (span + 1)), span))
