"""
Tests for commitment + blocker ledgers — SCRUM-018.

Done criteria:
  - a resolved blocker is never reported active
  - an old estimate is never treated as a new promise
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import src.blocker as blocker_ledger
import src.commitment as commitment_ledger
from src.db import connect


@pytest.fixture
def db():
    conn = connect(":memory:")
    # Seed a standup row so FK constraints pass
    conn.execute(
        "INSERT INTO standup (team_id, date, state, opened_at) VALUES ('team', '2026-10-21', 'open', '2026-10-21T09:00:00')"
    )
    conn.execute(
        "INSERT INTO standup (team_id, date, state, opened_at) VALUES ('team', '2026-10-22', 'open', '2026-10-22T09:00:00')"
    )
    conn.commit()
    return conn


STANDUP_ID_1 = 1
STANDUP_ID_2 = 2

BLOCKER_EXTRACTION = """{
  "done": [],
  "next": [],
  "blockers": [
    {"text": "waiting for Vimal on the API spec", "origin": "reported", "task_id": null, "owner_id": "vimal"}
  ],
  "task_ids": [],
  "commitments": []
}"""

COMMIT_EXTRACTION = """{
  "done": [],
  "next": [],
  "blockers": [],
  "task_ids": [],
  "commitments": [
    {"text": "finish the schema doc", "origin": "reported", "due_date": "2026-10-22", "date_type": "explicit", "task_id": null}
  ]
}"""

DONE_EXTRACTION = """{
  "done": [{"text": "finished the schema doc", "origin": "reported", "task_id": null}],
  "next": [],
  "blockers": [],
  "task_ids": [],
  "commitments": []
}"""


# ── Blocker ledger ────────────────────────────────────────────────────────────

def test_blocker_recorded(db) -> None:
    blocker_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", BLOCKER_EXTRACTION)
    open_b = blocker_ledger.get_open(db, "ritika")
    assert len(open_b) == 1
    assert "Vimal" in open_b[0]["description"] or "vimal" in open_b[0]["description"].lower()


def test_resolved_blocker_not_reported_active(db) -> None:
    """A resolved blocker must never appear in get_open — SCRUM-018 core criterion."""
    blocker_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", BLOCKER_EXTRACTION)
    open_b = blocker_ledger.get_open(db, "ritika")
    blocker_id = open_b[0]["id"]

    # Human confirms resolution
    blocker_ledger.resolve(db, blocker_id)

    # Must not appear as active
    still_open = blocker_ledger.get_open(db, "ritika")
    assert len(still_open) == 0


def test_resolve_sets_timestamp(db) -> None:
    blocker_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", BLOCKER_EXTRACTION)
    b_id = blocker_ledger.get_open(db, "ritika")[0]["id"]
    ts = datetime(2026, 10, 22, 10, 0, 0, tzinfo=timezone.utc)
    blocker_ledger.resolve(db, b_id, resolved_at=ts)

    row = db.execute("SELECT * FROM blocker WHERE id = ?", (b_id,)).fetchone()
    assert row["open"] == 0
    assert "2026-10-22" in row["resolved_at"]


def test_days_open_computed(db) -> None:
    """days_open is computed, never stored."""
    blocker_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", BLOCKER_EXTRACTION)
    open_b = blocker_ledger.get_open(db, "ritika")
    # standup date is 2026-10-21; as_of 2026-10-23 → 2 days
    days = blocker_ledger.days_open(open_b[0], date(2026, 10, 23))
    assert days == 2


def test_failed_extraction_records_no_blockers(db) -> None:
    blocker_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", "FAILED")
    assert blocker_ledger.get_open(db, "ritika") == []


def test_get_open_all(db) -> None:
    blocker_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", BLOCKER_EXTRACTION)
    blocker_ledger.record_from_extraction(db, STANDUP_ID_2, "vimal", BLOCKER_EXTRACTION)
    all_open = blocker_ledger.get_open_all(db)
    assert len(all_open) == 2


# ── Commitment ledger ─────────────────────────────────────────────────────────

def test_commitment_recorded(db) -> None:
    commitment_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", COMMIT_EXTRACTION)
    open_c = commitment_ledger.get_all_open(db, "ritika")
    assert len(open_c) == 1
    assert open_c[0]["description"] == "finish the schema doc"


def test_old_estimate_not_treated_as_new_promise(db) -> None:
    """
    Recording the same commitment description in day-2 extraction must not
    create a second pending row — it's the same promise, not a new one.
    SCRUM-018 core criterion: old estimate ≠ new promise.
    """
    commitment_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", COMMIT_EXTRACTION)
    # Day 2: same commitment text appears again (dev repeating estimate)
    commitment_ledger.record_from_extraction(db, STANDUP_ID_2, "ritika", COMMIT_EXTRACTION)

    # get_all_open uses the append-only latest-row query; both rows exist but
    # the test checks that we don't double-count open commitments in the ledger view.
    # The query returns the latest row per (member_id, description) that is 'pending'.
    open_c = commitment_ledger.get_all_open(db, "ritika")
    descriptions = [r["description"] for r in open_c]
    # Only one logical commitment for "finish the schema doc"
    assert descriptions.count("finish the schema doc") == 1


def test_commitment_marked_met_when_mentioned_in_done(db) -> None:
    commitment_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", COMMIT_EXTRACTION)
    # Day 2: done item mentions the commitment (≥2 word overlap)
    commitment_ledger.mark_met_if_mentioned(db, STANDUP_ID_2, "ritika", DONE_EXTRACTION)

    open_c = commitment_ledger.get_all_open(db, "ritika")
    assert len(open_c) == 0  # marked met → no longer open


def test_overdue_commitment_surfaces(db) -> None:
    commitment_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", COMMIT_EXTRACTION)
    # Due date was 2026-10-22; checking on 2026-10-23 → overdue
    overdue = commitment_ledger.get_overdue(db, "ritika", date(2026, 10, 23))
    assert len(overdue) == 1


def test_failed_extraction_records_no_commitments(db) -> None:
    commitment_ledger.record_from_extraction(db, STANDUP_ID_1, "ritika", "FAILED")
    assert commitment_ledger.get_all_open(db, "ritika") == []
