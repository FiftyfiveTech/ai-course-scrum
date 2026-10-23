# AI Scrum Master — Architecture

**Status:** draft — pending sign-off by Ritika, Vimal, Yash, Saurabh
**Date:** 2026-10-21
**Task:** SCRUM-005
**Rule:** No code is written before this document is signed off by all four.

---

## Sign-off

| Person | Role | Signed |
|---|---|---|
| Ritika | Builder / Evaluator | ☐ |
| Vimal | Builder | ☐ |
| Yash | Supervisor | ☐ |
| Saurabh | Supervisor | ☐ |

---

## 1. Core vs Adapters

The system is split into a **platform-agnostic core** and **swappable adapters**. The core never
imports from an adapter. Adapters depend on the core, not on each other.

```
┌─────────────────────────────────────────────────────┐
│                      CORE                           │
│                                                     │
│  Scheduler → StandUpLifecycle → Extractor           │
│       ↓             ↓               ↓               │
│  CommitmentLedger  BlockerLedger  FollowUpEngine    │
│       ↓             ↓               ↓               │
│            ReportBuilder                            │
│                   ↓                                 │
│             OdooWriter (allow-listed)               │
└────────────┬────────────────────────┬───────────────┘
             │                        │
    ┌────────▼────────┐    ┌──────────▼──────────┐
    │   Chat Adapter  │    │    Odoo Adapter      │
    │                 │    │                      │
    │  - CLI (test)   │    │  XML-RPC client      │
    │  - Teams (live) │    │  ODOO_URL: sandbox   │
    └─────────────────┘    └──────────────────────┘
```

### 1.1 Core responsibilities

| Module | Responsibility |
|---|---|
| `Scheduler` | Triggers stand-up open/close on a cron; Mon–Fri, one timezone, skips holidays |
| `StandUpLifecycle` | Owns the state machine; enforces `(team, date)` uniqueness |
| `Extractor` | Calls the model to parse a raw update into the JSON schema; stores model id + prompt version |
| `CommitmentLedger` | Append-only history of commitments; state transitions are code-only |
| `BlockerLedger` | Tracks open blockers; computes `days_open`; closes only on human confirmation |
| `FollowUpEngine` | Rule-based trigger selection (max 2/dev/stand-up); model only phrases the question |
| `ReportBuilder` | Builds the daily report from the database; publish is idempotent |
| `OdooWriter` | Allow-listed write wrapper; dry-run by default; logs every write |

### 1.2 Chat adapter contract

Each chat adapter must implement:

```python
class ChatAdapter(Protocol):
    def post(self, text: str) -> str:          # returns message id
    def get_replies(self, since: datetime) -> list[Message]:
    def post_private(self, user_id: str, text: str) -> str:
```

Adapters: **CLI** (stdin/stdout, fake clock — built first) and **Teams** (proactive messages,
one thread per stand-up). The Teams adapter runs on the Teams-managed bot path (1:1 messaging
proven; channel scope pending RSC consent) and is fronted by the FastAPI server described in §1.4.

### 1.3 Odoo adapter

Thin XML-RPC wrapper over `execute_kw`. All business logic stays in the core.
The adapter exposes typed read methods and a single `write(call: AllowedCall)` entry point.

**Target.** The adapter connects to whatever the `ODOO_*` settings name (`ODOO_URL`, `ODOO_DB`,
`ODOO_LOGIN`, `ODOO_API_KEY`). In development that is the local **sandbox**: Odoo in Docker on
`127.0.0.1:8069`, seeded with the `scrum-bot` user and a project shaped like the pilot boards
(`sandbox/odoo/`, `make sandbox-up`; settings in `sandbox/odoo/sandbox.env`). Tests and demos of
Odoo features run there, and `make test-sandbox` checks them. Pointing the adapter at the live
tenant (`odoo.fiftyfivetech.io`) is a configuration change for the pilot, not something done
during development.

The adapter never targets the **course board** (the AI Dev Learning project), even though it
lives on the same tenant. That board tracks our own tickets through the `odoo-board` MCP server
and is not part of the product. See the README, "Odoo: two roles, two instances".

### 1.4 Teams delivery: server, dashboard, hosting

The Teams adapter is fronted by a **FastAPI server** (`src/server.py`) — one process serving both
the bot and the dashboard over the same SQLite DB:

- `POST /api/messages` — Bot Framework webhook; inbound activities flow to `StandUpLifecycle`.
- `GET /dashboard` + `GET /api/*` — the read-only dashboard tab and its JSON routes.

