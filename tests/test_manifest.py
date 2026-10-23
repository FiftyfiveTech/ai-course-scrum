"""POC-16 — Teams app manifest build tests.

Runs build.sh with dummy values and asserts the generated manifest.json:
  - has no unsubstituted ${...} placeholders
  - has all required Teams manifest fields
  - bot, staticTab, and webApplicationInfo are wired to the same app id
  - validDomains contains the Railway domain
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
TEAMS_APP = REPO / "teams-app"
BUILD_SH = TEAMS_APP / "build.sh"
MANIFEST_OUT = TEAMS_APP / "manifest.json"

DUMMY_APP_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
DUMMY_DOMAIN = "scrum-test.up.railway.app"


@pytest.fixture(autouse=True)
def generated_manifest(tmp_path):
    """Run build.sh and yield the parsed manifest; clean up after."""
    env = {**os.environ, "MICROSOFT_APP_ID": DUMMY_APP_ID, "RAILWAY_DOMAIN": DUMMY_DOMAIN}
    result = subprocess.run(
        ["bash", str(BUILD_SH)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
    )
    assert result.returncode == 0, f"build.sh failed:\n{result.stderr}"
    yield json.loads(MANIFEST_OUT.read_text())
    # leave manifest.json in place — it is gitignored


def test_no_unsubstituted_placeholders(generated_manifest):
    raw = MANIFEST_OUT.read_text()
    assert "${" not in raw, "Unsubstituted placeholder found in manifest.json"


def test_required_top_level_fields(generated_manifest):
    m = generated_manifest
    for field in ("$schema", "manifestVersion", "version", "id", "name", "description", "icons"):
        assert field in m, f"Missing required field: {field}"


def test_app_id_is_substituted(generated_manifest):
    assert generated_manifest["id"] == DUMMY_APP_ID


def test_bot_section(generated_manifest):
    bots = generated_manifest.get("bots", [])
    assert len(bots) == 1, "Expected exactly one bot entry"
    bot = bots[0]
    assert bot["botId"] == DUMMY_APP_ID
    assert "groupChat" in bot["scopes"]
    assert "team" in bot["scopes"]


def test_static_tab(generated_manifest):
    tabs = generated_manifest.get("staticTabs", [])
    assert len(tabs) == 1, "Expected exactly one staticTab"
    tab = tabs[0]
    assert DUMMY_DOMAIN in tab["contentUrl"]
    assert DUMMY_DOMAIN in tab["websiteUrl"]


def test_web_application_info(generated_manifest):
    wai = generated_manifest.get("webApplicationInfo", {})
    assert wai.get("id") == DUMMY_APP_ID
    assert DUMMY_DOMAIN in wai.get("resource", "")
    assert DUMMY_APP_ID in wai.get("resource", "")


def test_valid_domains(generated_manifest):
    assert DUMMY_DOMAIN in generated_manifest.get("validDomains", [])


def test_icons_keys(generated_manifest):
    icons = generated_manifest.get("icons", {})
    assert "color" in icons
    assert "outline" in icons
