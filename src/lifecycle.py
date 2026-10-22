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

import src.blocker as blocker_ledger
import src.commitment as commitment_ledger
from src.adapters import Message
from src.adapters.cli import ScriptedCLIAdapter
from src.follow_up import FollowUpEngine


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
        FollowUpEngine selects which rules fire; the model only words them.
        Collect scripted answers.
        """
        rows = self.db.execute(
            "SELECT member_id, extraction FROM standup_update WHERE standup_id = ?",
            (self.standup_id,),
        ).fetchall()

        engine = FollowUpEngine(self.db, self.standup_id)

        # Also ask Q1 for members who sent no update
        members_with_update = {row["member_id"] for row in rows}
        silent_members = [m for m in self.members if m not in members_with_update]

        all_member_extractions: list[tuple[str, dict | None]] = [
            (row["member_id"],
             json.loads(row["extraction"]) if row["extraction"] and row["extraction"] != "FAILED" else None)
            for row in rows
        ] + [(m, None) for m in silent_members]

        for member_id, extraction in all_member_extractions:
            questions = engine.select(
                member_id=member_id,
                extraction=extraction,
                standup_date=self._standup_date,
                board_tasks=None,  # wired in when SCRUM-016 (Odoo read) is ready
            )

            for q in questions:
                self.adapter.post_private(member_id, q.text)
                self.db.execute(
                    """INSERT INTO follow_up_question
                       (standup_id, member_id, trigger_rule, question_text, asked_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        self.standup_id,
                        member_id,
                        q.rule,
                        q.text,
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
                            q.rule,
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
        commitment_ledger.mark_met_if_mentioned(
            self.db, self.standup_id, member_id, extraction_json
        )
        blocker_ledger.record_from_extraction(
            self.db, self.standup_id, member_id, extraction_json
        )

    def _set_state(self, state: str) -> None:
        self.db.execute(
            "UPDATE standup SET state = ? WHERE id = ?",
            (state, self.standup_id),
        )
        self.db.commit()
