"""CRUD operations for the action log."""

import sqlite3
from typing import Any


def append_action(
    conn: sqlite3.Connection,
    session_id: str,
    seq: int,
    action_type: str,
    params: str | None,
    time_cost_min: int | None,
    engine_snapshot_json: str | None,
    medical_phase: str | None,
    outcome: str | None,
) -> int:
    """
    Append a single action row and return its integer PK.
    """
    cursor = conn.execute(
        """
        INSERT INTO action_log
            (session_id, seq, action_type, params, time_cost_min,
             engine_snapshot, medical_phase, outcome)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id, seq, action_type, params, time_cost_min,
            engine_snapshot_json, medical_phase, outcome,
        ),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def get_action_log(
    conn: sqlite3.Connection,
    session_id: str,
) -> list[dict[str, Any]]:
    """
    Return all action rows for session_id, sorted by seq ascending.
    """
    cursor = conn.execute(
        "SELECT * FROM action_log WHERE session_id = ? ORDER BY seq ASC",
        (session_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


# Convenience alias
get_session_replay = get_action_log