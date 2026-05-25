from __future__ import annotations

from copy import deepcopy
from jsonschema import Draft202012Validator

from bioflow.core.hashing import hash_json
from bioflow.core.template_schema import TEMPLATE_SCHEMA


def _apply_phase5_defaults(template: dict) -> dict:
    t = deepcopy(template)
    rp = t.setdefault("resolved_parameters", {})

    # Phase 5 knobs (neutral defaults)
    rp.setdefault("vascular_tone_factor", 1.0)
    rp.setdefault("blood_volume_factor", 1.0)
    rp.setdefault("posture", "supine")
    rp.setdefault("pooling_bias_enabled", False)

    # Phase 5 (Step 6): hypovolemia via pure load-time scaling.
    # Strictly reversible: factor=1.0 produces identical template.
    #
    # IMPORTANT:
    # - Do NOT raise here for invalid values. validate_template() must return errors, not crash.
    # - Only apply scaling when factor is sensible (>0). Schema will reject invalid bounds.
    f_bv = float(rp.get("blood_volume_factor", 1.0))

    if f_bv != 1.0 and f_bv > 0.0:
        # Scale total blood volume if present
        if "total_blood_volume_ml" in rp:
            rp["total_blood_volume_ml"] = float(
                rp["total_blood_volume_ml"]) * f_bv

        # initial_state is top-level in this project
        init = t.get("initial_state")
        if isinstance(init, dict):
            if "V_art_ml" in init:
                init["V_art_ml"] = float(init["V_art_ml"]) * f_bv
            if "V_ven_ml" in init:
                init["V_ven_ml"] = float(init["V_ven_ml"]) * f_bv

    # DO NOT add these yet (until schema + physiology posture work exists):
    # rp.setdefault("posture", "supine")
    # rp.setdefault("pooling_bias_enabled", False)

    return t


def validate_template(template: dict) -> dict:
    warnings: list[str] = []

    normalized = _apply_phase5_defaults(template)

    errors: list[str] = []
    v = Draft202012Validator(TEMPLATE_SCHEMA)
    for err in v.iter_errors(normalized):
        errors.append(err.message)

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        # Hash the normalized template so missing-vs-explicit-neutral don't diverge.
        "template_hash": hash_json(normalized),
        "normalized_template": normalized,
    }
