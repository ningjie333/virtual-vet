"""DDL — create sessions and action_log tables."""

import sqlite3


def init_db(conn: sqlite3.Connection) -> None:
    """
    Create all required tables if they do not exist.

    Schema:
        sessions  — one row per game session
        action_log — one row per player action; session_id references sessions
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT    UNIQUE NOT NULL,
            case_id         TEXT    NOT NULL,
            species         TEXT,
            difficulty      INTEGER,
            disease_name    TEXT,
            outcome         TEXT    CHECK (outcome IN ('won','lost','ongoing')),
            time_spent_min  INTEGER,
            engine_snapshot TEXT,
            created_at      TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at      TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );

        CREATE TABLE IF NOT EXISTS action_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT    NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            seq             INTEGER NOT NULL,
            action_type     TEXT    NOT NULL,
            params          TEXT,
            time_cost_min   INTEGER,
            engine_snapshot TEXT,
            medical_phase   TEXT,
            outcome         TEXT,
            recorded_at      TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );

        CREATE INDEX IF NOT EXISTS idx_action_session_seq
            ON action_log(session_id, seq);

        CREATE INDEX IF NOT EXISTS idx_sessions_outcome
            ON sessions(outcome);
    """)
    conn.commit()