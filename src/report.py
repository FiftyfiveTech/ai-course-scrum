"""
Report builder — constructs the daily stand-up report from the database.
No model calls here; everything comes from stored extractions.
"""

from __future__ import annotations

import json
import sqlite3


def build_report(db: sqlite3.Connection, standup_id: int) -> str:
    standup = db.execute(
        "SELECT * FROM standup WHERE id = ?", (standup_id,)
    ).fetchone()

    updates = db.execute(
        "SELECT * FROM standup_update WHERE standup_id = ? ORDER BY member_id",
        (standup_id,),
    ).fetchall()

    follow_ups = db.execute(
        "SELECT * FROM follow_up_question WHERE standup_id = ? ORDER BY member_id",
        (standup_id,),
    ).fetchall()

    W = 62
    lines: list[str] = [
        "",
        "═" * W,
        f"  STAND-UP REPORT  ·  {standup['date']}  ·  {standup['team_id']}",
        "═" * W,
    ]

    for row in updates:
        lines.append(f"\n  ── {row['member_id']} ──")
        ext = row["extraction"]

        if not ext:
            lines.append(f"    [no extraction — raw stored]")
            lines.append(f"    {row['raw_text']}")
            continue

        if ext == "FAILED":
            lines.append(f"    ⚠️  extraction FAILED after 2 attempts")
            lines.append(f"    raw: {row['raw_text']}")
            continue

        data = json.loads(ext)

        if data.get("done"):
            lines.append("    ✅ Done:")
            for item in data["done"]:
                tag = f" [#{item['task_id']}]" if item.get("task_id") else ""
                lines.append(f"       • {item['text']}{tag}  [{item['origin']}]")

        if data.get("next"):
            lines.append("    🔜 Next:")
            for item in data["next"]:
                tag = f" [#{item['task_id']}]" if item.get("task_id") else ""
                lines.append(f"       • {item['text']}{tag}  [{item['origin']}]")

        if data.get("blockers"):
            lines.append("    🚫 Blockers:")
            for item in data["blockers"]:
                owner = f"  owner: {item['owner_id']}" if item.get("owner_id") else ""
                lines.append(f"       • {item['text']}{owner}  [{item['origin']}]")

        if data.get("commitments"):
            lines.append("    📅 Commitments:")
            for item in data["commitments"]:
                due = f"  due {item['due_date']}" if item.get("due_date") else ""
                lines.append(
                    f"       • {item['text']}{due}  [{item['date_type']}]"
                )

    if follow_ups:
        lines.append(f"\n  ── Follow-ups ──")
        for fq in follow_ups:
            answered = fq["answer_text"] or "[unanswered]"
            lines.append(f"    [{fq['trigger_rule']}] {fq['member_id']}")
            lines.append(f"       Q: {fq['question_text']}")
            lines.append(f"       A: {answered}")

    model = updates[0]["model_id"] if updates else "n/a"
    prompt = updates[0]["prompt_version"] if updates else "n/a"
    lines += [
        "",
        "─" * W,
        f"  model: {model}  ·  prompt: {prompt}",
        "═" * W,
        "",
    ]

    return "\n".join(lines)
