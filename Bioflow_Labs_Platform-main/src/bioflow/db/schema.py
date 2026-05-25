# src/bioflow/db/schema.py
import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  json TEXT NOT NULL,
  template_version TEXT NOT NULL,
  is_valid INTEGER NOT NULL CHECK (is_valid IN (0,1)),
  validation_errors TEXT,
  template_hash TEXT NOT NULL UNIQUE
);
/*
Example row (templates):
{
  id: 1,
  name: "Young Athlete Baseline",
  created_at: "2025-12-20T01:23:45.123Z",
  json: "{...canonical template json...}",
  template_version: "2.0",
  is_valid: 1,
  validation_errors: "[]",
  template_hash: "9ed165ee766fe8ff8fdf2d1ab8441a1ef5cd0adb0967b95f7ebab10101b5c9f8"
}
*/

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ended_at TEXT,
  template_hash TEXT NOT NULL,
  template_snapshot_json TEXT NOT NULL,
  engine_version TEXT NOT NULL,
  run_config_json TEXT NOT NULL,
  summary_json TEXT,
  FOREIGN KEY(template_hash) REFERENCES templates(template_hash)
);
/*
Example row (runs):
{
  id: 42,
  started_at: "2025-12-20T02:00:00.000Z",
  ended_at: "2025-12-20T02:00:01.500Z",
  template_hash: "9ed165ee...",
  template_snapshot_json: "{...}",
  engine_version: "2.0.0",
  run_config_json: "{\\"dt\\":0.01,\\"duration\\":1.0,\\"sample_rate\\":10}",
  summary_json: "{\\"ok\\":true}"
}
*/

CREATE TABLE IF NOT EXISTS run_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  t_ms INTEGER NOT NULL,
  global_state_json TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
);
/*
Example row (run_samples):
{
  id: 101,
  run_id: 42,
  t_ms: 100,
  global_state_json: "{\\"P_art\\":90.0,\\"Q\\":5.1}"
}
*/

CREATE TABLE IF NOT EXISTS run_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  t_ms INTEGER NOT NULL,
  level TEXT NOT NULL,
  code TEXT NOT NULL,
  message TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
);
/*
Example row (run_events):
{
  id: 301,
  run_id: 42,
  t_ms: 0,
  level: "INFO",
  code: "boot",
  message: "run started"
}
*/

CREATE INDEX IF NOT EXISTS idx_templates_is_valid ON templates(is_valid);
CREATE INDEX IF NOT EXISTS idx_samples_run_id_t ON run_samples(run_id, t_ms);
CREATE INDEX IF NOT EXISTS idx_events_run_id_t ON run_events(run_id, t_ms);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
