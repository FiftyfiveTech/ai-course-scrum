"""
Unit tests for src/identity.py — SCRUM-017.

Done criteria: one test per lookup, unknown sender gets no writes and a loud log line.
All tests use an in-memory IdentityMap (no file I/O).
"""

from __future__ import annotations

import pytest

from src.identity import IdentityMap, Member, UnknownSenderError

# ── Fixtures ─────────────────────────────────────────────────────────────────

RITIKA = Member(
    member_id="ritika",
    name="Ritika",
    login="ritika@fiftyfivetech.io",
    teams_id="29:ritika-teams-id",
    odoo_id="42",
)
VIMAL = Member(
    member_id="vimal",
    name="Vimal",
    login="vimal.vashisth@fiftyfivetech.io",
    teams_id="29:vimal-teams-id",
    odoo_id="15",
)
# Yash — teams_id and odoo_id not yet configured (blank)
YASH = Member(
    member_id="yash",
    name="Yash",
    login="yash.pancholi@fiftyfivetech.io",
    teams_id="",
    odoo_id="",
)


@pytest.fixture
def imap() -> IdentityMap:
    return IdentityMap([RITIKA, VIMAL, YASH])


# ── Happy-path lookups ────────────────────────────────────────────────────────

def test_from_teams_id(imap: IdentityMap) -> None:
    member = imap.from_teams("29:ritika-teams-id")
    assert member.member_id == "ritika"
    assert member.login == "ritika@fiftyfivetech.io"


def test_from_odoo_id(imap: IdentityMap) -> None:
    member = imap.from_odoo("15")
    assert member.member_id == "vimal"


def test_from_member_id(imap: IdentityMap) -> None:
    member = imap.from_member_id("ritika")
    assert member.name == "Ritika"


def test_from_login(imap: IdentityMap) -> None:
    # Pin by login, not display name — avoids the "Yash matches 3 users" problem.
    member = imap.from_login("yash.pancholi@fiftyfivetech.io")
    assert member.member_id == "yash"


def test_all_members(imap: IdentityMap) -> None:
    members = imap.all_members()
    assert len(members) == 3
    ids = {m.member_id for m in members}
    assert ids == {"ritika", "vimal", "yash"}


def test_len(imap: IdentityMap) -> None:
    assert len(imap) == 3


# ── Unknown sender — no writes, loud log ─────────────────────────────────────

def test_unknown_teams_id_raises(imap: IdentityMap) -> None:
    """An unknown Teams sender must raise — caller must not write anything."""
    with pytest.raises(UnknownSenderError, match="not in identity map"):
        imap.from_teams("29:unknown-stranger")


def test_unknown_teams_id_logs_warning(imap: IdentityMap, caplog: pytest.LogCaptureFixture) -> None:
    """Unknown sender must emit a WARNING — loud, not silent."""
    import logging
    with caplog.at_level(logging.WARNING, logger="src.identity"):
        with pytest.raises(UnknownSenderError):
            imap.from_teams("29:some-random-id")
    assert any("UNKNOWN SENDER" in r.message for r in caplog.records)
    assert any("29:some-random-id" in r.message for r in caplog.records)


def test_unknown_odoo_id_raises(imap: IdentityMap) -> None:
    with pytest.raises(UnknownSenderError):
        imap.from_odoo("9999")


def test_unknown_member_id_raises(imap: IdentityMap) -> None:
    with pytest.raises(UnknownSenderError):
        imap.from_member_id("ghost")


def test_unknown_login_raises(imap: IdentityMap) -> None:
    with pytest.raises(UnknownSenderError):
        imap.from_login("notauser@fiftyfivetech.io")


# ── Blank teams_id is not a valid lookup key ──────────────────────────────────

def test_blank_teams_id_not_matched(imap: IdentityMap) -> None:
    """
    Yash has teams_id="" — a blank id must never be a valid lookup key.
    An empty string arriving from Teams is still unknown.
    """
    with pytest.raises(UnknownSenderError):
        imap.from_teams("")


# ── Config file load ──────────────────────────────────────────────────────────

def test_from_config_loads(tmp_path: pytest.TempPathFactory) -> None:
    """IdentityMap.from_config() parses the YAML correctly."""
    yaml_content = """
members:
  - member_id: "alice"
    name: "Alice"
    login: "alice@example.com"
    teams_id: "29:alice-id"
    odoo_id: "7"
"""
    config = tmp_path / "identity_map.yaml"
    config.write_text(yaml_content)

    imap = IdentityMap.from_config(config)
    assert len(imap) == 1
    member = imap.from_teams("29:alice-id")
    assert member.name == "Alice"
    assert member.odoo_id == "7"
