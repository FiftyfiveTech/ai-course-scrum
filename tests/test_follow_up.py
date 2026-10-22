"""
Tests for follow-up question engine — SCRUM-019.

Done criteria:
  - one unit test per rule (Q1–Q7, Q-commit)
  - a 3rd question is never sent
"""

from __future__ import annotations

from datetime import date

import pytest

import src.blocker as blocker_ledger
import src.commitment as commitment_ledger
from src.db import connect
from src.follow_up import FollowUpEngine, MAX_PER_MEMBER

STANDUP_DATE = date(2026, 10, 22)
PRIOR_DATE = date(2026, 10, 21)


@pytest.fixture
def db():
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO standup (id, team_id, date, state, opened_at) "
        "VALUES (1, 'team', '2026-10-21', 'closed', '2026-10-21T09:00:00')"
    )
    conn.execute(
        "INSERT INTO standup (id, team_id, date, state, opened_at) "
        "VALUES (2, 'team', '2026-10-22', 'collect', '2026-10-22T09:00:00')"
    )
    conn.commit()
    return conn


def engine(db, standup_id=2):
    return FollowUpEngine(db, standup_id)


EXTRACTION_WITH_BLOCKER = {
    "done": [],
    "next": [{"text": "finish tests", "origin": "reported", "task_id": None}],
    "blockers": [{"text": "waiting on DB access from ops", "origin": "reported", "task_id": None, "owner_id": None}],
    "task_ids": [],
    "commitments": [],
}

EXTRACTION_CLEAN = {
    "done": [{"text": "deployed auth service", "origin": "reported", "task_id": "101"}],
    "next": [{"text": "write tests", "origin": "reported", "task_id": None}],
    "blockers": [],
    "task_ids": [{"task_id": "101", "origin": "reported", "mention": "#101"}],
    "commitments": [],
}

EXTRACTION_NO_DONE = {
    "done": [],
    "next": [{"text": "writing the schema doc", "origin": "reported", "task_id": None}],
    "blockers": [],
    "task_ids": [],
    "commitments": [],
}


# ── Q1: no update received ────────────────────────────────────────────────────

def test_q1_no_update(db) -> None:
    qs = engine(db).select("ritika", extraction=None, standup_date=STANDUP_DATE)
    assert any(q.rule == "Q1" for q in qs)


def test_q1_not_fired_when_update_present(db) -> None:
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE)
    assert not any(q.rule == "Q1" for q in qs)


# ── Q2: done on task but board shows open ─────────────────────────────────────

def test_q2_fires_when_board_shows_task_open(db) -> None:
    board_tasks = [{"id": 101, "name": "auth service", "state": "01_in_progress", "date_deadline": None}]
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE, board_tasks=board_tasks)
    assert any(q.rule == "Q2" for q in qs)


def test_q2_not_fired_when_board_tasks_none(db) -> None:
    """Q2 is board-driven — skipped without board data."""
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE, board_tasks=None)
    assert not any(q.rule == "Q2" for q in qs)


def test_q2_not_fired_when_task_already_done_on_board(db) -> None:
    board_tasks = [{"id": 101, "name": "auth service", "state": "1_done", "date_deadline": None}]
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE, board_tasks=board_tasks)
    assert not any(q.rule == "Q2" for q in qs)


# ── Q3: deadline today/tomorrow, not mentioned ────────────────────────────────

def test_q3_fires_for_deadline_today(db) -> None:
    board_tasks = [{"id": 999, "name": "ship MVP", "state": "01_in_progress", "date_deadline": "2026-10-22"}]
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE, board_tasks=board_tasks)
    assert any(q.rule == "Q3" for q in qs)


def test_q3_not_fired_when_board_tasks_none(db) -> None:
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE, board_tasks=None)
    assert not any(q.rule == "Q3" for q in qs)


# ── Q4: task overdue, not mentioned ──────────────────────────────────────────

def test_q4_fires_for_overdue_task(db) -> None:
    board_tasks = [{"id": 888, "name": "old ticket", "state": "01_in_progress", "date_deadline": "2026-10-19"}]
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE, board_tasks=board_tasks)
    assert any(q.rule == "Q4" for q in qs)


def test_q4_not_fired_when_board_tasks_none(db) -> None:
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE, board_tasks=None)
    assert not any(q.rule == "Q4" for q in qs)


# ── Q5: stale blocker from prior standup ─────────────────────────────────────

