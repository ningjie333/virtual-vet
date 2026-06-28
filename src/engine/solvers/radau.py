"""
radau.py — LSODA implicit solver step (via scipy.integrate.solve_ivp).

Solver Refactor Roadmap v3, Step 3: pure code-motion extraction from
`src/simulation.VirtualCreature._step_radau`. Zero behavior change.

This is the validation-path solver (roadmap: "Euler is production, LSODA is
validation"). It delegates the unified ODE integration to
`scipy.integrate.solve_ivp(method="LSODA")` over one engine timestep, then
runs the same post-integration physiology pipeline as the Euler path
(blood-factor writes, organ compute(), coupling, disease, organ_health,
history). Mirrors the style of `state_vector.py` / `step_common.py`:
module-level function taking the engine as the first argument.
`VirtualCreature._step_radau` keeps a thin wrapper for backward compat.

Verification note: original `solve_ivp(method="Radau")` hangs on the full
~50-ODE system (LU decomposition of the Jacobian, scipy >= 1.15). LSODA
auto-switches between stiff (BDF) and non-stiff (Adams) methods and works
reliably. The failure path (fallback to Euler) is covered by
tests/test_solver_fallback.py. See docs/solver-refactor-roadmap-v3.md
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.common_types import FactorCommand
from src.engine.step_common import (
    run_physiology_post,
    run_coupling,
    build_engine_state,
    run_organ_compute_chain,
    refresh_state_dicts,
)
from src.engine.step_contract import (
    StepGuard,
    PHASE_PRE_DISPATCH,
    PHASE_HEART_COMPUTE,
    PHASE_GUT_COMPUTE,
    PHASE_DISEASE,
    PHASE_IMMUNE,
    PHASE_ORGAN_HEALTH_TRACK,
    PHASE_ORGAN_HEALTH_APPLY,
    PHASE_HISTORY,
    PHASE_TIME_ADVANCE,
    DIVERGENCE_IMMUNE_ORDER,
    DIVERGENCE_DISEASE_ORDER,
    DIVERGENCE_COUPLING_RESOLVE_COUNT,
    DIVERGENCE_CHEMORECEPTOR_LAG,
    DIVERGENCE_ORGAN_HEALTH_MECHANISM,
)
from src.engine.factor_pipeline import snapshot_baselines, clear_baselines

if TYPE_CHECKING:
    from src.simulation import VirtualCreature

logger = logging.getLogger(__name__)


def run_radau_step(engine: "VirtualCreature") -> dict:
    """
    Radau 隐式求解器路径 — 单步推进。

    1. 调用 solve_ivp(method='Radau') 在 [t, t+dt] 上积分
    2. 解包结果到模块属性
    3. 执行耦合规则（同 Euler 路径）
    4. 执行疾病模块
    5. 记录 history

    Step 3: extracted verbatim from simulation._step_radau (self. → engine.).

    R3: StepGuard enforces ordering contracts at runtime.
    Documented divergences from Euler path are recorded via
    guard.divergence_ok() so they are explicit and auditable.
    """
    from scipy.integrate import solve_ivp

    t = engine.current_time_s
    dt = engine.dt

    # R3: create per-step guard and document intentional divergences from Euler.
    guard = StepGuard(label="radau")
    guard.divergence_ok(
        DIVERGENCE_IMMUNE_ORDER,
        "Radau: immune.compute() runs AFTER coupling (Step 7b). "
        "Euler: runs BEFORE coupling (Step 4.9). Radau's immune is "
        "integrated in solve_ivp; the post-step compute() is only for "
        "non-ODE outputs (CRP, cytokine display values)."
    )
    guard.divergence_ok(
        DIVERGENCE_DISEASE_ORDER,
        "Radau: disease runs AFTER coupling (Step 7). "
        "Euler: disease runs BEFORE organ compute (Step 2.5). "
        "Radau integrates disease state vars in solve_ivp; the post-step "
        "compute() applies residual factor_commands to instance attrs."
    )
    guard.divergence_ok(
        DIVERGENCE_COUPLING_RESOLVE_COUNT,
        "Radau: 1x coupling resolve (Step 8). "
        "Euler: 2x resolve (Step 4.95 + Step 8). Radau doesn't need "
        "the Gauss-Seidel relaxation because solve_ivp handles the "
        "implicit coupling internally."
    )
    guard.divergence_ok(
        DIVERGENCE_CHEMORECEPTOR_LAG,
        "Radau: neuro integrated in solve_ivp, no 1-step lag. "
        "Euler: chemoreceptor_drive read from previous step "
        "(Gauss-Seidel lag, O(dt) error, converges with dt refinement)."
    )
    guard.divergence_ok(
        DIVERGENCE_ORGAN_HEALTH_MECHANISM,
        "Radau: organ_health factor applied via apply_factor 'multiply' "
        "(goes through FactorPipeline, baseline-protected). "
        "Euler: direct setattr (self.heart.MAP *= factor). "
        "Radau uses apply_factor for audit-chain consistency."
    )

    # Step 0: 事件处理（Radau 路径独有：lifecycle/连续失血由 _unified_rhs 内部处理）
    engine._process_events(t)

    # Step 0.5: lifecycle check (before solve_ivp)
    if not engine.lifecycle.is_dead():
        engine.lifecycle.apply_age_factors(engine)
        death_cause = engine.lifecycle.death_check()
        if death_cause:
            engine._handle_death(death_cause)
            return {}

    guard.mark(PHASE_PRE_DISPATCH)

    # 2. 打包状态
    y0 = engine._pack_unified_state()
    if len(y0) == 0:
        # 无疾病状态，退化为 Euler
        return engine._step_euler()

    # 3. 预热：初始化 _cached_inputs
    _ = engine._unified_rhs(t, y0)

    # 4. solve_ivp 单步
    sol = solve_ivp(
        engine._unified_rhs,
        [t, t + dt],
        y0,
        method='LSODA',
        rtol=1e-5,
        atol=1e-8,
        dense_output=False,
        vectorized=False,
    )

    if not sol.success:
        # 求解失败，退化为 Euler
        # FIX(2026-06-13): P0 0a — return _step_euler() result instead of None
        # (was breaking step() return-type contract; twin-run harness could
        #  silently pass by self-comparing Euler)
        logger.warning("Radau failed at t=%.2fs: %s, falling back to Euler", t, sol.message)
        engine._solver_fallback_count += 1
        engine._solver_last_method_used = "euler_fallback"
        return engine._step_euler()

    # 5. 解包结果到模块属性
    engine._unpack_unified_state(sol.y[:, -1])
    engine._solver_last_method_used = "radau"
    # R3: heart state is now available from solve_ivp integration.
    # (Euler marks this after heart.compute(); Radau marks after unpack.)
    guard.mark(PHASE_HEART_COMPUTE)

    # 5a. Apply lung/kidney/immune/endocrine/coagulation/gut derivatives()'s blood
    # outputs via apply_factor (P0 0d: was 16+ direct engine.blood.X = Y writes).
    # Safe to apply post-solve_ivp — Newton iteration contamination concern was
    # theoretical; we're past the iteration now. Keeps the FactorCommand audit
    # chain intact.
    # LUNG (arterial blood gas)
    lung_out = engine.lung.derivatives(dt=dt, co_input=engine.heart.cardiac_output)[1]
    for path, attr in (
        ("blood.arterial_PO2", "arterial_PO2_mmHg"),
        ("blood.arterial_PCO2", "arterial_PCO2_mmHg"),
        ("blood.saturation", "arterial_saturation"),
        ("blood.pH", "arterial_pH"),
    ):
        if attr in lung_out:
            engine.apply_factor(FactorCommand(path, "set", lung_out[attr]))
    # KIDNEY (BUN, creatinine)
    kidney_out = engine.kidney.derivatives(
        dt=dt,
        map_input=engine.heart.mean_arterial_pressure,
        cvp_input=engine.heart.central_venous_pressure,
        co_input=engine.heart.cardiac_output,
    )[1]
    for path, key in (("blood.BUN", "bun_mg_dL"), ("blood.creatinine", "creatinine_mg_dL")):
        if key in kidney_out:
            engine.apply_factor(FactorCommand(path, "set", kidney_out[key]))
    # IMMUNE (temperature, CRP, sodium shift)
    immune_out = engine.immune.derivatives(dt=dt)[1]
    if "blood_core_temperature_C" in immune_out:
        engine.apply_factor(FactorCommand("blood.temperature", "set", immune_out["blood_core_temperature_C"]))
    if "blood_crp_mg_L" in immune_out:
        engine.apply_factor(FactorCommand("blood.CRP", "set", immune_out["blood_crp_mg_L"]))
    if "blood_sodium_shift" in immune_out:
        # immune.derivatives returns a "shift" (delta, not absolute) — use add op
        engine.apply_factor(FactorCommand("blood.sodium_mEq_L", "add", immune_out["blood_sodium_shift"]))
    # ENDOCRINE (T3, glucose, PTH, Ca, phosphate, albumin)
    endocrine_out = engine.endocrine.derivatives(dt=dt)[1]
    for src_key, target_path in (
        ("blood_core_temperature_C", "blood.temperature"),
        ("blood_glucose_mmol_L", "blood.glucose"),
        ("blood_PTH_pg_mL", None),  # not in _PARAM_PATHS yet
        ("blood_calcium_mg_dL", None),
        ("blood_phosphate_mg_dL", None),
        ("blood_albumin_g_dL", "blood.albumin"),
    ):
        if src_key in endocrine_out and target_path is not None:
            engine.apply_factor(FactorCommand(target_path, "set", endocrine_out[src_key]))
    # COAGULATION (PT, aPTT, fibrinogen)
    coag_out = engine.coagulation.derivatives(dt=dt)[1]
    for path, key in (
        ("blood.PT_sec", "PT_sec"),
        ("blood.aPTT_sec", "aPTT_sec"),
        ("blood.fibrinogen_mg_dL", "fibrinogen_mg_dL"),
    ):
        if key in coag_out:
            engine.apply_factor(FactorCommand(path, "set", coag_out[key]))
    # GUT (amino acids, fatty acids)
    gut_out = engine.gut.derivatives(dt=dt, co_input=engine.heart.cardiac_output)[1]
    if "blood_amino_acids_g_L" in gut_out:
        engine.apply_factor(FactorCommand("blood.amino_acids", "set", gut_out["blood_amino_acids_g_L"]))
    if "blood_fatty_acids_mmol_L" in gut_out:
        engine.apply_factor(FactorCommand("blood.fatty_acids", "set", gut_out["blood_fatty_acids_mmol_L"]))
    # LIVER (ammonia, BUN, albumin, bilirubin, ALT/AST/ALP, PT/INR, drug, amino acids, glucose)
    liver_out = engine.liver.derivatives(
        dt=dt, co_input=engine.heart.cardiac_output, gut_state=gut_out
    )[1]
    for src_key, target_path in (
        ("blood_ammonia_umol_L", "blood.ammonia"),
        ("blood_bun_mg_dL", "blood.BUN"),
        ("blood_albumin_g_dL", "blood.albumin"),
        ("blood_bilirubin_mg_dL", "blood.bilirubin_mg_dL"),
        ("blood_ALT_U_L", "blood.ALT"),
        ("blood_AST_U_L", "blood.AST"),
        ("blood_ALP_U_L", "blood.ALP"),
        ("blood_coagulation_factor_VII", "blood.coagulation_factor_VII"),
        ("blood_PT_sec", "blood.PT_sec"),
        ("blood_INR", "blood.INR"),
        ("blood_drug_concentration_mg_kg", "blood.drug_concentration_mg_kg"),
        ("blood_amino_acids_g_L", "blood.amino_acids"),
        ("blood_glucose_mmol_L", "blood.glucose"),
    ):
        if src_key in liver_out:
            engine.apply_factor(FactorCommand(target_path, "set", liver_out[src_key]))
    # LYMPHATIC (lymph_flow, interstitial_fluid, splenic_reserve)
    lymph_out = engine.lymphatic.derivatives(
        dt=dt,
        map_input=engine.heart.mean_arterial_pressure,
        hr_input=engine.heart.heart_rate,
        cytokine_input=engine.blood.cytokine_level if hasattr(engine.blood, 'cytokine_level') else 0.0,
        gut_fat_absorption=False,
    )[1]
    if "blood_lymph_flow_mL_min" in lymph_out:
        engine.apply_factor(FactorCommand("blood.lymph_flow_mL_min", "set", lymph_out["blood_lymph_flow_mL_min"]))
    if "blood_interstitial_fluid_mL" in lymph_out:
        engine.apply_factor(FactorCommand("blood.interstitial_fluid_mL", "set", lymph_out["blood_interstitial_fluid_mL"]))
    if "blood_splenic_reserve_mL" in lymph_out:
        engine.apply_factor(FactorCommand("blood.splenic_reserve_mL", "set", lymph_out["blood_splenic_reserve_mL"]))

    # 5b-5d: physiology post-processing (blood loss + fluid + sync)
    run_physiology_post(engine, dt, guard=guard)

    # 5e. P1.2: unified organ compute chain (liver→endocrine→coagulation→lymphatic→neuro)
    # Replaces the previous try/except + empty_state degraded version with
    # the same proper state-passing implementation used by the Euler path.
    gut_state = engine.gut.compute(dt, engine.heart.cardiac_output)
    guard.mark(PHASE_GUT_COMPUTE)
    # Build minimal heart/lung state dicts for the chain (Radau uses
    # engine attributes directly elsewhere, but the chain API expects dicts).
    heart_state_for_chain = {
        "heart_rate_bpm": engine.heart.heart_rate,
        "MAP_mmHg": engine.heart.mean_arterial_pressure,
        "cardiac_output_ml_min": engine.heart.cardiac_output,
    }
    lung_state_for_chain = {
        "arterial_PO2": engine.blood.arterial_PO2_mmHg,
        "diffusion_coefficient": engine.lung.diffusion_coefficient,
    }
    run_organ_compute_chain(engine, dt, gut_state,
                            heart_state_for_chain, lung_state_for_chain, guard=guard)

    # Step 8: coupling (publish signals + resolve) — after all organ compute()
    # Radau signal_time = current_time_s + dt (after step completion)
    run_coupling(engine, dt, signal_time=engine.current_time_s + dt, guard=guard)

    # R3: snapshot baselines before disease + organ_health multiply ops.
    # Mirrors Euler's snapshot pattern (Euler snapshots before disease at
    # Step 2.5 and before coupling at Step 4.95). Radau only needs one
    # snapshot here because disease + organ_health are the only multiply/
    # add phases after this point.
    # FIX(R3): Radau was previously missing snapshot_baselines entirely,
    # causing organ_health 'multiply' ops to compound across steps.
    snapshot_baselines(engine, guard=guard)

    # 7. 疾病模块（必须在 immune.compute 之前，以便 _infection_signal 等信号被疾病提前设置）
    # R5 Stage 1: 遍历所有 active 疾病（之前仅处理 engine.disease = 第一个）
    active_diseases = [d for d in engine.diseases if d.active]
    if active_diseases:
        engine_state = build_engine_state(engine)
        for d in active_diseases:
            d._current_time_s = engine.current_time_s
            for cmd in d.compute(dt, engine_state):
                engine.apply_factor(cmd)
        guard.mark(PHASE_DISEASE)

    # 7b. 免疫模块（在疾病输出后执行，使 _infection_signal 等已就位）
    # FIX(R3): empty_state was undefined, causing NameError caught by try/except
    # — immune.compute() in Radau path never actually ran. Now it does.
    empty_state: dict = {}
    try:
        engine.immune.compute(dt, endocrine_state=empty_state)
    except Exception as e:
        logger.warning("immune.compute failed: %s", e)
    guard.mark(PHASE_IMMUNE)

    # 器官健康追踪（Radau 特有：用解包后的当前状态作为 pre-state）
    # P0 0c: in Radau, organ_health factor is applied AFTER track() (see 6c below),
    # so the current state IS the pre-degradation state. Pass it as both.
    # Without this, track() falls back to (post-degradation) state for stress
    # detection, causing MAP×factor feedback oscillation.
    heart_state = {
        "heart_rate_bpm": engine.heart.heart_rate,
        "MAP_mmHg": engine.heart.mean_arterial_pressure,
        "cardiac_output_ml_min": engine.heart.cardiac_output,
        "contractility": engine.heart.contractility_factor,
    }
    lung_state = {
        "arterial_PO2": engine.blood.arterial_PO2_mmHg,
        "arterial_PCO2": engine.blood.arterial_PCO2_mmHg,
        "respiratory_rate": engine.lung.respiratory_rate,
    }
    kidney_state = {
        "GFR_ml_min": engine.kidney.GFR,
        "urine_output_mL_min": engine.kidney.urine_output,
    }
    liver_state = {
        "metabolic_activity": engine.liver.metabolic_activity,
        "detox_capacity": engine.liver.detox_capacity,
    }
    engine.organ_health.track(
        dt, heart_state, lung_state, kidney_state, liver_state,
        heart_state_pre=heart_state,  # P0 0c: same as current (Radau applies factor post-track)
        lung_state_pre=lung_state,
    )
    guard.mark(PHASE_ORGAN_HEALTH_TRACK)

    # 6c. 应用 organ_health 因子（一次性应用，不是乘法链）
    # NOTE(C6): 原问题——在已含旧因子的 dict 上再次相乘，导致累积乘法
    # 修复：直接用 heart_factor 作为唯一乘子，不再重复应用
    # P0(2026-06-13): 通过 apply_factor 写入（统一 FactorCommand 审计链）
    # R3: snapshot_baselines above makes these 'multiply' ops idempotent
    # (uses step-baseline as base, not current value — prevents compounding).
    if engine.organ_health.heart_factor < 1.0:
        engine.apply_factor(FactorCommand("heart.MAP", "multiply", engine.organ_health.heart_factor))
        engine.apply_factor(FactorCommand("heart.cardiac_output", "multiply", engine.organ_health.heart_factor))
    if engine.organ_health.lung_factor < 1.0:
        engine.apply_factor(FactorCommand("lung.diffusion_coefficient", "multiply", engine.organ_health.lung_factor))
    if engine.organ_health.kidney_factor < 1.0:
        engine.apply_factor(FactorCommand("kidney.GFR", "multiply", engine.organ_health.kidney_factor))
    guard.mark(PHASE_ORGAN_HEALTH_APPLY)

    # R3 FIX: refresh state dicts after organ_health factor application.
    # Mirrors Euler's refresh_state_dicts call (R1 fix). Radau was previously
    # missing this, leaving heart_state/lung_state/kidney_state dicts stale
    # after organ_health factor modified the instance attributes.
    refresh_state_dicts(engine, heart_state, lung_state, kidney_state, guard=guard)

    # 8. 记录历史（同 Euler 路径最后部分）
    if engine._record_history_enabled:
        engine._record_history(dt)
    guard.mark(PHASE_HISTORY)
    # 时间推进（统一在此，不在 _record_history 内）
    engine.current_time_s += dt
    guard.mark(PHASE_TIME_ADVANCE)

    # R3 FIX: clear per-step baselines (mirrors Euler's clear_baselines call).
    # Radau was previously missing this, allowing stale baselines to leak
    # across steps in tests that don't call step().
    clear_baselines(guard=guard)

    # 8.5: Legacy compatibility refresh for engine-owned signs state.
    engine._refresh_legacy_clinical_signs()
    return {}