**One Teams app, two capabilities.** A single `manifest.json` declares the **bot** and a **static
tab** (the dashboard). Both are the same install, backed by the same server and DB.

**Proactive posting.** To open a stand-up on a schedule, the bot posts proactively using a stored
**conversation reference** (`service_url` + `conversation_id`), captured on install (see the
`conversation_ref` table in §3.2). The bot messaging endpoint is HTTP-triggered by Teams; the
scheduler (§2.2) drives the proactive open.

**Manager-only dashboard.** The dashboard is read-only and restricted to the project owner via
**Teams SSO (Entra ID)**: the tab obtains an SSO token (`getAuthToken`), the server validates it
and checks the viewer against the team's `owner_id` (§3.2). Non-owners are refused on `/dashboard`
and every `/api/*` route — enforcement is server-side, not UI-hiding. SSO rides on the existing
Entra app registration, **not** Azure Bot Service.

**Hosting.** The pilot deploys to **Railway** (native Python/FastAPI, stable HTTPS domain,
always-on), replacing the earlier ngrok / Azure App Service options. The bot messaging endpoint and
the SSO Application ID URI both point at the Railway domain.

**Out of POC scope:** dashboard control actions (open/pause/post-report), Adaptive Card forms, and
the `/report` `/blockers` `/commitments` slash suite. See `teams-dashboard-poc.md`.

---

## 2. Stand-up State Machine

One stand-up per `(team, date)`. The state is stored in the database and the only source of
truth. The scheduler and the chat adapter drive transitions; they never skip a state.

```
         ┌──────────┐
    cron │          │
    ──── ►   OPEN   │  bot posts the stand-up prompt
         │          │
         └────┬─────┘
              │ updates received (or timeout)
         ┌────▼─────┐
         │ COLLECT  │  raw updates stored; extraction runs per message
         │          │
         └────┬─────┘
              │ collection window closes
         ┌────▼──────────┐
         │  FOLLOW_UP    │  rule-triggered questions posted (max 2/dev)
         │               │  unanswered questions stored
         └────┬──────────┘
              │ follow-up window closes
         ┌────▼─────┐
         │  CLOSED  │  no more updates accepted
         │          │
         └────┬─────┘
              │
         ┌────▼─────┐
         │  REPORT  │  report built from DB; Odoo notes written; published idempotently
         │          │
         └──────────┘
```

### 2.1 Transition rules

| From | To | Trigger | Guard |
|---|---|---|---|
| — | `OPEN` | Scheduler cron | No open stand-up for `(team, date)` |
| `OPEN` | `COLLECT` | First update received | — |
| `OPEN` | `CLOSED` | Deadline passed, no updates | — |
| `COLLECT` | `FOLLOW_UP` | Collection window ends | — |
| `FOLLOW_UP` | `CLOSED` | Follow-up window ends | — |
| `CLOSED` | `REPORT` | Immediate, synchronous | — |

### 2.2 Scheduler rules

- Mon–Fri only; skips dates in `config/holidays.yaml`
- One stand-up per `(team, date)` — enforced by a unique DB key
- One reminder per stand-up at a configurable offset before close
- No retroactive stand-ups

---

## 3. Data Model

SQLite for the pilot. Every table has `created_at` and `updated_at`. Foreign keys are on.

### 3.1 Entity diagram

```
Team ──< StandUp ──< Update ──< FollowUpQuestion
                │
                ├──< CommitmentHistory
                ├──< BlockerLedger
                └──< OdooWriteLog
```

### 3.2 Tables

#### `team`
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | e.g. `course-team` |
| `name` | TEXT | Project name; set via `/scrum-setup` |
| `timezone` | TEXT | e.g. `Asia/Kolkata` |
| `standup_time` | TEXT | e.g. `09:00`; set via `/scrum-setup` |
| `owner_id` | TEXT | Manager's Teams/Entra id (`aadObjectId`); gates the manager-only dashboard |
| `odoo_project_ids` | TEXT | JSON list of pinned project ids |

#### `conversation_ref`
| Column | Type | Notes |
|---|---|---|
| `team_id` | FK → team | |
| `service_url` | TEXT | Bot Framework service URL |
| `conversation_id` | TEXT | Teams conversation id |
| `captured_at` | DATETIME | On install / first activity |
| UNIQUE | `(team_id)` | One group per team for the POC |

