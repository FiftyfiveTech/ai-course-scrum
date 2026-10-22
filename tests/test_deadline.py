"""
Deadline tracking tests — SCRUM-020.

Done criteria: the 3 groups match a hand-built fixture exactly,
including a holiday and an absent member.

Fixture:
  as_of    = 2026-10-28 (Wednesday)
  holidays = [2026-10-29]  — Thursday (e.g. Diwali)
  absent   = {"yash"}

  Working-day window from 2026-10-28 (2 days, skipping holiday 10-29):
    +1 wd = 2026-10-30 (Friday)           [10-29 is holiday → skip]
    +2 wd = 2026-11-02 (Monday)           [10-31 Sat + 11-01 Sun → skip]
    cutoff = 2026-11-02

  Tasks:
    T1  id=101  deadline=2026-10-25  assignee=ritika  → OVERDUE  (3 days ago)
    T2  id=102  deadline=2026-10-28  assignee=vimal   → DUE_SOON (today)
    T3  id=103  deadline=2026-10-30  assignee=ritika  → DUE_SOON (+1 wd)
    T4  id=104  deadline=2026-11-03  assignee=vimal   → neither  (past cutoff 11-02)
    T5  id=105  deadline=2026-11-04  assignee=ritika  → neither  (past cutoff)
    T6  id=106  deadline=2026-10-25  assignee=yash    → EXCLUDED (absent)
    T7  id=107  deadline=2026-10-30  assignee=ritika  → DUE_SOON + DATE_MISMATCH (dev said 2026-10-28)
    T8  id=108  deadline=2026-10-29  assignee=vimal   → DUE_SOON (holiday date, still a valid deadline)
"""

from __future__ import annotations

from datetime import date

import pytest

from src.deadline import classify, working_days_ahead, DeadlineReport

# ── Fixture ───────────────────────────────────────────────────────────────────

AS_OF = date(2026, 10, 28)         # Wednesday
HOLIDAYS = [date(2026, 10, 29)]    # Thursday
ABSENT = {"yash"}

TASKS = [
    {"id": 101, "name": "Write tests",     "date_deadline": "2026-10-25", "assignee_id": "ritika"},
    {"id": 102, "name": "Review PR",       "date_deadline": "2026-10-28", "assignee_id": "vimal"},
    {"id": 103, "name": "Ship feature",    "date_deadline": "2026-10-30", "assignee_id": "ritika"},
    {"id": 104, "name": "Update docs",     "date_deadline": "2026-11-03", "assignee_id": "vimal"},
    {"id": 105, "name": "Refactor",        "date_deadline": "2026-11-04", "assignee_id": "ritika"},
    {"id": 106, "name": "Absent task",     "date_deadline": "2026-10-25", "assignee_id": "yash"},
    {"id": 107, "name": "Date mismatch",   "date_deadline": "2026-10-30", "assignee_id": "ritika"},
    {"id": 108, "name": "Holiday deadline","date_deadline": "2026-10-29", "assignee_id": "vimal"},
]

# dev stated 2026-10-28 for task 107, but board says 2026-10-30
DEV_DATES = {"107": date(2026, 10, 28)}


# ── working_days_ahead ────────────────────────────────────────────────────────

def test_working_days_skips_holiday() -> None:
    # +1 wd from 2026-10-28, skipping 2026-10-29 holiday → 2026-10-30
    assert working_days_ahead(date(2026, 10, 28), 1, HOLIDAYS) == date(2026, 10, 30)


def test_working_days_skips_weekend() -> None:
    # +1 wd from 2026-10-30 (Fri) → skip Sat 10-31, Sun 11-01 → Mon 11-02
    assert working_days_ahead(date(2026, 10, 30), 1, []) == date(2026, 11, 2)


def test_working_days_2_with_holiday() -> None:
    # +2 wd from 2026-10-28, holiday 10-29:
    # +1 wd = 2026-10-30 (Fri), +2 wd = skip Sat 10-31 + Sun 11-01 → Mon 11-02
    assert working_days_ahead(date(2026, 10, 28), 2, HOLIDAYS) == date(2026, 11, 2)


# ── Full fixture: exact group membership ─────────────────────────────────────

def _run() -> DeadlineReport:
    return classify(
        tasks=TASKS,
        as_of=AS_OF,
        holidays=HOLIDAYS,
        absent_members=ABSENT,
        dev_dates=DEV_DATES,
        window=2,
    )


def test_overdue_matches_fixture_exactly() -> None:
    """Only T1 (deadline 2026-10-25) is overdue. T6 (yash) excluded."""
    report = _run()
    overdue_ids = {t["id"] for t in report.overdue}
    assert overdue_ids == {101}, f"expected {{101}}, got {overdue_ids}"


def test_due_soon_matches_fixture_exactly() -> None:
    """T2 (today), T3 (+1 wd), T7 (same deadline as T3, also mismatch), T8 (holiday date)."""
    report = _run()
    due_soon_ids = {t["id"] for t in report.due_soon}
    assert due_soon_ids == {102, 103, 107, 108}, f"expected {{102, 103, 107, 108}}, got {due_soon_ids}"


def test_date_mismatch_matches_fixture_exactly() -> None:
    """Only T7: dev said 2026-10-28, board says 2026-10-30."""
    report = _run()
    mismatch_ids = {t["id"] for t in report.date_mismatch}
    assert mismatch_ids == {107}, f"expected {{107}}, got {mismatch_ids}"


def test_absent_member_excluded_from_all_groups() -> None:
    """T6 (yash, absent) must not appear in any group."""
    report = _run()
    all_ids = (
        {t["id"] for t in report.overdue}
        | {t["id"] for t in report.due_soon}
        | {t["id"] for t in report.date_mismatch}
    )
    assert 106 not in all_ids, "absent member's task must not appear in any group"


def test_far_future_tasks_in_no_group() -> None:
    """T4 (2026-11-03, past cutoff 11-02) and T5 (2026-11-04) must not appear in any group."""
    report = _run()
    all_ids = (
        {t["id"] for t in report.overdue}
        | {t["id"] for t in report.due_soon}
        | {t["id"] for t in report.date_mismatch}
    )
    assert 104 not in all_ids
    assert 105 not in all_ids


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_no_tasks_returns_empty_report() -> None:
    report = classify(tasks=[], as_of=AS_OF, holidays=HOLIDAYS)
    assert report.overdue == []
    assert report.due_soon == []
    assert report.date_mismatch == []


def test_task_with_no_deadline_only_in_mismatch_if_dev_date_set() -> None:
    tasks = [{"id": 200, "name": "No deadline", "date_deadline": None, "assignee_id": "ritika"}]
    # dev mentioned a date for it → mismatch
    report = classify(tasks=tasks, as_of=AS_OF, dev_dates={"200": date(2026, 10, 30)})
    assert any(t["id"] == 200 for t in report.date_mismatch)
    assert not any(t["id"] == 200 for t in report.overdue)
    assert not any(t["id"] == 200 for t in report.due_soon)


def test_matching_dev_date_no_mismatch() -> None:
    tasks = [{"id": 300, "name": "Matching", "date_deadline": "2026-10-30", "assignee_id": "ritika"}]
    report = classify(tasks=tasks, as_of=AS_OF, dev_dates={"300": date(2026, 10, 30)})
    assert report.date_mismatch == []


def test_holiday_in_due_soon_window() -> None:
    """
    A task due on the holiday date (2026-10-29) is still due_soon —
    the holiday affects working-day counting, not whether a deadline is valid.
    """
    report = _run()
    due_soon_ids = {t["id"] for t in report.due_soon}
    assert 108 in due_soon_ids
