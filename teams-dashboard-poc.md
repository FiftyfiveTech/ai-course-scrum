# Teams Scrum Dashboard — POC Scope & Tickets

**Date:** 2026-10-22
**Project:** AI Dev Learning — ai-course-scrum
**Status:** For review
**Scope:** Internal company proof-of-concept (POC) — single group, manager-gated dashboard

---

## 1. Purpose

Prove, end to end and inside Microsoft Teams, that a bot can run a team's daily stand-up and give
a manager a live, historical view of who is working on what — **without Azure Bot Service and with
zero spend**. This document is the review artifact: it states what is in scope, what is explicitly
out, the dependencies, and the full ticket list with hour estimates.

---

## 2. Product description

A Microsoft Teams app with two capabilities in **one** package:

1. **A stand-up bot** that lives in one internal group/channel. Each working day it posts a prompt,
   reads everyone's plain-text reply (done / next / blockers), stores it, and posts a summary
   report back to the group.
2. **A read-only dashboard tab** that only the manager can open. It shows today's status (who has
   submitted, who is pending) and the daily-log history from previous days, auto-refreshing every
   30 seconds.

The daily loop:

```
Bot posts prompt  →  members reply in plain text  →  bot reads + stores each update
     →  bot posts a report card when the window closes  →  dashboard reflects today + history
```

No separate tool, no browser, no external URL for members. Managers get the dashboard as a pinned
tab inside Teams.

---

## 3. Feasibility — Azure Bot vs Teams-managed bot

The original PRD assumed an **Azure Bot Service** registration was mandatory. It is not. "Azure
Bot" conflates three different things:

| Thing | Needed? | Status | Cost |
|---|---|---|---|
| **Azure Bot Service** (resource in an Azure subscription) | No | Not used | — |
| **Entra ID app registration** (formerly Azure AD app) | Yes | Already have it — a working Bot Framework token is issued | Free |
| **Teams-managed bot** (register via Teams Developer Portal, no Azure sub) | Yes — this is our path | Already working in 1:1 chat | Free |

Evidence already captured (`docs/access.md`):

```
PASS  Teams bot credentials  bot token issued
```

plus a real personal-chat activity received and replied to, with `from.aadObjectId` read correctly.

**Conclusion:** the entire POC — bot messaging, proactive posts, and manager-only dashboard SSO —
runs on the Teams-managed bot path. Nothing here requires Azure Bot Service.

---

## 4. What is already built (baseline — not re-estimated here)

The POC wires existing, tested core logic to Teams. Already in place and passing on the CLI adapter:

- Stand-up lifecycle: `open → collect → follow_up → close → report` (`make demo` green)
- Update extractor, report builder, commitment ledger, blocker ledger
- SQLite data model: `team`, `standup`, `update` tables
- Teams-managed bot credentials issuing tokens; 1:1 receive + reply working
- Captured fixtures: group-chat install, personal message

The POC's job is integration — the tickets below build the Teams-facing surface around this core.

---

## 5. Architecture

### 5.1 One app, two capabilities, one backend

A Teams app is a single `manifest.json` package that can declare several capabilities at once.
This POC declares a **bot** and a **static tab** (the dashboard), both served by one FastAPI
process over one SQLite database.

```
ONE Teams app (one manifest, one install, app id = MICROSOFT_APP_ID)
├── bot         → POST /api/messages   (receives updates, posts prompts/reports)
└── staticTab   → GET  /dashboard      (manager-only read-only view)
                       │
                       ▼
          ONE FastAPI server + ONE SQLite DB   ← the shared state / control plane
```

### 5.2 How the tab relates to the bot

The dashboard is a web page; it does not call the bot directly. Both read the same database. In
this POC the dashboard is **read-only** — it displays state, it does not drive the bot. (Control
actions such as "open stand-up now" are phase 2 and are listed in §9.)

### 5.3 Hosting

- Server and SQLite deploy to **Railway** (native Python/FastAPI, stable HTTPS domain, always-on).
  Railway gives a stable `*.up.railway.app` domain, so the bot messaging endpoint and the SSO
  Application ID URI stay fixed across restarts.
- One group, internal use only.

---

## 6. Access control — manager-only dashboard

The dashboard must be visible to the manager only. A Teams tab is served by our server and is, by
default, openable by anyone who sees it, so the restriction is enforced in **two layers**:

1. **Identify the viewer** via **Teams SSO (Entra ID)** — `microsoftTeams.authentication.getAuthToken()`
   hands the server a token proving who is viewing.
2. **Authorize on the server** — validate the token and check the viewer's id against the project's
   stored **owner id** (allow-list of one, set during `/scrum-setup`, held in the `team` table).
   Non-managers get "not authorized" on `/dashboard` and every `/api/*` route.

Enforcement is server-side; hiding the tab in the UI is not security.

**This rides on the Entra app registration we already have — not on Azure Bot Service.** SSO is an
Entra feature; the same app id that runs the bot exposes the SSO scope.

