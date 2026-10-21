"""
Gate: continuity test — THE PRODUCT.

  Day 1: dev-a commits to finishing the schema by EOD.
  Day 2: dev-a sends an update but is silent on the commitment.
  Day 3: the bot must ask about it AND the report must show it carried forward.

Done when:
  - test green on fake clock
  - fails if the day-3 Q-commit question is missing
  - fails if CARRIED FORWARD is missing from the day-3 report

No real API calls — uses a stub extractor.

Run:
  make gate
  .venv/bin/pytest tests/gates/test_continuity.py -v -s
"""

from datetime import date, datetime, timezone

from schemas.update import (
    CommitmentItem,
    Extraction,
    NextItem,
    StoredUpdate,
)
from src.adapters.cli import ScriptedCLIAdapter
from src.clock import FakeClock
from src.db import connect
from src.lifecycle import StandUpLifecycle
from src.report import build_report

DAY1 = date(2026, 10, 21)
DAY2 = date(2026, 10, 22)
DAY3 = date(2026, 10, 23)


def _make_stub(extraction_map: dict[str, Extraction]):
    """Stub extractor — returns pre-defined extractions by member_id."""
    def stub(raw: str, member_id: str, standup_date: date,
             update_id: str, source: str = "real") -> StoredUpdate:
        return StoredUpdate(
            id=update_id,
            raw=raw,
            member_id=member_id,
            standup_date=standup_date,
            model_id="stub",
            prompt_version="stub",
            extraction=extraction_map.get(member_id),
        )
    return stub


def _run_day(
    db,
    clock: FakeClock,
    scripts: dict[str, list[str]],
    extraction_map: dict[str, Extraction],
    members: list[str] = None,
) -> StandUpLifecycle:
    adapter = ScriptedCLIAdapter(scripts=scripts, clock=clock)
    lc = StandUpLifecycle(
        db=db,
        adapter=adapter,
        clock=clock,
        team_id="test-team",
        members=members or list(scripts.keys()),
        extractor=_make_stub(extraction_map),
    )
    lc.open()
    lc.collect()
    lc.follow_up()
    lc.close()
    return lc


def test_continuity():
    clock = FakeClock(start=datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc))
    db = connect(":memory:")

    # ── Day 1: dev-a commits to finishing the schema by EOD ──────────────
    _run_day(
        db, clock,
        scripts={"dev-a": ["Kicked off the work. Next: finish the schema. Committed to having it done by EOD."]},
        extraction_map={
            "dev-a": Extraction(
                done=[],
                next=[NextItem(text="finish the schema", origin="reported")],
                commitments=[
                    CommitmentItem(
                        text="finish the schema",
                        origin="reported",
                        due_date=DAY1,
                        date_type="explicit",
                    )
                ],
            )
        },
    )

    # ── Day 2: dev-a is silent on the schema commitment ──────────────────
    clock.advance(days=1)
    _run_day(
        db, clock,
        scripts={"dev-a": ["Working on other tasks today. No blockers."]},
        extraction_map={
            "dev-a": Extraction(
                done=[],
                next=[NextItem(text="working on other tasks", origin="reported")],
                commitments=[],
            )
        },
    )

    # ── Day 3: bot must ask about the commitment ──────────────────────────
    clock.advance(days=1)
    lc3 = _run_day(
        db, clock,
        scripts={
            "dev-a": [
                "Still catching up on a few things.",
                # follow-up answer when Q-commit fires
                "Will have the schema done by EOD today — almost there.",
            ]
        },
        extraction_map={
            "dev-a": Extraction(
                done=[],
                next=[NextItem(text="catching up", origin="reported")],
                commitments=[],
            )
        },
    )

    # ── Assertion 1: Q-commit follow-up question exists on day 3 ─────────
    fqs = db.execute(
        "SELECT * FROM follow_up_question WHERE standup_id = ? AND trigger_rule = 'Q-commit'",
        (lc3.standup_id,),
    ).fetchall()

    assert len(fqs) > 0, (
        "CONTINUITY FAIL: no Q-commit follow-up question on day 3.\n"
        "The bot must ask about the unresolved day-1 commitment."
    )

    # ── Assertion 2: report carries the commitment forward ────────────────
    report = build_report(db, lc3.standup_id)

    assert "CARRIED FORWARD" in report, (
        "CONTINUITY FAIL: 'CARRIED FORWARD' section missing from day-3 report.\n"
        "Open commitments from prior days must appear in the report."
    )
    assert "finish the schema" in report.lower(), (
        "CONTINUITY FAIL: commitment text 'finish the schema' missing from day-3 report."
    )

    print(
        f"\ncontinuity: day-1 commit → day-2 silent → day-3 asked + carried forward  PASS"
        f"\n  Q-commit questions on day 3 : {len(fqs)}"
        f"\n  question                    : {fqs[0]['question_text']}"
        f"\n  answer                      : {fqs[0]['answer_text']}"
    )
