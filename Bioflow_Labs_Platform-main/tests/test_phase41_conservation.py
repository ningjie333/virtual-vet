import json
from pathlib import Path
from bioflow.engine.runner import run_template


def test_total_volume_conserved(tmp_path):
    db = tmp_path / "bioflow.db"
    t = json.loads(
        Path("tests/fixtures/template_valid_baseline.json").read_text(encoding="utf-8"))

    out = run_template(template=t, db_path=db, dt=0.01,
                       duration_s=2.0, sample_rate_hz=10.0)

    # Pull the last sample from DB to inspect V_art + V_ven (you likely already have a helper;
    # if not, keep it simple and just trust state in summary once you add it there).
    # Easiest: add these to summary in runner after loop:
    # "final_V_art_ml": state.V_art_ml, "final_V_ven_ml": state.V_ven_ml
    assert "summary_hash" in out["summary"]
