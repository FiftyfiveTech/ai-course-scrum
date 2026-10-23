"""Teams adapter.

Two shapes live here, sharing one HTTP send path:

* **Receiver** (local dev): `--token` prints a Bot Framework token; running the module starts a
  tiny HTTP server that prints inbound activities and replies on @mention. The production webhook
  is `src/server.py` (FastAPI /api/messages); this receiver is kept for quick local pokes.
* **`TeamsAdapter`**: the `ChatAdapter` the core expects (`post` / `get_replies` / `post_private`),
  a drop-in for `ScriptedCLIAdapter`. Outbound posts go to the Bot Framework REST API; replies are
  read back from the `standup_update` table the webhook writes to.

Proactive posting needs a conversation reference (serviceUrl + conversation id). POC-03 takes it as
an injected `ConversationRef`; capturing/persisting it on install is POC-04.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Mapping

from src import db as db_module
from src import envfile
from src.adapters import Message

HOST, PORT = "127.0.0.1", 3978
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
SCOPE = "https://api.botframework.com/.default"


def get_token(env: Mapping[str, str]) -> dict[str, Any]:
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": env["MICROSOFT_APP_ID"],
        "client_secret": env["MICROSOFT_APP_PASSWORD"],
        "scope": SCOPE,
    }).encode()
    url = TOKEN_URL.format(tenant=urllib.parse.quote(env["MICROSOFT_APP_TENANT_ID"]))
    with urllib.request.urlopen(urllib.request.Request(url, data=form), timeout=10) as resp:
        return json.load(resp)


def claims(jwt: str) -> dict[str, Any]:
    """A JWT's payload, NOT verified. For looking at, never for trusting."""
    payload = jwt.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _post_json(url: str, token: str, body: Mapping[str, Any]) -> dict[str, Any]:
    """POST a JSON body with a bearer token; return the parsed JSON response ({} if empty).

    The one HTTP send seam. `TeamsAdapter` lets tests swap it out; `send_reply` calls it directly.
    """
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


MENTION_REPLY_TEXT = "This stand-up bot is still in development."


def is_mentioned(activity: Mapping[str, Any]) -> bool:
    """True if the bot is addressed: a `mention` entity names it (channel/group @tag), or the
    chat is personal scope, where every message is already to the bot and there is no @mention."""
    if activity.get("conversation", {}).get("conversationType") == "personal":
        return True
    bot_id = activity.get("recipient", {}).get("id")
    return any(
        entity.get("type") == "mention" and entity.get("mentioned", {}).get("id") == bot_id
        for entity in activity.get("entities", [])
    )


def build_reply(activity: Mapping[str, Any], text: str) -> dict[str, Any]:
    return {
        "type": "message",
        "from": activity["recipient"],
        "recipient": activity["from"],
        "conversation": activity["conversation"],
        "text": text,
    }


def send_reply(activity: Mapping[str, Any], text: str, env: Mapping[str, str]) -> None:
    token = get_token(env)["access_token"]
    service_url = activity["serviceUrl"].rstrip("/")
    conversation_id = urllib.parse.quote(activity["conversation"]["id"], safe="")
    activity_id = urllib.parse.quote(activity["id"], safe="")
    url = f"{service_url}/v3/conversations/{conversation_id}/activities/{activity_id}"
    _post_json(url, token, build_reply(activity, text))


# ── ChatAdapter implementation ──────────────────────────────────────────────

@dataclass
class ConversationRef:
    """Where the bot posts proactively: the Bot Framework service URL + a conversation id.

    POC-03 injects this; POC-04 will capture it on install and persist it (conversation_ref table).
    """

    service_url: str
    conversation_id: str


# transport(url, token, body) -> parsed JSON response. Defaults to the real HTTP send.
Transport = Callable[[str, str, Mapping[str, Any]], dict[str, Any]]


