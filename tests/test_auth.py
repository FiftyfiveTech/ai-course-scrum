"""
POC-02 gate: inbound Bot Framework token check.

Tokens are signed with a throwaway RSA keypair generated here, so verification runs
offline and deterministically — no Microsoft endpoint, no network, zero spend.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from src import db as db_module
from src.auth import BOTFRAMEWORK_ISSUER, TokenError, TokenValidator
from src.clock import FakeClock
from src.identity import IdentityMap, Member
from src.server import create_app

AUDIENCE = "test-app-id"
FIXTURE = Path(__file__).parent / "fixtures" / "teams" / "message_personal.json"


# ── keys ────────────────────────────────────────────────────────────────────

def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub


PRIV, PUB = _keypair()
_OTHER_PRIV, _ = _keypair()


def _token(priv=PRIV, *, aud=AUDIENCE, iss=BOTFRAMEWORK_ISSUER, exp_delta=timedelta(hours=1)):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"iss": iss, "aud": aud, "iat": now, "exp": now + exp_delta, "serviceurl": "x"},
        priv,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


def _validator(pub=PUB) -> TokenValidator:
    return TokenValidator(audience=AUDIENCE, key_resolver=lambda _tok: pub)


# ── TokenValidator unit tests ─────────────────────────────────────────────────

def test_valid_token_accepted():
    claims = _validator().validate(f"Bearer {_token()}")
    assert claims["aud"] == AUDIENCE
    assert claims["iss"] == BOTFRAMEWORK_ISSUER


@pytest.mark.parametrize(
    "header",
    [None, "", "Bearer ", "Basic abc", "not-a-header"],
    ids=["none", "empty", "bearer-no-token", "wrong-scheme", "garbage"],
)
def test_missing_or_malformed_header_rejected(header):
    with pytest.raises(TokenError):
        _validator().validate(header)


def test_expired_token_rejected():
    with pytest.raises(TokenError):
        _validator().validate(f"Bearer {_token(exp_delta=timedelta(hours=-1))}")


def test_wrong_audience_rejected():
    with pytest.raises(TokenError):
        _validator().validate(f"Bearer {_token(aud='someone-else')}")


def test_wrong_issuer_rejected():
    with pytest.raises(TokenError):
        _validator().validate(f"Bearer {_token(iss='https://evil.example')}")


def test_bad_signature_rejected():
    # Token signed with a different key than the resolver returns.
    with pytest.raises(TokenError):
        _validator().validate(f"Bearer {_token(priv=_OTHER_PRIV)}")


# ── server integration ───────────────────────────────────────────────────────

def _client(db):
    activity = json.loads(FIXTURE.read_text(encoding="utf-8"))
    identity = IdentityMap(
        [Member("testuser", "Test User", "test.user@fiftyfivetech.io", activity["from"]["id"], "")]
    )
    clock = FakeClock(datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc))
    app = create_app(db, identity, "test-team", clock=clock, token_validator=_validator())
    return TestClient(app), activity


def test_webhook_rejects_missing_token_and_stores_nothing():
    db = db_module.connect(":memory:")
    client, activity = _client(db)
    resp = client.post("/api/messages", json=activity)  # no Authorization header
    assert resp.status_code == 401
    assert db.execute("SELECT COUNT(*) AS n FROM standup_update").fetchone()["n"] == 0


def test_webhook_rejects_invalid_token():
    db = db_module.connect(":memory:")
    client, activity = _client(db)
    resp = client.post(
        "/api/messages", json=activity, headers={"Authorization": f"Bearer {_token(priv=_OTHER_PRIV)}"}
    )
    assert resp.status_code == 401


def test_webhook_accepts_valid_token_and_stores_row():
    db = db_module.connect(":memory:")
    client, activity = _client(db)
    resp = client.post(
        "/api/messages", json=activity, headers={"Authorization": f"Bearer {_token()}"}
    )
    assert resp.status_code == 200
    assert db.execute("SELECT COUNT(*) AS n FROM standup_update").fetchone()["n"] == 1
