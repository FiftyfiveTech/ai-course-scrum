"""
Seed the local Odoo sandbox — run by `make sandbox-up`. Safe to re-run.

Creates the `scrum-bot` user (Project / User) and an "AI Dev Learning (sandbox)" project with
the course board's stage names and a few tasks assigned to the bot. Prints the ids needed to
point a board client at it.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import xmlrpc.client
from pathlib import Path

ENV_FILE = Path(__file__).with_name("sandbox.env")
ADMIN_LOGIN = ADMIN_PASSWORD = "admin"  # Odoo's default for a fresh database
PROJECT_NAME = "AI Dev Learning (sandbox)"
STAGES = ["Plan Backlog", "inProgress", "Review", "Done"]  # the course board's columns
TASKS = [
    "[sandbox] Read the board and pick the earliest deadline",
    "[sandbox] Post a stand-up note",
    "[sandbox] Request review with real output",
]
# Fixtures for the board rules in tests/sandbox/: a card that is someone else's, a card already
# in Done, and a card on another project the board server must never reach.
TEAMMATE_LOGIN = "teammate"
TEAMMATE_TASK = "[sandbox] Teammate's task"
DONE_TASK = "[sandbox] Already done"
OTHER_PROJECT = "Other project (sandbox)"
OTHER_TASK = "[sandbox] Task on another project"
# The odoo-sandbox MCP server is pinned by id; the seed checks the ids it creates match.
MCP_JSON = Path(__file__).parents[2] / ".mcp.json"
READY_TIMEOUT_S = 180


def read_env(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def wait_for(url: str) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_S
    while True:
        try:
            urllib.request.urlopen(f"{url}/web/login", timeout=5).close()
            return
        except Exception:
            if time.monotonic() > deadline:
                sys.exit(f"Odoo did not answer at {url} within {READY_TIMEOUT_S}s — "
                         "check `docker compose -f sandbox/odoo/docker-compose.yml logs odoo`")
            time.sleep(2)


def main() -> int:
    env = read_env(ENV_FILE)
    url, db = env["ODOO_URL"], env["ODOO_DB"]
    login, password = env["ODOO_LOGIN"], env["ODOO_API_KEY"]
    wait_for(url)

    uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, ADMIN_LOGIN, ADMIN_PASSWORD, {})
    if not uid:
        sys.exit(f"admin login rejected on {url} db {db!r}")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)

    def kw(model, method, args, **kwargs):
        return models.execute_kw(db, uid, ADMIN_PASSWORD, model, method, args, kwargs)

    def ensure(model, domain, values):
        found = kw(model, "search", [domain], limit=1)
        return found[0] if found else kw(model, "create", [values])

    group = kw("ir.model.data", "search_read",
               [[["module", "=", "project"], ["name", "=", "group_project_user"]]], fields=["res_id"])
    if not group:
        sys.exit("the project app is not installed in the sandbox database")
    bot = ensure("res.users", [["login", "=", login]],
                 {"name": "Scrum Bot (sandbox)", "login": login, "groups_id": [(4, group[0]["res_id"])]})
    # Odoo refuses message_post (every board note) from a user with no email address.
    kw("res.users", "write", [[bot], {"password": password, "email": f"{login}@sandbox.invalid"}])

    project = ensure("project.project", [["name", "=", PROJECT_NAME]], {"name": PROJECT_NAME})
    stages = {}
    for seq, name in enumerate(STAGES):
        stages[name] = ensure("project.task.type", [["name", "=", name], ["project_ids", "in", [project]]],
                              {"name": name, "sequence": seq, "fold": name == "Done",
                               "project_ids": [(4, project)]})
    def task(name, project_id, stage, user):
        return ensure("project.task", [["name", "=", name], ["project_id", "=", project_id]],
                      {"name": name, "project_id": project_id, "stage_id": stage,
                       "user_ids": [(6, 0, [user])]})

    for name in TASKS:
        task(name, project, stages["Plan Backlog"], bot)
    teammate = ensure("res.users", [["login", "=", TEAMMATE_LOGIN]],
                      {"name": "Teammate (sandbox)", "login": TEAMMATE_LOGIN,
                       "email": f"{TEAMMATE_LOGIN}@sandbox.invalid", "groups_id": [(4, group[0]["res_id"])]})
    task(TEAMMATE_TASK, project, stages["Plan Backlog"], teammate)
    task(DONE_TASK, project, stages["Done"], bot)
    other = ensure("project.project", [["name", "=", OTHER_PROJECT]], {"name": OTHER_PROJECT})
    task(OTHER_TASK, other, False, bot)

    print(f"sandbox   {url} db={db}  (admin / admin in the browser)")
    print(f"bot       {login} (res.users {bot})")
    print(f"project   {PROJECT_NAME!r} id={project}  stages={stages}")

    pinned = json.loads(MCP_JSON.read_text(encoding="utf-8"))["mcpServers"]["odoo-sandbox"]["env"]
    want = {"ODOO_PROJECT_ID": str(project), "ODOO_DONE_STAGE_ID": str(stages["Done"])}
    if drift := {k: (pinned.get(k), v) for k, v in want.items() if pinned.get(k) != v}:
        sys.exit(f"{MCP_JSON.name} odoo-sandbox is pinned to the wrong ids (pinned, seeded): {drift}")
    print(f"mcp       odoo-sandbox in {MCP_JSON.name} matches (project {project}, Done stage {stages['Done']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
