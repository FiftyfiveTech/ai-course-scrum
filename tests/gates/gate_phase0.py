"""
GATE Phase 0 — SCRUM-014

Prints a PASS/FAIL table for all three Phase 0 exit criteria.
All three must pass for the gate to exit 0.

Checks:
  G1  continuity test green      (fake-clock, no API calls)
  G2  extraction schema-valid    (30/30 dev updates, real Groq call)
  G3  Teams go/no-go recorded    (docs/access.md exists with a decision)

Run:
  make gate
  .venv/bin/pytest tests/gates/gate_phase0.py -v -s

The supervisor re-runs this command and compares output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
W = 62


def _header() -> None:
    print()
    print("═" * W)
    print("  GATE Phase 0 — SCRUM-014")
    print("═" * W)


def _row(label: str, result: str, detail: str) -> None:
    status = "✅ PASS" if result == "PASS" else "❌ FAIL"
    print(f"  {status}  {label}")
    print(f"         {detail}")


def _footer(results: list[str]) -> None:
    print("─" * W)
    all_pass = all(r == "PASS" for r in results)
    verdict = "ALL CHECKS PASS — Phase 0 gate GREEN" if all_pass else "GATE FAILED — fix failing checks before advancing"
    print(f"  {verdict}")
    print("═" * W)
    print()


# ── G1: continuity test ───────────────────────────────────────────────────────

def check_continuity() -> tuple[str, str]:
    """Run test_continuity.py via pytest. No API calls."""
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/gates/test_continuity.py",
            "-q", "--tb=short",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if proc.returncode == 0:
        return "PASS", "day-1 commit → day-2 silent → day-3 asked + carried forward"
    return "FAIL", proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "test failed"


# ── G2: extraction schema-valid ───────────────────────────────────────────────

def check_extraction() -> tuple[str, str]:
    """
    Run the extractor over all dev updates and count schema-valid results.
    Requires GROQ_API_KEY in environment.
    """
    import os
    if not os.environ.get("GROQ_API_KEY"):
        return "FAIL", "GROQ_API_KEY not set — source .env before running gate"

    dev_path = REPO_ROOT / "evals" / "dev" / "updates.json"
    updates = json.loads(dev_path.read_text())

    # Import here so missing deps surface as a FAIL, not a crash
    try:
        from src.extractor import extract
    except ImportError as exc:
        return "FAIL", f"import error: {exc}"

    ok = failed = 0
    for u in updates:
        try:
            result = extract(
                raw=u["raw"],
                member_id=u["member_id"],
                standup_date=date.fromisoformat(u["standup_date"]),
                update_id=u["id"],
                source=u.get("source", "synthetic"),
            )
            if result.extraction == "FAILED":
                failed += 1
            else:
                ok += 1
        except Exception:
            failed += 1

    total = ok + failed
    detail = f"{ok}/{total} schema-valid, {failed} FAILED  (model: openai/gpt-oss-120b)"
    return ("PASS" if failed == 0 else "FAIL", detail)


# ── G3: Teams go/no-go recorded ──────────────────────────────────────────────

def check_teams_decision() -> tuple[str, str]:
    """Verify docs/access.md exists and contains a GO or NO-GO decision."""
    access_md = REPO_ROOT / "docs" / "access.md"
    if not access_md.exists():
        return "FAIL", "docs/access.md not found"

    content = access_md.read_text()
    if "NO-GO" in content:
        return "PASS", "docs/access.md — decision: NO-GO (Teams approval pending; pilot on CLI adapter)"
    if "GO" in content:
        return "PASS", "docs/access.md — decision: GO"
    return "FAIL", "docs/access.md exists but contains no GO / NO-GO decision"


# ── Gate runner ───────────────────────────────────────────────────────────────

def test_gate_phase0() -> None:
    """pytest entry point — fails the test if any check fails."""
    _header()

    checks = [
        ("G1  continuity test green",     check_continuity),
        ("G2  extraction schema-valid",   check_extraction),
        ("G3  Teams go/no-go recorded",   check_teams_decision),
    ]

    results = []
    for label, fn in checks:
        result, detail = fn()
        results.append(result)
        _row(label, result, detail)

    _footer(results)

    assert all(r == "PASS" for r in results), (
        "Phase 0 gate FAILED — see table above"
    )


if __name__ == "__main__":
    test_gate_phase0()
