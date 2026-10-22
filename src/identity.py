"""
Identity map — Teams user id ↔ Odoo res.users id ↔ member_id.

Safety rule: an unknown sender gets NO writes and a loud WARNING log line.
Raise UnknownSenderError; callers must catch it before touching the DB or Odoo.

Load order:
  IdentityMap.from_config()   — loads config/identity_map.yaml
  IdentityMap(members)        — build directly (tests)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "identity_map.yaml"


class UnknownSenderError(ValueError):
    """Raised when an incoming id does not match any configured member."""


@dataclass(frozen=True)
class Member:
    member_id: str   # internal stable handle used in DB + reports
    name: str        # display name
    login: str       # Odoo login (email) — unique, used to pin identity
    teams_id: str    # Bot Framework activity from.id; "" until bot is live
    odoo_id: str     # Odoo res.users numeric id as string; "" until configured


class IdentityMap:
    """
    Bidirectional lookup between Teams sender ids, Odoo user ids, and member_ids.

    Unknown ids raise UnknownSenderError — never silently accept an unrecognised sender.
    """

    def __init__(self, members: list[Member]) -> None:
        self._by_member_id: dict[str, Member] = {}
        self._by_teams_id: dict[str, Member] = {}
        self._by_odoo_id: dict[str, Member] = {}
        self._by_login: dict[str, Member] = {}

        for m in members:
            self._by_member_id[m.member_id] = m
            if m.teams_id:
                self._by_teams_id[m.teams_id] = m
            if m.odoo_id:
                self._by_odoo_id[m.odoo_id] = m
            self._by_login[m.login] = m

    # ── Lookups ───────────────────────────────────────────────────────────────

    def from_teams(self, teams_id: str) -> Member:
        """
        Look up a member by their Teams `from.id`.
        Raises UnknownSenderError and logs WARNING if not found.
        """
        member = self._by_teams_id.get(teams_id)
        if member is None:
            logger.warning(
                "UNKNOWN SENDER teams_id=%r — no write, no extraction. "
                "Add this id to config/identity_map.yaml.",
                teams_id,
            )
            raise UnknownSenderError(
                f"teams_id {teams_id!r} not in identity map. "
                "No writes will be made for this sender."
            )
        return member

    def from_odoo(self, odoo_id: str) -> Member:
        """Look up a member by their Odoo res.users id."""
        member = self._by_odoo_id.get(str(odoo_id))
        if member is None:
            logger.warning(
                "UNKNOWN SENDER odoo_id=%r — not in identity map.",
                odoo_id,
            )
            raise UnknownSenderError(
                f"odoo_id {odoo_id!r} not in identity map."
            )
        return member

    def from_member_id(self, member_id: str) -> Member:
        """Look up a member by their internal member_id handle."""
        member = self._by_member_id.get(member_id)
        if member is None:
            logger.warning(
                "UNKNOWN member_id=%r — not in identity map.",
                member_id,
            )
            raise UnknownSenderError(
                f"member_id {member_id!r} not in identity map."
            )
        return member

    def from_login(self, login: str) -> Member:
        """Look up a member by their Odoo login (email). Avoids display-name ambiguity."""
        member = self._by_login.get(login)
        if member is None:
            logger.warning(
                "UNKNOWN login=%r — not in identity map. "
                "Note: pin by login, not display name ('Yash' matches multiple users).",
                login,
            )
            raise UnknownSenderError(
                f"login {login!r} not in identity map."
            )
        return member

    def all_members(self) -> list[Member]:
        """Return all configured members."""
        return list(self._by_member_id.values())

    def __iter__(self) -> Iterator[Member]:
        return iter(self._by_member_id.values())

    def __len__(self) -> int:
        return len(self._by_member_id)

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, path: Path = _CONFIG_PATH) -> "IdentityMap":
        """Load the identity map from config/identity_map.yaml."""
        data = yaml.safe_load(path.read_text())
        members = [
            Member(
                member_id=str(row["member_id"]),
                name=str(row["name"]),
                login=str(row["login"]),
                teams_id=str(row.get("teams_id") or ""),
                odoo_id=str(row.get("odoo_id") or ""),
            )
            for row in data["members"]
        ]
        return cls(members)
