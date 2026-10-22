# Coach Page — Week 1 Phase 0 Review

**Task:** SCRUM-015
**Date:** 2026-10-22
**For:** Yash / Saurabh running the Friday review session

---

## What participants built this week

| Ticket | What was built | Gate evidence |
|---|---|---|
| SCRUM-008 | 50 labelled stand-up updates; 20 sealed as `heldout-v1` | `tests/gates/test_no_leakage.py` — dev ∩ heldout = ∅ |
| SCRUM-009 | Content-hash leakage test | `make gate` — no_leakage PASS |
| SCRUM-010 | Pydantic extraction schema + `prompts/extract_v1.md` | Schema in `schemas/update.py` |
| SCRUM-011 | CLI adapter + fake clock + full lifecycle | `make demo` runs open→collect→follow_up→close→report |
| SCRUM-012 | Continuity test | `make gate` — continuity PASS |
| SCRUM-013 | Teams spike (NO-GO, IT approval pending) | `docs/access.md` — decision recorded |
| SCRUM-014 | Phase 0 exit gate | `make gate` — ALL CHECKS PASS |

---

## The two concepts to check understanding of

### Concept 1: Structured extraction

Ask: *"Why do we extract to JSON instead of passing the raw message to the report builder?"*

Good answer includes:
- Code cannot reliably act on free text (deadline checks, blocker tracking require typed fields)
- The schema enforces a contract; partial or wrong output is `FAILED`, not silently wrong
- Stored extraction is replayable — re-running the report does not re-call the model

Red flag answers:
- "So the model can summarise it" (the model is not a summariser here)
- "For formatting" (the schema is for correctness, not presentation)

### Concept 2: AI interprets, code enforces

Ask: *"Give me one example of something the model decides and one example of something code decides."*

Good answer:
- Model decides: whether "Thursday" means 2026-10-23; whether "SCRUM-011" is a task id reference; how to word a follow-up question
- Code decides: whether a commitment is overdue (`due_date <= today`); whether a blocker is resolved; which Odoo write to make

Red flag:
- "The model decides if something is a blocker" — no, the developer decides (model just labels it); code tracks it
- "The model writes to Odoo" — never; the allow-list wrapper `OdooWriter` does, after code decides

---

## Gate command to re-run

```bash
make setup          # if first time
make gate           # G1 continuity + G2 extraction + G3 Teams decision
```

Expected output:
```
══════════════════════════════════════════════════════════════
  GATE Phase 0 — SCRUM-014
══════════════════════════════════════════════════════════════
  ✅ PASS  G1  continuity test green
           day-1 commit → day-2 silent → day-3 asked + carried forward
  ✅ PASS  G2  extraction schema-valid
           30/30 schema-valid, 0 FAILED  (model: openai/gpt-oss-120b)
  ✅ PASS  G3  Teams go/no-go recorded
           docs/access.md — decision: NO-GO (Teams approval pending; pilot on CLI adapter)
──────────────────────────────────────────────────────────────
  ALL CHECKS PASS — Phase 0 gate GREEN
══════════════════════════════════════════════════════════════
```

G2 requires `GROQ_API_KEY` set in `.env`. G1 and G3 need no API calls.

---

## What NO-GO on Teams means for Phase 1

The bot runs on the **CLI adapter** for Phase 0 and Phase 1. This is not a workaround — it was
planned in PRD §0, B1:

> "No Teams access by day 5 → run the week-2 pilot on the test adapter and keep Teams as a
> later swap. Do not stall the core."

`src/adapters/teams.py` is scaffolded and ready. When IT approves:
1. Fill credentials in `.env`
2. Run `PYTHONPATH=. .venv/bin/python src/spike_teams.py`
3. Confirm C1/C2/C3 PASS in `logs/teams_spike.log`
4. Update `docs/access.md`: NO-GO → GO
5. Swap `ScriptedCLIAdapter` for `TeamsAdapter` in `src/demo.py`

No code changes needed in the lifecycle, extractor, or report builder.

---

## Questions to prompt deeper thinking

1. "What happens if the model returns valid JSON but with `origin: inferred` on everything —
   even items the developer stated explicitly?" *(Answer: the extraction is schema-valid but
   the eval will penalise it — inferred items without textual evidence are hallucinations.)*

2. "Why do we store `model_id` and `prompt_version` alongside every extraction?"
   *(Answer: so you can reproduce the eval; when the prompt improves, old records stay
   under the version that produced them.)*

3. "Why is `FAILED` better than a partial extraction?"
   *(Answer: a partial extraction looks valid but may have invented fields. FAILED surfaces
   in the report and triggers a follow-up. A silent wrong answer is worse.)*

---

## Open items for the team to resolve before Phase 1

| Item | Owner | Blocker |
|---|---|---|
| SCRUM-002: Odoo `scrum-bot` user | Yash | Needs IT |
| SCRUM-003: Hosting decision | Saurabh | Needs sign-off |
| SCRUM-004: Privacy sign-off | Yash | Needs all pilot members |
| SCRUM-007: SQLite schema gate | Vimal | In Review |
| Teams B1 approval | Yash | IT pending |