class TeamsAdapter:
    """`ChatAdapter` for Teams — a drop-in for `ScriptedCLIAdapter`.

    * `post` / `post_private` call the Bot Framework REST API and return the real message id.
    * `get_replies` reads the `standup_update` rows the webhook (`src/server.py`) stores.

    Everything the methods touch is injectable so the whole thing runs offline in tests:
    `db` (sqlite connection), `env` (creds), `conversation` (the ref to post to),
    `token_provider` (access-token source), and `transport` (the HTTP seam).
    """

    def __init__(
        self,
        *,
        db: Any = None,
        env: Mapping[str, str] | None = None,
        conversation: ConversationRef | None = None,
        token_provider: Callable[[], str] | None = None,
        transport: Transport | None = None,
        clock: Any = None,
    ) -> None:
        self._db = db
        self._env = env
        self._conversation = conversation
        self._transport: Transport = transport or _post_json
        self._token_provider = token_provider or (lambda: get_token(self._get_env())["access_token"])
        self._clock = clock

    # ── lazy dependencies ────────────────────────────────────────────────────

    def _get_env(self) -> Mapping[str, str]:
        if self._env is None:
            self._env = envfile.load()[0]
        return self._env

    def _conn(self) -> Any:
        if self._db is None:
            self._db = db_module.connect(os.environ.get("DB_PATH", "scrum.db"))
        return self._db

    def _require_conversation(self) -> ConversationRef:
        if self._conversation is None:
            raise RuntimeError(
                "TeamsAdapter has no conversation reference (serviceUrl + conversation_id); "
                "it is captured on install in POC-04."
            )
        return self._conversation

    def _activities_url(self, service_url: str, conversation_id: str) -> str:
        base = service_url.rstrip("/")
        return f"{base}/v3/conversations/{urllib.parse.quote(conversation_id, safe='')}/activities"

    # ── ChatAdapter protocol ─────────────────────────────────────────────────

    def post(self, text: str) -> str:
        """Broadcast to the team conversation. Returns the real Bot Framework message id."""
        conv = self._require_conversation()
        url = self._activities_url(conv.service_url, conv.conversation_id)
        resp = self._transport(url, self._token_provider(), {"type": "message", "text": text})
        return resp["id"]

    def post_private(self, user_id: str, text: str) -> str:
        """DM one member: create a 1:1 conversation, then post into it. Returns the message id."""
        conv = self._require_conversation()  # service_url is the per-tenant Bot Framework endpoint
        env = self._get_env()
        token = self._token_provider()
        base = conv.service_url.rstrip("/")

        created = self._transport(
            f"{base}/v3/conversations",
            token,
            {
                "bot": {"id": f"28:{env['MICROSOFT_APP_ID']}"},
                "members": [{"id": user_id}],
                "isGroup": False,
                "tenantId": env.get("MICROSOFT_APP_TENANT_ID", ""),
            },
        )
        resp = self._transport(
            self._activities_url(conv.service_url, created["id"]),
            token,
            {"type": "message", "text": text},
        )
        return resp["id"]

    def get_replies(self, since: datetime) -> list[Message]:
        """Stored inbound updates (the webhook writes them to `standup_update`) at/after `since`."""
        rows = self._conn().execute(
            "SELECT chat_message_id, member_id, raw_text, created_at "
            "FROM standup_update ORDER BY created_at"
        ).fetchall()
        out: list[Message] = []
        for r in rows:
            timestamp = datetime.fromisoformat(r["created_at"])
            if timestamp >= since:
                out.append(Message(
                    id=r["chat_message_id"],
                    member_id=r["member_id"],
                    text=r["raw_text"],
                    timestamp=timestamp,
                ))
        return out


# ── Local dev receiver (superseded in production by src/server.py) ───────────

class Handler(BaseHTTPRequestHandler):
    env: Mapping[str, str] = {}

    def do_POST(self) -> None:
        if self.path != "/api/messages":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        activity = json.loads(self.rfile.read(length))
        print(json.dumps(activity, indent=2))
        self.send_response(200)
        self.end_headers()
        if activity.get("type") == "message" and is_mentioned(activity):
            send_reply(activity, MENTION_REPLY_TEXT, self.env)


if __name__ == "__main__":
    if sys.argv[1:] == ["--token"]:
        body = get_token(envfile.load()[0])
        c = claims(body["access_token"])
        print(f"token ok, expires in {body['expires_in']}s")
        print(f"aud={c['aud']} tid={c['tid']} appid={c.get('appid') or c.get('azp')}")
        sys.exit(0)
    Handler.env = envfile.load()[0]
    print(f"listening on http://{HOST}:{PORT}/api/messages")
    HTTPServer((HOST, PORT), Handler).serve_forever()
