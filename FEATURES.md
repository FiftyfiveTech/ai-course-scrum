# Feature Index

Quick lookup of what the system does and where it lives. Status reflects files present on this
branch: ✅ built · 🛠️ planned (Teams POC — see [`teams-dashboard-poc.md`](teams-dashboard-poc.md)).
Detailed behaviour is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Core (platform-agnostic)

| Feature | Where | Status |
|---|---|---|
| Stand-up scheduler (open/close cron, restart-safe) | `src/scheduler.py` | ✅ |
| Stand-up state machine (`open→collect→follow_up→close→report`) | `src/lifecycle.py` | ✅ |
| Update extraction (model → validated schema) | `src/extractor.py` | ✅ |
| Commitment ledger (append-only) | `src/commitment.py` | ✅ |
| Blocker ledger (`days_open`, human-close) | `src/blocker.py` | ✅ |
| Follow-up engine (rule-based, max 2/dev) | `src/follow_up.py` | ✅ |
| Report builder (from DB, idempotent) | `src/report.py` | ✅ |
| Deadline tracking / risk | `src/deadline.py` | ✅ |
| Identity map (chat user ↔ member) | `src/identity.py` | ✅ |
| Clock (real / fake for tests) | `src/clock.py` | ✅ |
| SQLite storage | `src/db.py` | ✅ |
| Demo (`make demo`) | `src/demo.py` | ✅ |
| Odoo write wrapper (allow-listed, dry-run) | `ARCHITECTURE.md` §4 | 🛠️ |

## Chat adapters

| Feature | Where | Status |
|---|---|---|
| CLI adapter (stdin/stdout, fake clock) | `src/adapters/cli.py` | ✅ |
| Teams adapter — receive + reply on @mention/DM, Bot Framework token | `src/adapters/teams.py` | ✅ (receiver) |
| Teams `ChatAdapter` protocol (`post`/`get_replies`/`post_private`) | `src/adapters/teams.py` | 🛠️ POC-03 |
| Teams spike C1/C2/C3 (channel scope) | `src/spike_teams.py` | 🛠️ scaffold; channel unverified |

## Teams delivery (POC)

See [`teams-dashboard-poc.md`](teams-dashboard-poc.md) for scope, tickets, and hours.

| Feature | Where | Status |
|---|---|---|
| FastAPI server + `POST /api/messages` webhook | `src/server.py` | 🛠️ POC-01 |
| Proactive posting (stored conversation reference) | `conversation_ref` table | 🛠️ POC-04/05 |
| Dashboard API (`today` / `members` / `history`) | `src/server.py` | 🛠️ POC-11 |
| Dashboard HTML (today + history, auto-refresh) | `src/dashboard.html` | 🛠️ POC-12 |
| Manager-only dashboard (Teams SSO + owner gate) | `src/server.py` | 🛠️ POC-13 |
| `/scrum-setup`, `/add-member` | `src/server.py` | 🛠️ POC-14/15 |
| Teams app manifest + icons + install | `manifest.json` | 🛠️ POC-16/17/18 |
| Railway deploy (messaging endpoint + SSO URI) | — | 🛠️ POC-19 |

## Odoo

| Feature | Where | Status |
|---|---|---|
| Env doctor (`make doctor`) | `src/doctor.py` | ✅ |
| Env-file loader | `src/envfile.py` | ✅ |
| Local Odoo sandbox (Docker, seeded) | `sandbox/odoo/`, `make sandbox-up` | ✅ |
| `odoo-board` MCP (our tickets) / `odoo-sandbox` MCP (product) | `.mcp.json` | ✅ |

## Gates & tests

| Gate | Where | Run |
|---|---|---|
| No-leakage (`dev ∩ heldout = ∅`) | `tests/gates/test_no_leakage.py` | `make gate` |
| Continuity | `tests/gates/test_continuity.py` | `make gate` |
| Phase-0 exit | `tests/gates/gate_phase0.py` | — |
| Scheduler restart | `tests/gates/test_scheduler_restart.py` | `make test` |

Full suite: `make test` · gates: `make gate`.

## Docs

| Doc | Purpose |
|---|---|
| [`README.md`](README.md) | Overview, layout, branch/PR workflow, Odoo roles |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Core/adapters, state machine, data model, Odoo allow-list, decisions |
| [`CLAUDE.md`](CLAUDE.md) | The contract and conventions |
| [`teams-dashboard-poc.md`](teams-dashboard-poc.md) | Teams POC scope, tickets, hours |
| `teams-dashboard-poc-plan.csv` / `teams-dashboard-plan.csv` | Ticket hours (POC 119h / fuller 133h) |
| [`docs/access.md`](docs/access.md) | Teams access go/no-go (Teams-managed bot path) |
| [`STANDUP.md`](STANDUP.md) | Daily log |
