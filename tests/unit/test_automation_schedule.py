from datetime import UTC, datetime

import pytest

from backend.automation_schedule import automation_fire_times, parse_automation_schedule


def test_supported_schedule_strings_parse_to_expected_kinds():
    assert parse_automation_schedule("hourly").kind == "hourly"
    assert parse_automation_schedule("daily@09:30").hour == 9
    assert parse_automation_schedule("weekdays@18:05").kind == "weekdays"
    assert parse_automation_schedule("weekly@07:00").kind == "weekly"


@pytest.mark.parametrize(
    "value",
    ["daily", "daily@24:00", "weekly@monday@09:00", "on_anomaly", "hourly@10:00"],
)
def test_unsupported_schedule_strings_fail_closed(value):
    with pytest.raises(ValueError):
        parse_automation_schedule(value)


def test_daily_schedule_uses_automation_timezone():
    fires = automation_fire_times(
        "daily@09:00",
        "Asia/Shanghai",
        datetime(2026, 8, 26, 0, 59, tzinfo=UTC),
        datetime(2026, 8, 26, 1, 0, tzinfo=UTC),
    )
    assert fires == [datetime(2026, 8, 26, 1, 0, tzinfo=UTC)]


def test_weekdays_and_weekly_use_local_calendar():
    monday_window = (
        datetime(2026, 8, 24, 8, 59, tzinfo=UTC),
        datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
    )
    saturday_window = (
        datetime(2026, 8, 22, 8, 59, tzinfo=UTC),
        datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
    )
    assert automation_fire_times("weekdays@09:00", "UTC", *monday_window)
    assert automation_fire_times("weekly@09:00", "UTC", *monday_window)
    assert not automation_fire_times("weekdays@09:00", "UTC", *saturday_window)
    assert not automation_fire_times("weekly@09:00", "UTC", *saturday_window)


def test_dst_nonexistent_wall_time_is_skipped():
    fires = automation_fire_times(
        "daily@02:30",
        "America/New_York",
        datetime(2024, 3, 10, 6, 0, tzinfo=UTC),
        datetime(2024, 3, 10, 8, 0, tzinfo=UTC),
    )
    assert fires == []


def test_dst_ambiguous_wall_time_has_two_distinct_occurrences():
    fires = automation_fire_times(
        "daily@01:30",
        "America/New_York",
        datetime(2024, 11, 3, 4, 0, tzinfo=UTC),
        datetime(2024, 11, 3, 7, 0, tzinfo=UTC),
    )
    assert fires == [
        datetime(2024, 11, 3, 5, 30, tzinfo=UTC),
        datetime(2024, 11, 3, 6, 30, tzinfo=UTC),
    ]
