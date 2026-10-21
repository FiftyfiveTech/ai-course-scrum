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
- Tasks come from the Odoo board via the `odoo-board` MCP server, not from this README.

## Branch and PR workflow

1. **Code goes to `dev` first.** Branch from `dev`, open the PR against `dev`, and promote `dev`
   to `main` only after review. Nothing is merged straight into `main`.
2. **PRs are opened with the `pr-dev` skill** ([`.claude/skills/pr-dev`](.claude/skills/pr-dev/SKILL.md)).
   In Claude Code, run `/pr-dev`: it checks the branch, runs the tests and gate, pushes, and opens
   the PR with `dev` as the base, so no PR goes to `main` by accident.
3. **For now, the Odoo board is empty.** Checks that depend on it — the `odoo-board` MCP calls,
   and the Odoo lines in `make doctor` — are expected to fail, and those failures are accepted
   until the board is populated. Every other test and gate must still pass.
