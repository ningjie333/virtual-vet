import json
from pathlib import Path


def load_baseline() -> dict:
    return json.loads(Path("tests/fixtures/template_valid_baseline.json").read_text(encoding="utf-8"))


def _pick_summary(out: dict) -> dict:
    if "summary_json" in out:
        return out["summary_json"]
    if "summary" in out:
        return out["summary"]
    raise KeyError(f"No summary field. Keys={list(out.keys())}")


def test_posture_supine_is_neutral(tmp_path):
    from bioflow.engine.runner import run_template

    db = tmp_path / "bioflow.db"

    t0 = load_baseline()

    t1 = load_baseline()
    t1.setdefault("resolved_parameters", {})["posture"] = "supine"

    a = run_template(template=t0, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)
    b = run_template(template=t1, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)

    assert a["template_hash"] == b["template_hash"]
    assert _pick_summary(a) == _pick_summary(b)


def test_posture_standing_changes_outputs_and_is_deterministic(tmp_path):
    from bioflow.engine.runner import run_template

    db = tmp_path / "bioflow.db"

    t = load_baseline()
    t.setdefault("resolved_parameters", {})["posture"] = "standing"

    a = run_template(template=t, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)
    b = run_template(template=t, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)

    assert a["template_hash"] == b["template_hash"]
    assert _pick_summary(a) == _pick_summary(b)

    base = run_template(template=load_baseline(), db_path=db,
                        dt=0.01, duration_s=1.0, sample_rate_hz=10.0)
    assert a["template_hash"] != base["template_hash"]
    assert _pick_summary(a) != _pick_summary(base)
