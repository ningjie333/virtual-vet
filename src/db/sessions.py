"""CRUD operations for game sessions."""

import sqlite3
from typing import Any


def create_session(
    conn: sqlite3.Connection,
    session_id: str,
    case_id: str,
    species: str | None,
    difficulty: int | None,
    disease_name: str | None,
) -> int:
    """
    Insert a new session row and return its integer PK.

    Uses INSERT OR REPLACE so that re-creating a session with the same
    session_id (e.g. replaying the same case) updates the existing row
    instead of raising a UNIQUE constraint violation.
    """
    cursor = conn.execute(
        """
        INSERT OR REPLACE INTO sessions (session_id, case_id, species, difficulty, disease_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, case_id, species, difficulty, disease_name),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def get_session(conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    """
    Return the session row for session_id, or None if not found.
    """
    cursor = conn.execute(
        "SELECT * FROM sessions WHERE session_id = ?",
        (session_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(row)


def update_session_outcome(
    conn: sqlite3.Connection,
    session_id: str,
    outcome: str,
    time_spent_min: int,
) -> None:
    """
    Record the final outcome and time spent for a session.
    """
    conn.execute(
        """
        UPDATE sessions
        SET outcome = ?, time_spent_min = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE session_id = ?
        """,
        (outcome, time_spent_min, session_id),
    )
    conn.commit()


def update_engine_snapshot(
    conn: sqlite3.Connection,
    session_id: str,
    engine_snapshot_json: str,
) -> None:
    """
    Persist a JSON snapshot of the VirtualCreature state.
    """
    conn.execute(
        """
        UPDATE sessions
        SET engine_snapshot = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE session_id = ?
        """,
        (engine_snapshot_json, session_id),
    )
    conn.commit()


def list_sessions(
    conn: sqlite3.Connection,
    outcome_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return all sessions, optionally filtered by outcome.
    """
    if outcome_filter:
        cursor = conn.execute(
            "SELECT * FROM sessions WHERE outcome = ? ORDER BY created_at DESC",
            (outcome_filter,),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC",
        )
    return [dict(row) for row in cursor.fetchall()]