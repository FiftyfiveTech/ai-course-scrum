"""
POC-01 gate: replaying a Teams activity through POST /api/messages stores one update row.

The fixture sender id is not in config/identity_map.yaml (teams_id is blank until the
bot is live), so the test injects its own IdentityMap mapping that sender to a member.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src import db as db_module
from src.clock import FakeClock
from src.identity import IdentityMap, Member
from src.server import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "teams" / "message_personal.json"
TEAM_ID = "test-team"


def _activity() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _identity_with_sender() -> IdentityMap:
    sender_id = _activity()["from"]["id"]
    return IdentityMap(
        [
            Member(
                member_id="testuser",
                name="Test User",
                login="test.user@fiftyfivetech.io",
                teams_id=sender_id,
                odoo_id="",
            )
        ]
    )


def _client(db):
    clock = FakeClock(datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc))
    return TestClient(create_app(db, _identity_with_sender(), TEAM_ID, clock=clock))


def test_healthz():
    db = db_module.connect(":memory:")
    assert _client(db).get("/healthz").json() == {"status": "ok"}


def test_replay_fixture_stores_one_update_row():
    db = db_module.connect(":memory:")
    activity = _activity()

    resp = _client(db).post("/api/messages", json=activity)
    assert resp.status_code == 200

    rows = db.execute(
        "SELECT member_id, raw_text, chat_message_id FROM standup_update"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["member_id"] == "testuser"
    assert rows[0]["raw_text"] == activity["text"]
    assert rows[0]["chat_message_id"] == activity["id"]


def test_unknown_sender_stores_nothing():
    db = db_module.connect(":memory:")
    empty_identity = IdentityMap([])  # the fixture sender is not mapped
    clock = FakeClock(datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc))
    client = TestClient(create_app(db, empty_identity, TEAM_ID, clock=clock))

    resp = client.post("/api/messages", json=_activity())
    assert resp.status_code == 200  # still acknowledged
    assert db.execute("SELECT COUNT(*) AS n FROM standup_update").fetchone()["n"] == 0


def test_duplicate_delivery_is_idempotent():
    db = db_module.connect(":memory:")
    client = _client(db)

    client.post("/api/messages", json=_activity())
    client.post("/api/messages", json=_activity())

    assert db.execute("SELECT COUNT(*) AS n FROM standup_update").fetchone()["n"] == 1
