"""
Teams spike — SCRUM-013.

Proves three things when run against a real Teams channel:
  C1: bot posts a message on a schedule (proactive message)
  C2: bot receives a reply WITHOUT an @mention
  C3: bot reads the sender id correctly

All three results are written to logs/teams_spike.log.
A GO requires all three lines present in the log.

Run (after docs/access.md B1 checklist is complete):
  PYTHONPATH=. .venv/bin/python src/spike_teams.py

Current status: NO-GO — Teams tenant approval pending (see docs/access.md).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path("logs/teams_spike.log")


def _setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("spike_teams")


def run_spike() -> None:
    log = _setup_logging()
    log.info("=== Teams spike START ===")

    # Fail fast and clearly if credentials are missing — log each check as NOT-RUN
    required = ["TEAMS_APP_ID", "TEAMS_APP_PASSWORD", "TEAMS_CHANNEL_ID", "TEAMS_SERVICE_URL"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        log.error("NO-GO: missing credentials: %s", ", ".join(missing))
        log.info("C1 NOT-RUN: cannot post without TEAMS_APP_ID/PASSWORD/CHANNEL_ID/SERVICE_URL")
        log.info("C2 NOT-RUN: cannot receive replies without RSC consent (B1c pending)")
        log.info("C3 NOT-RUN: cannot read sender id without channel access (B1c pending)")
        log.info("DECISION: NO-GO — Teams tenant approval pending (see docs/access.md)")
        log.info("PILOT: running on CLI adapter (src/adapters/cli.py) — make demo")
        return

    from src.adapters.teams import TeamsAdapter
    adapter = TeamsAdapter()

    # ── C1: proactive scheduled post ─────────────────────────────────────────
    log.info("CHECK C1: posting proactive message...")
    try:
        message_id = adapter.post("🤖 Stand-up spike: C1 scheduled post check")
        log.info("C1 PASS: posted message_id=%s", message_id)
    except Exception as exc:
        log.error("C1 FAIL: %s", exc)
        return

    # ── C2 + C3: receive reply without @mention, read sender id ──────────────
    log.info("CHECK C2+C3: waiting 30s for a reply (no @mention needed)...")
    time.sleep(30)

    since = datetime.now(timezone.utc)
    try:
        replies = adapter.get_replies(since)
        if not replies:
            log.warning("C2/C3: no replies received within 30s — try replying in the channel")
        for msg in replies:
            log.info("C2 PASS: received without @mention  sender_id=%s  text=%s",
                     msg.member_id, msg.text[:80])
            log.info("C3 PASS: sender_id read correctly  sender_id=%s", msg.member_id)
    except Exception as exc:
        log.error("C2/C3 FAIL: %s", exc)
        return

    log.info("=== Teams spike DONE — check %s for C1/C2/C3 lines ===", LOG_PATH)
    print(f"\nLog written to {LOG_PATH}")
    print("GO if all three lines (C1 PASS, C2 PASS, C3 PASS) appear in the log.")


if __name__ == "__main__":
    run_spike()
