"""
step_common.py — shared step scaffolding for the Euler path.

All pre-dispatch (event/lifecycle) and post-dispatch (fluid/耦合/history) steps
live here so the solver path contains only the inner ODE solve.

Phase 4 refactor: eliminates ~60% code duplication by extracting shared
step scaffolding without changing any behavior.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from src.common_types import FactorCommand
from src.engine.step_contract import (
    StepGuard,
    PHASE_PRE_DISPATCH,
    PHASE_HEART_COMPUTE,
    PHASE_ORGAN_CHAIN,
    PHASE_PHYSIOLOGY_POST,
    PHASE_COUPLING_RESOLVE_2,
    PHASE_COUPLING_PUBLISH,
    PHASE_ORGAN_HEALTH_APPLY,
    PHASE_REFRESH_DICTS,
)

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


# ── P1.1: unified engine_state builder ───────────────────────────────────────

def build_engine_state(engine: "VirtualCreature") -> dict:
    """Build a unified engine_state dict for disease modules.

    Provides a superset of fields from both Euler and Radau paths.
    All readings are taken from engine attributes at call time, so the
    caller must ensure relevant organ compute() calls have already run
    (typically after heart.compute()).

    Legacy aliases (HR, MAP, CO) are preserved for backward compatibility
    with old-style disease modules.
    """
    return {
        "heart": {
            "heart_rate_bpm": engine.heart.heart_rate,
            "MAP_mmHg": engine.heart.mean_arterial_pressure,
            "cardiac_output_ml_min": engine.heart.cardiac_output,
            # Legacy aliases
            "HR": engine.heart.heart_rate,
            "MAP": engine.heart.mean_arterial_pressure,
            "CO": engine.heart.cardiac_output,
            "contractility": engine.heart.contractility_factor,
            "SVR": engine.heart.SVR,
            "CVP": engine.heart.central_venous_pressure,
        },
        "lung": {
            "arterial_PO2": engine.blood.arterial_PO2_mmHg,
            "arterial_PCO2": engine.blood.arterial_PCO2_mmHg,
            "diffusion_coefficient": engine.lung.diffusion_coefficient,
            "respiratory_rate": engine.lung.respiratory_rate,
        },
        "kidney": {
            "GFR": engine.kidney.GFR,
            "GFR_ml_min": engine.kidney.GFR,
            "urine_output": engine.kidney.urine_output,
            "renin_activity": engine.kidney.renin_activity,
            "angiotensin_II": engine.kidney.angiotensin_II,
            "aldosterone": engine.kidney.aldosterone,
        },
        "blood": {
            "pH": engine.blood.arterial_pH,
            "lactate": engine.blood.lactate_mmol_L,
            "BUN": engine.blood.bun_mg_dL,
            "creatinine": engine.blood.creatinine_mg_dL,
            "glucose": engine.blood.glucose_mmol_L,
            "sodium": engine.blood.sodium_mEq_L,
            "potassium": engine.blood.potassium_mEq_L,
        },
        "immune": {
            "antibiotic_effect": engine.immune.antibiotic_effect,
        },
        "fluid": {
            "vascular_volume_ml": engine.fluid.vascular_volume_ml,
        },
        "temperature": engine.blood.core_temperature_C,
    }


# ── P1.2: unified organ compute chain ──────────────────────────────────────

def run_organ_compute_chain(
    engine: "VirtualCreature",
    dt: float,
    gut_state: dict,
    heart_state: dict,
    lung_state: dict,
    guard: StepGuard | None = None,
) -> dict:
    """Run organ compute() chain: liver → endocrine → coagulation →
    lymphatic → neuro.

    Immune is intentionally excluded — it has different ordering
    requirements in the Euler vs Radau paths (Euler: before coupling,
    Radau: after disease).

    Factor commands returned by organ modules are applied via
    engine.apply_factor(), keeping the FactorCommand audit chain intact.

    R3 contract:
        requires  PHASE_HEART_COMPUTE (heart_state dict must be populated)
        marks     PHASE_ORGAN_CHAIN

    Returns a dict with all organ state dicts keyed by module name.
    """
    if guard is not None:
        guard.require(PHASE_HEART_COMPUTE)

    CO = engine.heart.cardiac_output

    liver_state = engine.liver.compute(dt, gut_state, CO)
    endocrine_state = engine.endocrine.compute(dt)

    coagulation_state = engine.coagulation.compute(dt, liver_state, {})
    for cmd in coagulation_state.get("factor_commands", []):
        engine.apply_factor(cmd)

    lymphatic_state = engine.lymphatic.compute(dt, gut_state, {})
    for cmd in lymphatic_state.get("factor_commands", []):
        engine.apply_factor(cmd)

    neuro_state = engine.neuro.compute(dt, heart_state, lung_state)
    for cmd in neuro_state.get("factor_commands", []):
        engine.apply_factor(cmd)

    if guard is not None:
        guard.mark(PHASE_ORGAN_CHAIN)

    return {
        "liver": liver_state,
        "endocrine": endocrine_state,
        "coagulation": coagulation_state,
        "lymphatic": lymphatic_state,
        "neuro": neuro_state,
    }


# ── R1: refresh state dicts from instance attributes ──────────────────────────

def refresh_state_dicts(
    engine: "VirtualCreature",
    heart_state: dict,
    lung_state: dict | None = None,
    kidney_state: dict | None = None,
    guard: StepGuard | None = None,
) -> None:
    """R1: Refresh state dicts from instance attributes after all modifications.

    Replaces the conditional Step 5.5 sync. Instance attributes are the
    single source of truth — dicts are snapshots that may be stale after
    disease/organ_health/coupling modifications.

    Mutates the dicts in-place to reflect current instance attribute values.

    R3 contract:
        requires  PHASE_ORGAN_HEALTH_APPLY (instance attrs must be final)
        marks     PHASE_REFRESH_DICTS
    """
    if guard is not None:
        guard.require(PHASE_ORGAN_HEALTH_APPLY)

    heart_state["heart_rate_bpm"] = engine.heart.heart_rate
    heart_state["MAP_mmHg"] = engine.heart.mean_arterial_pressure
    heart_state["CVP_mmHg"] = engine.heart.central_venous_pressure
    heart_state["cardiac_output_ml_min"] = engine.heart.cardiac_output
    heart_state["SVR"] = engine.heart.SVR
    heart_state["contractility_factor"] = engine.heart.contractility_factor
    heart_state["blood_volume_ml"] = engine.heart.circulating_volume_ml

    if lung_state is not None:
        lung_state["arterial_PO2"] = engine.blood.arterial_PO2_mmHg
        lung_state["arterial_PCO2"] = engine.blood.arterial_PCO2_mmHg
        lung_state["arterial_saturation"] = engine.blood.arterial_saturation
        lung_state["respiratory_rate"] = engine.lung.respiratory_rate

    if kidney_state is not None:
        kidney_state["GFR_ml_min"] = engine.kidney.GFR
        kidney_state["urine_output_ml_min"] = engine.kidney.urine_output
        kidney_state["BUN_mg_dL"] = engine.blood.bun_mg_dL

    if guard is not None:
        guard.mark(PHASE_REFRESH_DICTS)


# ── pre-dispatch ───────────────────────────────────────────────────────────────

def run_pre_dispatch(engine: "VirtualCreature", guard: StepGuard | None = None) -> bool:
    """
    Steps 0-0.5 shared by both Euler and Radau.

    Returns True if the simulation should stop early (creature died).

    Executes:
      0. Event processing (scheduled blood_loss / fluid_infusion / etc.)
      0.x  Continuous blood loss sigmoid model (both Euler and Radau paths)
      0.5  Lifecycle apply_age_factors + death_check

    R3 contract:
        marks  PHASE_PRE_DISPATCH (only if not early-return)
    """
    t = engine.current_time_s
    dt = engine.dt

    # Step 0: scheduled events
    engine._process_events(t)

    # Step 0.x: continuous sigmoid blood loss
    # (identical formula in _step_euler)
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

    if guard is not None:
        guard.mark(PHASE_PRE_DISPATCH)

    return False


# ── post-dispatch (split into physiology + coupling phases) ──────────────────

def run_physiology_post(
    engine: "VirtualCreature",
    dt: float,
    guard: StepGuard | None = None,
) -> dict:
    """
    Steps 7.5-7.7: physiology post-processing shared by both Euler and Radau.

    Must be called AFTER kidney state is available (Euler: kidney.compute;
    Radau: solve_ivp unpack) but the exact phase varies by path.
    Radau path: call after 5a (apply derivatives), before run_organ_compute_chain.
    Euler path: call after organ chain, before run_coupling.

    Returns the fluid_state dict (needed by history recording).

    R3 contract:
        marks  PHASE_PHYSIOLOGY_POST
    (No phase prerequisite — kidney availability is path-specific:
     Euler marks PHASE_KIDNEY_COMPUTE explicitly; Radau integrates kidney
     inside solve_ivp. The driver code ensures correct ordering.)
    """
    # Step 7.5
    _apply_urine_blood_loss(engine, dt)

    # Step 7.6
    fluid_state = _apply_fluid_and_ph(engine, dt)

    # Step 7.7
    _sync_blood_volume(engine)

    if guard is not None:
        guard.mark(PHASE_PHYSIOLOGY_POST)

    return fluid_state


def run_coupling(
    engine: "VirtualCreature",
    dt: float,
    signal_time: float,
    guard: StepGuard | None = None,
) -> None:
    """
    Step 8: coupling engine — publish fresh signals + resolve (substep 2).

    R4: This is the SECOND substep of the Euler path's 2-substep Gauss-Seidel
    relaxation. The FIRST substep runs inline in `_step_euler` (Step 4.95,
    `PHASE_COUPLING_RESOLVE_1`) and reads the PREVIOUS step's published signals
    (lagged). This second substep publishes FRESH signals from the current
    step's organ states, then resolves again — forming one full relaxation
    sweep. Both substeps are required for Euler stability (twin-run proven).

    Args:
        engine: VirtualCreature instance
        dt: time step
        signal_time: timestamp for signal publication (current_time_s before +=dt).
        guard: optional StepGuard for R3 contract enforcement

    Must be called AFTER all organ compute() calls AND run_physiology_post().

    R3 contract:
        requires  PHASE_PHYSIOLOGY_POST
        marks     PHASE_COUPLING_RESOLVE_2 (after resolve+apply)
        marks     PHASE_COUPLING_PUBLISH (after refresh_legacy_clinical_signs)
    """
    if guard is not None:
        guard.require(PHASE_PHYSIOLOGY_POST)

    ctx = engine._organ_contexts
    t = signal_time

    # ── publish fresh signals from current organ states ────────────────────
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

    # ── substep 2: resolve coupling → FactorCommands (fresh signals) ───────
    coupling_cmds = engine.coupling_engine.resolve(ctx, dt)
    for cmd in coupling_cmds:
        engine.apply_factor(cmd)

    if guard is not None:
        guard.mark(PHASE_COUPLING_RESOLVE_2)

    # Step 8.5
    engine._refresh_legacy_clinical_signs()

    if guard is not None:
        guard.mark(PHASE_COUPLING_PUBLISH)


def run_post_dispatch(
    engine: "VirtualCreature",
    dt: float,
    signal_time: float,
    guard: StepGuard | None = None,
) -> dict:
    """
    Convenience wrapper: physiology_post + coupling in one call.

    Use when all organ compute() calls are already done before this call
    (e.g. Euler path where organs are computed before Step 7.5).

    For Radau path, prefer separate run_physiology_post() + run_coupling()
    calls with the 8-module compute() sandwiched between them.

    R3 contract: forwards guard to both sub-steps.
    """
    fluid_state = run_physiology_post(engine, dt, guard=guard)
    run_coupling(engine, dt, signal_time, guard=guard)
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