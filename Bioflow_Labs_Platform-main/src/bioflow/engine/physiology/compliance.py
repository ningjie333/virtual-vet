from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from bioflow.engine.state import GlobalState
from bioflow.engine.physiology.algebraic import BedParameters, compute_bed_flows, total_flow_ml_per_s

from .modifiers import (
    apply_modifiers_passthrough,
    apply_vascular_tone_to_beds,
    effective_standing_venous_v0_shift_ml
)


@dataclass(frozen=True)
class CompartmentParameters:
    C_ml_per_mmHg: float
    V0_ml: float


def pressure_mmHg(*, V_ml: float, C_ml_per_mmHg: float, V0_ml: float) -> float:
    # Simple linear compliance with floor at 0 mmHg
    P = (V_ml - V0_ml) / C_ml_per_mmHg
    return P if P > 0.0 else 0.0


def step_phase41_compliance(
    *,
    prev_state: GlobalState,
    dt_s: float,
    beds: List[BedParameters],
    baseline_flows_ml_per_s: Dict[str, float],
    pump_Q_ml_per_s: float,
    art: CompartmentParameters,
    ven: CompartmentParameters,
    resolved_parameters: Dict[str, object] | None = None,
) -> Tuple[GlobalState, dict]:
    """
    Phase 4.1: conservative volumes + compliance-derived pressures.

    State: V_art, V_ven
    Derived: P_art, P_ven
    Flows: bed flows from deltaP, pump flow constant (with limiters)
    """

    if dt_s <= 0:
        raise ValueError("dt_s must be > 0")
    if pump_Q_ml_per_s < 0:
        raise ValueError("pump_Q_ml_per_s must be >= 0")
    if art.C_ml_per_mmHg <= 0 or ven.C_ml_per_mmHg <= 0:
        raise ValueError("Compliance must be > 0")

    _mods = apply_modifiers_passthrough(
        resolved_parameters=resolved_parameters or {})  # Currently unused by design

    beds_eff = apply_vascular_tone_to_beds(
        beds=beds,
        vascular_tone_factor=_mods.vascular_tone_factor,
    )

    pooling_bias_enabled = bool(
        (resolved_parameters or {}).get("pooling_bias_enabled", False))

    venous_v0_shift_ml = effective_standing_venous_v0_shift_ml(
        posture=_mods.posture,
        pooling_bias_enabled=pooling_bias_enabled,
        beds=beds_eff,  # has pooling_bias field now
    )

    ven_eff = CompartmentParameters(
        C_ml_per_mmHg=ven.C_ml_per_mmHg,
        V0_ml=ven.V0_ml + venous_v0_shift_ml,
    )

    # 1) Compute pressures from current volumes
    P_art = pressure_mmHg(V_ml=prev_state.V_art_ml,
                          C_ml_per_mmHg=art.C_ml_per_mmHg, V0_ml=art.V0_ml)
    P_ven = pressure_mmHg(V_ml=prev_state.V_ven_ml,
                          C_ml_per_mmHg=ven_eff.C_ml_per_mmHg, V0_ml=ven_eff.V0_ml)

    # 2) Compute algebraic bed flows at these pressures
    bed_results = compute_bed_flows(
        P_art_mmHg=P_art,
        P_ven_mmHg=P_ven,
        beds=beds_eff,
        baseline_flows_ml_per_s=baseline_flows_ml_per_s,
    )
    Q_out = total_flow_ml_per_s(bed_results)

    # 3) Deterministic safety limiters (prevent negative volumes)
    # Venous update: V_ven_next = V_ven + (Q_out - Q_pump)*dt  >= 0
    # -> Q_pump <= Q_out + V_ven/dt
    max_pump = Q_out + (prev_state.V_ven_ml / dt_s)
    Q_pump = pump_Q_ml_per_s if pump_Q_ml_per_s <= max_pump else max_pump

    # Arterial update: V_art_next = V_art + (Q_pump - Q_out)*dt >= 0
    # -> Q_out <= Q_pump + V_art/dt
    max_out = Q_pump + (prev_state.V_art_ml / dt_s)
    if Q_out > max_out:
        # Scale down all bed flows proportionally (keeps competition ratios)
        scale = (max_out / Q_out) if Q_out > 0 else 0.0
        for i in range(len(bed_results)):
            bed_results[i] = bed_results[i].__class__(
                bed_id=bed_results[i].bed_id,
                deltaP_mmHg=bed_results[i].deltaP_mmHg,
                Q_ml_per_s=bed_results[i].Q_ml_per_s * scale,
                # perf index will be recomputed below anyway
                perfusion_index=bed_results[i].perfusion_index * scale,
            )
        Q_out = total_flow_ml_per_s(bed_results)

    # 4) Apply conservative volume updates
    dV_art = (Q_pump - Q_out) * dt_s
    V_art_next = prev_state.V_art_ml + dV_art
    V_ven_next = prev_state.V_ven_ml - dV_art  # conservation

    # 5) Recompute pressures at next volumes (so sampled state matches new volumes)
    P_art_next = pressure_mmHg(
        V_ml=V_art_next, C_ml_per_mmHg=art.C_ml_per_mmHg, V0_ml=art.V0_ml)
    P_ven_next = pressure_mmHg(
        V_ml=V_ven_next, C_ml_per_mmHg=ven_eff.C_ml_per_mmHg, V0_ml=ven_eff.V0_ml)

    # 6) Recompute flows for reporting at next-step pressures (optional but cleaner)
    bed_results_next = compute_bed_flows(
        P_art_mmHg=P_art_next,
        P_ven_mmHg=P_ven_next,
        beds=beds_eff,
        baseline_flows_ml_per_s=baseline_flows_ml_per_s,
    )

    bed_Q = {r.bed_id: r.Q_ml_per_s for r in bed_results_next}
    bed_perf = {r.bed_id: r.perfusion_index for r in bed_results_next}

    next_state = GlobalState(
        t_s=prev_state.t_s + dt_s,
        V_art_ml=V_art_next,
        V_ven_ml=V_ven_next,
        P_art_mmHg=P_art_next,
        P_ven_mmHg=P_ven_next,
        bed_Q_ml_per_s=bed_Q,
        bed_perfusion_index=bed_perf,
    )

    metrics = {
        "P_art_mmHg": P_art_next,
        "P_ven_mmHg": P_ven_next,
        "V_art_ml": V_art_next,
        "V_ven_ml": V_ven_next,
        "Q_pump_ml_per_s": Q_pump,
        "Q_out_ml_per_s": total_flow_ml_per_s(bed_results_next),
    }
    return next_state, metrics
