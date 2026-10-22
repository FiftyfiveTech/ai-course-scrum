"""
Deadline tracking — SCRUM-020.

Classifies tasks into three groups:
  overdue      — deadline strictly before today
  due_soon     — deadline within the next N working days (default 2)
  date_mismatch — dev's stated date in their update ≠ board date_deadline

Working days skip weekends and any date in the holidays list.
Absent members are excluded from all groups — their tasks generate no questions.

Usage:
    from src.deadline import classify, DeadlineReport

    report = classify(
        tasks=odoo_tasks,           # list of dicts with id, name, date_deadline, assignee_id
        as_of=date.today(),
        holidays=[date(2026, 10, 29)],
        absent_members={"yash"},
        dev_dates={"107": date(2026, 10, 30)},  # task_id → date dev mentioned
        window=2,
    )
    report.overdue       # tasks past their deadline
    report.due_soon      # tasks due within 2 working days
    report.date_mismatch # tasks where dev date ≠ board date
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


@dataclass
class DeadlineReport:
    overdue: list[dict[str, Any]] = field(default_factory=list)
    due_soon: list[dict[str, Any]] = field(default_factory=list)
    date_mismatch: list[dict[str, Any]] = field(default_factory=list)


def working_days_ahead(start: date, n: int, holidays: list[date]) -> date:
    """
    Return the date that is exactly n working days after start.
    Skips Saturdays, Sundays, and dates in holidays.
    start itself is not counted — this counts forward from start+1.
    """
    holiday_set = set(holidays)
    current = start
    counted = 0
    while counted < n:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in holiday_set:
            counted += 1
    return current


def classify(
    tasks: list[dict[str, Any]],
    as_of: date,
    holidays: list[date] | None = None,
    absent_members: set[str] | None = None,
    dev_dates: dict[str, date] | None = None,
    window: int = 2,
) -> DeadlineReport:
    """
    Classify tasks into overdue / due_soon / date_mismatch.

    Args:
        tasks:           List of task dicts. Each must have:
                           id           — task id (str or int)
                           name         — task name
                           date_deadline — ISO date string or None
                           assignee_id  — member_id string
        as_of:           The reference date (today in production).
        holidays:        List of date objects to skip in working-day counts.
        absent_members:  member_ids absent today — their tasks are excluded entirely.
        dev_dates:       {task_id: date} — the date the developer mentioned for that task.
                         Used to detect mismatches against board date_deadline.
        window:          Number of working days ahead to consider "due soon" (default 2).
    """
    holidays = holidays or []
    absent_members = absent_members or set()
    dev_dates = dev_dates or {}

    cutoff = working_days_ahead(as_of, window, holidays)

    report = DeadlineReport()

    for task in tasks:
        assignee = str(task.get("assignee_id", ""))
        if assignee in absent_members:
            continue  # absent — skip entirely

        raw_deadline = task.get("date_deadline")
        if not raw_deadline:
            # No deadline set — only check date_mismatch
            task_id = str(task["id"])
            if task_id in dev_dates:
                report.date_mismatch.append({**task, "dev_date": dev_dates[task_id]})
            continue

        try:
            deadline = date.fromisoformat(str(raw_deadline))
        except ValueError:
            continue

        task_id = str(task["id"])

        if deadline < as_of:
            report.overdue.append(task)
        elif deadline <= cutoff:
            report.due_soon.append(task)

        # Date mismatch check — independent of overdue/due_soon
        if task_id in dev_dates and dev_dates[task_id] != deadline:
            report.date_mismatch.append({**task, "dev_date": dev_dates[task_id]})

    return report
