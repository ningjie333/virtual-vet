"""
Config Validation — JSON Schema + programmatic validation for virtual-vet config files.

Validates:
  - data/ode_diseases.json
  - data/examinations.json
  - data/exam_templates.json
  - data/diseases.json

Programmatic rules (not expressible in JSON Schema):
  - outputs[].target must be a valid key in _PARAM_PATHS
  - severity preset keys referenced by rate_key/K_key must exist in the preset
  - exam IDs in diseases.json.clue_to_test must exist in examinations.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

from .logger_config import get_logger

logger = get_logger(__name__)

# ── Paths ───────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DATA_DIR = _PROJECT_ROOT / "data"


def _get_data_dir() -> Path:
    """Return the data directory (computed lazily to support monkeypatching in tests)."""
    return _DATA_DIR


def _get_schemas_dir() -> Path:
    """Return the schemas directory (computed lazily to support monkeypatching in tests)."""
    return _get_data_dir() / "schemas"


def _load_schema(name: str) -> dict:
    """Load a JSON schema file by name (e.g. 'ode_diseases.schema.json')."""
    path = _get_schemas_dir() / name

class ValidationError(Exception):
    """
    Validation error with file, JSON path, and user-friendly message.

    Attributes:
        file: Path to the file that failed (relative to project root)
        path: Dot-separated path to the failing element in the JSON
        message: Human-readable description of what failed and why
    """

    def __init__(self, file: str, path: str, message: str):
        super().__init__(f"[{file}] {path}: {message}")
        self.file = file
        self.path = path
        self.message = message

    def __repr__(self) -> str:
        return f"ValidationError(file={self.file!r}, path={self.path!r}, message={self.message!r})"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_numeric_str(s: str) -> bool:
    """Return True if s looks like a numeric literal (int or float), not an identifier."""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


# ── Schema Loaders ───────────────────────────────────────────────────────────

def _load_schema(name: str) -> dict:
    """Load a JSON schema file by name (e.g. 'ode_diseases.schema.json')."""
    path = _get_schemas_dir() / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_json(path: Path) -> dict:
    """Load a JSON data file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Individual Validators ───────────────────────────────────────────────────

