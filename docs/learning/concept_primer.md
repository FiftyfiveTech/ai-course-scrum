# Concept Primer — Structured Extraction and "AI Interprets, Code Enforces"

**Task:** SCRUM-015
**Date:** 2026-10-22
**Audience:** Course participants building the AI Scrum Master bot

---

## The core idea in one sentence

> The model reads language and labels what it finds.
> Code decides what to do with those labels.

---

## 1. What is structured extraction?

A developer sends a stand-up message like this:

```
Done: finished the auth refactor for SCRUM-010.
Next: PR review for SCRUM-011, should close it by Thursday.
Blocked by Vimal on the API contract — waiting for him to share the spec.
```

This is unstructured text. A human reads it and understands it. But you cannot write reliable
code against free text — you cannot check if a deadline was missed, or if a blocker is still open,
by pattern-matching strings.

**Structured extraction** is the step that converts the raw message into a typed JSON object:

```json
{
  "done": [
    { "text": "finished the auth refactor", "origin": "reported", "task_id": "3669" }
  ],
  "next": [
    { "text": "PR review for SCRUM-011", "origin": "reported", "task_id": "3670" }
  ],
  "blockers": [
    {
      "text": "waiting for Vimal to share the API contract spec",
      "origin": "reported",
      "task_id": null,
      "owner_id": "vimal"
    }
  ],
  "task_ids": [
    { "task_id": "3669", "origin": "reported", "mention": "SCRUM-010" },
    { "task_id": "3670", "origin": "reported", "mention": "SCRUM-011" }
  ],
  "commitments": [
    {
      "text": "PR review for SCRUM-011",
      "origin": "reported",
      "due_date": "2026-10-23",
      "date_type": "explicit",
      "task_id": "3670"
    }
  ]
}
```

Now code can check: is the commitment overdue? Is the blocker still open? Which tasks were
mentioned today? These questions have deterministic answers once the data is structured.

---

## 2. The `origin` field — why every item is tagged

Every extracted item carries `"origin": "reported"` or `"origin": "inferred"`.

| Value | Meaning | Example |
|---|---|---|
| `reported` | The developer stated it explicitly | `"blocked by Vimal"` |
| `inferred` | The model derived it from context | `"Thursday"` resolved to `2026-10-23` |

**Why does this matter?**

- `reported` items are facts from the developer. The model is just a parser.
- `inferred` items are the model's interpretation. They may be wrong.

When the bot escalates a blocker or flags a missed commitment, it must know whether the evidence
was stated or guessed. The evaluator checks `origin` tags when scoring: an invented commitment
with `origin: "inferred"` and no textual evidence is a hallucination, not an extraction.

The gate criterion for Phase 0 is: **0 invented commitments across 30 dev updates**.

---

## 3. "AI interprets, code enforces" — the design principle

### What the model does

The model reads raw language and produces a labelled structure. That is all.

```
raw text → [model] → labelled JSON
```

The model is allowed to:
- Parse items into `done`, `next`, `blockers`, `task_ids`, `commitments`
- Tag each item as `reported` or `inferred`
- Resolve relative dates (`"Thursday"` → ISO 8601)
- Word follow-up questions (phrasing only)

### What the model never does

The model never:
- Decides whether a commitment is overdue
- Decides whether a blocker is resolved
- Chooses which Odoo write to make
- Decides to move a task to Done
- Triggers any state change

These are **code decisions**, not model decisions.

### Why?

Three reasons:

**1. Models hallucinate.** If the model decided what to write to Odoo, a hallucination would
corrupt real project data. With structured extraction, the worst a hallucinated `inferred` field
can do is generate a spurious follow-up question — which a human sees before acting.

**2. Code is auditable.** Every commitment state change, every Odoo write, every blocker
resolution goes through Python with a traceable call stack. You can read the code and know
exactly what the system will do in every case. You cannot read a model's weights.

**3. The gate measures code, not vibes.** `task-id recall ≥ 0.95` is a number you can compute.
`"the model seemed to do well"` is not a gate criterion. Structured extraction gives you a
ground-truth label to compare against.

---

## 4. The extraction pipeline

```
Developer message
      │
      ▼
 src/extractor.py          ← one call to openai/gpt-oss-120b via Groq
      │                       retries once on invalid JSON
      │                       stores FAILED, never guesses
      ▼
StoredUpdate (Pydantic)    ← schema-validated; invalid = FAILED, not partial
      │
      ▼
SQLite (update table)      ← raw + extraction + model_id + prompt_version stored
      │
      ├── src/commitment.py   ← reads extraction; records commitments in DB
      ├── src/lifecycle.py    ← reads extraction; triggers follow-ups by rule
      └── src/report.py       ← reads DB; builds report from structured records
```

Key property: **the model is only called once per message**. Everything downstream reads the
stored extraction. If you re-run the report, you do not re-call the model.

---

## 5. What "FAILED" means — and why it is not a bug

If the model returns invalid JSON, or JSON that does not match the schema, the extractor stores
`"extraction": "FAILED"` and moves on.

It does **not**:
- Retry forever
- Store a partial result
- Guess what the developer meant

A FAILED extraction shows up in the report as a missing update. The bot asks the developer to
repeat their update in the follow-up round. This is intentional: a silent wrong answer is worse
than a visible failure.

The Phase 0 gate requires **0 FAILEDs across 30 dev updates**. If any fail, the prompt or model
needs fixing — not the schema.

---

## 6. Prompt version pinning

The extraction prompt is in `prompts/extract_v1.md`. Every stored extraction records:

- `model_id`: the HF repo id (`openai/gpt-oss-120b`) — not the provider
- `prompt_version`: `extract_v1`

This means you can re-evaluate any historical extraction by knowing exactly what instructions the
model was given. When the prompt improves to `extract_v2`, old extractions are not retroactively
changed — they stay as `extract_v1` records with their original output.

---

## 7. Coach notes — common mistakes in this week's builds

| Mistake | Why it matters | Correct approach |
|---|---|---|
| Letting the model decide if a commitment is overdue | Model answers change; overdue is a date comparison | `code: due_date <= today` |
| Storing `"inferred"` items without a text anchor | Impossible to audit; evaluator will flag as hallucination | Require evidence in the raw text before tagging inferred |
| Calling the model again in the report builder | Increases cost and latency; report is not a summariser | Read from DB only; model runs once at collection time |
| Trusting `task_id` as a string match | PR numbers look like task ids | Prompt rule 3: only Odoo numeric ids; GitHub PR numbers excluded |
| Skipping `prompt_version` in the stored record | Cannot reproduce evaluation later | Always store both `model_id` and `prompt_version` |
| Using `FAILED` as a signal to retry with a weaker prompt | Weaker prompts produce more hallucinations | Fix the prompt on `dev` evals; never lower the bar |

---

## 8. Quick reference

| Term | Definition |
|---|---|
| **Structured extraction** | Converting a raw text message into a validated JSON schema |
| **`reported`** | Developer explicitly stated this item |
| **`inferred`** | Model derived this from context (dates, implied task ids) |
| **`FAILED`** | Extraction produced invalid output; stored as-is, surfaced in report |
| **Commitment** | A next item with a date; tracked across days |
| **Continuity** | A commitment from day N appears in the report on day N+2 if unmet |
| **AI interprets** | Model labels language into the schema |
| **Code enforces** | All state changes, writes, and decisions are in Python, not the model |
| **HF repo id** | The model name used in stored records (`openai/gpt-oss-120b`, not "Groq") |
| **Gate** | A computed, printed number that must meet a threshold; not a judgement call |
