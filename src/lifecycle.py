"""
Stand-up lifecycle state machine.

States: open → collect → follow_up → closed → report

Rules:
- One stand-up per (team_id, date) — enforced by the DB unique key.
- Follow-up questions are rule-triggered; the model only phrases them.
- Max 2 follow-up questions per member per stand-up.
- The model never picks a write; code decides everything.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from functools import partial
from typing import Any, Callable

import src.commitment as commitment_ledger
from src.adapters import Message
from src.adapters.cli import ScriptedCLIAdapter


class StandUpLifecycle:
    def __init__(
        self,
        db: sqlite3.Connection,
        adapter: ScriptedCLIAdapter,
        clock: Any,
        team_id: str,
        members: list[str],
        extractor: Callable | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.clock = clock
        self.team_id = team_id
        self.members = members
        self.extractor = extractor
        self.standup_id: int | None = None
        self._standup_date: date | None = None

    # ── State transitions ────────────────────────────────────────────────────

    def open(self) -> None:
        now = self.clock.now()
        today = now.date()
        self._standup_date = today

        cur = self.db.execute(
            "INSERT INTO standup (team_id, date, state, opened_at) VALUES (?, ?, 'open', ?)",
            (self.team_id, today.isoformat(), now.isoformat()),
        )
        self.db.commit()
        self.standup_id = cur.lastrowid

        self.adapter.post(
            f"Good morning! Stand-up for {today} is now open.\n"
            f"Please share:\n"
            f"  ✅ Done  |  🔜 Next  |  🚫 Blockers"
        )
        self._set_state("collect")

    def collect(self) -> None:
        """Collect one scripted update from each member and run extraction."""
        for member_id in self.members:
            msg = self.adapter.collect_member_response(member_id)
            if msg:
                self._store_update(member_id, msg)
        self._set_state("follow_up")

    def follow_up(self) -> None:
        """
        Post rule-triggered questions (max 2 per member).
        Collect scripted answers.
        """
        rows = self.db.execute(
            "SELECT member_id, extraction FROM standup_update WHERE standup_id = ?",
            (self.standup_id,),
        ).fetchall()

        for row in rows:
            member_id = row["member_id"]
            extraction_json = row["extraction"]
            if not extraction_json or extraction_json == "FAILED":
                continue

            extraction = json.loads(extraction_json)
            questions: list[tuple[str, str]] = []  # (rule, text)

            # Q7 — open blocker mentioned
            for blocker in extraction.get("blockers", []):
                questions.append((
                    "Q7",
                    f"You mentioned a blocker: \"{blocker['text']}\". "
                    f"Who is working on unblocking this?",
                ))

            # Q2 — dev says done on a task; task may still be In Progress on board
            for done_item in extraction.get("done", []):
                if done_item.get("task_id"):
                    questions.append((
                        "Q2",
                        f"You said #{done_item['task_id']} is done. "
                        f"Should it move to Review?",
                    ))

            # Q-commit — open commitment from a prior day, not yet met
            for comm in commitment_ledger.get_overdue(
                self.db, member_id, self._standup_date
            ):
                # Skip if this commitment was recorded in today's standup
                if comm["standup_id"] == self.standup_id:
                    continue
                questions.append((
                    "Q-commit",
                    f"You committed to \"{comm['description']}\" "
                    f"(due {comm['due_date'] or 'next stand-up'}). "
                    f"What's the status?",
                ))

            for rule, question_text in questions[:2]:  # cap at 2 per member
                self.adapter.post_private(member_id, question_text)
                self.db.execute(
                    """INSERT INTO follow_up_question
                       (standup_id, member_id, trigger_rule, question_text, asked_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        self.standup_id,
                        member_id,
                        rule,
                        question_text,
                        self.clock.now().isoformat(),
                    ),
                )
                self.db.commit()

                # Collect scripted follow-up answer
                answer = self.adapter.collect_member_response(member_id)
                if answer:
                    self.db.execute(
                        """UPDATE follow_up_question
                           SET answered_at = ?, answer_text = ?
                           WHERE standup_id = ? AND member_id = ?
                             AND trigger_rule = ? AND answered_at IS NULL""",
                        (
                            self.clock.now().isoformat(),
                            answer.text,
                            self.standup_id,
                            member_id,
                            rule,
                        ),
                    )
                    self.db.commit()

    def close(self) -> None:
        now = self.clock.now()
        self.db.execute(
            "UPDATE standup SET closed_at = ? WHERE id = ?",
            (now.isoformat(), self.standup_id),
        )
        self.db.commit()
        self._set_state("closed")

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _store_update(self, member_id: str, msg: Message) -> None:
        extraction_json: str | None = None
        model_id: str | None = None
        prompt_version: str | None = None

        if self.extractor:
            result = self.extractor(
                raw=msg.text,
                member_id=member_id,
                standup_date=self._standup_date,
                update_id=msg.id,
            )
            model_id = result.model_id
            prompt_version = result.prompt_version
            if result.extraction == "FAILED":
                extraction_json = "FAILED"
            elif result.extraction is not None:
                extraction_json = result.extraction.model_dump_json()

        self.db.execute(
            """INSERT OR IGNORE INTO standup_update
               (standup_id, member_id, raw_text, chat_message_id,
                extraction, model_id, prompt_version, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self.standup_id,
                member_id,
                msg.text,
                msg.id,
                extraction_json,
                model_id,
                prompt_version,
                self.clock.now().isoformat(),
            ),
        )
        self.db.commit()

        # Record new commitments and mark prior ones met if mentioned today
        commitment_ledger.record_from_extraction(
            self.db, self.standup_id, member_id, extraction_json
        )
        commitment_ledger.mark_met_if_mentioned(self.db, member_id, extraction_json)

    def _set_state(self, state: str) -> None:
        self.db.execute(
            "UPDATE standup SET state = ? WHERE id = ?",
            (state, self.standup_id),
        )
        self.db.commit()
