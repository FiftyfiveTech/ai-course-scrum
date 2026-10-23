#!/usr/bin/env python
"""board88 — write/read helper for Odoo project #88 "SCRUM — AI Scrum Master".

The course `odoo-board` MCP is comment-only, pinned to project 60, and not runnable
on Windows (python3). This helper is what we use to keep board #88 in sync as work
proceeds: list / show / note / tag / untag / move-stage / create.

Hard-pinned to PROJECT_ID = 88. Every write first verifies the task lives in #88 and
refuses otherwise, so this tool can never touch another project. Uses the same
full-access Odoo API key the MCP reads (~/.config/ai-course-board.env).

Usage:
  python scripts/board88.py stages
  python scripts/board88.py list [--stage NAME] [--tag NAME]
  python scripts/board88.py show  <id>
  python scripts/board88.py note  <id> "progress text"
  python scripts/board88.py tag   <id> <label> [<label> ...]
  python scripts/board88.py untag <id> <label> [<label> ...]
  python scripts/board88.py move  <id> <stage>            # stage by name/prefix, e.g. "progress", "done"
  python scripts/board88.py create "Title" [--desc T] [--stage NAME] [--tags a,b] [--state "In Progress"]

Stage matching is case-insensitive and matches on prefix/substring, so "done" -> "Done ✅".
"""
from __future__ import annotations

import argparse
import os
import sys
import xmlrpc.client
from pathlib import Path

try:  # emoji-safe output on the Windows console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROJECT_ID = 88
ENV_FILES = [Path.home() / ".config/ai-course-board.env", Path.home() / ".config/secrets.env"]


def _connect():
    for env in ENV_FILES:
        if env.is_file():
            for line in env.read_text().splitlines():
                line = line.strip().removeprefix("export ").strip()
                if line.startswith("ODOO_") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    url = os.environ.get("ODOO_URL", "https://odoo.fiftyfivetech.io")
    db = os.environ.get("ODOO_DB", "odoo-db")
    user, key = os.environ.get("ODOO_USER"), os.environ.get("ODOO_KEY")
    if not (user and key):
        sys.exit(f"ODOO_USER / ODOO_KEY missing — add them to {ENV_FILES[0]}")
    uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, user, key, {})
    if not uid:
        sys.exit("auth failed — wrong ODOO_USER or expired/revoked ODOO_KEY")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def ex(model, method, *args, **kw):
        return models.execute_kw(db, uid, key, model, method, list(args), kw)

    return ex, uid


EX, UID = None, None  # set in main()


# ---- helpers ---------------------------------------------------------------
def stages():
    rows = EX("project.task.type", "search_read", [["project_ids", "in", [PROJECT_ID]]],
              fields=["id", "name", "sequence"], order="sequence,id")
    return rows


def resolve_stage(name):
    rows = stages()
    n = name.strip().lower()
    exact = [s for s in rows if s["name"].lower() == n]
    if exact:
        return exact[0]
    hits = [s for s in rows if n in s["name"].lower()]
    if len(hits) == 1:
        return hits[0]
    opts = ", ".join(repr(s["name"]) for s in rows)
    if not hits:
        sys.exit(f"no stage matches {name!r} in project #{PROJECT_ID}. Stages: {opts}")
    sys.exit(f"{name!r} is ambiguous ({', '.join(repr(s['name']) for s in hits)}). Stages: {opts}")


def tag_names(ids):
    if not ids:
        return {}
    rows = EX("project.tags", "search_read", [["id", "in", list(ids)]], fields=["id", "name"])
    return {r["id"]: r["name"] for r in rows}


def ensure_tags(names):
    """Return ids for tag names, reusing existing (exact match), creating the rest."""
    found = {t["name"]: t["id"] for t in
             EX("project.tags", "search_read", [["name", "in", names]], fields=["id", "name"])}
    out = []
    for name in names:
        if name in found:
            out.append(found[name])
        else:
            created = EX("project.tags", "create", {"name": name})
            out.append(created[0] if isinstance(created, list) else created)
            print(f"  created tag {name!r}")
    return out


def require_task(task_id):
    """Fetch a task and REFUSE if it is not in project #88."""
    rows = EX("project.task", "search_read", [["id", "=", int(task_id)]],
              fields=["id", "name", "project_id", "stage_id", "tag_ids"])
    if not rows:
        sys.exit(f"task {task_id} not found.")
    t = rows[0]
    if not t["project_id"] or t["project_id"][0] != PROJECT_ID:
        where = t["project_id"][1] if t["project_id"] else "(none)"
        sys.exit(f"REFUSED: task {task_id} is in {where}, not project #{PROJECT_ID}. "
                 "board88 only writes to #88.")
    return t


def fmt_task(t, names=None):
    names = names or tag_names(t.get("tag_ids", []))
    stg = t["stage_id"][1] if t.get("stage_id") else "-"
    tags = ", ".join(names.get(i, str(i)) for i in t.get("tag_ids", [])) or "-"
    return f"[{t['id']}] {t['name']}\n    stage: {stg}   tags: {tags}"


# ---- commands --------------------------------------------------------------
def cmd_stages(a):
    for s in stages():
        print(f"{s['id']:>5}  {s['name']}")


