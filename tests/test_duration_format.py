import math

from app.duration_format import format_duration


def test_duration_format_is_incremental_and_omits_empty_leading_units():
    assert format_duration(0) == "0s"
    assert format_duration(12) == "12s"
    assert format_duration(12 * 60 + 32) == "12:32"
    assert format_duration(12 * 3600 + 32 * 60 + 12) == "12:32:12"
    assert format_duration(86400 + 12 * 3600 + 32 * 60 + 12) == "1d 12:32:12"


def test_duration_format_collapses_exact_units_without_zero_suffixes():
    assert format_duration(60) == "01:00"
    assert format_duration(48 * 3600) == "48h"
    assert format_duration(30 * 86400) == "1m"
    assert format_duration(365 * 86400) == "1y"


def test_duration_format_rejects_missing_negative_and_non_finite_values():
    assert format_duration(None) == "—"
    assert format_duration(-1) == "—"
    assert format_duration(math.inf) == "—"
