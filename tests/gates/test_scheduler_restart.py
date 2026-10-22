"""
Gate for SCRUM-021.

Done when: kill mid-stand-up and restart — no duplicate stand-up, no lost
update.

A "restart" here is a fresh sqlite3 connection (and a fresh Scheduler
instance) reopened against the same database file — the same recovery
path a real process restart takes, since nothing but the DB is durable.

Run:
    .venv/bin/pytest tests/gates/test_scheduler_restart.py -v -s
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from src.clock import FakeClock
from src.db import connect
from src.scheduler import Scheduler, TeamSchedule


class _SpyAdapter:
    """Records every post() call; nothing is sent anywhere real."""

    def __init__(self) -> None:
        self.posts: list[str] = []

    def post(self, text: str) -> str:
        self.posts.append(text)
        return f"msg-{len(self.posts)}"

    def post_private(self, user_id: str, text: str) -> str:
        return "msg-private"

    def get_replies(self, since):
        return []


SCHEDULE = TeamSchedule(
    team_id="course-team",
    timezone="UTC",
    open_time=time(9, 0),
    close_time=time(11, 0),
    reminder_offset_minutes=60,  # reminder due at 10:00
    holidays=frozenset(),
)


def _standup_rows(db):
    return db.execute(
        "SELECT * FROM standup WHERE team_id = ? AND date = ?",
        (SCHEDULE.team_id, "2026-10-19"),
    ).fetchall()


def test_restart_causes_no_duplicate_standup_and_no_lost_update(tmp_path):
    db_path = str(tmp_path / "scrum.db")
    clock = FakeClock(start=datetime(2026, 10, 19, 8, 59, tzinfo=timezone.utc))  # a Monday

    # ── Before open time: nothing happens ──────────────────────────────────
    db = connect(db_path)
    adapter = _SpyAdapter()
    Scheduler(db, SCHEDULE, adapter, clock).tick()
    assert _standup_rows(db) == []
    db.close()

    # ── Open ────────────────────────────────────────────────────────────────
    clock.advance(minutes=2)  # 09:01
    db = connect(db_path)
    adapter = _SpyAdapter()
    Scheduler(db, SCHEDULE, adapter, clock).tick()
    rows = _standup_rows(db)
    assert len(rows) == 1
    assert rows[0]["state"] == "open"
    assert len(adapter.posts) == 1 and "now open" in adapter.posts[0]

    # Simulate a message arriving independently of the scheduler (the Teams
    # webhook writes straight to the DB on receipt) — this is the update
    # that must not be lost across the crash below.
    db.execute(
        """INSERT INTO standup_update
           (standup_id, member_id, raw_text, chat_message_id, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (rows[0]["id"], "dev-a", "done with setup", "activity-1", clock.now().isoformat()),
    )
    db.commit()
    db.close()  # ── crash: connection dropped mid-stand-up ──

    # ── Restart: tick again at the same instant, nothing re-opens ──────────
    db = connect(db_path)
    adapter = _SpyAdapter()
    Scheduler(db, SCHEDULE, adapter, clock).tick()
    assert len(_standup_rows(db)) == 1, "restart must not create a second stand-up for the same day"
    assert adapter.posts == [], "restart must not re-post the open message"
    update = db.execute(
        "SELECT * FROM standup_update WHERE chat_message_id = ?", ("activity-1",)
    ).fetchone()
    assert update is not None and update["raw_text"] == "done with setup", (
        "the update stored before the crash must still be there after restart"
    )
    db.close()

    # ── Reminder (due at 10:00) ─────────────────────────────────────────────
    clock.set(datetime(2026, 10, 19, 10, 1, tzinfo=timezone.utc))
    db = connect(db_path)
    adapter = _SpyAdapter()
    Scheduler(db, SCHEDULE, adapter, clock).tick()
    assert len(adapter.posts) == 1 and "Reminder" in adapter.posts[0]
    standup = _standup_rows(db)[0]
    assert standup["reminder_sent_at"] is not None
    db.close()  # ── crash again, right after the reminder ──

    # ── Restart: same instant, reminder is not sent twice ───────────────────
    db = connect(db_path)
    adapter = _SpyAdapter()
    Scheduler(db, SCHEDULE, adapter, clock).tick()
    assert adapter.posts == [], "restart must not re-send the one reminder"
    assert len(_standup_rows(db)) == 1
    db.close()

    # ── Close (due at 11:00) ─────────────────────────────────────────────────
    clock.set(datetime(2026, 10, 19, 11, 1, tzinfo=timezone.utc))
    db = connect(db_path)
    adapter = _SpyAdapter()
    Scheduler(db, SCHEDULE, adapter, clock).tick()
    standup = _standup_rows(db)[0]
    assert standup["state"] == "closed"
    assert len(adapter.posts) == 1 and "closed" in adapter.posts[0]
    db.close()

    # ── Restart after close: fully idempotent, no re-close, no duplicate ───
    db = connect(db_path)
    adapter = _SpyAdapter()
    Scheduler(db, SCHEDULE, adapter, clock).tick()
    assert adapter.posts == []
    final_rows = _standup_rows(db)
    assert len(final_rows) == 1, "exactly one stand-up for (course-team, 2026-10-19), start to finish"
    assert final_rows[0]["state"] == "closed"
    db.close()

    print(
        "\nscheduler restart gate: open -> crash -> restart -> reminder -> crash -> "
        "restart -> close -> crash -> restart"
        f"\n  final stand-up rows for the day : {len(final_rows)}"
        f"\n  update survived every restart    : {update['raw_text']!r}"
    )


def test_non_workday_is_skipped_even_with_a_config_holiday():
    db = connect(":memory:")
    holiday_schedule = TeamSchedule(
        team_id="course-team",
        timezone="UTC",
        open_time=time(9, 0),
        close_time=time(11, 0),
        reminder_offset_minutes=60,
        holidays=frozenset({date(2026, 10, 20)}),  # a Tuesday
    )
    clock = FakeClock(start=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc))
    adapter = _SpyAdapter()
    Scheduler(db, holiday_schedule, adapter, clock).tick()
    assert db.execute("SELECT * FROM standup").fetchall() == []
    assert adapter.posts == []
