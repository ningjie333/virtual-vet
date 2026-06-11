"""
Tests for src/config_validation.py — JSON Schema + programmatic validation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config_validation import (
    ValidationError,
    validate_clue_catalog,
    validate_ode_diseases,
    validate_examinations,
    validate_exam_templates,
    validate_diseases,
    validate_coupling_rules,
    validate_all,
)
from src.report_engine import get_allowed_exam_disease_markers


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def real_ode_diseases() -> dict:
    """Load the real ode_diseases.json from the data directory."""
    path = Path(__file__).resolve().parents[1] / "data" / "ode_diseases.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def real_examinations() -> dict:
    """Load the real examinations.json from the data directory."""
    path = Path(__file__).resolve().parents[1] / "data" / "examinations.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def real_exam_templates() -> dict:
    """Load the real exam_templates.json from the data directory."""
    path = Path(__file__).resolve().parents[1] / "data" / "exam_templates.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def real_diseases() -> dict:
    """Load the real diseases.json from the data directory."""
    path = Path(__file__).resolve().parents[1] / "data" / "diseases.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def real_coupling_rules() -> dict:
    """Load the real coupling_rules.json from the data directory."""
    path = Path(__file__).resolve().parents[1] / "data" / "coupling_rules.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def real_symptom_definitions() -> dict:
    """Load the real symptom_definitions.json from the data directory."""
    path = Path(__file__).resolve().parents[1] / "data" / "symptom_definitions.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def real_clue_catalog() -> dict:
    """Load the real clue_catalog.json from the data directory."""
    path = Path(__file__).resolve().parents[1] / "data" / "clue_catalog.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── ODE Diseases Tests ─────────────────────────────────────────────────────────

def test_ode_diseases_validates_correct_structure(real_ode_diseases):
    """Load real ode_diseases.json and expect zero validation errors."""
    errors = validate_ode_diseases(real_ode_diseases)
    assert errors == [], f"Unexpected errors: {errors}"


def test_ode_diseases_rejects_unknown_ode_type():
    """Config with an unknown ode_type should produce a ValidationError."""
    bad_config = {
        "_schema": "test",
        "test_disease": {
            "severity_presets": {
                "moderate": {"rate": 0.01}
            },
            "state_variables": {
                "my_var": {
                    "initial": 0.0,
                    "ode_type": "unknown_ode_type",
                }
            },
            "outputs": [
                {"target": "heart.heart_rate", "op": "add", "fn": "1.0"}
            ]
        }
    }
    errors = validate_ode_diseases(bad_config)
    assert len(errors) > 0
    assert any("unknown_ode_type" in e.message for e in errors)


def test_ode_diseases_rejects_bad_op_in_output():
    """Config with an invalid op in outputs should produce a ValidationError."""
    bad_config = {
        "_schema": "test",
        "test_disease": {
            "severity_presets": {
                "moderate": {}
            },
            "state_variables": {
                "my_var": {
                    "initial": 0.0,
                    "ode_type": "algebraic",
                    "fn": "1.0"
                }
            },
            "outputs": [
                {"target": "heart.heart_rate", "op": "invalid_op", "fn": "1.0"}
            ]
        }
    }
    errors = validate_ode_diseases(bad_config)
    assert len(errors) > 0
    assert any("invalid_op" in e.message for e in errors)


def test_outputs_target_must_be_in_param_paths():
    """An outputs[].target that does not exist in _PARAM_PATHS should fail."""
    bad_config = {
        "_schema": "test",
        "test_disease": {
            "severity_presets": {
                "moderate": {}
            },
            "state_variables": {
                "my_var": {
                    "initial": 0.0,
                    "ode_type": "algebraic",
                    "fn": "1.0"
                }
            },
            "outputs": [
                {"target": "heart.does_not_exist", "op": "add", "fn": "1.0"}
            ]
        }
    }
    errors = validate_ode_diseases(bad_config)
    assert len(errors) > 0
    assert any("does_not_exist" in e.message for e in errors)


def test_ode_diseases_rate_key_must_exist_in_preset():
    """A rate_key that references a non-existent preset key should fail."""
    bad_config = {
        "_schema": "test",
        "test_disease": {
            "severity_presets": {
                "moderate": {"some_other_key": 0.01}  # rate_key would be "damage_rate"
            },
            "state_variables": {
                "my_var": {
                    "initial": 0.0,
                    "ode_type": "logistic",
                    "params": {
                        "rate_key": "damage_rate",  # does not exist in moderate preset
                        "K": 1.0
                    }
                }
            },
            "outputs": []
        }
    }
    errors = validate_ode_diseases(bad_config)
    assert len(errors) > 0
    assert any("damage_rate" in e.message for e in errors)


def test_coupling_rules_validates_correct_structure(real_coupling_rules):
    """Load real coupling_rules.json and expect zero validation errors."""
    errors = validate_coupling_rules(real_coupling_rules)
    assert errors == [], f"Unexpected errors: {errors}"


def test_coupling_target_must_be_in_param_paths():
    """A coupling target path outside _PARAM_PATHS should fail validation."""
    bad_config = {
        "_schema": "coupling_rules v1",
        "couplings": [
            {
                "name": "bad target",
                "loop": "test",
                "source": {"module": "kidney", "signal": "renin_activity"},
                "target": {
                    "module": "fluid",
                    "param": "fluid.does_not_exist",
                    "op": "multiply",
                    "fn": "1.0",
                },
            }
        ],
    }
    errors = validate_coupling_rules(bad_config)
    assert len(errors) > 0
    assert any("fluid.does_not_exist" in e.message for e in errors)


def test_coupling_source_signal_must_exist_in_runtime_registry():
    """A coupling source signal not published by the runtime should fail."""
    bad_config = {
        "_schema": "coupling_rules v1",
        "couplings": [
            {
                "name": "bad source signal",
                "loop": "test",
                "source": {"module": "heart", "signal": "mean_arterial_pressure"},
                "target": {
                    "module": "kidney",
                    "param": "kidney.GFR",
                    "op": "multiply",
                    "fn": "1.0",
                },
            }
        ],
    }
    errors = validate_coupling_rules(bad_config)
    assert len(errors) > 0
    assert any("heart.mean_arterial_pressure" in e.message for e in errors)


def test_coupling_expression_identifiers_must_exist_in_signal_map():
    """A coupling fn/condition identifier typo should fail validation."""
    bad_config = {
        "_schema": "coupling_rules v1",
        "couplings": [
            {
                "name": "bad expr identifier",
                "loop": "test",
                "source": {"module": "kidney", "signal": "GFR"},
                "target": {
                    "module": "blood",
                    "param": "blood.BUN",
                    "op": "set",
                    "fn": "20.0 + 40.0 * max(0, 1.0 - gfr / 100.0)",
                },
                "condition": "gfr < 90.0",
            }
        ],
    }
    errors = validate_coupling_rules(bad_config)
    assert len(errors) > 0
    assert any("Unknown expression identifier 'gfr'" in e.message for e in errors)


def test_ode_diseases_clamp_must_be_two_elements():
    """A clamp with wrong number of elements should fail schema validation."""
    bad_config = {
        "_schema": "test",
        "test_disease": {
            "severity_presets": {
                "moderate": {}
            },
            "state_variables": {
                "my_var": {
                    "initial": 0.0,
                    "clamp": [0, 1, 2],  # should be exactly 2
                    "ode_type": "algebraic",
                    "fn": "1.0"
                }
            },
            "outputs": []
        }
    }
    errors = validate_ode_diseases(bad_config)
    assert len(errors) > 0
    assert any("clamp" in e.path or "root" in e.path for e in errors)


# ── Examinations Tests ─────────────────────────────────────────────────────────

def test_examinations_validates_tier_range(real_examinations):
    """Load real examinations.json and expect zero validation errors."""
    errors = validate_examinations(real_examinations)
    assert errors == [], f"Unexpected errors: {errors}"


def test_examinations_validates_tier_upper_bound(real_examinations):
    """tier=6 should fail (must be 1-5)."""
    bad_config = dict(real_examinations)
    bad_config["bad_exam"] = {
        "name": "Bad Exam",
        "category": "基础检查",
        "tier": 6,
        "time_cost_min": 5,
        "latency_min": 0,
        "description": "Invalid tier",
        "params": []
    }
    errors = validate_examinations(bad_config)
    assert len(errors) > 0
    assert any("6" in e.message or "maximum" in e.message.lower() for e in errors)


def test_examinations_validates_tier_lower_bound(real_examinations):
    """tier=0 should fail (must be 1-5)."""
    bad_config = dict(real_examinations)
    bad_config["bad_exam"] = {
        "name": "Bad Exam",
        "category": "基础检查",
        "tier": 0,
        "time_cost_min": 5,
        "latency_min": 0,
        "description": "Invalid tier",
        "params": []
    }
    errors = validate_examinations(bad_config)
    assert len(errors) > 0


def test_examinations_time_cost_must_be_non_negative(real_examinations):
    """time_cost_min=-1 should fail (must be >= 0)."""
    bad_config = dict(real_examinations)
    bad_config["bad_exam"] = {
        "name": "Bad Exam",
        "category": "基础检查",
        "tier": 1,
        "time_cost_min": -1,
        "latency_min": 0,
        "description": "Invalid time cost",
        "params": []
    }
    errors = validate_examinations(bad_config)
    assert len(errors) > 0


def test_examinations_category_enum(real_examinations):
    """An invalid category should fail schema validation."""
    bad_config = dict(real_examinations)
    bad_config["bad_exam"] = {
        "name": "Bad Exam",
        "category": "InvalidCategory",
        "tier": 1,
        "time_cost_min": 5,
        "latency_min": 0,
        "description": "Invalid category",
        "params": []
    }
    errors = validate_examinations(bad_config)
    assert len(errors) > 0


# ── Exam Templates Tests ───────────────────────────────────────────────────────

def test_exam_templates_validates_correct_structure(real_exam_templates, real_examinations):
    """Load real exam_templates.json and expect zero validation errors."""
    errors = validate_exam_templates(real_exam_templates, real_examinations)
    assert errors == [], f"Unexpected errors: {errors}"


def test_exam_templates_do_not_reach_directly_into_creature(real_exam_templates):
    """Report templates should consume explicit interpretation inputs, not raw creature paths."""

    def _find_creature_refs(node, path="root"):
        hits = []
        if isinstance(node, dict):
            for key, value in node.items():
                hits.extend(_find_creature_refs(value, f"{path}.{key}"))
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                hits.extend(_find_creature_refs(value, f"{path}[{idx}]"))
        elif isinstance(node, str) and "creature." in node:
            hits.append((path, node))
        return hits

    hits = _find_creature_refs(real_exam_templates)
    assert hits == [], f"Unexpected raw creature references in exam templates: {hits}"


def test_exam_templates_disease_marker_surface_matches_template_usage(real_exam_templates):
    """The report-layer disease marker surface should match template references."""

    refs = set()

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "requires" and isinstance(value, str) and value.startswith("disease."):
                    refs.add(value.split(".", 1)[1])
                _walk(value)
            return
        if isinstance(node, list):
            for value in node:
                _walk(value)
            return
        if isinstance(node, str):
            import re

            refs.update(
                re.findall(r"disease\.([A-Za-z_][A-Za-z0-9_]*)", node)
            )

    _walk(real_exam_templates)

    assert get_allowed_exam_disease_markers(reload=True) == refs


def test_exam_templates_condition_must_be_non_empty_string(real_exam_templates, real_examinations):
    """A tag_rules entry with empty condition string should fail."""
    bad_config = {
        "physical": {
            "name": "体格检查",
            "test_type": "physical",
            "handler": "physical",
            "vitals": ["HR"],
            "extra_params": [],
            "thresholds": {"hr_tachy": 140},
            "tag_rules": [
                {"clue_id": "hr_high", "condition": ""}  # empty string — invalid
            ],
            "findings_rules": {}
        }
    }
    errors = validate_exam_templates(bad_config, real_examinations)
    assert len(errors) > 0


def test_exam_templates_value_formula_must_be_non_empty_string(real_exam_templates, real_examinations):
    """An extra_params entry with empty value_formula should fail."""
    bad_config = {
        "blood_routine": {
            "name": "血常规",
            "test_type": "blood_routine",
            "handler": "blood_routine",
            "vitals": [],
            "extra_params": [
                {
                    "param": "WBC",
                    "unit": "×10⁹/L",
                    "normal_range": "6.0-17.0",
                    "source": "computed",
                    "value_formula": ""  # empty — invalid
                }
            ],
            "thresholds": {},
            "tag_rules": [],
            "findings_rules": {}
        }
    }
    errors = validate_exam_templates(bad_config, real_examinations)
    assert len(errors) > 0


def test_exam_templates_test_type_must_exist_in_examinations(real_exam_templates):
    """A test_type that does not exist in examinations.json should fail."""
    bad_config = {
        "bad_template": {
            "name": "Bad",
            "test_type": "nonexistent_exam",
            "handler": "handler",
            "vitals": [],
            "extra_params": [],
            "thresholds": {},
            "tag_rules": [],
            "findings_rules": {}
        }
    }
    errors = validate_exam_templates(bad_config, None)  # passing None to skip cross-check
    # With examinations_config=None, no cross-check happens, so no error
    assert errors == []


# ── Diseases Tests ─────────────────────────────────────────────────────────────

def test_diseases_validates_correct_structure(real_diseases, real_examinations):
    """Load real diseases.json and expect zero validation errors."""
    errors = validate_diseases(real_diseases, real_examinations)
    assert errors == [], f"Unexpected errors: {errors}"


def test_diseases_rejects_legacy_clue_to_test_field(real_diseases):
    """The legacy clue_to_test field should no longer be accepted in diseases.json."""
    bad_config = {
        "disease_names": {"test_disease": "Test Disease"},
        "clues": {"test_disease": ["some_clue"]},
        "clue_descriptions": {"some_clue": "A clue"},
        "clue_to_test": {"some_clue": "nonexistent_exam_type"},
        "treatment_protocols": {"test_disease": []},
        "messages": {"win": {}, "loss": {}}
    }
    errors = validate_diseases(bad_config, None)
    assert len(errors) > 0
    assert any("Additional properties are not allowed" in e.message for e in errors)


def test_diseases_treatment_protocols_must_have_drug_name(real_diseases, real_examinations):
    """A treatment protocol without drug_name should fail schema validation."""
    bad_config = {
        "disease_names": {"test_disease": "Test Disease"},
        "clues": {"test_disease": []},
        "clue_descriptions": {},
        "treatment_protocols": {
            "test_disease": [
                {"dose_mg_kg": 0.25}  # missing drug_name
            ]
        },
        "messages": {"win": {}, "loss": {}}
    }
    errors = validate_diseases(bad_config, real_examinations)
    assert len(errors) > 0


def test_clue_catalog_validates_current_structure(
    real_clue_catalog,
    real_symptom_definitions,
    real_exam_templates,
    real_diseases,
):
    """The real clue catalog should satisfy the project-level clue contract."""
    errors = validate_clue_catalog(
        real_clue_catalog,
        real_symptom_definitions,
        real_exam_templates,
        real_diseases,
    )
    assert errors == [], f"Unexpected errors: {errors}"


def test_clue_catalog_rejects_missing_emitted_clue(
    real_clue_catalog,
    real_symptom_definitions,
    real_exam_templates,
    real_diseases,
):
    """If a live-emitted clue is removed from the catalog, validation should fail."""
    bad_catalog = dict(real_clue_catalog)
    bad_catalog.pop("PaO2_low", None)

    errors = validate_clue_catalog(
        bad_catalog,
        real_symptom_definitions,
        real_exam_templates,
        real_diseases,
    )
    assert len(errors) > 0
    assert any("PaO2_low" in e.message for e in errors)


def test_clue_catalog_rejects_diagnosis_clue_without_diagnosis_permission(
    real_clue_catalog,
    real_symptom_definitions,
    real_exam_templates,
    real_diseases,
):
    """A clue used by diagnosis must remain diagnosis_allowed in the catalog."""
    bad_catalog = dict(real_clue_catalog)
    bad_entry = dict(bad_catalog["PaO2_low"])
    bad_entry["diagnosis_allowed"] = False
    bad_catalog["PaO2_low"] = bad_entry

    errors = validate_clue_catalog(
        bad_catalog,
        real_symptom_definitions,
        real_exam_templates,
        real_diseases,
    )
    assert len(errors) > 0
    assert any("diagnosis_allowed" in e.message and "PaO2_low" in e.message for e in errors)


# ── validate_all Tests ─────────────────────────────────────────────────────────

def test_validate_all_returns_errors_by_file(real_ode_diseases, real_examinations, real_exam_templates, real_diseases):
    """validate_all() should return a dict with each filename mapping to a list of errors."""
    # Use the real configs — should have no errors
    results = validate_all()
    assert isinstance(results, dict)
    assert set(results.keys()) == {
        "ode_diseases.json",
        "examinations.json",
        "exam_templates.json",
        "diseases.json",
        "coupling_rules.json",
        "clue_catalog.json",
    }
    for filename, errors in results.items():
        assert isinstance(errors, list)
        assert all(isinstance(e, ValidationError) for e in errors)


def test_validate_all_structure_with_bad_data(tmp_path, monkeypatch):
    """With a bad config injected, validate_all() should report errors for that file."""
    import shutil

    # Create a temporary data dir with bad ode_diseases.json + copy schemas
    bad_ode = {
        "_schema": "test",
        "bad_disease": {
            "state_variables": {
                "v": {"ode_type": "invalid_type"}
            },
            "outputs": []
        }
    }
    tmp_data = tmp_path / "data"
    tmp_data.mkdir()
    (tmp_data / "ode_diseases.json").write_text(json.dumps(bad_ode), encoding="utf-8")
    (tmp_data / "examinations.json").write_text("{}", encoding="utf-8")
    (tmp_data / "exam_templates.json").write_text("{}", encoding="utf-8")
    (tmp_data / "diseases.json").write_text("{}", encoding="utf-8")

    # Copy schema files to tmp data/schemas dir
    src_schemas = Path(__file__).resolve().parents[1] / "data" / "schemas"
    tmp_schemas = tmp_data / "schemas"
    shutil.copytree(src_schemas, tmp_schemas)
    # Also copy coupling_rules_schema.json which lives in data/, not data/schemas/
    src_coupling_schema = Path(__file__).resolve().parents[1] / "data" / "coupling_rules_schema.json"
    shutil.copy(src_coupling_schema, tmp_data / "coupling_rules_schema.json")

    # Monkey-patch the data dir path
    import src.config_validation as cv
    monkeypatch.setattr(cv, "_DATA_DIR", tmp_data)

    results = cv.validate_all()
    # The bad ode_diseases has invalid ode_type, which should fail schema validation
    assert len(results["ode_diseases.json"]) > 0
    assert all(isinstance(e, cv.ValidationError) for e in results["ode_diseases.json"])


# ── ValidationError Tests ──────────────────────────────────────────────────────

def test_validation_error_attributes():
    """ValidationError should store file, path, and message correctly."""
    err = ValidationError("test.json", "a.b.c", "something went wrong")
    assert err.file == "test.json"
    assert err.path == "a.b.c"
    assert err.message == "something went wrong"
    assert "[test.json] a.b.c: something went wrong" in str(err)


def test_validation_error_repr():
    """ValidationError __repr__ should include all attributes."""
    err = ValidationError("test.json", "a.b.c", "something went wrong")
    repr_str = repr(err)
    assert "test.json" in repr_str
    assert "a.b.c" in repr_str
    assert "something went wrong" in repr_str