The bot replays this reference to post proactively (open the stand-up on schedule) — see §1.4.

#### `standup`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `team_id` | FK → team | |
| `date` | DATE | |
| `state` | TEXT | `open / collect / follow_up / closed / report` |
| `opened_at` | DATETIME | |
| `closed_at` | DATETIME | |
| `report_message_id` | TEXT | Chat message id; null until published |
| UNIQUE | `(team_id, date)` | |

#### `update`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `standup_id` | FK → standup | |
| `member_id` | TEXT | Odoo `res.users` id |
| `raw_text` | TEXT | Verbatim message |
| `chat_message_id` | TEXT | Dedup key (Teams activity id or CLI uuid) |
| `extraction` | TEXT | JSON — validated against `schemas/update.json` |
| `model_id` | TEXT | HF repo id of the model used |
| `prompt_version` | TEXT | |
| UNIQUE | `(standup_id, chat_message_id)` | Duplicate protection |

**Extraction JSON fields:** `done`, `next`, `blockers`, `task_ids`, `commitments`
Each field is tagged `reported` (dev said it) or `inferred` (model derived it).

#### `follow_up_question`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `standup_id` | FK → standup | |
| `member_id` | TEXT | |
| `trigger_rule` | TEXT | Q1–Q7 (see PRD §8.2) |
| `target_type` | TEXT | `commitment / blocker / task` |
| `target_id` | TEXT | Id of the referenced entity |
| `question_text` | TEXT | Model-phrased question |
| `asked_at` | DATETIME | |
| `answered_at` | DATETIME | Null if unanswered |
| `answer_text` | TEXT | Raw reply |

**Rules:** max 2 per member per stand-up; highest-priority trigger wins ties.

#### `commitment_history`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `standup_id` | FK → standup | Stand-up where this commitment was recorded |
| `member_id` | TEXT | |
| `task_id` | TEXT | Odoo task id; null if no ticket |
| `description` | TEXT | What was promised |
| `due_date` | DATE | Explicit date, or next stand-up date if *implied* |
| `date_type` | TEXT | `explicit / implied` |
| `state` | TEXT | `pending / met / missed / deferred` |
| `state_changed_at` | DATETIME | |
| `state_changed_by` | TEXT | `code` — model never changes state |

**Append-only:** new rows are inserted on each state change; the latest row per `(member_id,
description)` is the current state.

#### `blocker`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `standup_id` | FK → standup | Stand-up where first reported |
| `member_id` | TEXT | |
| `task_id` | TEXT | Odoo task id; null if not linked |
| `description` | TEXT | |
| `owner_id` | TEXT | Who is unblocking; null if unknown |
| `open` | BOOLEAN | True until human confirms resolved |
| `days_open` | INTEGER | Computed in queries; not stored |
| `resolved_at` | DATETIME | |

#### `odoo_write_log`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `standup_id` | FK → standup | |
| `task_id` | TEXT | Odoo task id |
| `kind` | TEXT | `task_note / daily_log / alert / new_task / deadline / stage` |
| `payload` | TEXT | JSON of what was written |
| `odoo_message_id` | TEXT | Returned by Odoo; null if dry-run |
| `dry_run` | BOOLEAN | |
| `written_at` | DATETIME | |
| UNIQUE | `(standup_id, task_id, kind)` | Idempotency key |

---

## 4. Odoo Write Allow-list

The `OdooWriter` wrapper is the only code that calls `execute_kw` for writes.
Any call not in this table raises `NotAllowedError`. Any project id not in the team's pinned
list raises `ProjectNotPinnedError`.

### 4.1 Allowed writes

| # | Write | Odoo call | Trigger | Approval |
|---|---|---|---|---|
| W1 | Per-task stand-up note | `message_post` (log note, `subtype_xmlid="mail.mt_note"`) | After report publishes | Auto |
| W2 | Daily stand-up log | `message_post` (log note) on the pinned log task | After report publishes | Auto |
| W3 | Blocker / deadline-risk alert | `message_post` (`mail.mt_comment`, pings followers) | Max 1 per task per day | Auto |
| W4 | New Backlog task from action item | `project.task.create` with tag `from-standup` | Per action item in report | Auto; deduped by title + standup_id |
| W5 | Deadline change | `project.task.write({"date_deadline": ...})` | Owner confirms in chat | Owner confirmation required |
| W6 | Stage move to Review | `project.task.write({"stage_id": ...})` | Owner confirms in chat | Owner confirmation required; never to Done |

