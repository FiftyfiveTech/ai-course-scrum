"""
SQLite setup. Call connect() to get a ready connection with the full schema.
Pass ":memory:" for tests and demo; pass a file path for production.

Tables follow ARCHITECTURE.md §3. Two invariants are enforced by the database itself,
not by app code, so no caller can get them wrong:

- Uniqueness: one stand-up per (team_id, date); one Odoo write per (standup_id, task_id, kind).
- commitment_history is append-only: UPDATE and DELETE abort. A state change is a new row;
  the latest row per (member_id, description) is the current state (view commitment_current).
"""

from __future__ import annotations

import json
import sqlite3

# ISO-8601 UTC, same shape the app writes from its clock.
_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"

SCHEMA = f"""
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS team (
    id               TEXT     PRIMARY KEY,
    name             TEXT     NOT NULL,
    timezone         TEXT     NOT NULL,
    odoo_project_ids TEXT     NOT NULL DEFAULT '[]',   -- JSON list of pinned project ids
    created_at       DATETIME NOT NULL DEFAULT {_NOW},
    updated_at       DATETIME NOT NULL DEFAULT {_NOW}
);

CREATE TABLE IF NOT EXISTS standup (
    id                INTEGER  PRIMARY KEY AUTOINCREMENT,
    team_id           TEXT     NOT NULL REFERENCES team(id),
    date              DATE     NOT NULL,
    state             TEXT     NOT NULL DEFAULT 'open'
                      CHECK (state IN ('open', 'collect', 'follow_up', 'closed', 'report')),
    opened_at         DATETIME NOT NULL,
    closed_at         DATETIME,
    report_message_id TEXT,                              -- chat message id; null until published
    created_at        DATETIME NOT NULL DEFAULT {_NOW},
    updated_at        DATETIME NOT NULL DEFAULT {_NOW},
    UNIQUE (team_id, date)
);

CREATE TABLE IF NOT EXISTS standup_update (
    id               INTEGER  PRIMARY KEY AUTOINCREMENT,
    standup_id       INTEGER  NOT NULL REFERENCES standup(id),
    member_id        TEXT     NOT NULL,                  -- Odoo res.users id
    raw_text         TEXT     NOT NULL,
    chat_message_id  TEXT     NOT NULL,                  -- Teams activity id or CLI uuid
    extraction       TEXT,                               -- JSON, schemas/update.json
    model_id         TEXT,                               -- HF repo id
    prompt_version   TEXT,
    created_at       DATETIME NOT NULL DEFAULT {_NOW},
    updated_at       DATETIME NOT NULL DEFAULT {_NOW},
    UNIQUE (standup_id, chat_message_id)
);

CREATE TABLE IF NOT EXISTS follow_up_question (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    standup_id    INTEGER  NOT NULL REFERENCES standup(id),
    member_id     TEXT     NOT NULL,
    trigger_rule  TEXT     NOT NULL,                     -- Q1–Q7 (PRD §8.2)
    target_type   TEXT     CHECK (target_type IN ('commitment', 'blocker', 'task')),
    target_id     TEXT,
    question_text TEXT     NOT NULL,
    asked_at      DATETIME NOT NULL,
    answered_at   DATETIME,
    answer_text   TEXT,
    created_at    DATETIME NOT NULL DEFAULT {_NOW},
    updated_at    DATETIME NOT NULL DEFAULT {_NOW}
);

CREATE TABLE IF NOT EXISTS commitment_history (
    id               INTEGER  PRIMARY KEY AUTOINCREMENT,
    standup_id       INTEGER  NOT NULL REFERENCES standup(id),
    member_id        TEXT     NOT NULL,
    task_id          TEXT,                               -- Odoo task id; null if no ticket
    description      TEXT     NOT NULL,
    due_date         DATE,
    date_type        TEXT     NOT NULL DEFAULT 'implied'
                     CHECK (date_type IN ('explicit', 'implied')),
    state            TEXT     NOT NULL DEFAULT 'pending'
                     CHECK (state IN ('pending', 'met', 'missed', 'deferred')),
    state_changed_at DATETIME NOT NULL DEFAULT {_NOW},
    state_changed_by TEXT     NOT NULL DEFAULT 'code'
                     CHECK (state_changed_by = 'code'),  -- the model never changes state
    created_at       DATETIME NOT NULL DEFAULT {_NOW}
    -- no updated_at: rows are never updated
);

CREATE INDEX IF NOT EXISTS commitment_history_key
    ON commitment_history (member_id, description, id);

CREATE TRIGGER IF NOT EXISTS commitment_history_no_update
BEFORE UPDATE ON commitment_history
BEGIN
    SELECT RAISE(ABORT, 'commitment_history is append-only');
END;

CREATE TRIGGER IF NOT EXISTS commitment_history_no_delete
BEFORE DELETE ON commitment_history
BEGIN
    SELECT RAISE(ABORT, 'commitment_history is append-only');
END;

-- Current state of each commitment: its latest history row, plus the stand-up it was first
-- made in.
CREATE VIEW IF NOT EXISTS commitment_current AS
SELECT h.*,
       first.standup_id AS first_standup_id
FROM commitment_history h
JOIN (
    SELECT member_id, description, MAX(id) AS last_id, MIN(id) AS first_id
    FROM commitment_history
    GROUP BY member_id, description
) g ON h.id = g.last_id
JOIN commitment_history first ON first.id = g.first_id;

CREATE TABLE IF NOT EXISTS blocker (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    standup_id   INTEGER  NOT NULL REFERENCES standup(id),  -- where first reported
    member_id    TEXT     NOT NULL,
    task_id      TEXT,
    description  TEXT     NOT NULL,
    owner_id     TEXT,                                      -- who is unblocking
    open         INTEGER  NOT NULL DEFAULT 1 CHECK (open IN (0, 1)),
    resolved_at  DATETIME,                                  -- days_open is computed, not stored
    created_at   DATETIME NOT NULL DEFAULT {_NOW},
    updated_at   DATETIME NOT NULL DEFAULT {_NOW}
);

CREATE TABLE IF NOT EXISTS odoo_write_log (
    id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    standup_id      INTEGER  NOT NULL REFERENCES standup(id),
    -- NOT NULL on purpose: SQLite treats NULLs as distinct in a UNIQUE key, so a null task_id
    -- would let the same write through twice. The daily log writes to the pinned log task.
    task_id         TEXT     NOT NULL,
    kind            TEXT     NOT NULL
                    CHECK (kind IN ('task_note', 'daily_log', 'alert', 'new_task', 'deadline', 'stage')),
    payload         TEXT     NOT NULL,                      -- JSON of what was written
    odoo_message_id TEXT,                                   -- null if dry-run
    dry_run         INTEGER  NOT NULL CHECK (dry_run IN (0, 1)),
    written_at      DATETIME NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT {_NOW},
    updated_at      DATETIME NOT NULL DEFAULT {_NOW},
    UNIQUE (standup_id, task_id, kind)
);
"""

# Keep updated_at honest on every mutable table. Recursive triggers are off by default, so the
# inner UPDATE does not re-fire this trigger.
_MUTABLE = ("team", "standup", "standup_update", "follow_up_question", "blocker", "odoo_write_log")
SCHEMA += "".join(
    f"""
CREATE TRIGGER IF NOT EXISTS {t}_touch AFTER UPDATE ON {t}
BEGIN
    UPDATE {t} SET updated_at = {_NOW} WHERE id = NEW.id;
END;
"""
    for t in _MUTABLE
)


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def add_team(
    db: sqlite3.Connection,
    team_id: str,
    name: str,
    timezone: str,
    odoo_project_ids: list[int] | None = None,
) -> None:
    """Register a team. Stand-ups reference it, so it must exist before the first open()."""
    db.execute(
        "INSERT INTO team (id, name, timezone, odoo_project_ids) VALUES (?, ?, ?, ?)",
        (team_id, name, timezone, json.dumps(odoo_project_ids or [])),
    )
    db.commit()
