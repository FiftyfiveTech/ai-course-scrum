"""
Chat adapter protocol. Every adapter (CLI, Teams, …) must satisfy this interface.
The core never imports a concrete adapter directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class Message:
    id: str
    member_id: str
    text: str
    timestamp: datetime


class ChatAdapter(Protocol):
    def post(self, text: str) -> str:
        """Broadcast a message to the whole team. Returns a message id."""
        ...

    def get_replies(self, since: datetime) -> list[Message]:
        """Return all replies received after `since`."""
        ...

    def post_private(self, user_id: str, text: str) -> str:
        """Send a private message to one member. Returns a message id."""
        ...