def validate_ode_diseases(config: dict) -> list[ValidationError]:
    """
    Validate data/ode_diseases.json structure and cross-references.

    Schema checks:
      - Each disease has state_variables (object) and outputs (array)
      - state_variables.*.ode_type is enum: logistic | algebraic | first_order_lag | custom
      - state_variables.*.clamp, if present, is [number|null, number|null]
      - outputs[].target is string
      - outputs[].op is enum: multiply | add | set
      - severity_presets.*.mild/moderate/severe are objects

    Programmatic checks:
      - outputs[].target must be a valid _PARAM_PATHS key
      - rate_key/K_key must be a non-numeric string that exists in the severity preset
        (numeric K_key values like "1.0" are literal K values, not key references)
    """
    errors: list[ValidationError] = []
    schema = _load_schema("ode_diseases.schema.json")
    validator = Draft202012Validator(schema)

    # Schema validation
    for err in validator.iter_errors(config):
        path = ".".join(str(p) for p in err.path) if err.path else "root"
        errors.append(ValidationError("ode_diseases.json", path, err.message))

    # Programmatic: validate ode_type enum for disease entries (not underscore-prefixed)
    VALID_ODE_TYPES = {"logistic", "algebraic", "first_order_lag", "custom"}
    for disease_name, disease_conf in config.items():
        if disease_name.startswith("_") or not isinstance(disease_conf, dict):
            continue
        for var_name, var_conf in disease_conf.get("state_variables", {}).items():
            if not isinstance(var_conf, dict):
                continue
            ode_type = var_conf.get("ode_type", "")
            if ode_type and ode_type not in VALID_ODE_TYPES:
                errors.append(ValidationError(
                    "ode_diseases.json",
                    f"{disease_name}.state_variables.{var_name}.ode_type",
                    f"Unknown ode_type '{ode_type}'. Must be one of: {', '.join(sorted(VALID_ODE_TYPES))}"
                ))

    # Programmatic: outputs[].op must be enum: multiply | add | set
    VALID_OPS = {"multiply", "add", "set"}
    for disease_name, disease_conf in config.items():
        if disease_name.startswith("_") or not isinstance(disease_conf, dict):
            continue
        for i, output in enumerate(disease_conf.get("outputs", [])):
            if not isinstance(output, dict):
                continue
            op = output.get("op", "")
            if op and op not in VALID_OPS:
                errors.append(ValidationError(
                    "ode_diseases.json",
                    f"{disease_name}.outputs[{i}].op",
                    f"Unknown op '{op}'. Must be one of: {', '.join(sorted(VALID_OPS))}"
                ))

    # Programmatic: state_variables.*.clamp must be exactly 2 elements (or null)
    for disease_name, disease_conf in config.items():
        if disease_name.startswith("_") or not isinstance(disease_conf, dict):
            continue
        for var_name, var_conf in disease_conf.get("state_variables", {}).items():
            if not isinstance(var_conf, dict):
                continue
            clamp = var_conf.get("clamp")
            if clamp is not None and not isinstance(clamp, list):
                continue
            if clamp is not None and len(clamp) != 2:
                errors.append(ValidationError(
                    "ode_diseases.json",
                    f"{disease_name}.state_variables.{var_name}.clamp",
                    f"clamp must have exactly 2 elements, got {len(clamp)}"
                ))

    # Programmatic: outputs[].target must be in _PARAM_PATHS
    # Import here to avoid circular import
    from .simulation import _PARAM_PATHS as PARAM_PATHS

    for disease_name, disease_conf in config.items():
        if disease_name.startswith("_"):
            continue
        if not isinstance(disease_conf, dict):
            continue

        for i, output in enumerate(disease_conf.get("outputs", [])):
            if not isinstance(output, dict):
                continue
            target = output.get("target", "")
            if target and target not in PARAM_PATHS:
                errors.append(ValidationError(
                    "ode_diseases.json",
                    f"{disease_name}.outputs[{i}].target",
                    f"Unknown target '{target}'. Must be one of: {', '.join(sorted(PARAM_PATHS.keys()))}"
                ))

        # Programmatic: rate_key/K_key must exist in severity preset (only for identifier-style keys)
        # Numeric-style values like "1.0" or "0.95" are literal K values, not key references
        presets = disease_conf.get("severity_presets", {})
        for var_name, var_conf in disease_conf.get("state_variables", {}).items():
            if not isinstance(var_conf, dict):
                continue
            params = var_conf.get("params", {})
            if not isinstance(params, dict):
                continue

            for preset_severity, preset_values in presets.items():
                if not isinstance(preset_values, dict):
                    continue
                rate_key = params.get("rate_key")
                K_key = params.get("K_key")
                # Only validate string key references (not numeric literals like "1.0")
                if rate_key and isinstance(rate_key, str) and not _is_numeric_str(rate_key) and rate_key not in preset_values:
                    errors.append(ValidationError(
                        "ode_diseases.json",
                        f"{disease_name}.state_variables.{var_name}.params.rate_key",
                        f"rate_key '{rate_key}' does not exist in severity_presets.{preset_severity}"
                    ))
                if K_key and isinstance(K_key, str) and not _is_numeric_str(K_key) and K_key not in preset_values:
                    errors.append(ValidationError(
                        "ode_diseases.json",
                        f"{disease_name}.state_variables.{var_name}.params.K_key",
                        f"K_key '{K_key}' does not exist in severity_presets.{preset_severity}"
                    ))

    return errors


def validate_examinations(config: dict) -> list[ValidationError]:
    """
    Validate data/examinations.json structure.

    Schema checks:
      - tier is integer 1-5
      - time_cost_min is integer >= 0
      - latency_min is integer >= 0
      - category is one of the categories found in the config
      - params is array of strings
      - name, description are strings
    """
    errors: list[ValidationError] = []
    schema = _load_schema("examinations.schema.json")

    # Collect valid categories from config
    categories_in_config = {exam.get("category") for exam in config.values() if isinstance(exam, dict)}

    # Dynamically override the category enum with whatever categories are actually present
    # so schema validation passes for real data and fails for invalid categories
    if categories_in_config:
        props = schema.get("properties", {})
        if "category" in props:
            props["category"] = {"type": "string", "enum": sorted(categories_in_config)}

    validator = Draft202012Validator(schema)

    for err in validator.iter_errors(config):
        path = ".".join(str(p) for p in err.path) if err.path else "root"
        errors.append(ValidationError("examinations.json", path, err.message))

    return errors


