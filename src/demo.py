"""
Demo: one full stand-up for 3 fake members with a fake clock.

Demonstrates the complete lifecycle:
  open → collect → follow_up → close → report

Run:
  export GROQ_API_KEY=<key>
  PYTHONPATH=. .venv/bin/python -m src.demo
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.adapters.cli import ScriptedCLIAdapter
from src.clock import FakeClock
from src.db import add_team, connect
from src.extractor import extract
from src.lifecycle import StandUpLifecycle
from src.report import build_report

TEAM_ID = "demo-team"
MEMBERS = ["dev-a", "dev-b", "dev-c"]

# index 0 = initial stand-up update
# index 1 = answer to follow-up question (if one is triggered for that member)
SCRIPTS: dict[str, list[str]] = {
    "dev-a": [
        (
            "Done: finished the extraction prompt v1 and tested it on 5 messages. "
            "Next: write the JSON schema and hook it into the parser. "
            "No blockers. Committed to having the schema done by EOD today."
        ),
    ],
    "dev-b": [
        (
            "Yesterday I worked on #3668 and #3667. The leakage test is done. "
            "Still need to label more examples — probably finish tomorrow. "
            "Blocked waiting for Vimal to share the real board messages."
        ),
        # follow-up answer for Q7 (blocker)
        "Vimal said he'd share them this afternoon — should be unblocked by 2pm.",
    ],
    "dev-c": [
        (
            "Finished #3674 and pushed to review. "
            "Starting #3679 deadline tracking today. No issues."
        ),
        # follow-up answer for Q2 (dev says done, task may still be In Progress)
        "Yes, #3674 should move to Review — the PR is approved.",
    ],
}


def main() -> None:
    clock = FakeClock(start=datetime(2026, 10, 21, 9, 0, 0, tzinfo=timezone.utc))
    db = connect(":memory:")
    add_team(db, TEAM_ID, "Demo team", "Asia/Kolkata")
    adapter = ScriptedCLIAdapter(scripts=SCRIPTS, clock=clock)

    lifecycle = StandUpLifecycle(
        db=db,
        adapter=adapter,
        clock=clock,
        team_id=TEAM_ID,
        members=MEMBERS,
        extractor=extract,
    )

    print("\n" + "═" * 62)
    print("  AI SCRUM MASTER — DEMO")
    print("  fake clock: 2026-10-21 09:00 UTC | 3 members | CLI adapter")
    print("═" * 62)

    # open
    lifecycle.open()
    clock.advance(minutes=5)

    # collect
    lifecycle.collect()
    clock.advance(minutes=10)

    # follow up
    lifecycle.follow_up()
    clock.advance(minutes=5)

    # close
    lifecycle.close()

    # report
    report = build_report(db, lifecycle.standup_id)
    print(report)

    print("✅  make demo: open → collect → follow_up → close → report  DONE\n")


if __name__ == "__main__":
    main()
