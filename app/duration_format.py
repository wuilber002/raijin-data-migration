"""Shared duration presentation for durable backend messages.

The browser counterpart lives in ``app/static/duration-format.js``. Both use
the same fixed operational units because these are counters, not calendar
timestamps: 30 days per month and 365 days per year.
"""

from __future__ import annotations

import math

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR
MONTH = 30 * DAY
YEAR = 365 * DAY


def _clock_part(seconds: int) -> str:
    if seconds <= 0:
        return ""
    hours, remainder = divmod(seconds, HOUR)
    minutes, remaining_seconds = divmod(remainder, MINUTE)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    if minutes:
        return f"{minutes:02d}:{remaining_seconds:02d}"
    return f"{remaining_seconds}s"


def format_duration(value: float | int | None, *, empty: str = "—") -> str:
    """Format seconds using the platform's incremental duration contract."""
    if value is None:
        return empty
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return empty
    if not math.isfinite(numeric) or numeric < 0:
        return empty
    remaining = math.floor(numeric + 0.5)
    if remaining == 0:
        return "0s"

    if remaining % YEAR == 0:
        return f"{remaining // YEAR}y"
    if remaining < YEAR and remaining % MONTH == 0:
        return f"{remaining // MONTH}m"
    if remaining < MONTH and remaining % HOUR == 0:
        return f"{remaining // HOUR}h"
    years, remaining = divmod(remaining, YEAR)
    months, remaining = divmod(remaining, MONTH)
    days, remaining = divmod(remaining, DAY)
    parts = []
    if years:
        parts.append(f"{years}y")
    if months:
        parts.append(f"{months}m")
    if days:
        parts.append(f"{days}d")
    clock = _clock_part(remaining)
    if clock:
        parts.append(clock)
    return " ".join(parts)
