"""
SQLite setup. Call connect() to get a ready connection with the full schema.
Pass ":memory:" for tests and demo; pass a file path for production.
"""

from __future__ import annotations

import sqlite3

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS standup (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id     TEXT    NOT NULL,
    date        DATE    NOT NULL,
    state       TEXT    NOT NULL DEFAULT 'open',
    opened_at   DATETIME NOT NULL,
    closed_at   DATETIME,
    UNIQUE(team_id, date)
);

CREATE TABLE IF NOT EXISTS standup_update (
    id               INTEGER  PRIMARY KEY AUTOINCREMENT,
    standup_id       INTEGER  NOT NULL REFERENCES standup(id),
    member_id        TEXT     NOT NULL,
    raw_text         TEXT     NOT NULL,
    chat_message_id  TEXT     NOT NULL,
    extraction       TEXT,
    model_id         TEXT,
    prompt_version   TEXT,
    created_at       DATETIME NOT NULL,
    UNIQUE(standup_id, chat_message_id)
);

CREATE TABLE IF NOT EXISTS follow_up_question (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    standup_id    INTEGER  NOT NULL REFERENCES standup(id),
    member_id     TEXT     NOT NULL,
    trigger_rule  TEXT     NOT NULL,
    question_text TEXT     NOT NULL,
    asked_at      DATETIME NOT NULL,
    answered_at   DATETIME,
    answer_text   TEXT
);

CREATE TABLE IF NOT EXISTS blocker (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    standup_id   INTEGER  NOT NULL REFERENCES standup(id),
    member_id    TEXT     NOT NULL,
    task_id      TEXT,
    description  TEXT     NOT NULL,
    owner_id     TEXT,
    open         INTEGER  NOT NULL DEFAULT 1,
    resolved_at  DATETIME
);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