**Caveats:**
- Exposing the SSO scope may need one tenant-admin consent — the same free admin path already used
  for RSC, not a new system.
- SSO's Application ID URI is tied to the hosting domain; Railway's stable domain satisfies this
  (unlike a rotating tunnel URL).

---

## 7. External dependencies & risks

| # | Dependency | Owner | Risk if it slips | Mitigation |
|---|---|---|---|---|
| D1 | RSC consent `ChannelMessage.Read.Group` (read all messages without @mention) + bot installed in the pilot group | Tenant admin (Yash) | Channel-scope collection (C2) can't be verified | Build against captured fixtures; nothing stalls |
| D2 | Tenant-admin consent for the Teams SSO scope | Tenant admin (Yash) | Manager-only gate can't be exercised | Same admin path as D1; request together |
| D3 | Railway project with a stable HTTPS domain | Dev | No reachable endpoint for the webhook / SSO | Provision Railway up front; stable domain is built in |
| D4 | Proactive posting (C1) not yet proven in a channel | Dev | Scheduled prompt may need rework | Dedicated spike ticket (POC-05) before wiring the scheduler |

The honest risk is channel scope (D1/D4), not Azure. All dependencies are free or low-cost and on
the Teams-managed path.

---

## 8. Tickets

IDs are `POC-01 … POC-23`. "Depends on" lists hard prerequisites. Acceptance criteria are
measurable — a ticket is done when its check is **printed/observed**, not when it looks right.

### Epic A — Bot messaging backbone

**POC-01 — FastAPI server skeleton + `/api/messages` webhook** · **7h**
Create `src/server.py` (FastAPI). `POST /api/messages` receives a Teams activity, returns 200.
Port the existing `src/adapters/teams.py` receiver logic in.
*Accept:* replaying `tests/fixtures/teams/message_personal.json` produces a stored `update` row.
*Depends on:* —

**POC-02 — Minimal inbound Bot Framework token check** · **3h**
Validate the inbound activity's auth header (issuer/audience) so only genuine Teams traffic is
processed.
*Accept:* a request with a missing/invalid token is rejected; a valid one is accepted (logged).
*Depends on:* POC-01

**POC-03 — Teams adapter `ChatAdapter` protocol** · **8h**
Implement `post()` / `get_replies()` / `post_private()` on the Teams adapter so it is a drop-in for
the CLI adapter the core expects. Reconcile the current receiver-shaped `teams.py`.
*Accept:* `post()` returns a real message id; `get_replies()` returns stored messages typed as the
core expects.
*Depends on:* POC-01

**POC-04 — Conversation reference capture + storage** · **6h**
On `installationUpdate` / first activity, capture and persist the conversation reference
(`serviceUrl` + conversation id) needed for proactive posting.
*Accept:* reference row stored from the group-chat install fixture; survives restart.
*Depends on:* POC-01

**POC-05 — Proactive scheduled posting spike (C1)** · **6h**
Post a message to the group on demand using the stored conversation reference.
*Accept:* log shows `posted message_id=<id>` for a proactive (not reply) post in the pilot group.
*Depends on:* POC-04, D1

**POC-06 — Channel read without @mention spike (C2)** · **6h**
Confirm the bot receives group replies that do not @mention it.
*Accept:* log shows `received sender_id=<id> text=<text>` for an @mention-free channel message.
*Depends on:* D1

### Epic B — Daily stand-up loop

**POC-07 — Scheduler cron → lifecycle open/close** · **5h**
Wire a scheduler to call `lifecycle.open()` / `close()` at the configured time (one timezone,
working days).
*Accept:* at the set time the lifecycle transitions and the prompt is posted; logged.
*Depends on:* POC-03, POC-05

**POC-08 — Wire `StandUpLifecycle` to the Teams adapter** · **7h**
Replace the CLI adapter in the live path with the Teams adapter so updates flow from the webhook
into `_store_update()`.
*Accept:* a channel reply appears as an `update` row with correct `member_id` and dedup key.
*Depends on:* POC-03, POC-06

**POC-09 — Stand-up prompt message on open** · **3h**
Post the daily prompt text when the stand-up opens.
*Accept:* opening a stand-up posts the prompt in the group; message id recorded.
*Depends on:* POC-07

**POC-10 — Report card posted on close** · **5h**
Build the per-member done/next/blockers summary from the DB and post it as a card when the window
closes.
*Accept:* closing a stand-up posts a report card matching the DB contents; idempotent.
*Depends on:* POC-08

### Epic C — Dashboard (read-only, manager-only)

**POC-11 — Dashboard API routes** · **6h**
`GET /api/standup/today` (state + who submitted), `GET /api/members`, `GET /api/history?limit=7`.
*Accept:* all three return valid JSON verified with curl.
*Depends on:* POC-08

