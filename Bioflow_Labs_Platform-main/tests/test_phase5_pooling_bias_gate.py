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


def test_pooling_bias_gate_off_matches_current_standing(tmp_path):
    from bioflow.engine.runner import run_template

    db = tmp_path / "bioflow.db"

    t = load_baseline()
    rp = t.setdefault("resolved_parameters", {})
    rp["posture"] = "standing"
    rp["pooling_bias_enabled"] = False

    a = run_template(template=t, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)
    b = run_template(template=t, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)

    assert a["template_hash"] == b["template_hash"]
    assert _pick_summary(a) == _pick_summary(b)


def test_pooling_bias_gate_on_changes_standing_when_bias_present(tmp_path):
    from bioflow.engine.runner import run_template

    db = tmp_path / "bioflow.db"

    # Standing baseline (gate off)
    t_off = load_baseline()
    rp_off = t_off.setdefault("resolved_parameters", {})
    rp_off["posture"] = "standing"
    rp_off["pooling_bias_enabled"] = False

    # Standing with bias (gate on)
    t_on = load_baseline()
    rp_on = t_on.setdefault("resolved_parameters", {})
    rp_on["posture"] = "standing"
    rp_on["pooling_bias_enabled"] = True

    # Add a nonzero pooling_bias to at least one bed
    rp_on["beds"][0]["pooling_bias"] = 4.0

    out_off = run_template(template=t_off, db_path=db,
                           dt=0.01, duration_s=1.0, sample_rate_hz=10.0)
    out_on1 = run_template(template=t_on, db_path=db,
                           dt=0.01, duration_s=1.0, sample_rate_hz=10.0)
    out_on2 = run_template(template=t_on, db_path=db,
                           dt=0.01, duration_s=1.0, sample_rate_hz=10.0)

    # Determinism
    assert out_on1["template_hash"] == out_on2["template_hash"]
    assert _pick_summary(out_on1) == _pick_summary(out_on2)

    # Effect
    assert out_on1["template_hash"] != out_off["template_hash"]
    assert _pick_summary(out_on1) != _pick_summary(out_off)
