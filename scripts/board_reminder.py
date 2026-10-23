#!/usr/bin/env python
"""Printed into context on every user prompt by a UserPromptSubmit hook.

Reminds the assistant to keep Odoo board #88 in sync with the work. Deliberately
short and conditional so it does not nag on conversational turns. ASCII-only so it
prints cleanly whatever the hook shell's console encoding is.
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

print(
    "[board-sync] This project tracks work on Odoo board #88 (SCRUM - AI Scrum Master). "
    "If this prompt starts, advances, finishes, or defines board work, reflect it on #88 "
    'with scripts/board88.py (move <id> <stage> | note <id> "..." | tag/untag | create). '
    "Stages: Backlog, In Progress, Blocked, Review (gate), Done. "
    "Skip for purely conversational/read-only prompts; never set Done on someone else's "
    "verified gate without authorization."
)
