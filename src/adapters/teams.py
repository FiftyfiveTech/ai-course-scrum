"""
Teams adapter — scaffold, awaiting credentials.

Satisfies the same ChatAdapter protocol as ScriptedCLIAdapter.
No lifecycle or report changes needed when this is swapped in.

Prerequisites (docs/access.md B1 checklist):
  TEAMS_APP_ID, TEAMS_APP_PASSWORD, TEAMS_CHANNEL_ID, TEAMS_SERVICE_URL
  must be set in .env before this adapter can be used.

Spike checks (SCRUM-013):
  C1 — bot posts a proactive message on schedule
  C2 — bot receives a reply WITHOUT an @mention
  C3 — bot reads the sender id correctly
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from src.adapters import Message

logger = logging.getLogger(__name__)

# ── Credentials ──────────────────────────────────────────────────────────────
# Loaded from .env — never hard-coded.

def _require_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"{key} not set. Add it to .env — see docs/access.md for setup steps."
        )
    return val


class TeamsAdapter:
    """
    Teams channel adapter.

    One thread per stand-up (channel mode).
    Proactive messages use the Bot Framework REST API.
    Reads all channel messages via RSC ChannelMessage.Read.Group consent.
    """

    def __init__(self) -> None:
        self._app_id = _require_env("TEAMS_APP_ID")
        self._app_password = _require_env("TEAMS_APP_PASSWORD")
        self._channel_id = _require_env("TEAMS_CHANNEL_ID")
        self._service_url = _require_env("TEAMS_SERVICE_URL")
        self._token: str | None = None
        self._inbox: list[Message] = []

    # ── ChatAdapter protocol ─────────────────────────────────────────────────

    def post(self, text: str) -> str:
        """Post a proactive message to the stand-up channel thread."""
        # C1 check: scheduled proactive message
        token = self._get_token()
        message_id = self._send_channel_message(text, token)
        logger.info("C1 posted message_id=%s", message_id)
        return message_id

    def post_private(self, user_id: str, text: str) -> str:
        """Send a private message to one member (1:1 chat or channel reply)."""
        token = self._get_token()
        message_id = self._send_channel_message(f"@{user_id} {text}", token)
        logger.info("posted private to user_id=%s message_id=%s", user_id, message_id)
        return message_id

    def get_replies(self, since: datetime) -> list[Message]:
        """
        Return all replies received after `since`.
        Reads channel messages via RSC consent — no @mention required.
        """
        # C2 + C3 checks: receive replies without @mention, read sender id
        messages = self._poll_channel_messages(since)
        for m in messages:
            logger.info("C2/C3 received sender_id=%s text=%s", m.member_id, m.text[:60])
        return messages

    # ── Bot Framework helpers (stubs — fill in when credentials arrive) ──────

    def _get_token(self) -> str:
        """Fetch an OAuth2 token from the Bot Framework token endpoint."""
        # POST https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token
        # grant_type=client_credentials, client_id=APP_ID, client_secret=APP_PASSWORD
        # scope=https://api.botframework.com/.default
        raise NotImplementedError(
            "Teams credentials not yet available — see docs/access.md."
        )

    def _send_channel_message(self, text: str, token: str) -> str:
        """POST a message to the Teams channel via Bot Framework REST API."""
        # POST {SERVICE_URL}/v3/conversations/{CHANNEL_ID}/activities
        raise NotImplementedError(
            "Teams credentials not yet available — see docs/access.md."
        )

    def _poll_channel_messages(self, since: datetime) -> list[Message]:
        """
        GET channel messages via Microsoft Graph API.
        Requires RSC ChannelMessage.Read.Group admin consent (B1c).
        """
        # GET https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages
        raise NotImplementedError(
            "Teams credentials not yet available — see docs/access.md."
        )
