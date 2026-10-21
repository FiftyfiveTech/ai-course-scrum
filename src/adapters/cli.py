"""
CLI adapter.

ScriptedCLIAdapter — pre-loaded member responses for demo and tests.
No real stdin; all output goes to stdout.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.adapters import Message


class ScriptedCLIAdapter:
    """
    Chat adapter driven by pre-scripted responses.

    scripts = { member_id: ["initial update", "follow-up answer", ...] }

    Each call to collect_member_response() advances that member's cursor by one
    and queues the reply in the inbox.
    """

    def __init__(self, scripts: dict[str, list[str]], clock: Any = None) -> None:
        self._scripts: dict[str, list[str]] = {k: list(v) for k, v in scripts.items()}
        self._cursors: dict[str, int] = {k: 0 for k in scripts}
        self._inbox: list[Message] = []
        self._clock = clock

    # ── ChatAdapter protocol ────────────────────────────────────────────────

    def post(self, text: str) -> str:
        msg_id = uuid.uuid4().hex[:8]
        print(f"\n{'─' * 60}")
        for line in text.splitlines():
            print(f"  [BOT] {line}")
        print(f"{'─' * 60}")
        return msg_id

    def post_private(self, user_id: str, text: str) -> str:
        msg_id = uuid.uuid4().hex[:8]
        print(f"\n  [BOT → {user_id}] {text}")
        return msg_id

    def get_replies(self, since: datetime) -> list[Message]:
        return [m for m in self._inbox if m.timestamp >= since]

    # ── Demo helper ─────────────────────────────────────────────────────────

    def collect_member_response(self, member_id: str) -> Message | None:
        """
        Advance the script for one member and queue their next response.
        Returns None when the script is exhausted.
        """
        cursor = self._cursors.get(member_id, 0)
        responses = self._scripts.get(member_id, [])
        if cursor >= len(responses):
            return None

        text = responses[cursor]
        self._cursors[member_id] = cursor + 1
        now = self._clock.now() if self._clock else datetime.now(timezone.utc)

        msg = Message(
            id=f"{member_id}-{cursor}",
            member_id=member_id,
            text=text,
            timestamp=now,
        )
        self._inbox.append(msg)
        print(f"\n  [{member_id}] {text}")
        return msg