### 4.2 Never allowed

| Action | Reason |
|---|---|
| Move task to Done | Supervisor-only gate |
| Delete any record | Irreversible |
| Reassign a task | Human decision |
| Edit task description | Could corrupt Odoo state |
| Touch non-pinned projects | Out of scope |
| Write to `mail.message` ids not posted by the bot | Overwrites system notices (VRAG-000) |

### 4.3 Safety controls

| Control | Detail |
|---|---|
| **Bot user** | `scrum-bot` Odoo user; Project: User rights only; member of pilot boards only. Never the tenant admin key. In development, the sandbox seeds a `scrum-bot` with the same rights. |
| **Code allow-list** | `OdooWriter.write(call)` checks `call.method` and `call.project_id` before every call |
| **Model never picks a write** | Model fills text fields only. Code decides whether and where to write. |
| **Dry-run switch** | `ODOO_WRITE=off\|dry\|on`. Default: `dry`. Flip to `on` only after supervisor sign-off in week 3. |
| **Idempotency** | Key `(standup_id, task_id, kind)` stored before retry. Note body carries hidden marker `standup:<id>`. |
| **Untrusted text** | Task descriptions and chatter passed to the model as quoted data only — cannot trigger writes. |
| **Audit log** | Every write logged in `odoo_write_log` with stand-up id, task id, kind, and Odoo message id. |

### 4.4 Known Odoo traps

- **HTML escaping:** `message_post` over XML-RPC escapes `<p>`. Fix: post a placeholder, then
  `mail.message.write([[msg_id], {"body": html}])` on the returned id. Unwrap with `posted[0]`.
- **System notices:** never write to all messages on a task — includes system notifications.
  Write only the id just returned by `message_post`.
- **`execute_kw` arg format:** `read`, `[id1, id2]` — not `[[id1, id2]]`.
- **`<br/>` normalisation:** Odoo normalises to `<br>`. Never patch text by matching markup.
- **`state` not `kanban_state`:** Odoo 19 removed `kanban_state`. Use `state`:
  `01_in_progress`, `02_changes_requested`, `03_approved`, `1_done`, `1_canceled`.
- **Sandbox version:** the sandbox runs `odoo:19.0`, to match the live tenant. Two 17 → 19
  differences have bitten us so far: `res.users.groups_id` is now `group_ids`, and a fresh 19
  database ships 14 stages of its own, so seeded stage ids start at 15 (the sandbox's Done is
  `18`). Never hard-code a stage id; look it up by name within the pinned project.
- **Sender email:** `message_post` fails ("please configure the sender's email address") when
  the posting user has no email. The live `scrum-bot` needs one, like the sandbox's.

---

## 5. Key decisions (record here, not in chat)

| Decision | Choice | Rationale |
|---|---|---|
| DB | SQLite | Enough for a 5–30 dev pilot; easy to inspect |
| Chat adapter (phase 0) | CLI with fake clock | Proves continuity before Teams unblocked |
| Chat adapter (phase 1) | Teams channel, one thread per stand-up | Keeps replies linked |
| Ticket system | Odoo only | Already integrated; no second system |
| Odoo comment type default | Log note (no pings) | Reduce noise |
| Model | Groq free tier, `meta-llama/Llama-3.3-70B-Instruct` | HF id, zero spend |
| Report writer | Template from DB | Model writes at most a one-line summary |
| Pilot team | Course team (Ritika, Vimal, Yash, Saurabh) | Small, real, safe |
| Teams bot hosting | Teams-managed bot, not Azure Bot Service | Zero spend; Entra app registration only, no Azure subscription |
| Deployment (pilot) | Railway | Native Python/FastAPI, stable HTTPS, always-on; replaces ngrok / Azure App Service |
| Dashboard | Read-only, manager-only via Teams SSO | One tab for the manager; owner gate on the Entra app, not Azure Bot |
| Teams app packaging | One app: bot + static tab | Single install, shared FastAPI server + DB |

---

## 6. Open questions (fill in during the 60-min session)

- [ ] What are the exact collection and follow-up window durations?
- [ ] What holidays go in `config/holidays.yaml`?
- [ ] Which Odoo project id is the pinned "Daily stand-up log" task?
- [ ] What is the Teams channel id for the pilot? (Blocked on B1)
- [ ] Who owns the `scrum-bot` Odoo user request? (B3)
- [ ] Agreed field names for the extraction JSON schema?
