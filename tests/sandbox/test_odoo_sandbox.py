"""
Odoo against the local sandbox — `make test-sandbox` (needs `make sandbox-up`).

Two things are tested here, both against localhost:8069 and never the course board:
  - the doctor's Odoo check, over real XML-RPC;
  - the `odoo-sandbox` MCP server, loaded with exactly the env `.mcp.json` gives it, so the board
    rules it enforces (one project, your tasks only, no Done) are checked on the code Claude Code runs.

If the sandbox is down these tests fail; they do not skip.
"""

from __future__ import annotations

import importlib.util
import json
import os
import xmlrpc.client
from pathlib import Path

import pytest

from src import doctor

ROOT = Path(__file__).parents[2]
SANDBOX_ENV = ROOT / "sandbox" / "odoo" / "sandbox.env"
MCP_ENV = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["odoo-sandbox"]["env"]
ADMIN = "admin"


def read_env(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


ENV = read_env(SANDBOX_ENV)


def assert_sandbox(url: str, db: str) -> None:
    # A wrong env here would post notes to the course board. Refuse before any call.
    assert url.startswith(("http://127.0.0.1:", "http://localhost:")) and db == "sandbox", \
        f"not the sandbox: {url} {db}"


assert_sandbox(ENV["ODOO_URL"], ENV["ODOO_DB"])
assert_sandbox(MCP_ENV["ODOO_URL"], MCP_ENV["ODOO_DB"])


class Admin:
    """Admin view of the sandbox, to look up fixtures and check what the tools did."""

    def __init__(self):
        url, self.db = ENV["ODOO_URL"], ENV["ODOO_DB"]
        try:
            self.uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(self.db, ADMIN, ADMIN, {})
        except OSError as exc:
            pytest.fail(f"sandbox not reachable at {url} ({exc}) — run `make sandbox-up`", pytrace=False)
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def kw(self, model, method, args, **kwargs):
        return self.models.execute_kw(self.db, self.uid, ADMIN, model, method, args, kwargs)

    def task_id(self, name: str) -> int:
        found = self.kw("project.task", "search", [[["name", "=", name]]], limit=1)
        assert found, f"fixture {name!r} missing — run `make sandbox-up` to re-seed"
        return found[0]

    def stage(self, task_id: int) -> int | bool:
        stage = self.kw("project.task", "read", [[task_id]], fields=["stage_id"])[0]["stage_id"]
        return stage and stage[0]

    def last_message(self, task_id: int) -> str:
        msgs = self.kw("mail.message", "search_read",
                       [[["model", "=", "project.task"], ["res_id", "=", task_id], ["message_type", "=", "comment"]]],
                       fields=["body"], order="id desc", limit=1)
        return msgs[0]["body"] if msgs else ""


class Tools:
    """Collects the tools the board server registers, as an MCP runtime would."""

    def tool(self):
        def register(fn):
            setattr(self, fn.__name__, fn)
            return fn
        return register


@pytest.fixture(scope="module")
def admin():
    return Admin()


@pytest.fixture(scope="module")
def board(admin):
    kit = os.environ.get("AI_COURSE_KIT")
    if not kit or not (Path(kit) / "odoo_board_mcp.py").is_file():
        pytest.fail("AI_COURSE_KIT does not point at the course kit's board-mcp folder", pytrace=False)
    with pytest.MonkeyPatch.context() as mp:
        for k, v in MCP_ENV.items():
            mp.setenv(k, v)
        spec = importlib.util.spec_from_file_location("odoo_board_mcp_sandbox", Path(kit) / "odoo_board_mcp.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert_sandbox(module.URL, module.DB)
        tools = module.register(Tools())
        module.board()  # authenticate while the sandbox env is set
    tools.module = module
    return tools


# ── the doctor's Odoo check, over real XML-RPC ──────────────────────────────


def test_doctor_odoo_check_passes_and_names_the_sandbox(admin):
    r = doctor.check_odoo(ENV)
    assert r.ok, r.detail
    assert f"on {ENV['ODOO_URL']}" in r.detail


def test_doctor_odoo_check_fails_on_a_wrong_key(admin):
    r = doctor.check_odoo({**ENV, "ODOO_API_KEY": "wrong"})
    assert not r.ok and "rejected" in r.detail


def test_doctor_odoo_check_fails_on_an_unknown_database(admin):
    assert not doctor.check_odoo({**ENV, "ODOO_DB": "no-such-db"}).ok


# ── the odoo-sandbox MCP server: board rules ────────────────────────────────


def test_whoami_is_the_bot_on_the_sandbox_project(board):
    out = board.whoami()
    assert MCP_ENV["ODOO_USER"] in out and f"project {MCP_ENV['ODOO_PROJECT_ID']}" in out


def test_my_tasks_lists_only_the_bots_tasks(board):
    out = board.my_tasks()
    assert "[sandbox] Post a stand-up note" in out
    assert "Teammate's task" not in out
    assert "another project" not in out


def test_board_view_shows_the_teammates_task_but_no_other_project(board):
    out = board.board_view()
    assert "Teammate's task" in out
    assert "another project" not in out


def test_a_task_on_another_project_is_unreachable(board, admin):
    other = admin.task_id("[sandbox] Task on another project")
    assert "not on the" in board.task(other)
    with pytest.raises(ValueError, match="not on the"):
        board.note(other, "should never land")


def test_a_teammates_task_is_read_only(board, admin):
    theirs = admin.task_id("[sandbox] Teammate's task")
    assert "read-only" in board.task(theirs)
    with pytest.raises(ValueError, match="not assigned to you"):
        board.start(theirs)


def test_start_posts_a_started_note(board, admin):
    tid = admin.task_id("[sandbox] Read the board and pick the earliest deadline")
    board.start(tid)
    assert "STARTED" in admin.last_message(tid)


def test_request_review_needs_evidence_and_leaves_the_card_where_it_is(board, admin):
    tid = admin.task_id("[sandbox] Request review with real output")
    before = admin.stage(tid)
    assert board.request_review(tid, "it works").startswith("Refused")
    board.request_review(tid, "$ make test\n28 passed in 0.78s")
    assert "REVIEW REQUESTED" in admin.last_message(tid)
    assert admin.stage(tid) == before


def test_set_done_is_refused_and_moves_nothing(board, admin):
    tid = admin.task_id("[sandbox] Post a stand-up note")
    before = admin.stage(tid)
    assert board.set_done(tid).startswith("Refused")
    assert admin.stage(tid) == before != int(MCP_ENV["ODOO_DONE_STAGE_ID"])


def test_a_done_task_cannot_be_restarted(board, admin):
    tid = admin.task_id("[sandbox] Already done")
    assert "supervisor's call" in board.start(tid)
