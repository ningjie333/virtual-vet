import json
from pathlib import Path

from bioflow.db.conn import connect
from bioflow.db.schema import init_db
from bioflow.db.templates import insert_template
from bioflow.core.validate_template import validate_template
from bioflow.engine.runner import run_template, run_template_by_db_id, run_template_from_json_file, RunnerError


def make_valid_template():
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
                {"bed_id": "brain", "R_mmHg_s_per_ml": 1.0}
            ],
        },
        "initial_state": {
            "V_art_ml": 1500,
            "V_ven_ml": 3500,
            "P_art_mmHg": 95.0,
            "P_ven_mmHg": 5.0,
        },
    }


def make_invalid_template():
    # Missing required field: resolved_parameters.beds
    return {
        "template_version": "2.0",
        "resolved_parameters": {
            "total_blood_volume_ml": 5000,
            "posture": "supine",
            "baseline": {"P_art_mmHg": 100.0, "P_ven_mmHg": 4.0},
        },
        "initial_state": {"P_art_mmHg": 100.0, "P_ven_mmHg": 4.0},
    }


def test_same_template_twice_identical_summary_hash(tmp_path):
    db = tmp_path / "bioflow.db"
    t = make_valid_template()

    a = run_template(template=t, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)
    b = run_template(template=t, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)

    assert a["summary"]["summary_hash"] == b["summary"]["summary_hash"]


def test_run_invalid_template_hard_fails_no_run_row_created(tmp_path):
    db = tmp_path / "bioflow.db"
    t = make_invalid_template()

    # ensure DB exists so we can inspect it after
    conn = connect(db)
    init_db(conn)

    try:
        run_template(template=t, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)
        assert False, "Expected RunnerError"
    except RunnerError:
        pass

    # no run rows created because we fail before create_run()
    n = conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
    assert n == 0


def test_run_from_db_id_and_json_path(tmp_path):
    db = tmp_path / "bioflow.db"
    conn = connect(db)
    init_db(conn)

    t = make_valid_template()
    v = validate_template(t)
    tid = insert_template(conn, name="good", template=t, validation=v)

    out1 = run_template_by_db_id(
        template_id=tid, db_path=db, dt=0.01, duration_s=1.0, sample_rate_hz=10.0)
    assert out1["template_hash"] == v["template_hash"]

    json_path = tmp_path / "t.json"
    json_path.write_text(json.dumps(t), encoding="utf-8")
    out2 = run_template_from_json_file(
        json_path=json_path, db_path=db, dt=0.01, duration_s=1.0, sample_rate_hz=10.0)
    assert out2["template_hash"] == v["template_hash"]


def test_same_template_twice_identical_summary_hash(tmp_path):
    db = tmp_path / "bioflow.db"
    t = make_valid_template()

    a = run_template(template=t, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)
    b = run_template(template=t, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)

    assert a["summary"]["summary_hash"] == b["summary"]["summary_hash"]


def test_run_invalid_template_hard_fails_no_run_row_created(tmp_path):
    db = tmp_path / "bioflow.db"
    t = make_invalid_template()

    # ensure DB exists so we can inspect it after
    conn = connect(db)
    init_db(conn)

    try:
        run_template(template=t, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)
        assert False, "Expected RunnerError"
    except RunnerError:
        pass

    # no run rows created because we fail before create_run()
    n = conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
    assert n == 0


def test_run_from_db_id_and_json_path(tmp_path):
    db = tmp_path / "bioflow.db"
    conn = connect(db)
    init_db(conn)

    t = make_valid_template()
    v = validate_template(t)
    tid = insert_template(conn, name="good", template=t, validation=v)

    out1 = run_template_by_db_id(
        template_id=tid, db_path=db, dt=0.01, duration_s=1.0, sample_rate_hz=10.0)
    assert out1["template_hash"] == v["template_hash"]

    json_path = tmp_path / "t.json"
    json_path.write_text(json.dumps(t), encoding="utf-8")
    out2 = run_template_from_json_file(
        json_path=json_path, db_path=db, dt=0.01, duration_s=1.0, sample_rate_hz=10.0)
    assert out2["template_hash"] == v["template_hash"]
