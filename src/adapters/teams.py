"""Teams adapter.

Step 1: receive activities on /api/messages and print them.
Step 2: get a Bot Framework token for the bot (`--token` checks it).
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


class Handler(BaseHTTPRequestHandler):
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


if __name__ == "__main__":
    if sys.argv[1:] == ["--token"]:
        body = get_token(envfile.load()[0])
        c = claims(body["access_token"])
        print(f"token ok, expires in {body['expires_in']}s")
        print(f"aud={c['aud']} tid={c['tid']} appid={c.get('appid') or c.get('azp')}")
        sys.exit(0)
    print(f"listening on http://{HOST}:{PORT}/api/messages")
    HTTPServer((HOST, PORT), Handler).serve_forever()
