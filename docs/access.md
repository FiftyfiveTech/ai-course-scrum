# Teams Access — Go / No-Go

**Task:** SCRUM-013
**Due:** 2026-10-23
**Decision date:** 2026-10-22
**Decision owner:** Vimal + Yash/Saurabh (supervisors)

---

## Correction, 2026-10-22 (later same day)

The NO-GO below was recorded on the assumption that IT access (B1) was still pending. It
wasn't: credentials arrived the same day, via a **Teams-managed bot** (Developer Portal
registration, no Azure subscription — see ARCHITECTURE.md §5) rather than the Azure Bot path
this checklist originally assumed. Updated status:

| # | Item | Status |
|---|---|---|
| B1a | Permission to upload a custom Teams app | ✅ Granted — app installed, real activities received |
| B1b | ~~Entra app registration + Azure Bot (free tier)~~ Entra app registration (Teams-managed bot, no Azure Bot) | ✅ Granted — `MICROSOFT_APP_ID`/`MICROSOFT_APP_PASSWORD`/`MICROSOFT_APP_TENANT_ID` issue a working token |
| B1c | Admin consent for RSC `ChannelMessage.Read.Group` (channel) | ⏳ Not yet verified — only personal (1:1) chat has been exercised so far |
| B1d | A test channel for the spike | ⏳ Not yet verified — same gap as B1c |

Real evidence, this session:
```
PYTHONPATH=. .venv/Scripts/python.exe -m src.doctor
PASS  Teams bot credentials  bot token issued
```
Plus a real personal-chat activity received and replied to (sender `aadObjectId` read correctly,
matching C3 below).

---

## Spike: 3 checks to pass for a GO

The spike must prove all three before a GO is declared:

| # | Check | How to verify | Result |
|---|---|---|---|
| C1 | Bot posts a message on a schedule (proactive message) | Log shows `posted message_id=<id>` at scheduled time | ⏳ Not run — nothing proactive has been posted yet, only reactive replies |
| C2 | Bot receives a reply **without** an @mention | Log shows `received sender_id=<id> text=<text>` | ⏳ Not run in channel scope. Trivially true in personal scope (no @mention concept there), which is not what this check is testing |
| C3 | Bot reads the sender id correctly | Log shows sender id matching the config identity map | ✅ Confirmed in personal scope: `from.aadObjectId` on a real activity matched the real sender |

C1 and C2 still need a real channel-scope run before a full GO. Don't claim them without that
log output — see `src/spike_teams.py` for the originally planned check format.

---

## Decision: GO (personal chat / DM) — NO-GO still stands for channel scope

**What changed:** the original NO-GO assumed IT access never arrived. It did (Teams-managed bot,
not Azure Bot — see ARCHITECTURE.md §5), and personal-chat messaging works end to end today:
receive → read sender id → reply. That's enough to stop blocking on "no Teams access."

**What's still open:** channel-scope behavior (RSC consent, @mention-only delivery, a scheduled
proactive post) has not been exercised — B1c, B1d, C1, C2 above are still unverified. Don't call
a full GO until those are run against the real test channel with `src/spike_teams.py` (or its
equivalent for the current `src/adapters/teams.py` shape — the two have diverged; reconcile
before relying on that script as-is).

- Phase 0 pilot evidence below (`make demo` / CLI adapter) is unaffected and still stands as a
  fallback if channel scope doesn't clear in time
- `src/adapters/teams.py` is a working HTTP receiver + reply-on-mention/DM adapter today, not the
  stubbed `ChatAdapter`-protocol class this doc originally described — it does not yet implement
  `post`/`get_replies`/`post_private`, so it isn't wired into `src/demo.py` yet

**Pilot confirmed running on CLI adapter** — verified 2026-10-22:
```
make demo   # runs open → collect → follow_up → close → report via ScriptedCLIAdapter
make gate   # 2 passed — no_leakage + continuity both green
```

---

## What's left for a full GO

1. Get the bot into the actual pilot test channel (not just personal chat) and confirm B1c/B1d
2. Run a channel-scope spike: C1 (proactive scheduled post) and C2 (@mention-free channel read)
3. Record the real log output here, replacing the "Not run" rows above
4. Decide whether `src/spike_teams.py`'s `TeamsAdapter` scaffold or the working
   `src/adapters/teams.py` HTTP-receiver shape is the one to build the `ChatAdapter` protocol on
5. Swap the CLI adapter for Teams in `src/demo.py` once the protocol methods exist

---

## Teams adapter, current state

`src/adapters/teams.py` — a working `127.0.0.1:3978/api/messages` HTTP receiver (`make teams`):
gets a Bot Framework token, prints every activity, and replies when addressed (@mention in
channel/group scope, or any message in personal scope — there's no @mention there to check).
It does **not** yet implement the `ChatAdapter` protocol (`post` / `get_replies` / `post_private`)
that `src/demo.py` and the core expect, so it isn't a drop-in swap for the CLI adapter yet.
