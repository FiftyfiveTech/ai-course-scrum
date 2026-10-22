"""
Blocker ledger — SCRUM-018.

Rules:
- A blocker is recorded from extraction when a developer reports one.
- A blocker stays open (open=1) until a human explicitly confirms it is resolved.
  The model never resolves a blocker.
- days_open is computed from the standup date; it is never stored.
- Resolving a blocker sets open=0 and records resolved_at; the original row
  is mutated (blockers are not append-only — they have a single lifecycle: open → resolved).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone


def record_from_extraction(
    db: sqlite3.Connection,
    standup_id: int,
    member_id: str,
    extraction_json: str | None,
) -> None:
    """Insert blocker rows from an extraction into the ledger."""
    if not extraction_json or extraction_json == "FAILED":
        return
    data = json.loads(extraction_json)
    for item in data.get("blockers", []):
        db.execute(
            """INSERT INTO blocker
               (standup_id, member_id, task_id, description, owner_id, open)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (
                standup_id,
                member_id,
                item.get("task_id"),
                item["text"],
                item.get("owner_id"),
            ),
        )
    db.commit()


def resolve(
    db: sqlite3.Connection,
    blocker_id: int,
    resolved_at: datetime | None = None,
) -> None:
    """
    Mark a blocker resolved. Must be called by code after a human confirms.
    The model never calls this.
    """
    ts = (resolved_at or datetime.now(timezone.utc)).isoformat()
    db.execute(
        "UPDATE blocker SET open = 0, resolved_at = ? WHERE id = ?",
        (ts, blocker_id),
    )
    db.commit()


def get_open(
    db: sqlite3.Connection,
    member_id: str,
) -> list[sqlite3.Row]:
    """Return all open (unresolved) blockers for a member."""
    return db.execute(
        """SELECT b.*, s.date AS standup_date
           FROM blocker b
           JOIN standup s ON b.standup_id = s.id
           WHERE b.member_id = ? AND b.open = 1
           ORDER BY s.date""",
        (member_id,),
    ).fetchall()


def get_open_all(db: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all open blockers across all members."""
    return db.execute(
        """SELECT b.*, s.date AS standup_date
           FROM blocker b
           JOIN standup s ON b.standup_id = s.id
           WHERE b.open = 1
           ORDER BY b.member_id, s.date""",
    ).fetchall()


def days_open(blocker_row: sqlite3.Row, as_of: date) -> int:
    """
    Compute how many days a blocker has been open.
    Computed from the standup date — never stored.
    """
    reported_date = date.fromisoformat(blocker_row["standup_date"])
    return (as_of - reported_date).days