def test_q5_fires_for_prior_unresolved_blocker(db) -> None:
    # Record a blocker from standup 1 (prior day)
    extraction_json = '{"done":[],"next":[],"blockers":[{"text":"ops team hasn\'t replied","origin":"reported","task_id":null,"owner_id":null}],"task_ids":[],"commitments":[]}'
    blocker_ledger.record_from_extraction(db, 1, "ritika", extraction_json)

    # Today's update has no mention of that blocker
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE)
    assert any(q.rule == "Q5" for q in qs)


def test_q5_not_fired_when_no_prior_blockers(db) -> None:
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE)
    assert not any(q.rule == "Q5" for q in qs)


# ── Q6: no done items ────────────────────────────────────────────────────────

def test_q6_fires_when_no_done_items(db) -> None:
    qs = engine(db).select("ritika", extraction=EXTRACTION_NO_DONE, standup_date=STANDUP_DATE)
    assert any(q.rule == "Q6" for q in qs)


def test_q6_not_fired_when_done_items_present(db) -> None:
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE)
    assert not any(q.rule == "Q6" for q in qs)


# ── Q7: new blocker mentioned today ──────────────────────────────────────────

def test_q7_fires_for_new_blocker(db) -> None:
    qs = engine(db).select("ritika", extraction=EXTRACTION_WITH_BLOCKER, standup_date=STANDUP_DATE)
    assert any(q.rule == "Q7" for q in qs)


def test_q7_not_fired_when_no_blockers(db) -> None:
    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE)
    assert not any(q.rule == "Q7" for q in qs)


# ── Q-commit: prior overdue commitment ───────────────────────────────────────

def test_q_commit_fires_for_overdue_commitment(db) -> None:
    import json
    extraction_json = json.dumps({
        "done": [], "next": [], "blockers": [], "task_ids": [],
        "commitments": [{"text": "write unit tests", "origin": "reported",
                         "due_date": "2026-10-21", "date_type": "explicit", "task_id": None}]
    })
    commitment_ledger.record_from_extraction(db, 1, "ritika", extraction_json)

    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE)
    assert any(q.rule == "Q-commit" for q in qs)


def test_q_commit_not_fired_for_todays_commitment(db) -> None:
    """Commitments made today should not trigger Q-commit on the same day."""
    import json
    extraction_json = json.dumps({
        "done": [], "next": [], "blockers": [], "task_ids": [],
        "commitments": [{"text": "write unit tests", "origin": "reported",
                         "due_date": "2026-10-22", "date_type": "explicit", "task_id": None}]
    })
    # Record in standup 2 (today's standup)
    commitment_ledger.record_from_extraction(db, 2, "ritika", extraction_json)

    qs = engine(db).select("ritika", extraction=EXTRACTION_CLEAN, standup_date=STANDUP_DATE)
    assert not any(q.rule == "Q-commit" for q in qs)


# ── Cap: never more than MAX_PER_MEMBER questions ────────────────────────────

def test_third_question_never_sent(db) -> None:
    """Core safety check: no matter how many rules fire, max 2 questions sent."""
    import json

    # Seed everything to fire as many rules as possible:
    # Prior blocker (Q5), prior overdue commitment (Q-commit), blocker today (Q7)
    blocker_json = json.dumps({
        "done": [], "next": [], "blockers": [
            {"text": "waiting on infra team", "origin": "reported", "task_id": None, "owner_id": None}
        ], "task_ids": [], "commitments": []
    })
    commit_json = json.dumps({
        "done": [], "next": [], "blockers": [], "task_ids": [],
        "commitments": [{"text": "write schema doc", "origin": "reported",
                         "due_date": "2026-10-21", "date_type": "explicit", "task_id": None}]
    })
    blocker_ledger.record_from_extraction(db, 1, "ritika", blocker_json)
    commitment_ledger.record_from_extraction(db, 1, "ritika", commit_json)

    board_tasks = [
        {"id": 999, "name": "overdue task", "state": "01_in_progress", "date_deadline": "2026-10-19"},
        {"id": 101, "name": "auth service", "state": "01_in_progress", "date_deadline": "2026-10-22"},
    ]

    qs = engine(db).select(
        "ritika",
        extraction=EXTRACTION_WITH_BLOCKER,
        standup_date=STANDUP_DATE,
        board_tasks=board_tasks,
    )

    assert len(qs) <= MAX_PER_MEMBER, (
        f"Got {len(qs)} questions — must never exceed {MAX_PER_MEMBER}"
    )
