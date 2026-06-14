"""
radau.py — Radau implicit solver step (5th-order Radau IIA).

Solver Refactor Roadmap v3, Step 3: pure code-motion extraction from
`src/simulation.VirtualCreature._step_radau`. Zero behavior change.

This is the validation-path solver (roadmap: "Euler is production, Radau is
validation"). It delegates the unified ODE integration to
`scipy.integrate.solve_ivp(method="Radau")` over one engine timestep, then
runs the same post-integration physiology pipeline as the Euler path
(blood-factor writes, organ compute(), coupling, disease, organ_health,
history). Mirrors the style of `state_vector.py` / `step_common.py`:
module-level function taking the engine as the first argument.
`VirtualCreature._step_radau` keeps a thin wrapper for backward compat.

Verification note: real `solve_ivp(Radau)` hangs on Python 3.14 + scipy 1.17
>5min/step (environment issue, baseline-confirmed in Step 4). The extraction
is verified bit-equal via a faked-success solve_ivp that drives the full
post-integration code path; the failure path (fallback to Euler) is covered
by tests/test_solver_fallback.py. See docs/solver-refactor-roadmap-v3.md
Step 3 verification section.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.common_types import FactorCommand
from src.engine.step_common import run_physiology_post, run_coupling

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
    """
    from scipy.integrate import solve_ivp

    t = engine.current_time_s
    dt = engine.dt

    # Step 0: 事件处理（Radau 路径独有：lifecycle/连续失血由 _unified_rhs 内部处理）
    engine._process_events(t)

    # Step 0.5: lifecycle check (before solve_ivp)
    if not engine.lifecycle.is_dead():
        engine.lifecycle.apply_age_factors(engine)
        death_cause = engine.lifecycle.death_check()
        if death_cause:
            engine._handle_death(death_cause)
            return {}

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
        method='Radau',
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

    # 5b-5d: physiology post-processing (blood loss + fluid + sync)
    run_physiology_post(engine, dt)

    # 5e. C1 修复：补全 8 个模块的 compute()（与 Euler 路径等价）
    # 顺序参照 Euler 路径 Step 4-4.9
    # NOTE: 先建空 dict 给 compute() 作为"上游 state"占位（与 Euler 路径等价语义）
    empty_state: dict = {}
    try:
        engine.gut.compute(dt, engine.heart.cardiac_output)
    except Exception as e:
        logger.warning("gut.compute failed: %s", e)
    try:
        engine.liver.compute(dt, gut_state=empty_state, cardiac_output=engine.heart.cardiac_output)
    except Exception as e:
        logger.warning("liver.compute failed: %s", e)
    try:
        engine.endocrine.compute(dt)
    except Exception as e:
        logger.warning("endocrine.compute failed: %s", e)
    try:
        engine.lymphatic.compute(dt, gut_state=empty_state, immune_state=empty_state)
    except Exception as e:
        logger.warning("lymphatic.compute failed: %s", e)
    try:
        engine.coagulation.compute(dt, liver_state=empty_state, immune_state=empty_state)
    except Exception as e:
        logger.warning("coagulation.compute failed: %s", e)
    try:
        engine.neuro.compute(dt, heart_state=empty_state, lung_state=empty_state)
    except Exception as e:
        logger.warning("neuro.compute failed: %s", e)
    # tox/pharmacology 由 schedule_event / 外部 API 触发，不强制每步调

    # Step 8: coupling (publish signals + resolve) — after all organ compute()
    # Radau signal_time = current_time_s + dt (after step completion)
    run_coupling(engine, dt, signal_time=engine.current_time_s + dt)

    # 7. 疾病模块（必须在 immune.compute 之前，以便 _infection_signal 等信号被疾病提前设置）
    if engine.disease is not None:
        engine_state = {
            "heart": {"HR": engine.heart.heart_rate, "MAP": engine.heart.mean_arterial_pressure,
                      "CO": engine.heart.cardiac_output, "contractility": engine.heart.contractility_factor,
                      "SVR": engine.heart.SVR, "CVP": engine.heart.central_venous_pressure},
            "lung": {"arterial_PO2": engine.blood.arterial_PO2_mmHg,
                     "arterial_PCO2": engine.blood.arterial_PCO2_mmHg,
                     "diffusion_coefficient": engine.lung.diffusion_coefficient,
                     "respiratory_rate": engine.lung.respiratory_rate},
            "kidney": {"GFR": engine.kidney.GFR, "urine_output": engine.kidney.urine_output,
                       "renin_activity": engine.kidney.renin_activity,
                       "angiotensin_II": engine.kidney.angiotensin_II,
                       "aldosterone": engine.kidney.aldosterone},
            "blood": {"pH": engine.blood.arterial_pH, "lactate": engine.blood.lactate_mmol_L,
                      "BUN": engine.blood.bun_mg_dL, "creatinine": engine.blood.creatinine_mg_dL,
                      "glucose": engine.blood.glucose_mmol_L, "sodium": engine.blood.sodium_mEq_L,
                      "potassium": engine.blood.potassium_mEq_L},
            "fluid": {"vascular_volume_ml": engine.fluid.vascular_volume_ml},
            "temperature": engine.blood.core_temperature_C,
        }
        cmds = engine.disease.compute(dt, engine_state)
        for cmd in cmds:
            engine.apply_factor(cmd)

    # 7b. 免疫模块（在疾病输出后执行，使 _infection_signal 等已就位）
    try:
        engine.immune.compute(dt, endocrine_state=empty_state)
    except Exception as e:
        logger.warning("immune.compute failed: %s", e)

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

    # 6c. 应用 organ_health 因子（一次性应用，不是乘法链）
    # NOTE(C6): 原问题——在已含旧因子的 dict 上再次相乘，导致累积乘法
    # 修复：直接用 heart_factor 作为唯一乘子，不再重复应用
    # P0(2026-06-13): 通过 apply_factor 写入（统一 FactorCommand 审计链）
    if engine.organ_health.heart_factor < 1.0:
        engine.apply_factor(FactorCommand("heart.MAP", "multiply", engine.organ_health.heart_factor))
        engine.apply_factor(FactorCommand("heart.cardiac_output", "multiply", engine.organ_health.heart_factor))
    if engine.organ_health.lung_factor < 1.0:
        engine.apply_factor(FactorCommand("lung.diffusion_coefficient", "multiply", engine.organ_health.lung_factor))
    if engine.organ_health.kidney_factor < 1.0:
        engine.apply_factor(FactorCommand("kidney.GFR", "multiply", engine.organ_health.kidney_factor))

    # 8. 记录历史（同 Euler 路径最后部分）
    if engine._record_history_enabled:
        engine._record_history(dt)
    # 时间推进（统一在此，不在 _record_history 内）
    engine.current_time_s += dt

    # 8.5: Legacy compatibility refresh for engine-owned signs state.
    engine._refresh_legacy_clinical_signs()
    return {}
