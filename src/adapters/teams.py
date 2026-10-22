"""Teams adapter.

Step 1: receive activities on /api/messages and print them.
Step 2: get a Bot Framework token for the bot (`--token` checks it).
Step 3: reply when a channel message @mentions the bot.
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Mapping

from src import envfile

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
    body = json.dumps(build_reply(activity, text)).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


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