def cmd_list(a):
    domain = [["project_id", "=", PROJECT_ID]]
    if a.stage:
        domain.append(["stage_id", "=", resolve_stage(a.stage)["id"]])
    if a.tag:
        domain.append(["tag_ids.name", "=", a.tag])
    rows = EX("project.task", "search_read", domain,
              fields=["id", "name", "stage_id", "tag_ids"], order="name")
    allnames = tag_names({i for r in rows for i in r["tag_ids"]})
    for r in rows:
        print(fmt_task(r, allnames))
    print(f"--- {len(rows)} task(s) in project #{PROJECT_ID}"
          + (f", stage {a.stage!r}" if a.stage else "")
          + (f", tag {a.tag!r}" if a.tag else ""))


def cmd_show(a):
    import html
    import re
    t = require_task(a.id)
    full = EX("project.task", "search_read", [["id", "=", t["id"]]],
              fields=["id", "name", "stage_id", "tag_ids", "description", "date_deadline"])[0]
    print(fmt_task(full))
    if full.get("date_deadline"):
        print("    deadline:", full["date_deadline"])
    body = full.get("description") or ""
    body = re.sub(r"<a [^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", r"\2 -> \1", body)
    body = html.unescape(re.sub(r"<[^>]+>", "\n", body))
    body = "\n".join(ln.strip() for ln in body.splitlines() if ln.strip())
    print("\n" + (body or "(no description)"))


def cmd_note(a):
    t = require_task(a.id)
    EX("project.task", "message_post", [t["id"]],
       body=f"<p>{a.text}</p>", message_type="comment")
    print(f"noted on [{t['id']}] {t['name']}")


def cmd_tag(a):
    t = require_task(a.id)
    ids = ensure_tags(a.labels)
    EX("project.task", "write", [t["id"]], {"tag_ids": [(4, i) for i in ids]})
    after = require_task(a.id)
    print(f"[{t['id']}] tags now: " + ", ".join(tag_names(after["tag_ids"]).values()))


def cmd_untag(a):
    t = require_task(a.id)
    found = {x["name"]: x["id"] for x in
             EX("project.tags", "search_read", [["name", "in", a.labels]], fields=["id", "name"])}
    cmds = [(3, found[n]) for n in a.labels if n in found]
    if not cmds:
        sys.exit(f"none of {a.labels} are existing tags.")
    EX("project.task", "write", [t["id"]], {"tag_ids": cmds})
    after = require_task(a.id)
    print(f"[{t['id']}] tags now: " + (", ".join(tag_names(after["tag_ids"]).values()) or "(none)"))


def cmd_move(a):
    t = require_task(a.id)
    old = t["stage_id"][1] if t["stage_id"] else "-"
    s = resolve_stage(a.stage)
    EX("project.task", "write", [t["id"]], {"stage_id": s["id"]})
    if a.note:
        EX("project.task", "message_post", [t["id"]],
           body=f"<p><b>{old} → {s['name']}</b>: {a.note}</p>", message_type="comment")
    print(f"[{t['id']}] {t['name']}\n    {old} → {s['name']}")


def cmd_create(a):
    vals = {"name": a.title, "project_id": PROJECT_ID}
    if a.desc:
        vals["description"] = a.desc
    if a.stage:
        vals["stage_id"] = resolve_stage(a.stage)["id"]
    if a.state:
        vals["state"] = a.state
    if a.tags:
        vals["tag_ids"] = [(4, i) for i in ensure_tags([x.strip() for x in a.tags.split(",") if x.strip()])]
    created = EX("project.task", "create", vals)
    tid = created[0] if isinstance(created, list) else created
    print(f"created [{tid}] {a.title} in project #{PROJECT_ID}")


def build_parser():
    p = argparse.ArgumentParser(prog="board88", description="Odoo project #88 board helper.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stages", help="list the stages of #88").set_defaults(fn=cmd_stages)

    s = sub.add_parser("list", help="list tasks"); s.set_defaults(fn=cmd_list)
    s.add_argument("--stage"); s.add_argument("--tag")

    s = sub.add_parser("show", help="task detail"); s.set_defaults(fn=cmd_show)
    s.add_argument("id", type=int)

    s = sub.add_parser("note", help="post a progress comment"); s.set_defaults(fn=cmd_note)
    s.add_argument("id", type=int); s.add_argument("text")

    s = sub.add_parser("tag", help="add label(s)"); s.set_defaults(fn=cmd_tag)
    s.add_argument("id", type=int); s.add_argument("labels", nargs="+")

    s = sub.add_parser("untag", help="remove label(s)"); s.set_defaults(fn=cmd_untag)
    s.add_argument("id", type=int); s.add_argument("labels", nargs="+")

    s = sub.add_parser("move", help="move to a stage"); s.set_defaults(fn=cmd_move)
    s.add_argument("id", type=int); s.add_argument("stage"); s.add_argument("--note", default="")

    s = sub.add_parser("create", help="create a task in #88"); s.set_defaults(fn=cmd_create)
    s.add_argument("title")
    s.add_argument("--desc", default=""); s.add_argument("--stage", default="")
    s.add_argument("--tags", default=""); s.add_argument("--state", default="")
    return p


def main(argv=None):
    global EX, UID
    args = build_parser().parse_args(argv)
    EX, UID = _connect()
    args.fn(args)


if __name__ == "__main__":
    main()
