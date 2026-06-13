"""
step_common.py — shared step scaffolding for Euler and Radau paths.

All pre-dispatch (event/lifecycle) and post-dispatch (fluid/耦合/history) steps
live here so the two solver paths differ only in the inner ODE solve.

Phase 4 refactor: eliminates ~60% code duplication between _step_euler and
_step_radau without changing any behavior.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from src.common_types import FactorCommand

if TYPE_CHECKING:
    from src.simulation import VirtualCreature

logger = logging.getLogger(__name__)


# ── helpers ────────────────────────────────────────────────────────────────────────

def _apply_urine_blood_loss(engine: "VirtualCreature", dt: float) -> None:
    """Step 7.5: urine blood volume loss → heart.blood_volume."""
    bv_loss = engine.kidney.blood_volume_loss_rate * dt / 60.0
    if bv_loss > 0:
        engine.apply_factor(FactorCommand("heart.blood_volume", "add", -bv_loss))


def _apply_fluid_and_ph(engine: "VirtualCreature", dt: float) -> dict:
    """Step 7.6: three-compartment fluid + Henderson-Hasselbalch pH."""
    fluid_state = engine.fluid.compute(dt)
    engine._hh.hco3 = engine.fluid.vascular_hco3_meq_l
    engine._hh.pco2 = engine.blood.arterial_PCO2_mmHg
    engine.blood.arterial_pH = engine._hh._compute_ph()
    return fluid_state


def _sync_blood_volume(engine: "VirtualCreature") -> None:
    """Step 7.7: sync blood.total_volume_ml to heart.circulating_volume_ml."""
    engine.blood.total_volume_ml = engine.heart.circulating_volume_ml


# ── pre-dispatch ───────────────────────────────────────────────────────────────

def run_pre_dispatch(engine: "VirtualCreature") -> bool:
    """
    Steps 0-0.5 shared by both Euler and Radau.

    Returns True if the simulation should stop early (creature died).

    Executes:
      0. Event processing (scheduled blood_loss / fluid_infusion / etc.)
      0.x  Continuous blood loss sigmoid model (both Euler and Radau paths)
      0.5  Lifecycle apply_age_factors + death_check
    """
    t = engine.current_time_s
    dt = engine.dt

    # Step 0: scheduled events
    engine._process_events(t)

    # Step 0.x: continuous sigmoid blood loss
    # (identical formula in _step_euler and _unified_rhs)
    if engine._blood_loss_config is not None:
        cfg = engine._blood_loss_config
        t_rel = t - cfg["t_onset"]
        if t_rel >= 0:
            sigmoid_on = 1.0 / (1.0 + np.exp(-t_rel / cfg["width"]))
            t_fall = t_rel - 3 * cfg["width"]
            sigmoid_off = 1.0 / (1.0 + np.exp(-t_fall / cfg["width"]))
            rate = cfg["k"] * sigmoid_on * (1.0 - sigmoid_off)
            engine.apply_factor(FactorCommand("heart.blood_volume", "add", -rate * dt))

    # Step 0.5: lifecycle + death check
    if not engine.lifecycle.is_dead():
        engine.lifecycle.apply_age_factors(engine)
        death_cause = engine.lifecycle.death_check()
        if death_cause:
            engine._handle_death(death_cause)
            return True

    return False


# ── post-dispatch (split into physiology + coupling phases) ──────────────────

def run_physiology_post(engine: "VirtualCreature", dt: float) -> dict:
    """
    Steps 7.5-7.7: physiology post-processing shared by both Euler and Radau.

    Must be called AFTER all organ compute() calls but BEFORE coupling resolve.
    Radau path: call after 5e (8-module compute), before run_coupling().

    Returns the fluid_state dict (needed by history recording).
    """
    # Step 7.5
    _apply_urine_blood_loss(engine, dt)

    # Step 7.6
    fluid_state = _apply_fluid_and_ph(engine, dt)

    # Step 7.7
    _sync_blood_volume(engine)

    return fluid_state


def run_coupling(engine: "VirtualCreature", dt: float, signal_time: float) -> None:
    """
    Step 8: coupling engine — publish signals + resolve rules.

    Args:
        engine: VirtualCreature instance
        dt: time step
        signal_time: timestamp for signal publication.
            Euler: current_time_s (before +=dt); Radau: current_time_s + dt (after step)

    Must be called AFTER all organ compute() calls AND run_physiology_post().
    """
    ctx = engine._organ_contexts
    t = signal_time

    # ── publish signals ─────────────────────────────────────────────────────
    heart_state_for_ctx = {
        "cardiac_output_ml_min": engine.heart.cardiac_output,
        "MAP_mmHg": engine.heart.mean_arterial_pressure,
        "central_venous_pressure": engine.heart.central_venous_pressure,
        "heart_rate_bpm": engine.heart.heart_rate,
        "stroke_volume": engine.heart.stroke_volume,
        "SVR": engine.heart.SVR,
    }
    _publish_heart_signals(ctx, heart_state_for_ctx, t)
    _publish_lung_signals(ctx, engine, t)
    _publish_kidney_signals(ctx, engine, t)
    _publish_blood_signals(ctx, engine, t)
    _publish_fluid_signals(ctx, engine, t)
    _publish_liver_signals(ctx, engine, t)

    # ── resolve coupling → FactorCommands ───────────────────────────────────
    coupling_cmds = engine.coupling_engine.resolve(ctx, dt)
    for cmd in coupling_cmds:
        engine.apply_factor(cmd)

    # Step 8.5
    engine._refresh_legacy_clinical_signs()


def run_post_dispatch(engine: "VirtualCreature", dt: float, signal_time: float) -> dict:
    """
    Convenience wrapper: physiology_post + coupling in one call.

    Use when all organ compute() calls are already done before this call
    (e.g. Euler path where organs are computed before Step 7.5).

    For Radau path, prefer separate run_physiology_post() + run_coupling()
    calls with the 8-module compute() sandwiched between them.
    """
    fluid_state = run_physiology_post(engine, dt)
    run_coupling(engine, dt, signal_time)
    return fluid_state


# ── signal helpers (used by both pre- and post-dispatch in Radau path) ─────────

def _publish_heart_signals(ctx, heart_state: dict, t: float) -> None:
    from src.organs.coupling import PhysiologicalSignal
    ctx["heart"].publish(PhysiologicalSignal("cardiac_output", heart_state["cardiac_output_ml_min"], "mL/min", "heart", t))
    ctx["heart"].publish(PhysiologicalSignal("MAP", heart_state["MAP_mmHg"], "mmHg", "heart", t))
    ctx["heart"].publish(PhysiologicalSignal("central_venous_pressure", heart_state["central_venous_pressure"], "mmHg", "heart", t))
    ctx["heart"].publish(PhysiologicalSignal("heart_rate", heart_state["heart_rate_bpm"], "bpm", "heart", t))
    ctx["heart"].publish(PhysiologicalSignal("stroke_volume", heart_state["stroke_volume"], "mL", "heart", t))
    ctx["heart"].publish(PhysiologicalSignal("SVR", heart_state["SVR"], "mmHg·s/mL", "heart", t))


def _publish_lung_signals(ctx, engine: "VirtualCreature", t: float) -> None:
    from src.organs.coupling import PhysiologicalSignal
    minute_vent = engine.lung.respiratory_rate * engine.lung.tidal_volume
    ctx["lung"].publish(PhysiologicalSignal("arterial_PO2", engine.blood.arterial_PO2_mmHg, "mmHg", "lung", t))
    ctx["lung"].publish(PhysiologicalSignal("arterial_PCO2", engine.blood.arterial_PCO2_mmHg, "mmHg", "lung", t))
    ctx["lung"].publish(PhysiologicalSignal("arterial_saturation", engine.blood.arterial_saturation, "", "lung", t))
    ctx["lung"].publish(PhysiologicalSignal("respiratory_rate", engine.lung.respiratory_rate, "/min", "lung", t))
    ctx["lung"].publish(PhysiologicalSignal("minute_ventilation", minute_vent, "mL/min", "lung", t))
    ctx["lung"].publish(PhysiologicalSignal("diffusion_coefficient", engine.lung.diffusion_coefficient, "", "lung", t))


def _publish_kidney_signals(ctx, engine: "VirtualCreature", t: float) -> None:
    from src.organs.coupling import PhysiologicalSignal
    ctx["kidney"].publish(PhysiologicalSignal("GFR", engine.kidney.GFR, "mL/min", "kidney", t))
    ctx["kidney"].publish(PhysiologicalSignal("renin_activity", engine.kidney.renin_activity, "", "kidney", t))
    ctx["kidney"].publish(PhysiologicalSignal("angiotensin_II", engine.kidney.angiotensin_II, "", "kidney", t))
    ctx["kidney"].publish(PhysiologicalSignal("aldosterone", engine.kidney.aldosterone, "", "kidney", t))
    ctx["kidney"].publish(PhysiologicalSignal("urine_output", engine.kidney.urine_output, "mL/min", "kidney", t))


def _publish_blood_signals(ctx, engine: "VirtualCreature", t: float) -> None:
    from src.organs.coupling import PhysiologicalSignal
    ctx["blood"].publish(PhysiologicalSignal("arterial_pH", engine.blood.arterial_pH, "", "blood", t))
    ctx["blood"].publish(PhysiologicalSignal("arterial_PCO2", engine.blood.arterial_PCO2_mmHg, "mmHg", "blood", t))
    ctx["blood"].publish(PhysiologicalSignal("lactate", engine.blood.lactate_mmol_L, "mmol/L", "blood", t))
    ctx["blood"].publish(PhysiologicalSignal("potassium", engine.blood.potassium_mEq_L, "mEq/L", "blood", t))
    ctx["blood"].publish(PhysiologicalSignal("albumin", engine.blood.albumin_g_dL, "g/dL", "blood", t))
    ctx["blood"].publish(PhysiologicalSignal("ALT", engine.blood.ALT_U_L, "U/L", "blood", t))
    ctx["blood"].publish(PhysiologicalSignal("PT_sec", engine.blood.PT_sec, "sec", "blood", t))
    ctx["blood"].publish(PhysiologicalSignal("fibrinogen_mg_dL", engine.blood.fibrinogen_mg_dL, "mg/dL", "blood", t))
    ctx["blood"].publish(PhysiologicalSignal("HCO3", engine.fluid.vascular_hco3_meq_l, "mEq/L", "blood", t))


def _publish_fluid_signals(ctx, engine: "VirtualCreature", t: float) -> None:
    from src.organs.coupling import PhysiologicalSignal
    ctx["fluid"].publish(PhysiologicalSignal("vascular_volume_ml", engine.fluid.vascular_volume_ml, "mL", "fluid", t))


def _publish_liver_signals(ctx, engine: "VirtualCreature", t: float) -> None:
    from src.organs.coupling import PhysiologicalSignal
    ctx["liver"].publish(PhysiologicalSignal("metabolic_activity", engine.liver.metabolic_activity, "", "liver", t))