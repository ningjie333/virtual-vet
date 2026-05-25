import json
from pathlib import Path
from bioflow.core.validate_template import validate_template

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_valid_template_passes():
    out = validate_template(load("template_valid_baseline.json"))
    assert out["is_valid"] is True
    assert out["errors"] == []
    assert isinstance(out["template_hash"], str) and len(
        out["template_hash"]) == 64


def test_invalid_template_fails():
    out = validate_template(load("template_invalid_missing_field.json"))
    assert out["is_valid"] is False
    assert len(out["errors"]) > 0


def test_hash_is_deterministic():
    t = load("template_valid_baseline.json")
    a = validate_template(t)["template_hash"]
    b = validate_template(t)["template_hash"]
    assert a == b


def test_vascular_tone_factor_defaults_to_neutral():
    t = load("template_valid_baseline.json")

    # Ensure the knob is missing (simulate old Phase 4.1 fixture)
    t.setdefault("resolved_parameters", {}).pop("vascular_tone_factor", None)

    out = validate_template(t)
    assert out["is_valid"] is True
    assert out["normalized_template"]["resolved_parameters"]["vascular_tone_factor"] == 1.0


def test_vascular_tone_factor_bounds_fail():
    t = load("template_valid_baseline.json")
    t.setdefault("resolved_parameters", {})["vascular_tone_factor"] = 0.0

    out = validate_template(t)
    assert out["is_valid"] is False
    assert len(out["errors"]) > 0


def test_blood_volume_factor_defaults_to_neutral():
    t = load("template_valid_baseline.json")
    t.setdefault("resolved_parameters", {}).pop("blood_volume_factor", None)

    out = validate_template(t)
    assert out["is_valid"] is True
    assert out["normalized_template"]["resolved_parameters"]["blood_volume_factor"] == 1.0


def test_blood_volume_factor_bounds_fail():
    t = load("template_valid_baseline.json")
    t.setdefault("resolved_parameters", {})["blood_volume_factor"] = 0.0

    out = validate_template(t)
    assert out["is_valid"] is False


def test_posture_defaults_to_supine():
    t = load("template_valid_baseline.json")
    t.setdefault("resolved_parameters", {}).pop("posture", None)

    out = validate_template(t)
    assert out["is_valid"] is True
    assert out["normalized_template"]["resolved_parameters"]["posture"] == "supine"


def test_posture_invalid_value_fails():
    t = load("template_valid_baseline.json")
    t.setdefault("resolved_parameters", {})["posture"] = "upside_down"

    out = validate_template(t)
    assert out["is_valid"] is False


def test_pooling_bias_enabled_defaults_false():
    t = load("template_valid_baseline.json")
    t.setdefault("resolved_parameters", {}).pop("pooling_bias_enabled", None)

    out = validate_template(t)
    assert out["is_valid"] is True
    assert out["normalized_template"]["resolved_parameters"]["pooling_bias_enabled"] is False
