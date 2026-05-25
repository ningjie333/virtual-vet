import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_blood_volume_factor_1_is_no_change_in_normalized_template():
    from bioflow.core.validate_template import validate_template

    t = load("template_valid_baseline.json")
    t.setdefault("resolved_parameters", {})["blood_volume_factor"] = 1.0

    out = validate_template(t)
    assert out["is_valid"] is True

    norm = out["normalized_template"]
    # For factor=1.0, normalized should match original values
    assert norm["initial_state"]["V_art_ml"] == t["initial_state"]["V_art_ml"]
    assert norm["initial_state"]["V_ven_ml"] == t["initial_state"]["V_ven_ml"]
    assert norm["resolved_parameters"]["total_blood_volume_ml"] == t["resolved_parameters"]["total_blood_volume_ml"]


def test_blood_volume_factor_scales_initial_volumes_and_tbv():
    from bioflow.core.validate_template import validate_template

    t = load("template_valid_baseline.json")
    t.setdefault("resolved_parameters", {})["blood_volume_factor"] = 0.8

    out = validate_template(t)
    assert out["is_valid"] is True

    norm = out["normalized_template"]

    assert norm["initial_state"]["V_art_ml"] == float(
        t["initial_state"]["V_art_ml"]) * 0.8
    assert norm["initial_state"]["V_ven_ml"] == float(
        t["initial_state"]["V_ven_ml"]) * 0.8
    assert norm["resolved_parameters"]["total_blood_volume_ml"] == float(
        t["resolved_parameters"]["total_blood_volume_ml"]) * 0.8
