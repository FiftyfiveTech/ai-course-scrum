# Teams Dashboard POC — Board Tickets

**Source:** [`teams-dashboard-poc.md`](teams-dashboard-poc.md) §8 · [`teams-dashboard-poc-plan.csv`](teams-dashboard-poc-plan.csv)
**Purpose:** Reference list of the 23 POC tickets now live on the Odoo board (project #88).
**Labels:** every ticket carries `teams-poc` plus a per-epic label; they group separately from the
existing `SCRUM-xxx` tickets.
**Repo status** reflects files present on branch `teams-dashboard-poc-docs` as of 2026-10-23.

---

## Repo progress snapshot (before sync)

None of `POC-01 … POC-23` are started. The platform-agnostic **core is built and green on the CLI
adapter** (`make demo`): lifecycle, extractor, report, commitment/blocker ledgers, follow-up,
deadline, identity, scheduler, SQLite, clock. The POC tickets wire that core to Teams.

Teams-facing groundwork that already exists (reduces, but does not close, the Epic-A tickets):

| On disk | What it gives | Leaves open |
|---|---|---|
| `src/adapters/teams.py` (receiver + `get_token`/`claims` + @mention reply) | HTTP receiver + Bot Framework token helper to port into `server.py` | POC-01/02/03 — no FastAPI app, no inbound token *validation*, no `ChatAdapter` protocol |
| `src/spike_teams.py` (scaffold, **NO-GO** — tenant approval pending) | Structure for the C1/C2/C3 channel spikes | POC-05/06 — unverified; blocked on **D1** |
| `tests/fixtures/teams/message_personal.json` | POC-01 acceptance input (replay → stored `update`) | POC-01 itself |
| `tests/fixtures/teams/installation_update_groupchat.json` | POC-04 acceptance input (group-chat install) | POC-04 itself |

Not present yet: `src/server.py`, `src/dashboard.html`, `manifest.json`, app icons, `conversation_ref`
storage, Railway deploy.

---

## Summary

| Epic | Tickets | Hours |
|---|---|---|
| A — Bot messaging backbone | POC-01 … POC-06 | 36 |
| B — Daily stand-up loop | POC-07 … POC-10 | 20 |
| C — Dashboard (manager-only) | POC-11 … POC-13 | 20 |
| D — Setup & membership | POC-14 … POC-15 | 9 |
| E — Packaging & pilot | POC-16 … POC-19 | 12 |
| F — Verification | POC-20 … POC-23 | 22 |
| **Total** | **23** | **119** |

All tickets carry label **`teams-poc`**. "Depends on" lists hard prerequisites (D1–D4 are the
external dependencies in `teams-dashboard-poc.md` §7). Acceptance criteria are measurable — a ticket
is done when its check is **printed/observed**, not when it looks right.

---

## Epic A — Bot messaging backbone

### POC-01 — FastAPI server skeleton + `/api/messages` webhook · 7h
Create `src/server.py` (FastAPI). `POST /api/messages` receives a Teams activity, returns 200. Port
the existing `src/adapters/teams.py` receiver logic in.
- **Accept:** replaying `tests/fixtures/teams/message_personal.json` produces a stored `update` row.
- **Depends on:** —
- **Label:** `teams-poc`
- **Repo status:** Not started — `src/server.py` absent; receiver logic exists in `teams.py` to port.

### POC-02 — Minimal inbound Bot Framework token check · 3h
Validate the inbound activity's auth header (issuer/audience) so only genuine Teams traffic is
processed.
- **Accept:** a request with a missing/invalid token is rejected; a valid one is accepted (logged).
- **Depends on:** POC-01
- **Label:** `teams-poc`
- **Repo status:** Not started — `get_token`/`claims` helpers exist; inbound *validation* not done.

### POC-03 — Teams adapter `ChatAdapter` protocol · 8h
Implement `post()` / `get_replies()` / `post_private()` on the Teams adapter so it is a drop-in for
the CLI adapter the core expects. Reconcile the current receiver-shaped `teams.py`.
- **Accept:** `post()` returns a real message id; `get_replies()` returns stored messages typed as
  the core expects.
- **Depends on:** POC-01
- **Label:** `teams-poc`
- **Repo status:** Not started — `teams.py` is receiver-shaped only, no protocol methods.

### POC-04 — Conversation reference capture + storage · 6h
On `installationUpdate` / first activity, capture and persist the conversation reference
(`serviceUrl` + conversation id) needed for proactive posting.
- **Accept:** reference row stored from the group-chat install fixture; survives restart.
- **Depends on:** POC-01
- **Label:** `teams-poc`
- **Repo status:** Not started — fixture present; no `conversation_ref` table/storage.

### POC-05 — Proactive scheduled posting spike (C1) · 6h
Post a message to the group on demand using the stored conversation reference.
- **Accept:** log shows `posted message_id=<id>` for a proactive (not reply) post in the pilot group.
- **Depends on:** POC-04, D1
- **Label:** `teams-poc`
- **Repo status:** Not started / blocked on D1 — `spike_teams.py` scaffold is NO-GO (tenant pending).

### POC-06 — Channel read without @mention spike (C2) · 6h
Confirm the bot receives group replies that do not @mention it.
- **Accept:** log shows `received sender_id=<id> text=<text>` for an @mention-free channel message.
- **Depends on:** D1
- **Label:** `teams-poc`
- **Repo status:** Not started / blocked on D1 — covered by `spike_teams.py` scaffold (unverified).

---

## Epic B — Daily stand-up loop

### POC-07 — Scheduler cron → lifecycle open/close · 5h
Wire a scheduler to call `lifecycle.open()` / `close()` at the configured time (one timezone,
working days).
- **Accept:** at the set time the lifecycle transitions and the prompt is posted; logged.
- **Depends on:** POC-03, POC-05
- **Label:** `teams-poc`
- **Repo status:** Not started — core `scheduler.py`/`lifecycle.py` exist (CLI-wired only).

### POC-08 — Wire `StandUpLifecycle` to the Teams adapter · 7h
Replace the CLI adapter in the live path with the Teams adapter so updates flow from the webhook into
`_store_update()`.
- **Accept:** a channel reply appears as an `update` row with correct `member_id` and dedup key.
- **Depends on:** POC-03, POC-06
- **Label:** `teams-poc`
- **Repo status:** Not started.

### POC-09 — Stand-up prompt message on open · 3h
Post the daily prompt text when the stand-up opens.
- **Accept:** opening a stand-up posts the prompt in the group; message id recorded.
- **Depends on:** POC-07
- **Label:** `teams-poc`
- **Repo status:** Not started.

### POC-10 — Report card posted on close · 5h
Build the per-member done/next/blockers summary from the DB and post it as a card when the window
closes.
- **Accept:** closing a stand-up posts a report card matching the DB contents; idempotent.
- **Depends on:** POC-08
- **Label:** `teams-poc`
- **Repo status:** Not started — core `report.py` exists (DB → report, idempotent).

---

## Epic C — Dashboard (read-only, manager-only)

### POC-11 — Dashboard API routes · 6h
`GET /api/standup/today` (state + who submitted), `GET /api/members`, `GET /api/history?limit=7`.
- **Accept:** all three return valid JSON verified with curl.
- **Depends on:** POC-08
- **Label:** `teams-poc`
- **Repo status:** Not started.

### POC-12 — Dashboard HTML (today + history, auto-refresh) · 7h
`src/dashboard.html`: today panel (submitted / pending) + history table; 30-second auto-refresh;
`GET /dashboard` serves it.
- **Accept:** opened in a browser against the server, shows today + past logs and refreshes.
- **Depends on:** POC-11
- **Label:** `teams-poc`
- **Repo status:** Not started — `src/dashboard.html` absent.

### POC-13 — Manager-only SSO gate · 7h
Teams SSO on the tab (`getAuthToken`) + server-side validation + manager allow-list check against the
`team` owner id on `/dashboard` and all `/api/*` routes. Expose-an-API config on the Entra app;
`webApplicationInfo` in the manifest.
- **Accept:** the manager sees the dashboard; a non-manager gets "not authorized" (server-enforced).
- **Depends on:** POC-12, POC-16, D2, D3
- **Label:** `teams-poc`
- **Repo status:** Not started / needs D2 (SSO consent) + D3 (Railway domain).

---

## Epic D — Setup & membership

### POC-14 — `/scrum-setup` → `team` table · 5h
Slash command posts a config card; on submit writes project name, stand-up time, timezone, and
**owner (manager) id** to the `team` table.
- **Accept:** running `/scrum-setup` persists a `team` row including the owner id.
- **Depends on:** POC-01
- **Label:** `teams-poc`
- **Repo status:** Not started.

### POC-15 — `/add-member @user` · 4h
Adds a member to the project's team in the DB.
- **Accept:** `/add-member` inserts the member; appears in `GET /api/members`.
- **Depends on:** POC-14
- **Label:** `teams-poc`
- **Repo status:** Not started.

---

## Epic E — Packaging & pilot

### POC-16 — Teams app manifest (bot + staticTab) · 4h
`manifest.json` declaring the bot and the dashboard static tab; includes `webApplicationInfo` for SSO
(POC-13).
- **Accept:** manifest validates in the Developer Portal.
- **Depends on:** —
- **Label:** `teams-poc`
- **Repo status:** Not started — `manifest.json` absent.

### POC-17 — App icons (colour + outline) · 2h
192×192 colour and 32×32 outline icons.
- **Accept:** icons present and valid in the package.
- **Depends on:** —
- **Label:** `teams-poc`
- **Repo status:** Not started — no icon assets.

### POC-18 — Package + install in Teams · 3h
Zip the app and install it in the pilot group.
- **Accept:** dashboard tab pinned in the group; bot present.
- **Depends on:** POC-16, POC-17
- **Label:** `teams-poc`
- **Repo status:** Not started.

### POC-19 — Deploy to Railway + set messaging endpoint · 3h
Deploy the FastAPI server + SQLite to Railway; set the bot messaging endpoint and the SSO Application
ID URI to the Railway domain.
- **Accept:** Teams reaches `/api/messages`; SSO URI resolves; both survive a redeploy.
- **Depends on:** POC-01, D3
- **Label:** `teams-poc`
- **Repo status:** Not started — no Railway project yet (D3).

---

## Epic F — Verification

### POC-20 — Fixture-driven end-to-end integration test · 6h
Automated test driving open → collect → close → report against captured fixtures.
- **Accept:** test passes in CI; stored rows match expected.
- **Depends on:** POC-10
- **Label:** `teams-poc`
- **Repo status:** Not started.

### POC-21 — Gate checks (no-leakage + continuity) · 3h
Keep the existing gates green with the new server/adapter in place.
- **Accept:** `make gate` → both gates pass.
- **Depends on:** POC-20
- **Label:** `teams-poc`
- **Repo status:** Not started — gates currently green pre-server (`tests/gates/`).

### POC-22 — End-to-end POC dry run · 5h
One full real stand-up in the pilot group: prompt → replies → report → dashboard updates.
- **Accept:** one complete cycle observed; manager sees it on the gated dashboard.
- **Depends on:** POC-13, POC-18, POC-19
- **Label:** `teams-poc`
- **Repo status:** Not started.

### POC-23 — Bug-fix + hardening buffer · 8h
Reserved for integration issues surfaced by POC-20/POC-22.
- **Accept:** known POC issues closed.
- **Depends on:** POC-22
- **Label:** `teams-poc`
- **Repo status:** Not started (buffer).

---

## On the board — project #88

The 23 tickets are **live on Odoo project #88 `SCRUM — AI Scrum Master`**, each carrying the
`teams-poc` label plus a per-epic label (`bot-messaging`, `standup-loop`, `dashboard`, `setup`,
`packaging`, `verification`), all in the **Backlog** stage. (The `odoo-board` MCP is read/worker-only
and pinned to another project, so #88 is managed directly — see below.)

Manage them from here with the repo-owned helper, which is hard-pinned to #88 and refuses any other
project:

```
python scripts/board88.py list [--stage backlog] [--tag teams-poc]
python scripts/board88.py move  <id> "in progress" --note "..."
python scripts/board88.py note  <id> "progress / measured output"
python scripts/board88.py tag|untag <id> <label ...>
python scripts/board88.py create "Title" --tags teams-poc,<epic> --stage backlog
```

Stages: **Backlog · In Progress · Blocked · Review (gate) · Done ✅**. A `UserPromptSubmit` hook
(`scripts/board_reminder.py`, in local settings) nudges to keep #88 in sync as work proceeds.