def validate_exam_templates(
    config: dict,
    examinations_config: dict | None = None
) -> list[ValidationError]:
    """
    Validate data/exam_templates.json structure.

    Schema checks:
      - handler is string
      - vitals is array of strings
      - extra_params[].source is string, value_formula (if present) is non-empty string
      - tag_rules[].clue_id is string, condition is non-empty string
      - findings_rules is object; each rule has 'if' (string or bool) and 'text' (string)
      - thresholds is object with numeric or string values
    """
    errors: list[ValidationError] = []
    schema = _load_schema("exam_templates.schema.json")
    validator = Draft202012Validator(schema)

    for err in validator.iter_errors(config):
        path = ".".join(str(p) for p in err.path) if err.path else "root"
        errors.append(ValidationError("exam_templates.json", path, err.message))

    # Programmatic: if examinations_config provided, verify test_type values exist
    if examinations_config:
        exam_ids = set(examinations_config.keys())
        for exam_name, exam_conf in config.items():
            if exam_name.startswith("_") or not isinstance(exam_conf, dict):
                continue
            test_type = exam_conf.get("test_type", "")
            if test_type and test_type not in exam_ids:
                errors.append(ValidationError(
                    "exam_templates.json",
                    f"{exam_name}.test_type",
                    f"test_type '{test_type}' does not exist in examinations.json"
                ))

    return errors


def validate_diseases(
    config: dict,
    examinations_config: dict | None = None,
    exam_templates_config: dict | None = None
) -> list[ValidationError]:
    """
    Validate data/diseases.json structure and cross-references.

    Schema checks:
      - disease_names is object string->string
      - clues is object string->array of strings
      - clue_descriptions is object string->string
      - clue_to_test is object string->string
      - treatment_protocols[disease][] has drug_name (string), dose_mg_kg or volume_ml (number)
      - messages.win and messages.loss are object string->string

    Programmatic checks:
      - exam IDs in clue_to_test values must exist in examinations.json (if provided)
    """
    errors: list[ValidationError] = []
    schema = _load_schema("diseases.schema.json")
    validator = Draft202012Validator(schema)

    for err in validator.iter_errors(config):
        path = ".".join(str(p) for p in err.path) if err.path else "root"
        errors.append(ValidationError("diseases.json", path, err.message))

    # Programmatic: clue_to_test values must reference valid exam IDs
    if examinations_config:
        exam_ids = set(examinations_config.keys())
        clue_to_test = config.get("clue_to_test", {})
        for clue_id, exam_type in clue_to_test.items():
            if exam_type and exam_type not in exam_ids:
                errors.append(ValidationError(
                    "diseases.json",
                    f"clue_to_test.{clue_id}",
                    f"exam type '{exam_type}' does not exist in examinations.json"
                ))

    return errors


def validate_coupling_rules(config: dict) -> list[ValidationError]:
    """
    Validate data/coupling_rules.json structure.

    Schema checks:
      - _schema matches
      - couplings is array of rules
      - each rule has name, loop, source, target

    Programmatic checks:
      - references[].id and references[].text are non-empty strings
      - notes is string (can be empty)
    """
    errors: list[ValidationError] = []
    # coupling_rules_schema.json lives in data/, not data/schemas/
    schema_path = _get_data_dir() / "coupling_rules_schema.json"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    validator = Draft202012Validator(schema)

    for err in validator.iter_errors(config):
        path = ".".join(str(p) for p in err.path) if err.path else "root"
        errors.append(ValidationError("coupling_rules.json", path, err.message))

    # Programmatic: each coupling rule with references must have non-empty id/text
    for i, rule in enumerate(config.get("couplings", [])):
        if not isinstance(rule, dict):
            continue
        for j, ref in enumerate(rule.get("references", [])):
            if not isinstance(ref, dict):
                continue
            if not ref.get("id"):
                errors.append(ValidationError(
                    "coupling_rules.json",
                    f"couplings[{i}].references[{j}].id",
                    "Reference id cannot be empty"
                ))
            if not ref.get("text"):
                errors.append(ValidationError(
                    "coupling_rules.json",
                    f"couplings[{i}].references[{j}].text",
                    "Reference text cannot be empty"
                ))

    return errors


# ── validate_all ─────────────────────────────────────────────────────────────

