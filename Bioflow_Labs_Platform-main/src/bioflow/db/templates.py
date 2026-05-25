# src/bioflow/db/templates.py
import json
import sqlite3
from typing import Any


def insert_template(
    conn: sqlite3.Connection,
    *,
    name: str | None,
    template: dict[str, Any],
    validation: dict[str, Any],
) -> int:
    raw_json = json.dumps(template, sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
    errors_json = json.dumps(validation.get("errors", []), ensure_ascii=False)

    cur = conn.execute(
        """
        INSERT INTO templates (name, json, template_version, is_valid, validation_errors, template_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            raw_json,
            str(template.get("template_version", "")),
            1 if validation.get("is_valid") else 0,
            errors_json,
            validation["template_hash"],
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_runnable_templates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT id, name, created_at, template_version, template_hash
            FROM templates
            WHERE is_valid = 1
            ORDER BY created_at DESC
            """
        ).fetchall()
    )


def delete_invalid_templates(conn: sqlite3.Connection) -> int:
    cur = conn.execute("DELETE FROM templates WHERE is_valid = 0")
    conn.commit()
    return int(cur.rowcount)


def fetch_template_by_id(conn: sqlite3.Connection, template_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()


def fetch_template_by_hash(conn: sqlite3.Connection, template_hash: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM templates WHERE template_hash = ?", (template_hash,)).fetchone()
