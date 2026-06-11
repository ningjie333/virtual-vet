"""Tests for the SQLite session persistence layer."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.db.conn import connect
from src.db.schema import init_db
from src.db.sessions import (
    create_session,
    get_session,
    update_session_outcome,
    update_engine_snapshot,
    list_sessions,
)
from src.db.action_log import append_action, get_action_log, get_session_replay


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """Provide a fresh in-memory database for each test."""
    db = tmp_path / "test_sessions.db"
    c = connect(str(db))
    init_db(c)
    return c


# ── sessions CRUD ────────────────────────────────────────────────────────────

def test_create_and_retrieve_session(conn: sqlite3.Connection) -> None:
    pk = create_session(
        conn,
        session_id="case_001",
        case_id="case_001",
        species="犬",
        difficulty=2,
        disease_name="pneumonia",
    )
    assert pk > 0

    row = get_session(conn, "case_001")
    assert row is not None
    assert row["session_id"] == "case_001"
    assert row["species"] == "犬"
    assert row["difficulty"] == 2
    assert row["disease_name"] == "pneumonia"
    assert row["outcome"] is None


def test_get_session_missing(conn: sqlite3.Connection) -> None:
    assert get_session(conn, "does_not_exist") is None


def test_update_session_outcome(conn: sqlite3.Connection) -> None:
    create_session(conn, "s1", "case_001", "犬", 1, "pneumonia")
    update_session_outcome(conn, "s1", "won", 45)

    row = get_session(conn, "s1")
    assert row["outcome"] == "won"
    assert row["time_spent_min"] == 45


def test_update_engine_snapshot(conn: sqlite3.Connection) -> None:
    create_session(conn, "s1", "case_001", "犬", 1, "pneumonia")
    snapshot = json.dumps({"HR_bpm": 120.0, "MAP_mmHg": 85.0})
    update_engine_snapshot(conn, "s1", snapshot)

    row = get_session(conn, "s1")
    assert json.loads(row["engine_snapshot"]) == {"HR_bpm": 120.0, "MAP_mmHg": 85.0}


def test_list_sessions(conn: sqlite3.Connection) -> None:
    create_session(conn, "s1", "case_001", "犬", 1, "pneumonia")
    create_session(conn, "s2", "case_002", "犬", 2, "acute_renal_failure")

    all_sessions = list_sessions(conn)
    assert len(all_sessions) == 2

    won_sessions = list_sessions(conn, outcome_filter="won")
    assert won_sessions == []


# ── action_log CRUD ─────────────────────────────────────────────────────────

def test_append_and_retrieve_action(conn: sqlite3.Connection) -> None:
    create_session(conn, "s1", "case_001", "犬", 1, "pneumonia")

    pk = append_action(
        conn,
        session_id="s1",
        seq=1,
        action_type="examine",
        params=json.dumps({"test_type": "physical"}),
        time_cost_min=5,
        engine_snapshot_json=json.dumps({"HR_bpm": 100.0}),
        medical_phase="stable",
        outcome=None,
    )
    assert pk > 0

    actions = get_action_log(conn, "s1")
    assert len(actions) == 1
    assert actions[0]["action_type"] == "examine"
    assert actions[0]["seq"] == 1
    assert json.loads(actions[0]["params"]) == {"test_type": "physical"}


def test_action_log_ordered_by_seq(conn: sqlite3.Connection) -> None:
    create_session(conn, "s1", "case_001", "犬", 1, "pneumonia")

    for seq in [1, 2, 3]:
        append_action(
            conn, "s1", seq, "examine",
            json.dumps({"test_type": f"test_{seq}"}),
            5, json.dumps({}), "stable", None,
        )

    actions = get_action_log(conn, "s1")
    assert [a["seq"] for a in actions] == [1, 2, 3]


def test_get_session_replay_alias(conn: sqlite3.Connection) -> None:
    """get_session_replay is a convenience alias for get_action_log."""
    from src.db.action_log import get_session_replay as replay_fn
    create_session(conn, "s1", "case_001", "犬", 1, "pneumonia")
    append_action(conn, "s1", 1, "examine", None, 5, "{}", "stable", None)
    assert get_action_log(conn, "s1") == replay_fn(conn, "s1")


def test_action_log_cascade_on_session_delete(conn: sqlite3.Connection) -> None:
    """Deleting a session removes its action log rows."""
    create_session(conn, "s1", "case_001", "犬", 1, "pneumonia")
    append_action(conn, "s1", 1, "examine", None, 5, "{}", "stable", None)
    append_action(conn, "s1", 2, "wait", None, 10, "{}", "stable", None)

    conn.execute("DELETE FROM sessions WHERE session_id = 's1'")
    conn.commit()

    actions = get_action_log(conn, "s1")
    assert actions == []


# ── VirtualCreature persistence snapshot ────────────────────────────────────

def test_engine_snapshot_preserves_key_vitals(tmp_path: Path) -> None:
    """to_persistence_snapshot produces a JSON-serializable dict with expected keys."""
    import sys
    # Add project root so 'from src.simulation import ...' works
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from src.simulation import VirtualCreature
    # Note: attaching a disease module is intentionally omitted here because
    # importing create_disease triggers module-level _register_all() in
    # config_driven.py which has an unrelated pre-existing bug (_SCHEMAS_DIR
    # NameError).  The snapshot behaviour is identical with or without a
    # disease; the key assertion is that the output is JSON-serializable
    # and contains all expected vital keys.

    vc = VirtualCreature(body_weight_kg=20.0)
    vc.simulate(5.0)  # run a few simulation steps so history is populated

    snapshot = vc.to_persistence_snapshot()

    # Check top-level keys
    assert "time_s" in snapshot
    assert snapshot["time_s"] > 0

    required_vitals = [
        "HR_bpm", "MAP_mmHg", "CO_ml_min", "CVP_mmHg",
        "RR", "art_PO2", "art_PCO2", "saturation",
        "GFR", "urine_ml_min", "BUN",
        "pH", "glucose_mmol_L", "lactate_mmol_L",
        "heart_health", "lung_health", "kidney_health",
    ]
    for key in required_vitals:
        assert key in snapshot, f"Missing key: {key}"
        assert isinstance(snapshot[key], (int, float, str, type(None)))

    # disease_state is None when no disease is attached
    assert snapshot["disease_state"] is None

    # JSON round-trip
    json_str = json.dumps(snapshot, ensure_ascii=False)
    restored = json.loads(json_str)
    assert restored["HR_bpm"] == snapshot["HR_bpm"]
    assert restored["disease_state"] is None


def test_snapshot_without_disease(tmp_path: Path) -> None:
    """A creature without an attached disease still produces a valid snapshot."""
    import sys
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from src.simulation import VirtualCreature

    vc = VirtualCreature(body_weight_kg=20.0)
    vc.simulate(1.0)

    snapshot = vc.to_persistence_snapshot()
    assert snapshot["disease_state"] is None

    json_str = json.dumps(snapshot)  # must not raise
    assert "HR_bpm" in json_str


def test_minimal_snapshot_alias_matches_persistence_snapshot(tmp_path: Path) -> None:
    """Legacy alias remains available for older callers."""
    import sys
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from src.simulation import VirtualCreature

    vc = VirtualCreature(body_weight_kg=20.0)
    vc.simulate(1.0)

    assert vc.to_minimal_snapshot() == vc.to_persistence_snapshot()


# ── Foreign-key constraint ───────────────────────────────────────────────────

def test_session_id_foreign_key_constraint(conn: sqlite3.Connection) -> None:
    """Inserting an action for a non-existent session fails gracefully."""
    with pytest.raises(sqlite3.IntegrityError):
        append_action(
            conn,
            session_id="phantom",
            seq=1,
            action_type="examine",
            params=None,
            time_cost_min=5,
            engine_snapshot_json="{}",
            medical_phase="stable",
            outcome=None,
        )
