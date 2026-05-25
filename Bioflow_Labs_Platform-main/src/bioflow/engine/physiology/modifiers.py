# src/bioflow/engine/physiology/modifiers.py
"""
Phase 5 modifiers (posture, tone, hypovolemia) live here.

CRITICAL CONSTRAINTS:
- Pure transforms only (no randomness, no feedback control loops).
- Neutral knobs MUST produce identical behavior to Phase 4.1.
- No runner / DB / hashing changes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional

from bioflow.engine.physiology.algebraic import BedParameters


@dataclass(frozen=True)
class EffectiveModifiers:
    """
    Values returned by apply_modifiers().

    For Step 1: everything is neutral / passthrough.
    Later steps will fill these in.
    """
    vascular_tone_factor: float = 1.0          # scales resistances: R_eff = R * factor
    blood_volume_factor: float = 1.0           # scales TBV and initial volumes
    posture: str = "supine"                    # "supine" | "standing"

    # For later: per-bed V0 shifts (pooling). Keep optional so we don't break anything.
    # Example: {"periphery": +500.0}
    bed_v0_shift_ml: Optional[Dict[str, float]] = None


def read_phase5_knobs(resolved_parameters: Dict[str, Any]) -> EffectiveModifiers:
    """
    Read knobs from resolved_parameters, but default to Phase 4.1 neutral behavior.

    IMPORTANT:
    - This function MUST be safe even if keys don't exist (Phase 4.1 templates).
    """
    posture = resolved_parameters.get("posture", "supine")
    vascular_tone_factor = float(
        resolved_parameters.get("vascular_tone_factor", 1.0))
    blood_volume_factor = float(
        resolved_parameters.get("blood_volume_factor", 1.0))

    # Step 1: no pooling behavior yet.
    return EffectiveModifiers(
        posture=posture,
        vascular_tone_factor=vascular_tone_factor,
        blood_volume_factor=blood_volume_factor,
        bed_v0_shift_ml=None,
    )


def apply_modifiers_passthrough(*, resolved_parameters: Dict[str, Any]) -> EffectiveModifiers:
    """
    Step 1: neutral passthrough. Safe even for Phase 4.1 templates.
    """
    return read_phase5_knobs(resolved_parameters)


def apply_vascular_tone_to_beds(
    *,
    beds: List[BedParameters],
    vascular_tone_factor: float,
) -> List[BedParameters]:
    """
    Pure transform: R_eff = R * vascular_tone_factor.

    MUST be reversible:
    - factor=1.0 returns identical parameters (no changes).
    """
    if vascular_tone_factor == 1.0:
        return beds

    if vascular_tone_factor <= 0:
        raise ValueError("vascular_tone_factor must be > 0")

    beds_eff: List[BedParameters] = []
    for b in beds:
        # BedParameters is a dataclass in your codebase; replace() preserves other fields.
        beds_eff.append(
            replace(b, R_mmHg_s_per_ml=b.R_mmHg_s_per_ml * vascular_tone_factor))
    return beds_eff


def effective_standing_venous_v0_shift_ml(
    *,
    posture: str,
    pooling_bias_enabled: bool,
    beds: list["BedParameters"],
) -> float:
    """
    Standing pooling model (Phase 5, minimal + stable):

    base_shift_ml = 500 mL when standing, else 0.

    If pooling_bias_enabled:
      scale = 1 + gain * avg_bias
      avg_bias = mean(pooling_bias across beds)
      gain chosen conservative.
    """
    if posture == "supine":
        return 0.0
    if posture != "standing":
        raise ValueError(f"Unknown posture: {posture!r}")

    base_shift_ml = 500.0
    if not pooling_bias_enabled:
        return base_shift_ml

    if not beds:
        return base_shift_ml

    avg_bias = sum(max(0.0, float(b.pooling_bias)) for b in beds) / len(beds)

    gain = 0.25  # conservative: bias=4 -> scale=2.0
    scale = 1.0 + gain * avg_bias

    # Hard clamp so this can't blow up.
    if scale < 1.0:
        scale = 1.0
    if scale > 3.0:
        scale = 3.0

    return base_shift_ml * scale
