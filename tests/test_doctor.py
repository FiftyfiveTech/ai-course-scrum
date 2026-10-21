"""
SCRUM-006 — env doctor and the no-silent-skip rule.

No network: every live call goes through a fake transport.
"""

from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest

from src import doctor
from src.extractor import MODEL_ID

pytest_plugins = ["pytester"]

SECRETS = {
    "GROQ_API_KEY": "gsk-secret-groq",
    "ODOO_URL": "https://odoo.example",
    "ODOO_DB": "prod",
    "ODOO_LOGIN": "scrum-bot",
    "ODOO_API_KEY": "secret-odoo-key",
    "ODOO_WRITE": "dry",
    "MICROSOFT_APP_ID": "app-id",
    "MICROSOFT_APP_PASSWORD": "secret-teams-pw",
    "MICROSOFT_APP_TENANT_ID": "tenant-1",
}


def ok_http(method, url, headers, body):
    if url == doctor.GROQ_MODELS_URL:
        return {"data": [{"id": MODEL_ID}, {"id": "other/model"}]}
    if "login.microsoftonline.com" in url:
        return {"access_token": "tok", "expires_in": 3599}
    raise AssertionError(f"unexpected call {method} {url}")


class FakeCommon:
    def __init__(self, uid):
        self.uid = uid

    def authenticate(self, db, login, key, ctx):
        return self.uid


def ok_common(url):
    return FakeCommon(7)


def failing_http(code):
    def http(method, url, headers, body):
        raise urllib.error.HTTPError(url, code, "nope", {}, None)
    return http


def verdicts(out):
    return [line.split()[0] for line in out.splitlines() if line.startswith(("PASS", "FAIL"))]


# ── main(): output and exit code ────────────────────────────────────────────


def test_all_good_prints_pass_per_dependency_and_exits_zero(capsys):
    assert doctor.main(SECRETS, ok_http, ok_common) == 0
    out = capsys.readouterr().out
    assert verdicts(out) == ["PASS"] * 4
    assert "4/4 passed" in out


def test_empty_env_fails_every_check_and_exits_nonzero(capsys):
    def no_network(*args):
        pytest.fail("a check made a network call with no credentials")

    assert doctor.main({}, no_network, no_network) == 1
    out = capsys.readouterr().out
    assert verdicts(out) == ["FAIL"] * 4
    assert "missing GROQ_API_KEY" in out
    assert "missing ODOO_URL, ODOO_DB, ODOO_LOGIN, ODOO_API_KEY" in out
    assert "0/4 passed" in out


def test_one_failure_is_enough_for_a_nonzero_exit(capsys):
    env = {**SECRETS, "ODOO_WRITE": "yes"}
    assert doctor.main(env, ok_http, ok_common) == 1
    assert "3/4 passed" in capsys.readouterr().out


# ── individual checks ───────────────────────────────────────────────────────


def test_groq_rejected_key_fails():
    r = doctor.check_groq(SECRETS, failing_http(401))
    assert not r.ok and "HTTP 401" in r.detail


def test_groq_fails_when_extraction_model_is_not_offered():
    r = doctor.check_groq(SECRETS, lambda *a: {"data": [{"id": "other/model"}]})
    assert not r.ok and MODEL_ID in r.detail


def test_odoo_rejected_login_fails():
    r = doctor.check_odoo(SECRETS, lambda url: FakeCommon(False))
    assert not r.ok and "rejected" in r.detail


def test_odoo_network_error_fails():
    def boom(url):
        raise ConnectionRefusedError("refused")
    r = doctor.check_odoo(SECRETS, boom)
    assert not r.ok and "ConnectionRefusedError" in r.detail


@pytest.mark.parametrize("mode", ["off", "dry", "on"])
def test_odoo_write_valid_modes_pass(mode):
    r = doctor.check_odoo_write({"ODOO_WRITE": mode})
    assert r.ok
    if mode == "on":
        assert "LIVE" in r.detail


@pytest.mark.parametrize("value", ["", "  ", "ON", "true", "dry  # comment"])
def test_odoo_write_unset_or_invalid_fails(value):
    assert not doctor.check_odoo_write({"ODOO_WRITE": value}).ok


def test_teams_rejected_secret_fails():
    r = doctor.check_teams(SECRETS, failing_http(401))
    assert not r.ok and "HTTP 401" in r.detail


def test_teams_response_without_token_fails():
    r = doctor.check_teams(SECRETS, lambda *a: {"error": "invalid_client"})
    assert not r.ok


def test_secrets_never_appear_in_output():
    secrets = [v for k, v in SECRETS.items() if "KEY" in k or "PASSWORD" in k]
    runs = [
        doctor.run(SECRETS, ok_http, ok_common),
        [doctor.check_groq(SECRETS, failing_http(401)), doctor.check_teams(SECRETS, failing_http(401))],
    ]
    text = " ".join(r.detail for results in runs for r in results)
    for s in secrets:
        assert s not in text


def test_real_transport_sends_its_own_user_agent(monkeypatch):
    # Groq's Cloudflare rejects urllib's default User-Agent with 403 / error 1010.
    seen = {}

    class Resp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self, *a):
            return b"{}"

    def fake_urlopen(req, timeout):
        seen.update(req.header_items())
        return Resp()

    monkeypatch.setattr(doctor.urllib.request, "urlopen", fake_urlopen)
    doctor._http("GET", doctor.GROQ_MODELS_URL, {"Authorization": "Bearer x"}, None)
    assert seen["User-agent"] == doctor.USER_AGENT


# ── a silent skip is a FAIL ─────────────────────────────────────────────────

CONFTEST = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")


def test_unmarked_skip_is_reported_as_failure(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        import os, pytest
        def test_live():
            if not os.environ.get("NOPE_NOT_SET"):
                pytest.skip("no key")
        """
    )
    result = pytester.runpytest("-rs")
    result.assert_outcomes(failed=1, skipped=0)
    result.stdout.fnmatch_lines(["*unexpected skip*no key*"])


def test_marked_skip_is_allowed(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        import pytest
        @pytest.mark.expected_skip("needs a real tenant")
        def test_live():
            pytest.skip("no tenant")
        """
    )
    pytester.runpytest().assert_outcomes(skipped=1, failed=0)


def test_xfail_is_not_touched(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        import pytest
        @pytest.mark.xfail(reason="known bug")
        def test_bug():
            assert False
        """
    )
    pytester.runpytest().assert_outcomes(xfailed=1)