**POC-12 — Dashboard HTML (today + history, auto-refresh)** · **7h**
`src/dashboard.html`: today panel (submitted / pending) + history table; 30-second auto-refresh;
`GET /dashboard` serves it.
*Accept:* opened in a browser against the server, shows today + past logs and refreshes.
*Depends on:* POC-11

**POC-13 — Manager-only SSO gate** · **7h**
Teams SSO on the tab (`getAuthToken`) + server-side validation + manager allow-list check against
the `team` owner id on `/dashboard` and all `/api/*` routes. Expose-an-API config on the Entra app;
`webApplicationInfo` in the manifest.
*Accept:* the manager sees the dashboard; a non-manager gets "not authorized" (server-enforced).
*Depends on:* POC-12, POC-16, D2, D3

### Epic D — Setup & membership

**POC-14 — `/scrum-setup` → `team` table** · **5h**
Slash command posts a config card; on submit writes project name, stand-up time, timezone, and
**owner (manager) id** to the `team` table.
*Accept:* running `/scrum-setup` persists a `team` row including the owner id.
*Depends on:* POC-01

**POC-15 — `/add-member @user`** · **4h**
Adds a member to the project's team in the DB.
*Accept:* `/add-member` inserts the member; appears in `GET /api/members`.
*Depends on:* POC-14

### Epic E — Packaging & pilot

**POC-16 — Teams app manifest (bot + staticTab)** · **4h**
`manifest.json` declaring the bot and the dashboard static tab; includes `webApplicationInfo` for
SSO (POC-13).
*Accept:* manifest validates in the Developer Portal.
*Depends on:* —

**POC-17 — App icons (colour + outline)** · **2h**
192×192 colour and 32×32 outline icons.
*Accept:* icons present and valid in the package.
*Depends on:* —

**POC-18 — Package + install in Teams** · **3h**
Zip the app and install it in the pilot group.
*Accept:* dashboard tab pinned in the group; bot present.
*Depends on:* POC-16, POC-17

**POC-19 — Deploy to Railway + set messaging endpoint** · **3h**
Deploy the FastAPI server + SQLite to Railway; set the bot messaging endpoint and the SSO
Application ID URI to the Railway domain.
*Accept:* Teams reaches `/api/messages`; SSO URI resolves; both survive a redeploy.
*Depends on:* POC-01, D3

### Epic F — Verification

**POC-20 — Fixture-driven end-to-end integration test** · **6h**
Automated test driving open → collect → close → report against captured fixtures.
*Accept:* test passes in CI; stored rows match expected.
*Depends on:* POC-10

**POC-21 — Gate checks (no-leakage + continuity)** · **3h**
Keep the existing gates green with the new server/adapter in place.
*Accept:* `make gate` → both gates pass.
*Depends on:* POC-20

**POC-22 — End-to-end POC dry run** · **5h**
One full real stand-up in the pilot group: prompt → replies → report → dashboard updates.
*Accept:* one complete cycle observed; manager sees it on the gated dashboard.
*Depends on:* POC-13, POC-18, POC-19

**POC-23 — Bug-fix + hardening buffer** · **8h**
Reserved for integration issues surfaced by POC-20/POC-22.
*Accept:* known POC issues closed.
*Depends on:* POC-22

---

## 9. Out of scope (phase 2)

- **Dashboard control actions** — open/pause/post-report buttons that drive the bot (the SSO gate
  here is the foundation they will reuse).
- **Adaptive Card forms** ("fill a form instead") — text replies only in the POC.
- **Commitments / blockers panels + RAG colours** on the dashboard.
- **`/report` `/blockers` `/commitments` slash commands** — dashboard covers these views.
- **Multiple teams / multiple groups** — one group only.
- **Role-based access beyond manager/not-manager.**

---

## 10. Summary — hours

| Epic | Tickets | Hours |
|---|---|---|
| A — Bot messaging backbone | POC-01 … POC-06 | 36 |
| B — Daily stand-up loop | POC-07 … POC-10 | 20 |
| C — Dashboard (manager-only) | POC-11 … POC-13 | 20 |
| D — Setup & membership | POC-14 … POC-15 | 9 |
| E — Packaging & pilot | POC-16 … POC-19 | 12 |
| F — Verification | POC-20 … POC-23 | 22 |
| **Total** | **23 tickets** | **119** |

Estimates are generous (include review, integration friction, and debugging). The heaviest buffers
sit on the unknowns: the adapter protocol (POC-03), the channel spikes (POC-05/06), the SSO gate
(POC-13), and the end-to-end buffer (POC-23).

---

## 11. Review checklist

- [ ] Scope agreed (§5, §6) — one group, read-only manager-only dashboard, text replies
- [ ] Out-of-scope list agreed (§9)
- [ ] Dependencies owned and scheduled (§7 — D1/D2 admin consent, D3 Railway)
- [ ] Ticket breakdown and hours accepted (§8, §10)
- [ ] Decision: proceed with POC-01, or adjust scope first