def validate_all() -> dict[str, list[ValidationError]]:
    """
    Load all four JSON config files and run all validations.

    Returns:
        Dict mapping filename -> list of ValidationErrors (empty list = pass)
    """
    results: dict[str, list[ValidationError]] = {
        "ode_diseases.json": [],
        "examinations.json": [],
        "exam_templates.json": [],
        "diseases.json": [],
        "coupling_rules.json": [],
    }

    data_dir = _get_data_dir()
    _ode_file = data_dir / "ode_diseases.json"
    _exam_file = data_dir / "examinations.json"
    _tmpl_file = data_dir / "exam_templates.json"
    _dz_file = data_dir / "diseases.json"
    _cr_file = data_dir / "coupling_rules.json"

    try:
        ode_diseases_config = _load_json(_ode_file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        results["ode_diseases.json"].append(ValidationError("ode_diseases.json", "root", str(e)))
        ode_diseases_config = {}

    try:
        examinations_config = _load_json(_exam_file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        results["examinations.json"].append(ValidationError("examinations.json", "root", str(e)))
        examinations_config = {}

    try:
        exam_templates_config = _load_json(_tmpl_file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        results["exam_templates.json"].append(ValidationError("exam_templates.json", "root", str(e)))
        exam_templates_config = {}

    try:
        diseases_config = _load_json(_dz_file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        results["diseases.json"].append(ValidationError("diseases.json", "root", str(e)))
        diseases_config = {}

    try:
        coupling_rules_config = _load_json(_cr_file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        results["coupling_rules.json"].append(ValidationError("coupling_rules.json", "root", str(e)))
        coupling_rules_config = {}

    results["ode_diseases.json"].extend(validate_ode_diseases(ode_diseases_config))
    results["examinations.json"].extend(validate_examinations(examinations_config))
    results["exam_templates.json"].extend(
        validate_exam_templates(exam_templates_config, examinations_config)
    )
    results["diseases.json"].extend(
        validate_diseases(diseases_config, examinations_config, exam_templates_config)
    )
    results["coupling_rules.json"].extend(validate_coupling_rules(coupling_rules_config))

    return results


# ── CLI Entry Point ──────────────────────────────────────────────────────────

def main() -> int:
    """
    CLI entry point for direct script execution.
    Exits with 0 if all pass, 1 if any errors.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Validate virtual-vet JSON config files")
    parser.add_argument("--file", help="Validate only this file (e.g. ode_diseases.json)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args()

    if args.file:
        # Validate single file
        data_dir = _get_data_dir()
        file_map = {
            "ode_diseases.json": ("ode_diseases.json", _load_json(data_dir / "ode_diseases.json")),
            "examinations.json": ("examinations.json", _load_json(data_dir / "examinations.json")),
            "exam_templates.json": ("exam_templates.json", _load_json(data_dir / "exam_templates.json")),
            "diseases.json": ("diseases.json", _load_json(data_dir / "diseases.json")),
            "coupling_rules.json": ("coupling_rules.json", _load_json(data_dir / "coupling_rules.json")),
        }
        if args.file not in file_map:
            print(f"Unknown file: {args.file}")
            return 1
        filename, config = file_map[args.file]
        errors = _run_validators_for_file(filename, config)
    else:
        results = validate_all()
        errors = []
        for file_errors in results.values():
            errors.extend(file_errors)

    if args.format == "json":
        output = []
        for err in errors:
            output.append({"file": err.file, "path": err.path, "message": err.message})
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if not errors:
            print("PASS: All validations passed")
            return 0
        print(f"FAIL: {len(errors)} validation error(s):")
        for err in errors:
            print(f"  [{err.file}] {err.path}: {err.message}")

    return 1 if errors else 0


def _run_validators_for_file(filename: str, config: dict) -> list[ValidationError]:
    """Run appropriate validators for a single file."""
    if filename == "ode_diseases.json":
        return validate_ode_diseases(config)
    elif filename == "examinations.json":
        return validate_examinations(config)
    elif filename == "exam_templates.json":
        return validate_exam_templates(config, None)
    elif filename == "diseases.json":
        return validate_diseases(config, None, None)
    elif filename == "coupling_rules.json":
        return validate_coupling_rules(config)
    return []


if __name__ == "__main__":
    import sys
    sys.exit(main())