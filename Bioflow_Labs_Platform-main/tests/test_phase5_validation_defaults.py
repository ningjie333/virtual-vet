import json
from pathlib import Path


def _load_baseline_template() -> dict:
    p = Path(__file__).parent / "fixtures" / "template_valid_baseline.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_phase5_defaults_injected_and_hash_equivalent():
    from bioflow.core.validate_template import validate_template

    t1 = _load_baseline_template()  # likely missing the new knobs

    r1 = validate_template(t1)
    assert r1["is_valid"]
    rp1 = r1["normalized_template"]["resolved_parameters"]
    assert rp1["vascular_tone_factor"] == 1.0
    assert rp1["blood_volume_factor"] == 1.0
    assert rp1.get("posture", "supine") == "supine"
    assert rp1["pooling_bias_enabled"] is False

    # Now make an explicit-neutral version and ensure hash matches.
    t2 = _load_baseline_template()
    t2.setdefault("resolved_parameters", {})["vascular_tone_factor"] = 1.0
    t2["resolved_parameters"]["blood_volume_factor"] = 1.0
    t2["resolved_parameters"]["pooling_bias_enabled"] = False

    r2 = validate_template(t2)
    assert r2["is_valid"]
    assert r1["template_hash"] == r2["template_hash"]
