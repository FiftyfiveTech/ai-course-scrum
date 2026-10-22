"""Scheduler config loading: config/teams.yaml -> TeamSchedule per team."""

from __future__ import annotations

from datetime import time

from src.scheduler import load_schedules


def test_loads_course_team_from_config_teams_yaml():
    schedules = load_schedules("config/teams.yaml")
    assert "course-team" in schedules

    schedule = schedules["course-team"]
    assert schedule.timezone == "Asia/Kolkata"
    assert schedule.open_time == time(9, 0)
    assert schedule.close_time == time(11, 0)
    assert schedule.reminder_offset_minutes == 120
    assert schedule.holidays == frozenset()


def test_holidays_are_skipped_as_workdays(tmp_path):
    config = tmp_path / "teams.yaml"
    config.write_text(
        "test-team:\n"
        "  timezone: UTC\n"
        "  open_time: \"09:00\"\n"
        "  reminder_offset_minutes: 60\n"
        "  close_time: \"11:00\"\n"
        "  holidays: [\"2026-10-20\"]\n"
    )
    schedules = load_schedules(str(config))
    schedule = schedules["test-team"]

    from datetime import date
    assert schedule.is_workday(date(2026, 10, 19)) is True   # Monday
    assert schedule.is_workday(date(2026, 10, 20)) is False  # configured holiday
    assert schedule.is_workday(date(2026, 10, 24)) is False  # Saturday
