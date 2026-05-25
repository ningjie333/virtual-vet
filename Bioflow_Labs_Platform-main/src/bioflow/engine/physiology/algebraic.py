# src/bioflow/engine/physiology/algebraic.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class BedParameters:
    """
    Algebraic bed parameters for Phase 4 (static flow only).

    R_mmHg_s_per_ml:
      Resistance measured in mmHg * s / mL.
      So flow becomes mL/s from (mmHg) / (mmHg*s/mL).
    """
    bed_id: str
    R_mmHg_s_per_ml: float
    pooling_bias: float = 0.0


@dataclass(frozen=True)
class BedFlowResult:
    bed_id: str
    deltaP_mmHg: float
    Q_ml_per_s: float
    perfusion_index: float  # 0..200-ish, baseline=100


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def compute_bed_flows(
    *,
    P_art_mmHg: float,
    P_ven_mmHg: float,
    beds: List[BedParameters],
    baseline_flows_ml_per_s: Dict[str, float],
) -> List[BedFlowResult]:
    """
    Phase 4 (non-negotiable): pure algebraic flows, deterministic, stable.

    Q_bed = max(0, (P_art - P_ven) / R_bed)

    perfusion_index = clamp(100 * Q / Q_baseline, 0, 200)
      - baseline missing or 0 -> perfusion_index = 0 (explicit, no division games)
    """
    deltaP_mmHg = P_art_mmHg - P_ven_mmHg

    results: List[BedFlowResult] = []
    for bed in beds:
        if bed.R_mmHg_s_per_ml <= 0:
            # Hard fail: invalid physics parameter (keep it loud)
            raise ValueError(
                f"Bed '{bed.bed_id}' has non-positive resistance R={bed.R_mmHg_s_per_ml}")

        raw_Q = deltaP_mmHg / bed.R_mmHg_s_per_ml
        Q_ml_per_s = raw_Q if raw_Q > 0 else 0.0

        baseline_Q = baseline_flows_ml_per_s.get(bed.bed_id, 0.0)
        if baseline_Q <= 0:
            perf_index = 0.0
        else:
            perf_index = _clamp(100.0 * (Q_ml_per_s / baseline_Q), 0.0, 200.0)

        results.append(
            BedFlowResult(
                bed_id=bed.bed_id,
                deltaP_mmHg=deltaP_mmHg,
                Q_ml_per_s=Q_ml_per_s,
                perfusion_index=perf_index,
            )
        )

    return results


def total_flow_ml_per_s(bed_flows: List[BedFlowResult]) -> float:
    return sum(b.Q_ml_per_s for b in bed_flows)
