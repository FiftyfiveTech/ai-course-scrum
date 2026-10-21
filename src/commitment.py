"""
Commitment ledger.

Records commitments from extractions, marks them met when mentioned in done
items, and surfaces overdue open ones for Q-commit follow-up questions.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "to", "of", "in", "is", "it",
    "on", "i", "my", "by", "will", "have", "be", "this", "that",
}


def record_from_extraction(
    db: sqlite3.Connection,
    standup_id: int,
    member_id: str,
    extraction_json: str | None,
) -> None:
    """Store all commitments found in an extraction into the ledger."""
    if not extraction_json or extraction_json == "FAILED":
        return
    data = json.loads(extraction_json)
    for item in data.get("commitments", []):
        db.execute(
            """INSERT INTO commitment
               (standup_id, member_id, description, due_date, date_type, state)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (
                standup_id,
                member_id,
                item["text"],
                item.get("due_date"),
                item.get("date_type", "implied"),
            ),
        )
    db.commit()


def mark_met_if_mentioned(
    db: sqlite3.Connection,
    member_id: str,
    extraction_json: str | None,
) -> None:
    """
    If today's done items overlap significantly with an open commitment,
    mark that commitment as met.
    Overlap threshold: ≥2 non-stop-word tokens in common.
    """
    if not extraction_json or extraction_json == "FAILED":
        return
    data = json.loads(extraction_json)
    done_texts = [d["text"].lower() for d in data.get("done", [])]
    if not done_texts:
        return

    pending = db.execute(
        "SELECT id, description FROM commitment WHERE member_id = ? AND state = 'pending'",
        (member_id,),
    ).fetchall()

    for comm in pending:
        comm_words = {
            w for w in comm["description"].lower().split()
            if w not in _STOP_WORDS
        }
        for done_text in done_texts:
            done_words = set(done_text.split())
            if len(comm_words & done_words) >= 2:
                db.execute(
                    "UPDATE commitment SET state = 'met' WHERE id = ?",
                    (comm["id"],),
                )
                break
    db.commit()


def get_overdue(
    db: sqlite3.Connection,
    member_id: str,
    as_of: date,
) -> list[sqlite3.Row]:
    """
    Return open commitments for a member due on or before as_of.
    These are the candidates for a Q-commit follow-up question.
    """
    return db.execute(
        """SELECT * FROM commitment
           WHERE member_id = ? AND state = 'pending'
             AND (due_date IS NULL OR due_date <= ?)
           ORDER BY due_date""",
        (member_id, as_of.isoformat()),
    ).fetchall()


def get_all_open(
    db: sqlite3.Connection,
    member_id: str,
) -> list[sqlite3.Row]:
    """Return all pending commitments for a member regardless of date."""
    return db.execute(
        """SELECT c.*, s.date AS committed_on
           FROM commitment c
           JOIN standup s ON c.standup_id = s.id
           WHERE c.member_id = ? AND c.state = 'pending'
           ORDER BY c.due_date""",
        (member_id,),
    ).fetchall()
