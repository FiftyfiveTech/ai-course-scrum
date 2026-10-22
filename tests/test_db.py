"""
Schema gate for SCRUM-007.

Done when: tests prove both unique keys reject a duplicate; history rows
are never updated, only appended.

Run:
    .venv/bin/pytest tests/test_db.py -v
"""

from __future__ import annotations

import json
import sqlite3

import pytest

import src.commitment as commitment_ledger
from src.db import connect


def _open_standup(db: sqlite3.Connection, team_id: str = "team-a", day: str = "2026-10-21") -> int:
    cur = db.execute(
        "INSERT INTO standup (team_id, date, state, opened_at) VALUES (?, ?, 'open', ?)",
        (team_id, day, f"{day}T09:00:00"),
    )
    db.commit()
    return cur.lastrowid


def test_standup_unique_team_date_rejects_duplicate():
    db = connect(":memory:")
    _open_standup(db, "team-a", "2026-10-21")
    with pytest.raises(sqlite3.IntegrityError):
        _open_standup(db, "team-a", "2026-10-21")


def test_odoo_write_log_unique_standup_task_kind_rejects_duplicate():
    db = connect(":memory:")
    standup_id = _open_standup(db)
    db.execute(
        """INSERT INTO odoo_write_log (standup_id, task_id, kind, dry_run)
           VALUES (?, ?, ?, 1)""",
        (standup_id, "42", "task_note"),
    )
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO odoo_write_log (standup_id, task_id, kind, dry_run)
               VALUES (?, ?, ?, 1)""",
            (standup_id, "42", "task_note"),
        )


def test_commitment_history_is_append_only():
    db = connect(":memory:")
    standup_id = _open_standup(db)

    commit_extraction = json.dumps({
        "commitments": [
            {"text": "finish the schema", "due_date": "2026-10-21", "date_type": "explicit"}
        ]
    })
    commitment_ledger.record_from_extraction(db, standup_id, "dev-a", commit_extraction)

    before = db.execute("SELECT * FROM commitment_history ORDER BY id").fetchall()
    assert len(before) == 1
    original_id = before[0]["id"]
    assert before[0]["state"] == "pending"

    done_extraction = json.dumps({"done": [{"text": "finish the schema", "origin": "reported"}]})
    commitment_ledger.mark_met_if_mentioned(db, standup_id, "dev-a", done_extraction)

    after = db.execute("SELECT * FROM commitment_history ORDER BY id").fetchall()
    assert len(after) == 2, "a state change must append a new row, not update the old one"
    assert after[0]["id"] == original_id
    assert after[0]["state"] == "pending", "the original row must be left unchanged"
    assert after[1]["state"] == "met"
    assert after[1]["id"] != original_id

    print(
        "\ncommitment_history append-only: "
        f"{len(before)} row before mark-met -> {len(after)} rows after (original row unchanged)"
    )
