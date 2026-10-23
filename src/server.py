"""
FastAPI server — the Teams-managed bot's HTTP front end (POC-01).

Routes:
  POST /api/messages   receive a Teams Bot Framework activity, store it, return 200
  GET  /healthz        liveness probe (used by the Railway deploy, POC-19)

POC-01 scope is the messaging *backbone*: an inbound stand-up message from a known
sender becomes one `standup_update` row (raw text only). Extraction (a model call)
is deliberately left out here and wired in later via the lifecycle (POC-08);
conversation-reference capture is POC-04.

Dependencies (DB, identity map, team, clock) are injected through `create_app` so
tests can drive the webhook against an in-memory DB and a test identity map. The
production app is built by `create_production_app` from env + config — run it with:

    uv run uvicorn --factory src.server:create_production_app
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import date
from typing import Any, Mapping

from fastapi import FastAPI, HTTPException, Request

from src import db as db_module
from src.auth import TokenError, TokenValidator, botframework_validator
from src.clock import Clock, ClockProtocol
from src.identity import IdentityMap, UnknownSenderError

logger = logging.getLogger(__name__)


def _get_or_open_standup(
    db: sqlite3.Connection, team_id: str, today: date, now_iso: str
) -> int:
    """Return today's stand-up id for the team, creating an open one if absent.

    A real schedule opens stand-ups on a cron (POC-07); until that is wired, an
    inbound message lands in today's stand-up, opening it on first contact.
    """
    row = db.execute(
        "SELECT id FROM standup WHERE team_id = ? AND date = ?",
        (team_id, today.isoformat()),
    ).fetchone()
    if row is not None:
        return row["id"]

    cur = db.execute(
        "INSERT INTO standup (team_id, date, state, opened_at) VALUES (?, ?, 'open', ?)",
        (team_id, today.isoformat(), now_iso),
    )
    db.commit()
    return cur.lastrowid


def ingest_activity(
    db: sqlite3.Connection,
    identity: IdentityMap,
    team_id: str,
    activity: Mapping[str, Any],
    clock: ClockProtocol,
) -> int | None:
    """Store one Teams activity as a stand-up update row.

    Returns the `standup_update` row id, or None when nothing is stored:
    a non-message activity, or an unknown sender (safety rule — no write).
    """
    if activity.get("type") != "message":
        return None

    sender_id = activity.get("from", {}).get("id", "")
    try:
        member = identity.from_teams(sender_id)
    except UnknownSenderError:
        # from_teams already logged a WARNING; swallow so the webhook still 200s.
        return None

    chat_message_id = activity.get("id")
    if not chat_message_id:
        logger.warning("activity has no id; cannot store (sender=%r)", sender_id)
        return None

    now = clock.now()
    standup_id = _get_or_open_standup(db, team_id, now.date(), now.isoformat())

    cur = db.execute(
        """INSERT OR IGNORE INTO standup_update
               (standup_id, member_id, raw_text, chat_message_id, created_at)
               VALUES (?, ?, ?, ?, ?)""",
        (
            standup_id,
            member.member_id,
            activity.get("text", ""),
            chat_message_id,
            now.isoformat(),
        ),
    )
    db.commit()

    if cur.rowcount == 0:
        # Duplicate delivery (unique on standup_id + chat_message_id) — return the id we already have.
        existing = db.execute(
            "SELECT id FROM standup_update WHERE standup_id = ? AND chat_message_id = ?",
            (standup_id, chat_message_id),
        ).fetchone()
        return existing["id"] if existing else None

    return cur.lastrowid


def create_app(
    db: sqlite3.Connection,
    identity: IdentityMap,
    team_id: str,
    clock: ClockProtocol | None = None,
    token_validator: TokenValidator | None = None,
) -> FastAPI:
    """Build the FastAPI app around injected dependencies.

    token_validator: when set, POST /api/messages rejects any request whose
    Authorization header is missing or fails verification (POC-02). Left None in
    tests that exercise ingestion only.
    """
    app = FastAPI(title="AI Scrum Master")
    app.state.db = db
    app.state.identity = identity
    app.state.team_id = team_id
    app.state.clock = clock or Clock()
    app.state.token_validator = token_validator

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/messages")
    async def messages(request: Request) -> dict[str, str]:
        validator: TokenValidator | None = app.state.token_validator
        if validator is not None:
            try:
                claims = validator.validate(request.headers.get("Authorization"))
            except TokenError as exc:
                logger.warning("rejected inbound request: %s", exc)
                raise HTTPException(status_code=401, detail="invalid bot token") from exc
            logger.info("accepted inbound token aud=%s iss=%s", claims.get("aud"), claims.get("iss"))

        activity = await request.json()
        ingest_activity(
            app.state.db,
            app.state.identity,
            app.state.team_id,
            activity,
            app.state.clock,
        )
        # Bot Framework only needs a 200; the body is ignored.
        return {"status": "ok"}

    return app


def create_production_app() -> FastAPI:
    """Factory for `uvicorn --factory src.server:create_production_app`."""
    logging.basicConfig(level=logging.INFO)
    db = db_module.connect(os.environ.get("DB_PATH", "scrum.db"))
    identity = IdentityMap.from_config()
    team_id = os.environ.get("TEAM_ID", "course-team")
    app_id = os.environ.get("MICROSOFT_APP_ID")
    if not app_id:
        raise RuntimeError("MICROSOFT_APP_ID is required to verify inbound Bot Framework tokens")
    return create_app(db, identity, team_id, token_validator=botframework_validator(app_id))
