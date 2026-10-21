"""
Env doctor — `make doctor`.

Checks every external dependency and prints one PASS/FAIL line each. Exits 1 if anything
fails. A missing variable is a FAIL, never a skip: a silently skipped check is how a broken
setup ships.

Each live check makes one free, read-only call: no model inference, no Odoo write.
Secret values are never printed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xmlrpc.client
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from src.extractor import MODEL_ID

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
TEAMS_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
TEAMS_SCOPE = "https://api.botframework.com/.default"
ODOO_WRITE_MODES = ("off", "dry", "on")
TIMEOUT_S = 10

# (method, url, headers, body) -> parsed JSON. Raises on HTTP or network error.
Http = Callable[[str, str, Mapping[str, str], bytes | None], Any]
# url -> object with .authenticate(db, login, key, {}) — the shape of ServerProxy(".../common").
OdooCommon = Callable[[str], Any]


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def _http(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> Any:
    req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.load(resp)


def _odoo_common(url: str) -> Any:
    return xmlrpc.client.ServerProxy(f"{url.rstrip('/')}/xmlrpc/2/common", allow_none=True)


def _missing(env: Mapping[str, str], names: tuple[str, ...]) -> list[str]:
    return [n for n in names if not env.get(n, "").strip()]


def _error(exc: Exception) -> str:
    # HTTPError's str() is "HTTP Error 401: Unauthorized" — no request body, so no secret.
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    return type(exc).__name__ + (f": {exc}" if str(exc) else "")


def check_groq(env: Mapping[str, str], http: Http = _http) -> Result:
    name = "Groq API key"
    if missing := _missing(env, ("GROQ_API_KEY",)):
        return Result(name, False, f"missing {', '.join(missing)}")
    try:
        body = http("GET", GROQ_MODELS_URL, {"Authorization": f"Bearer {env['GROQ_API_KEY']}"}, None)
    except Exception as exc:
        return Result(name, False, f"GET /models failed: {_error(exc)}")
    ids = {m.get("id") for m in body.get("data", [])}
    if MODEL_ID not in ids:
        return Result(name, False, f"key works but {MODEL_ID} is not offered")
    return Result(name, True, f"key accepted; {MODEL_ID} available")


def check_odoo(env: Mapping[str, str], common: OdooCommon = _odoo_common) -> Result:
    name = "Odoo credentials"
    names = ("ODOO_URL", "ODOO_DB", "ODOO_LOGIN", "ODOO_API_KEY")
    if missing := _missing(env, names):
        return Result(name, False, f"missing {', '.join(missing)}")
    try:
        uid = common(env["ODOO_URL"]).authenticate(
            env["ODOO_DB"], env["ODOO_LOGIN"], env["ODOO_API_KEY"], {}
        )
    except Exception as exc:
        return Result(name, False, f"authenticate failed: {_error(exc)}")
    if not uid:
        return Result(name, False, f"login {env['ODOO_LOGIN']!r} rejected")
    return Result(name, True, f"authenticated as {env['ODOO_LOGIN']!r} (uid {uid})")


def check_odoo_write(env: Mapping[str, str]) -> Result:
    name = "ODOO_WRITE mode"
    mode = env.get("ODOO_WRITE", "").strip()
    if not mode:
        return Result(name, False, f"missing ODOO_WRITE - set it explicitly to one of {'|'.join(ODOO_WRITE_MODES)}")
    if mode not in ODOO_WRITE_MODES:
        return Result(name, False, f"{mode!r} is not one of {'|'.join(ODOO_WRITE_MODES)}")
    if mode == "on":
        return Result(name, True, "on - LIVE writes (needs supervisor sign-off, SCRUM-029)")
    return Result(name, True, mode)


def check_teams(env: Mapping[str, str], http: Http = _http) -> Result:
    name = "Teams bot credentials"
    names = ("MICROSOFT_APP_ID", "MICROSOFT_APP_PASSWORD", "MICROSOFT_APP_TENANT_ID")
    if missing := _missing(env, names):
        return Result(name, False, f"missing {', '.join(missing)}")
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": env["MICROSOFT_APP_ID"],
        "client_secret": env["MICROSOFT_APP_PASSWORD"],
        "scope": TEAMS_SCOPE,
    }).encode()
    url = TEAMS_TOKEN_URL.format(tenant=urllib.parse.quote(env["MICROSOFT_APP_TENANT_ID"]))
    try:
        body = http("POST", url, {"Content-Type": "application/x-www-form-urlencoded"}, form)
    except Exception as exc:
        return Result(name, False, f"token request failed: {_error(exc)}")
    if not body.get("access_token"):
        return Result(name, False, "token endpoint returned no access_token")
    return Result(name, True, "bot token issued")


def run(env: Mapping[str, str], http: Http = _http, common: OdooCommon = _odoo_common) -> list[Result]:
    return [
        check_groq(env, http),
        check_odoo(env, common),
        check_odoo_write(env),
        check_teams(env, http),
    ]


def main(
    env: Mapping[str, str] = os.environ,
    http: Http = _http,
    common: OdooCommon = _odoo_common,
) -> int:
    results = run(env, http, common)
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name:<22} {r.detail}")
    failed = sum(not r.ok for r in results)
    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
