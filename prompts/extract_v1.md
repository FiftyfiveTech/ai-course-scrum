# extract_v1

## Purpose

Parse one developer's raw stand-up message into structured JSON.
Return **only** the JSON object — no explanation, no markdown fences.

## Rules

1. Extract only what the developer actually said.
   - `"origin": "reported"` — the developer stated it explicitly.
   - `"origin": "inferred"` — you derived it from context (e.g. a date implied by "tomorrow", a task id implied by a ticket name).
2. Never invent facts. If a field has no evidence, return an empty array `[]`.
3. `task_ids`: include only Odoo numeric task ids (e.g. `"3668"`). A GitHub PR number or any non-numeric reference is **not** a task id.
4. `commitments`: a commitment is a *next* item with a date. No date → `due_date` is the next stand-up date, `date_type` is `"implied"`. Only explicit ones (dev stated a date) count as overdue.
5. A concern or question is **not** a blocker unless the developer explicitly says it is blocking their work.
6. `"on leave"`, `"sick"`, `"WFH"` alone with no work items → all arrays empty.
7. Resolve relative dates (today, tomorrow, Friday, end of week, next Wednesday) to ISO 8601 using the `standup_date` field provided.

## Input

```json
{
  "standup_date": "<ISO date>",
  "member_id": "<anonymised handle>",
  "raw": "<verbatim stand-up message>"
}
```

## Output schema

Return a single JSON object with exactly these keys:

```json
{
  "done": [
    { "text": "<string>", "origin": "reported|inferred", "task_id": "<string>|null" }
  ],
  "next": [
    { "text": "<string>", "origin": "reported|inferred", "task_id": "<string>|null" }
  ],
  "blockers": [
    { "text": "<string>", "origin": "reported|inferred", "task_id": "<string>|null", "owner_id": "<string>|null" }
  ],
  "task_ids": [
    { "task_id": "<string>", "origin": "reported|inferred", "mention": "<exact text used>" }
  ],
  "commitments": [
    { "text": "<string>", "origin": "reported|inferred", "due_date": "<ISO date>|null", "date_type": "explicit|implied", "task_id": "<string>|null" }
  ]
}
```

All five keys must be present. Arrays may be empty. No extra keys.
