"""
Follow-up question engine — SCRUM-019.

Rules Q1–Q7 + Q-commit. Code picks which rules fire; the model only words the question.
Max 2 questions per member per stand-up — enforced by this module, not the caller.

Rule priority (highest first — ties broken by position in this list):
  Q7        — blocker mentioned today (safety: get owner on record)
  Q-commit  — prior commitment overdue (continuity: don't drop promises)
  Q2        — dev says done, task may still be open on board
  Q5        — blocker from a prior day not mentioned as resolved
  Q1        — no update received at all
  Q6        — no done items (what did you ship?)
  Q3        — task deadline today/tomorrow, not in update  [needs board data]
  Q4        — task overdue, not in update                  [needs board data]

Q3 and Q4 are board-driven (require Odoo task data from SCRUM-016).
They return no questions when board_tasks is None.

Usage:
    from src.follow_up import FollowUpEngine

    engine = FollowUpEngine(db, clock)
    questions = engine.select(
        standup_id=1,
        member_id="ritika",
        extraction=extraction_dict_or_none,
        standup_date=date.today(),
        board_tasks=None,   # pass list[dict] from Odoo when SCRUM-016 is ready
    )
    # questions is a list of (rule, text), capped at MAX_PER_MEMBER
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any

import src.blocker as blocker_ledger
import src.commitment as commitment_ledger

MAX_PER_MEMBER = 2


@dataclass(frozen=True)
class FollowUpQuestion:
    rule: str    # e.g. "Q7", "Q-commit"
    text: str    # the question text to send to the developer


class FollowUpEngine:
    """
    Selects follow-up questions for one member based on their extraction and
    ledger state. Never sends more than MAX_PER_MEMBER questions.
    """

    def __init__(self, db: sqlite3.Connection, standup_id: int) -> None:
        self._db = db
        self._standup_id = standup_id

    def select(
        self,
        member_id: str,
        extraction: dict[str, Any] | None,
        standup_date: date,
        board_tasks: list[dict[str, Any]] | None = None,
    ) -> list[FollowUpQuestion]:
        """
        Return up to MAX_PER_MEMBER follow-up questions for this member,
        ordered by rule priority.
        """
        candidates: list[FollowUpQuestion] = []

        # Q7 — blocker mentioned today (highest priority: get owner on record)
        candidates.extend(self._q7_new_blocker(extraction))

        # Q-commit — prior commitment overdue
        candidates.extend(self._q_commit(member_id, standup_date))

        # Q2 — dev says done, board may still show task in progress
        candidates.extend(self._q2_done_not_closed(extraction, board_tasks))

        # Q5 — blocker from prior standup not mentioned as resolved today
        candidates.extend(self._q5_stale_blocker(member_id, extraction, standup_date))

        # Q1 — no update at all
        candidates.extend(self._q1_no_update(extraction))

        # Q6 — no done items
        candidates.extend(self._q6_no_done(extraction))

        # Q3 — deadline today/tomorrow, not in update (needs board data)
        candidates.extend(self._q3_deadline_soon(extraction, board_tasks, standup_date))

        # Q4 — task overdue, not in update (needs board data)
        candidates.extend(self._q4_overdue_task(extraction, board_tasks, standup_date))

        return candidates[:MAX_PER_MEMBER]

    # ── Rule implementations ─────────────────────────────────────────────────

    def _q7_new_blocker(
        self, extraction: dict[str, Any] | None
    ) -> list[FollowUpQuestion]:
        """Q7: blocker mentioned in today's update — get owner on record."""
        if not extraction:
            return []
        questions = []
        for b in extraction.get("blockers", []):
            questions.append(FollowUpQuestion(
                rule="Q7",
                text=(
                    f"You mentioned a blocker: \"{b['text']}\". "
                    f"Who is working on unblocking this, and what's the ETA?"
                ),
            ))
        return questions

    def _q_commit(
        self, member_id: str, standup_date: date
    ) -> list[FollowUpQuestion]:
        """Q-commit: prior commitment overdue and not mentioned as done today."""
        overdue = commitment_ledger.get_overdue(self._db, member_id, standup_date)
        # Skip commitments recorded in this same standup (just made today)
        overdue = [c for c in overdue if c["standup_id"] != self._standup_id]
        questions = []
        for comm in overdue:
            due = comm["due_date"] or "next stand-up"
            questions.append(FollowUpQuestion(
                rule="Q-commit",
                text=(
                    f"You committed to \"{comm['description']}\" (due {due}). "
                    f"What's the status?"
                ),
            ))
        return questions

    def _q2_done_not_closed(
        self,
        extraction: dict[str, Any] | None,
        board_tasks: list[dict[str, Any]] | None,
    ) -> list[FollowUpQuestion]:
        """
        Q2: dev says done on a task, but board still shows it open.
        Requires board_tasks from SCRUM-016. Skipped if board_tasks is None.
        """
        if not extraction or board_tasks is None:
            return []
        open_task_ids = {
            str(t["id"]) for t in board_tasks
            if t.get("state") not in ("1_done", "1_canceled")
        }
        questions = []
        for done_item in extraction.get("done", []):
            task_id = done_item.get("task_id")
            if task_id and str(task_id) in open_task_ids:
                questions.append(FollowUpQuestion(
                    rule="Q2",
                    text=(
                        f"You said task #{task_id} is done. "
                        f"Should it move to Review on the board?"
                    ),
                ))
        return questions

    def _q5_stale_blocker(
        self,
        member_id: str,
        extraction: dict[str, Any] | None,
        standup_date: date,
    ) -> list[FollowUpQuestion]:
        """Q5: blocker from a prior standup not mentioned as resolved today."""
        open_blockers = blocker_ledger.get_open(self._db, member_id)
        # Exclude blockers reported in this standup (those are Q7)
        prior_blockers = [
            b for b in open_blockers
            if b["standup_id"] != self._standup_id
        ]
        if not prior_blockers:
            return []

        # Check which prior blockers are mentioned in today's extraction
        today_texts = set()
        if extraction:
            for item in extraction.get("blockers", []) + extraction.get("done", []):
                today_texts.add(item["text"].lower())

        questions = []
        for b in prior_blockers:
            age = blocker_ledger.days_open(b, standup_date)
            # Only ask if the blocker isn't mentioned today
            if b["description"].lower() not in today_texts:
                questions.append(FollowUpQuestion(
                    rule="Q5",
                    text=(
                        f"Your blocker \"{b['description']}\" has been open "
                        f"for {age} day{'s' if age != 1 else ''}. "
                        f"Any update or change in status?"
                    ),
                ))
        return questions

    def _q1_no_update(
        self, extraction: dict[str, Any] | None
    ) -> list[FollowUpQuestion]:
        """Q1: no update received at all from this member."""
        if extraction is not None:
            return []
        return [FollowUpQuestion(
            rule="Q1",
            text="We didn't receive your stand-up update today. Are you available?",
        )]

    def _q6_no_done(
        self, extraction: dict[str, Any] | None
    ) -> list[FollowUpQuestion]:
        """Q6: update received but no done items — nothing shipped."""
        if not extraction:
            return []
        if extraction.get("done"):
            return []
        # Only ask if they had next items (they were working on something)
        if not extraction.get("next"):
            return []
        return [FollowUpQuestion(
            rule="Q6",
            text=(
                "Your update doesn't mention anything completed. "
                "Was there a reason nothing shipped, or is it in progress?"
            ),
        )]

    def _q3_deadline_soon(
        self,
        extraction: dict[str, Any] | None,
        board_tasks: list[dict[str, Any]] | None,
        standup_date: date,
    ) -> list[FollowUpQuestion]:
        """
        Q3: task deadline is today or tomorrow, not mentioned in the update.
        Requires board_tasks from SCRUM-016. Skipped if board_tasks is None.
        """
        if board_tasks is None or not extraction:
            return []
        mentioned_ids = {
            str(item.get("task_id"))
            for field in ("done", "next", "blockers")
            for item in extraction.get(field, [])
            if item.get("task_id")
        }
        questions = []
        for task in board_tasks:
            deadline = task.get("date_deadline")
            if not deadline:
                continue
            try:
                dl = date.fromisoformat(deadline)
            except ValueError:
                continue
            days_until = (dl - standup_date).days
            if 0 <= days_until <= 1 and str(task["id"]) not in mentioned_ids:
                label = "today" if days_until == 0 else "tomorrow"
                questions.append(FollowUpQuestion(
                    rule="Q3",
                    text=(
                        f"Task #{task['id']} \"{task.get('name', '')}\" is due {label}. "
                        f"Is it on track?"
                    ),
                ))
        return questions

    def _q4_overdue_task(
        self,
        extraction: dict[str, Any] | None,
        board_tasks: list[dict[str, Any]] | None,
        standup_date: date,
    ) -> list[FollowUpQuestion]:
        """
        Q4: task deadline has passed (overdue), not mentioned in the update.
        Requires board_tasks from SCRUM-016. Skipped if board_tasks is None.
        """
        if board_tasks is None or not extraction:
            return []
        mentioned_ids = {
            str(item.get("task_id"))
            for field in ("done", "next", "blockers")
            for item in extraction.get(field, [])
            if item.get("task_id")
        }
        questions = []
        for task in board_tasks:
            deadline = task.get("date_deadline")
            if not deadline:
                continue
            try:
                dl = date.fromisoformat(deadline)
            except ValueError:
                continue
            if dl < standup_date and str(task["id"]) not in mentioned_ids:
                days_late = (standup_date - dl).days
                questions.append(FollowUpQuestion(
                    rule="Q4",
                    text=(
                        f"Task #{task['id']} \"{task.get('name', '')}\" was due "
                        f"{days_late} day{'s' if days_late != 1 else ''} ago. "
                        f"What's the status?"
                    ),
                ))
        return questions
