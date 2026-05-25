import json

from bioflow.db.conn import connect
from bioflow.db.schema import init_db
from bioflow.db.templates import (
    insert_template,
    list_runnable_templates,
    delete_invalid_templates,
    fetch_template_by_id,
    fetch_template_by_hash,
)
from bioflow.core.validate_template import validate_template


def _valid_template_phase41() -> dict:
    return {
        "template_version": "2.0",
        "resolved_parameters": {
            "total_blood_volume_ml": 5000,
            "posture": "supine",
            "baseline": {"P_art_mmHg": 95.0, "P_ven_mmHg": 5.0},
            "pump": {"Q_ml_per_s": 83.0},
            "compartments": {
                "arterial": {"C_ml_per_mmHg": 2.0, "V0_ml": 700.0},
                "venous": {"C_ml_per_mmHg": 30.0, "V0_ml": 2500.0},
            },
            "beds": [
                {
                    "bed_id": "brain",
                    "R_mmHg_s_per_ml": 1.0,
                    "C_ml_per_mmHg": 2.0,
                    "unstressed_volume_ml": 200,
                }
            ],
        },
        "initial_state": {
            "V_art_ml": 1500,
            "V_ven_ml": 3500,
            "P_art_mmHg": 95.0,
            "P_ven_mmHg": 5.0,
        },
    }


def _invalid_template_missing_required_fields() -> dict:
    # Invalid under Phase 4.1 schema: missing beds + pump + compartments
    return {
        "template_version": "2.0",
        "resolved_parameters": {
            "total_blood_volume_ml": 5000,
            "posture": "supine",
            "baseline": {"P_art_mmHg": 95.0, "P_ven_mmHg": 5.0},
        },
        "initial_state": {"P_art_mmHg": 95.0, "P_ven_mmHg": 5.0},
    }


def test_db_creates_cleanly(tmp_path):
    conn = connect(tmp_path / "bioflow.db")
    init_db(conn)
    # smoke query
    conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()


def test_insert_invalid_template_stored_flagged_not_runnable(tmp_path):
    conn = connect(tmp_path / "bioflow.db")
    init_db(conn)

    invalid = _invalid_template_missing_required_fields()
    v = validate_template(invalid)
    tid = insert_template(conn, name="bad", template=invalid, validation=v)

    row = fetch_template_by_id(conn, tid)
    assert row is not None
    assert row["is_valid"] == 0

    runnable = list_runnable_templates(conn)
    assert len(runnable) == 0


def test_delete_invalid_templates_only_invalid_removed(tmp_path):
    conn = connect(tmp_path / "bioflow.db")
    init_db(conn)

    valid = _valid_template_phase41()
    invalid = _invalid_template_missing_required_fields()

    t1 = insert_template(conn, name="good", template=valid,
                         validation=validate_template(valid))
    t2 = insert_template(conn, name="bad", template=invalid,
                         validation=validate_template(invalid))

    deleted = delete_invalid_templates(conn)
    assert deleted == 1
    assert fetch_template_by_id(conn, t2) is None
    assert fetch_template_by_id(conn, t1) is not None


def test_fetch_by_hash(tmp_path):
    conn = connect(tmp_path / "bioflow.db")
    init_db(conn)

    valid = _valid_template_phase41()
    v = validate_template(valid)
    tid = insert_template(conn, name="good", template=valid, validation=v)

    row = fetch_template_by_hash(conn, v["template_hash"])
    assert row is not None
    assert row["id"] == tid
