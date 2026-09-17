from datetime import datetime, timezone

import pytest

from app.aws_restore_semantics import s3_restore_expiry


def test_restore_expiry_adds_retention_then_rounds_to_next_utc_midnight():
    assert s3_restore_expiry(
        datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc), 3
    ) == datetime(2026, 9, 19, 0, 0, tzinfo=timezone.utc)


def test_restores_completed_on_same_utc_day_share_expiry():
    early = s3_restore_expiry(datetime(2026, 9, 12, 0, 1, tzinfo=timezone.utc), 3)
    late = s3_restore_expiry(datetime(2026, 9, 12, 23, 59, tzinfo=timezone.utc), 3)
    assert early == late == datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)


def test_restore_window_crossing_utc_midnight_produces_two_expiry_groups():
    before = s3_restore_expiry(datetime(2026, 9, 12, 23, 59, tzinfo=timezone.utc), 3)
    after = s3_restore_expiry(datetime(2026, 9, 13, 0, 1, tzinfo=timezone.utc), 3)
    assert before == datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)
    assert after == datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc)


def test_restore_expiry_interprets_legacy_naive_timestamp_as_utc():
    assert s3_restore_expiry(datetime(2026, 9, 15, 10, 30), 1) == datetime(
        2026, 9, 17, 0, 0, tzinfo=timezone.utc
    )


def test_restore_expiry_rejects_zero_retention():
    with pytest.raises(ValueError, match="at least one day"):
        s3_restore_expiry(datetime.now(timezone.utc), 0)
