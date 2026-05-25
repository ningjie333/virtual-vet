import json
from pathlib import Path


def load_baseline() -> dict:
    return json.loads(Path("tests/fixtures/template_valid_baseline.json").read_text(encoding="utf-8"))


def _pick_summary(out: dict) -> dict:
    """
    Runner returns one of these. We support both without changing runner.
    """
    if "summary_json" in out:
        return out["summary_json"]
    if "summary" in out:
        return out["summary"]
    raise KeyError(
        f"Runner output has no summary field. Keys={list(out.keys())}")


def test_hypovolemia_factor_1_matches_baseline(tmp_path):
    from bioflow.engine.runner import run_template

    db = tmp_path / "bioflow.db"

    t0 = load_baseline()

    t1 = load_baseline()
    t1.setdefault("resolved_parameters", {})["blood_volume_factor"] = 1.0

    a = run_template(template=t0, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)
    b = run_template(template=t1, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)

    # With normalization + defaults, these should be identical effective templates.
    assert a["template_hash"] == b["template_hash"]

    # And deterministic outputs should match exactly.
    assert _pick_summary(a) == _pick_summary(b)


def test_hypovolemia_changes_outputs_and_is_deterministic(tmp_path):
    from bioflow.engine.runner import run_template

    db = tmp_path / "bioflow.db"

    t_hypo = load_baseline()
    t_hypo.setdefault("resolved_parameters", {})["blood_volume_factor"] = 0.8

    a = run_template(template=t_hypo, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)
    b = run_template(template=t_hypo, db_path=db, dt=0.01,
                     duration_s=1.0, sample_rate_hz=10.0)

    # Determinism: same template -> same summary
    assert a["template_hash"] == b["template_hash"]
    assert _pick_summary(a) == _pick_summary(b)

    # Effect: should differ from baseline
    t_base = load_baseline()
    base = run_template(template=t_base, db_path=db, dt=0.01,
                        duration_s=1.0, sample_rate_hz=10.0)

    assert a["template_hash"] != base["template_hash"]
    assert _pick_summary(a) != _pick_summary(base)
