"""
Scheduler — config-based: Mon-Fri, one timezone per team, open -> one
reminder -> close, one stand-up per (team, date).

Config lives in config/teams.yaml, one block per team:

    course-team:
      timezone: Asia/Kolkata
      open_time: "09:00"
      reminder_offset_minutes: 120
      close_time: "11:00"
      holidays: ["2026-10-24"]

Restart-safe by construction, not by a lock: tick() is idempotent against
whatever is already in the database, so calling it again after a crash
repeats no transition that already happened.

  - open:     INSERT guarded by the (team_id, date) unique key — a second
              attempt hits IntegrityError and is a no-op.
  - reminder: UPDATE ... WHERE reminder_sent_at IS NULL — a second attempt
              matches zero rows, so no second reminder is posted.
  - close:    UPDATE ... WHERE state != 'closed' — same pattern.

No cron/async runtime here — call tick() on whatever interval the caller
chooses (a loop with sleep, an OS timer); each call only looks at the
current clock time and the DB, never at what the last tick did.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from src.adapters import ChatAdapter
from src.clock import ClockProtocol

DEFAULT_CONFIG_PATH = "config/teams.yaml"


@dataclass(frozen=True)
class TeamSchedule:
    team_id: str
    timezone: str
    open_time: time
    close_time: time
    reminder_offset_minutes: int
    holidays: frozenset[date]

    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def is_workday(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays

    def reminder_time(self) -> time:
        close_dt = datetime.combine(date.min, self.close_time)
        reminder_dt = max(close_dt - timedelta(minutes=self.reminder_offset_minutes), datetime.min)
        return reminder_dt.time()


def load_schedules(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, TeamSchedule]:
    """Parse config/teams.yaml into one TeamSchedule per team."""
    raw = yaml.safe_load(Path(path).read_text()) or {}
    schedules: dict[str, TeamSchedule] = {}
    for team_id, cfg in raw.items():
        schedules[team_id] = TeamSchedule(
            team_id=team_id,
            timezone=cfg["timezone"],
            open_time=_parse_hhmm(cfg["open_time"]),
            close_time=_parse_hhmm(cfg["close_time"]),
            reminder_offset_minutes=int(cfg.get("reminder_offset_minutes", 0)),
            holidays=frozenset(date.fromisoformat(str(d)) for d in cfg.get("holidays", [])),
        )
    return schedules


def _parse_hhmm(s: str) -> time:
    hour, minute = s.split(":")
    return time(int(hour), int(minute))


class Scheduler:
    """Drives one team's stand-up open/reminder/close off its config and the clock."""

    def __init__(
        self,
        db: sqlite3.Connection,
        schedule: TeamSchedule,
        adapter: ChatAdapter,
        clock: ClockProtocol,
    ) -> None:
        self.db = db
        self.schedule = schedule
        self.adapter = adapter
        self.clock = clock

    def tick(self) -> None:
        """Look at now() and the DB; perform whichever transition is due, if any."""
        local_now = self.clock.now().astimezone(self.schedule.tz())
        today = local_now.date()

        if not self.schedule.is_workday(today):
            return

        standup = self._get_standup(today)

        if standup is None:
            if local_now.time() >= self.schedule.open_time:
                self._open(today)
            return

        if standup["state"] == "closed":
            return

        if standup["reminder_sent_at"] is None and local_now.time() >= self.schedule.reminder_time():
            self._remind(standup)

        if local_now.time() >= self.schedule.close_time:
            self._close(standup)

    # ── transitions, each idempotent against DB state ──────────────────────

    def _open(self, today: date) -> None:
        try:
            self.db.execute(
                "INSERT INTO standup (team_id, date, state, opened_at) VALUES (?, ?, 'open', ?)",
                (self.schedule.team_id, today.isoformat(), self.clock.now().isoformat()),
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            return  # (team_id, date) unique key — another tick already opened it
        self.adapter.post(
            f"Good morning! Stand-up for {today} is now open.\n"
            f"Please share:\n"
            f"  ✅ Done  |  \U0001f51c Next  |  \U0001f6ab Blockers"
        )

    def _remind(self, standup: sqlite3.Row) -> None:
        cur = self.db.execute(
            "UPDATE standup SET reminder_sent_at = ? WHERE id = ? AND reminder_sent_at IS NULL",
            (self.clock.now().isoformat(), standup["id"]),
        )
        self.db.commit()
        if cur.rowcount:
            self.adapter.post("Reminder: stand-up closes soon — please post your update.")

    def _close(self, standup: sqlite3.Row) -> None:
        cur = self.db.execute(
            "UPDATE standup SET state = 'closed', closed_at = ? WHERE id = ? AND state != 'closed'",
            (self.clock.now().isoformat(), standup["id"]),
        )
        self.db.commit()
        if cur.rowcount:
            self.adapter.post(f"Stand-up closed for {standup['date']}.")

    def _get_standup(self, today: date) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM standup WHERE team_id = ? AND date = ?",
            (self.schedule.team_id, today.isoformat()),
        ).fetchone()
