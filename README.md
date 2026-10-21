# AI Scrum Master

A Teams-managed bot that runs the team's daily stand-up. It opens and closes the stand-up on a
schedule, extracts each developer's update into a validated schema, tracks commitments and
blockers, asks rule-based follow-ups, builds the daily report, and writes back to Odoo through an
allow-listed, dry-run-by-default writer. The core is platform-agnostic: Microsoft Teams is the
live chat adapter, the CLI adapter (with a fake clock) drives tests and the demo. See
[`ARCHITECTURE.md`](ARCHITECTURE.md).

Built by hand, phase by phase, as the scrum track of the FiftyFive AI engineering course.

## Use it

```bash
git clone https://github.com/FiftyfiveTech/ai-course-scrum.git
cd ai-course-scrum
make setup
make demo
```

## Layout

| Path | Holds |
|---|---|
| `src/` | The system. Small modules, one job each. |
| `prompts/` | Versioned prompt files (`extract_v1.md`, `extract_v2.md`, …). Never inline a prompt in code. |
| `schemas/` | Pydantic models. Structured output is validated, not parsed by hand. |
| `evals/dev/` | **Builder** tunes here. 15 cases. |
| `evals/heldout/` | **Evaluator** only. Sealed Wednesday, tagged `heldout-v1`. The Builder never reads it. |
| `tests/gates/` | One script per phase gate. It prints the number; the number decides. |
| `STANDUP.md` | Daily log. Two minutes, append-only. |

## Deliberately missing

Two files are absent because they are Week 0 tasks, not scaffolding:

- `tests/gates/test_no_leakage.py` — asserts `evals/dev ∩ evals/heldout = ∅` by content hash
  (task **0.7**). Until it exists, the blind-labelling rule is unenforced.
- `src/telemetry.py` — the shared cost/latency logger every model call goes through (task **0.8**).

Write them. Do not import them from somewhere else.

## Held-out eval set

| File | sha256 |
|---|---|
| `evals/heldout/updates.json` | `e29b910154053a5ff0ba974dc2a4ab281bd006ff1c29626142c847646d6ba3d0` |

Sealed 2026-10-21. Tagged `heldout-v1`. The Builder never reads `evals/heldout/`.
Verify integrity: `sha256sum evals/heldout/updates.json`

## Rules that live in this repo

`CLAUDE.md` carries the full contract. The short version:

- Models and datasets are named by **Hugging Face repo id**. The provider is only where it runs.
- **Zero spend.** A paid call is a STOP-and-ask, never a judgement call.
- A phase is done when its gate **prints the number**, not when the code looks right.
- Every PR is reviewed by the other person. `main` is protected; self-merges are the one thing
  the Friday retro always checks.
- Tasks come from the course Odoo board via the `odoo-board` MCP server, not from this README.
  The bot's own Odoo work runs against the local sandbox (see [Odoo](#odoo-two-roles-two-instances)).

## Branch and PR workflow

1. **Code goes to `dev` first.** Branch from `dev`, open the PR against `dev`, and promote `dev`
   to `main` only after review. Nothing is merged straight into `main`.
2. **PRs are opened with the `pr-dev` skill** ([`.claude/skills/pr-dev`](.claude/skills/pr-dev/SKILL.md)).
   In Claude Code, run `/pr-dev`: it checks the branch, runs the tests and gate, pushes, and opens
   the PR with `dev` as the base, so no PR goes to `main` by accident.
3. **For now, the course Odoo board is empty.** Checks that depend on it — the `odoo-board` MCP
   calls, and the Odoo lines in `make doctor` — are expected to fail, and those failures are
   accepted until the board is populated. The sandbox has no such exception: `make doctor-sandbox`
   must pass. Every other test and gate must still pass.

## Odoo: two roles, two instances

Odoo appears twice in this project. Keep them apart.

| Role | Instance | Reached through | Used for |
|---|---|---|---|
| **Ticket tracking** for our own work | The course board (`odoo.fiftyfivetech.io`) | `odoo-board` MCP server | `my_tasks`, `start`, `note`, `request_review`. Only the supervisor sets Done. |
| **A requirement of the product** — the bot reads tasks and writes stand-up notes back | The local **sandbox** (Docker, `localhost:8069`) | `odoo-sandbox` MCP server; `ODOO_*` settings for the bot's own code | Building and testing the bot's Odoo features |

The bot never develops against the course board, and our tickets never live in the sandbox.

### The sandbox

```bash
make sandbox-up        # Odoo 17 + Postgres 16 in Docker on localhost:8069, seeded
make doctor-sandbox    # make doctor with the Odoo settings pointed at the sandbox
make sandbox-down      # stop it; WIPE=1 also deletes its data
```

`sandbox/odoo/seed.py` creates the `scrum-bot` user (Project / User rights, as in
`ARCHITECTURE.md`), an "AI Dev Learning (sandbox)" project with the board's stage names, and
fixtures for the board rules: a teammate's task, a task already in Done, and a task on another
project. It can be re-run safely, and it fails if the ids it creates don't match the pins in
`.mcp.json`. The browser login is `admin` / `admin`. The sandbox's settings live in
`sandbox/odoo/sandbox.env`. They are throwaway local values: `make doctor-sandbox` exports them
for that one command, so never source that file into your shell.

The `odoo-sandbox` MCP server runs the same board server as `odoo-board` (from
`$AI_COURSE_KIT`), pinned to the sandbox project, so its tools behave like the real board's:
pinned to one project, and Done is refused. It starts via `uv run --with mcp`, so it needs only
`uv` and a running sandbox. Claude Code asks once before enabling a new project MCP server.

A result against `localhost:8069` is evidence about the bot's code, **not** a course-board gate.
Nothing in the sandbox moves a course-board ticket.
