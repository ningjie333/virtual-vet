from bioflow.db.conn import connect
from bioflow.db.schema import init_db
from bioflow.db.templates import insert_template
from bioflow.db.runs import create_run, append_sample, append_event, finalize_run, commit_buffer
from bioflow.core.validate_template import validate_template
from bioflow.core.version import ENGINE_VERSION


def test_run_write_path_works(tmp_path):
    conn = connect(tmp_path / "bioflow.db")
    init_db(conn)

    template = {
        "template_version": "2.0",
        "resolved_parameters": {"total_blood_volume_ml": 5000},
        "beds": [{"name": "brain", "R": 1.0, "C": 2.0, "unstressed_volume_ml": 200}]
    }
    v = validate_template(template)
    insert_template(conn, name="good", template=template, validation=v)

    run_id = create_run(
        conn,
        template_hash=v["template_hash"],
        template_snapshot=template,
        engine_version=ENGINE_VERSION,
        run_config={"dt": 0.01, "duration": 1.0, "sample_rate": 10},
    )

    append_sample(conn, run_id=run_id, t_ms=0, global_state={"P_art": 90.0})
    append_event(conn, run_id=run_id, t_ms=0, level="INFO",
                 code="boot", message="run started")
    commit_buffer(conn)

    finalize_run(conn, run_id=run_id, summary={"ok": True})
    row = conn.execute(
        "SELECT ended_at, summary_json FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row["ended_at"] is not None
    assert "ok" in row["summary_json"]
