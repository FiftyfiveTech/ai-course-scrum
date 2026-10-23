"""POC-03 gate: TeamsAdapter is a drop-in ChatAdapter.

Everything runs offline. Outbound calls go through an injected fake transport (no HTTP, no token);
get_replies reads an in-memory DB seeded the same way the live webhook seeds it — by replaying a
captured Teams activity through POST /api/messages (mirrors tests/test_server.py).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import db as db_module
from src.adapters import Message
from src.adapters.teams import ConversationRef, TeamsAdapter
from src.clock import FakeClock
from src.identity import IdentityMap, Member
from src.server import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "teams" / "message_personal.json"
TEAM_ID = "test-team"
CONV = ConversationRef(service_url="https://smba.trafficmanager.net/emea/", conversation_id="19:abc@thread.v2")
ENV = {"MICROSOFT_APP_ID": "app-123", "MICROSOFT_APP_TENANT_ID": "tenant-9"}


class FakeTransport:
    """Records every (url, token, body) and returns canned responses in order."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url: str, token: str, body: dict) -> dict:
        self.calls.append({"url": url, "token": token, "body": body})
        return self._responses.pop(0)


def _adapter(transport: FakeTransport, *, conversation=CONV, db=None) -> TeamsAdapter:
    return TeamsAdapter(
        db=db,
        env=ENV,
        conversation=conversation,
        token_provider=lambda: "fake-token",
        transport=transport,
    )


# ── post() ───────────────────────────────────────────────────────────────────

def test_post_returns_real_message_id():
    transport = FakeTransport([{"id": "1234"}])
    adapter = _adapter(transport)

    message_id = adapter.post("hello team")

    assert message_id == "1234"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == (
        "https://smba.trafficmanager.net/emea/v3/conversations/"
        "19%3Aabc%40thread.v2/activities"
    )
    assert call["body"] == {"type": "message", "text": "hello team"}
    assert call["token"] == "fake-token"


def test_post_without_conversation_reference_errors():
    adapter = _adapter(FakeTransport([]), conversation=None)
    with pytest.raises(RuntimeError, match="conversation reference"):
        adapter.post("nowhere to send this")


# ── post_private() ─────────────────────────────────────────────────────────────

def test_post_private_creates_conversation_then_posts():
    # First response = create-conversation; second = the posted activity.
    transport = FakeTransport([{"id": "conv-9"}, {"id": "m-7"}])
    adapter = _adapter(transport)

    message_id = adapter.post_private("29:user-xyz", "just between us")

    assert message_id == "m-7"
    assert len(transport.calls) == 2

    create = transport.calls[0]
    assert create["url"] == "https://smba.trafficmanager.net/emea/v3/conversations"
    assert create["body"]["members"] == [{"id": "29:user-xyz"}]
    assert create["body"]["isGroup"] is False
    assert create["body"]["bot"] == {"id": "28:app-123"}
    assert create["body"]["tenantId"] == "tenant-9"

    post = transport.calls[1]
    assert post["url"] == (
        "https://smba.trafficmanager.net/emea/v3/conversations/conv-9/activities"
    )
    assert post["body"] == {"type": "message", "text": "just between us"}


# ── get_replies() ──────────────────────────────────────────────────────────────

def _seeded_db():
    """In-memory DB with one stored update, written exactly as the live webhook writes it."""
    db = db_module.connect(":memory:")
    activity = json.loads(FIXTURE.read_text(encoding="utf-8"))
    sender_id = activity["from"]["id"]
    identity = IdentityMap([
        Member(member_id="testuser", name="Test User",
               login="test.user@fiftyfivetech.io", teams_id=sender_id, odoo_id="")
    ])
    clock = FakeClock(datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc))
    client = TestClient(create_app(db, identity, TEAM_ID, clock=clock))
    resp = client.post("/api/messages", json=activity)
    assert resp.status_code == 200
    return db, activity


def test_get_replies_returns_stored_messages_typed():
    db, activity = _seeded_db()
    adapter = _adapter(FakeTransport([]), db=db)

    replies = adapter.get_replies(datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc))

    assert len(replies) == 1
    msg = replies[0]
    assert isinstance(msg, Message)
    assert msg.id == activity["id"]
    assert msg.member_id == "testuser"
    assert msg.text == activity["text"]
    assert isinstance(msg.timestamp, datetime)
    assert msg.timestamp == datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc)


def test_get_replies_honours_since():
    db, _ = _seeded_db()  # the stored row is at 11:00 UTC
    adapter = _adapter(FakeTransport([]), db=db)

    before = adapter.get_replies(datetime(2026, 10, 22, 10, 59, tzinfo=timezone.utc))
    after = adapter.get_replies(datetime(2026, 10, 22, 11, 1, tzinfo=timezone.utc))

    assert len(before) == 1
    assert after == []


# ── protocol conformance ───────────────────────────────────────────────────────

def test_satisfies_chat_adapter_protocol():
    adapter = _adapter(FakeTransport([]))
    for method in ("post", "get_replies", "post_private"):
        assert callable(getattr(adapter, method))
