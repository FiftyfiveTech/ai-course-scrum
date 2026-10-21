"""
SCRUM-007 — the schema's invariants, enforced by SQLite itself.

Done when: both unique keys reject a duplicate; commitment_history rows are never
updated, only appended.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

import src.commitment as commitment_ledger
from src.db import add_team, connect

TS = "2026-10-21T09:00:00+00:00"


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = connect(":memory:")
    add_team(conn, "team-a", "Team A", "Asia/Kolkata", [88])
    return conn


def _standup(db: sqlite3.Connection, date: str = "2026-10-21", team: str = "team-a") -> int:
    cur = db.execute(
        "INSERT INTO standup (team_id, date, opened_at) VALUES (?, ?, ?)", (team, date, TS)
    )
    return cur.lastrowid


def _write(db: sqlite3.Connection, standup_id: int, task_id: str | None, kind: str) -> None:
    db.execute(
        """INSERT INTO odoo_write_log
           (standup_id, task_id, kind, payload, dry_run, written_at)
           VALUES (?, ?, ?, '{}', 1, ?)""",
        (standup_id, task_id, kind, TS),
    )


def _history(db: sqlite3.Connection) -> list[tuple]:
    return [tuple(r) for r in db.execute("SELECT * FROM commitment_history ORDER BY id")]


# ── Unique key (team_id, date) ──────────────────────────────────────────────


def test_one_standup_per_team_and_date(db):
    _standup(db)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        _standup(db)


def test_same_team_next_day_and_other_team_same_day_are_allowed(db):
    add_team(db, "team-b", "Team B", "Asia/Kolkata")
    _standup(db, "2026-10-21", "team-a")
    _standup(db, "2026-10-22", "team-a")
    _standup(db, "2026-10-21", "team-b")
    assert db.execute("SELECT COUNT(*) FROM standup").fetchone()[0] == 3


def test_standup_needs_a_known_team(db):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        _standup(db, team="no-such-team")


# ── Unique key (standup_id, task_id, kind) ──────────────────────────────────


def test_one_odoo_write_per_standup_task_and_kind(db):
    sid = _standup(db)
    _write(db, sid, "3666", "task_note")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        _write(db, sid, "3666", "task_note")


def test_other_kind_or_task_is_a_different_write(db):
    sid = _standup(db)
    _write(db, sid, "3666", "task_note")
    _write(db, sid, "3666", "alert")
    _write(db, sid, "3665", "task_note")
    assert db.execute("SELECT COUNT(*) FROM odoo_write_log").fetchone()[0] == 3


def test_null_task_id_cannot_slip_past_the_unique_key(db):
    # SQLite treats NULLs as distinct inside UNIQUE, so a nullable task_id would let
    # the same write in twice. The column is NOT NULL to close that hole.
    sid = _standup(db)
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
        _write(db, sid, None, "daily_log")


def test_replayed_chat_message_is_stored_once(db):
    sid = _standup(db)
    insert = """INSERT INTO standup_update
                (standup_id, member_id, raw_text, chat_message_id) VALUES (?, 'u1', 'hi', 'm-1')"""
    db.execute(insert, (sid,))
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        db.execute(insert, (sid,))


# ── commitment_history is append-only ───────────────────────────────────────


def _commit(db: sqlite3.Connection, sid: int, state: str = "pending") -> None:
    db.execute(
        """INSERT INTO commitment_history (standup_id, member_id, description, state)
           VALUES (?, 'u1', 'finish the schema', ?)""",
        (sid, state),
    )


def test_history_rows_cannot_be_updated(db):
    _commit(db, _standup(db))
    before = _history(db)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE commitment_history SET state = 'met'")
    assert _history(db) == before


def test_history_rows_cannot_be_deleted(db):
    _commit(db, _standup(db))
    before = _history(db)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM commitment_history")
    assert _history(db) == before


def test_only_code_may_change_state(db):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        db.execute(
            """INSERT INTO commitment_history
               (standup_id, member_id, description, state_changed_by)
               VALUES (?, 'u1', 'x', 'model')""",
            (_standup(db),),
        )


def test_state_change_appends_and_latest_row_is_current(db):
    day1, day2 = _standup(db, "2026-10-21"), _standup(db, "2026-10-22")
    _commit(db, day1, "pending")
    _commit(db, day2, "met")

    states = [r["state"] for r in db.execute("SELECT state FROM commitment_history ORDER BY id")]
    assert states == ["pending", "met"]

    current = db.execute("SELECT * FROM commitment_current").fetchall()
    assert len(current) == 1
    assert current[0]["state"] == "met"
    assert current[0]["standup_id"] == day2
    assert current[0]["first_standup_id"] == day1


def test_ledger_marks_met_by_appending_not_updating(db):
    day1, day2 = _standup(db, "2026-10-21"), _standup(db, "2026-10-22")
    commitment_ledger.record_from_extraction(
        db, day1, "u1",
        json.dumps({"commitments": [{"text": "finish the sqlite schema", "date_type": "implied"}]}),
    )
    first_row = _history(db)[0]

    commitment_ledger.mark_met_if_mentioned(
        db, day2, "u1", json.dumps({"done": [{"text": "finished the sqlite schema"}]})
    )

    rows = _history(db)
    assert len(rows) == 2
    assert rows[0] == first_row  # day-1 row untouched
    assert commitment_ledger.get_all_open(db, "u1") == []


# ── updated_at ──────────────────────────────────────────────────────────────


def test_updated_at_is_reset_by_the_trigger_on_every_update(db):
    sid = _standup(db)
    # Without the trigger this stale value would stick; with it, it is overwritten with now.
    db.execute("UPDATE standup SET updated_at = '2000-01-01' WHERE id = ?", (sid,))
    assert db.execute("SELECT updated_at FROM standup WHERE id = ?", (sid,)).fetchone()[0] != "2000-01-01"
