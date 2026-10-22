# Teams Access — Go / No-Go

**Task:** SCRUM-013
**Due:** 2026-10-23
**Decision date:** 2026-10-22
**Decision owner:** Vimal + Yash/Saurabh (supervisors)

---

## What was needed (B1 checklist)

To run the Teams echo bot spike, Office55 IT must grant all four of these:

| # | Item | Status |
|---|---|---|
| B1a | Permission to upload a custom Teams app | ⏳ Pending |
| B1b | Entra app registration + Azure Bot (free tier) | ⏳ Pending |
| B1c | Admin consent for RSC `ChannelMessage.Read.Group` (channel) | ⏳ Pending |
| B1d | A test channel for the spike | ⏳ Pending |

---

## Spike: 3 checks to pass for a GO

The spike must prove all three before a GO is declared:

| # | Check | How to verify | Result |
|---|---|---|---|
| C1 | Bot posts a message on a schedule (proactive message) | Log shows `posted message_id=<id>` at scheduled time | ⏳ Not run |
| C2 | Bot receives a reply **without** an @mention | Log shows `received sender_id=<id> text=<text>` | ⏳ Not run |
| C3 | Bot reads the sender id correctly | Log shows sender id matching the config identity map | ⏳ Not run |

All three must appear in `logs/teams_spike.log` for a GO.

---

## Decision: NO-GO

**Reason:** Teams tenant approval (B1) was not granted by day 5 (2026-10-23).
The IT request was sent on 2026-10-21 and is still pending as of 2026-10-22.

**Consequence (per PRD §0, B1):**
> "No Teams access by day 5 → run the week-2 pilot on the test adapter and keep Teams as a later swap. Do not stall the core."

- Phase 0 and Phase 1 pilots run on the **CLI adapter** (`src/adapters/cli.py`)
- Teams becomes an adapter swap in a later phase, not a blocker
- `src/adapters/teams.py` is scaffolded and ready; it needs only the Azure credentials to activate

---

## What to do when IT approves

1. Fill in `B1a–B1d` above with the granted values
2. Add credentials to `.env`:
   ```
   TEAMS_APP_ID=
   TEAMS_APP_PASSWORD=
   TEAMS_CHANNEL_ID=
   TEAMS_SERVICE_URL=
   ```
3. Run `PYTHONPATH=. .venv/bin/python src/spike_teams.py`
4. Confirm all three checks appear in `logs/teams_spike.log`
5. Update this doc: change **NO-GO → GO** and record the log snippet
6. Swap `ScriptedCLIAdapter` for `TeamsAdapter` in `src/demo.py`

---

## Teams adapter skeleton

`src/adapters/teams.py` — scaffolded, awaiting credentials.
Satisfies the same `ChatAdapter` protocol as the CLI adapter.
No code changes needed in the lifecycle or report builder when Teams is activated.
