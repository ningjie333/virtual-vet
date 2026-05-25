# src/bioflow/db/runs.py
import json
import sqlite3
from typing import Any


def create_run(
    conn: sqlite3.Connection,
    *,
    template_hash: str,
    template_snapshot: dict[str, Any],
    engine_version: str,
    run_config: dict[str, Any],
) -> int:
    snap_json = json.dumps(template_snapshot, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    cfg_json = json.dumps(run_config, sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)

    cur = conn.execute(
        """
        INSERT INTO runs (template_hash, template_snapshot_json, engine_version, run_config_json)
        VALUES (?, ?, ?, ?)
        """,
        (template_hash, snap_json, engine_version, cfg_json),
    )
    conn.commit()
    return int(cur.lastrowid)


def append_sample(conn: sqlite3.Connection, *, run_id: int, t_ms: int, global_state: dict[str, Any]) -> None:
    state_json = json.dumps(global_state, sort_keys=True,
                            separators=(",", ":"), ensure_ascii=False)
    conn.execute(
        "INSERT INTO run_samples (run_id, t_ms, global_state_json) VALUES (?, ?, ?)",
        (run_id, int(t_ms), state_json),
    )


def append_event(conn: sqlite3.Connection, *, run_id: int, t_ms: int, level: str, code: str, message: str) -> None:
    conn.execute(
        "INSERT INTO run_events (run_id, t_ms, level, code, message) VALUES (?, ?, ?, ?, ?)",
        (run_id, int(t_ms), level, code, message),
    )


def finalize_run(conn: sqlite3.Connection, *, run_id: int, summary: dict[str, Any]) -> None:
    summary_json = json.dumps(summary, sort_keys=True,
                              separators=(",", ":"), ensure_ascii=False)
    conn.execute(
        """
        UPDATE runs
        SET ended_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            summary_json = ?
        WHERE id = ?
        """,
        (summary_json, int(run_id)),
    )
    conn.commit()


def commit_buffer(conn: sqlite3.Connection) -> None:
    conn.commit()
