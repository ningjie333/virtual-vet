"""
Action System — 玩家行动处理系统。

职责:
  - GameState 数据类：承载整个游戏状态
  - process_action()：处理玩家行动（检查/治疗/等待），推进引擎时间
  - determine_phase()：基于引擎数值自动判定病情阶段
  - check_death()：濒死倒计时 + 死亡判定
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.simulation import VirtualCreature
from game.time_manager import (
    is_night_time,
    get_night_hr_factor,
    get_night_progression_factor,
    format_game_time,
)

logger = logging.getLogger(__name__)

# ── 常量 ──
K_SECONDS_PER_ACTION = 60  # 1 次行动 = 60 秒 ODE 仿真
MORIBUND_ACTIONS_REMAINING = 3  # 进入濒死后还能做的行动次数


# ── 病情阶段判定阈值 ──
# 元组格式: (low_moribund, low_critical, low_worsening, high_worsening, high_critical, high_moribund)
_THRESHOLDS = {
    "MAP": (40, 50, 60, 150, 160, 180),
    "SpO2": (70, 80, 90, 100, 100, 100),  # SpO2 只有低侧危险
    "HR": (40, 50, 60, 160, 180, 200),
    "pH": (7.0, 7.1, 7.2, 7.6, 7.7, 7.8),
}

# ── 检查项目 cost 表（与 data/examinations.json 同步） ──
_EXAM_COSTS: dict[str, int] = {
    "physical": 0,
    "auscultation": 0,
    "inspection": 0,
    "blood_routine": 1,
    "ecg": 1,
    "blood_biochem": 3,
    "blood_gas": 3,
    "chest_xray": 3,
    "ultrasound": 4,
    "ct": 5,
}


def _get_examine_cost(action_type: str, params: dict) -> int:
    """返回行动消耗次数。cost=0 返回 1（至少消耗 1 行动）。"""
    if action_type in ("treat", "wait", "administer_drug"):
        return 1
    test_type = params.get("test_type", "physical")
    cost = _EXAM_COSTS.get(test_type, 1)
    return max(1, cost)


# ── DO₂ 阶段判定阈值（相对值，健康犬归一化 ≈ 1.0） ──
# DO₂ = CO × SaO₂（相对值），临界点基于提取率代偿极限
_DO2_WARN = 0.6  # 低于此值 → 失代偿（提取率已到极限）
_DO2_CRIT = 0.4  # 低于此值 → 危重（无氧代谢主导）
_DO2_MORIB = 0.25  # 低于此值 → 濒死

# 乳酸阈值（mmol_L）
_LACTATE_WARN = 3.0  # 轻微升高 → 代偿期
_LACTATE_CRIT = 5.0  # 显著升高 → 失代偿期

# 尿量阈值（mL/min/kg），低于此值为少尿
_URINE_OLIGURIA = 0.008  # 正常 0.02，低于 0.008 为少尿
_URINE_ANURIA = 0.002  # 接近无尿


@dataclass
class GameState:
    """游戏状态数据类"""

    engine: VirtualCreature
    disease_name: str
    action_count: int = 0
    elapsed_time_s: float = 0.0
    phase: str = "playing"  # "playing" | "won" | "lost"
    death_timer: Optional[int] = None  # 濒死倒计时（剩余行动次数）
    reports: list = field(default_factory=list)
    treatment_applied: Optional[str] = None
    game_clock_s: float = 0.0  # 游戏内时间（秒），用于夜间判定


def compute_DO2(engine: VirtualCreature) -> float:
    """
    计算氧输送指数 DO₂（相对值）。

    DO₂ = CO × CaO₂ ∝ CO × SaO₂
    健康犬归一化值 ≈ 1.0，用于阶段判定。

    临床意义:
    - DO₂ 下降但提取率代偿 → 乳酸轻微升高（代偿期）
    - DO₂ 低于临界提取率极限 → 乳酸飙升（失代偿）
    - DO₂ 极低 → 无氧代谢主导（不可逆）
    """
    hist = engine.history

    def _last(key: str, fallback):
        vals = hist.get(key, [])
        return vals[-1] if vals else fallback

    # 读取当前值
    co = _last("CO_ml_min", 1700.0)  # 健康犬基础 CO ≈ 1700 mL/min
    sao2 = _last("saturation", 0.97)  # 健康犬基础 SaO₂ ≈ 97%

    # 归一化 DO₂（健康犬 = 1.0）
    do2 = (co / 1700.0) * sao2
    return max(0.0, min(1.0, do2))


def determine_phase(engine: VirtualCreature) -> str:
    """
    根据引擎当前状态判定病情阶段。

    综合评分体系:
    1. 传统阈值评分（MAP/SpO2/HR/pH）
    2. DO₂ 氧输送指数（CO × SaO₂）
    3. 乳酸（组织灌注指标）
    4. 尿量（内脏灌注最敏感指标）

    返回:
        "stable"    — 代偿期：DO₂ 下降但乳酸 < 3，尿量正常
        "worsening" — 失代偿：DO₂ 低于提取率极限，乳酸 > 3
        "critical"  — 危重：多参数显著偏离，乳酸 > 5
        "moribund"  — 濒死：尿量消失 + HR 开始下降，不可逆
    """
    hist = engine.history

    def _last(key: str, fallback):
        vals = hist.get(key, [])
        return vals[-1] if vals else fallback

    map_val = _last("MAP_mmHg", engine.heart.mean_arterial_pressure)
    hr = _last("HR_bpm", engine.heart.heart_rate)
    sp_o2 = _last("saturation", engine.blood.arterial_saturation) * 100
    ph = _last("pH", engine.blood.arterial_pH)
    do2 = compute_DO2(engine)
    lactate = engine.blood.lactate_mmol_L
    urine_output = _last("urine_ml_min", engine.kidney.urine_output)
    bw_kg = engine.w
    urine_per_kg = urine_output / bw_kg if bw_kg > 0 else 0.0

    # ── 传统阈值评分 ──
    # 0=stable, 1=worsening, 2=critical, 3=moribund
    def _score(value, param):
        lo_mor, lo_crit, lo_warn, hi_warn, hi_crit, hi_mor = _THRESHOLDS[param]
        if value <= lo_mor or value >= hi_mor:
            return 3
        if value <= lo_crit or value >= hi_crit:
            return 2
        if value <= lo_warn or value >= hi_warn:
            return 1
        return 0

    threshold_score = max(
        _score(map_val, "MAP"),
        _score(sp_o2, "SpO2"),
        _score(hr, "HR"),
        _score(ph, "pH"),
    )

    # ── DO₂ 评分 ──
    if do2 <= _DO2_MORIB:
        do2_score = 3
    elif do2 <= _DO2_CRIT:
        do2_score = 2
    elif do2 <= _DO2_WARN:
        do2_score = 1
    else:
        do2_score = 0

    # ── 乳酸评分 ──
    if lactate >= _LACTATE_CRIT:
        lactate_score = 2
    elif lactate >= _LACTATE_WARN:
        lactate_score = 1
    else:
        lactate_score = 0

    # ── 尿量评分 ──
    if urine_per_kg < _URINE_ANURIA:
        urine_score = 3  # 无尿 → 濒死
    elif urine_per_kg < _URINE_OLIGURIA:
        urine_score = 2  # 少尿 → 危重
    else:
        urine_score = 0

    # ── 综合评分 ──
    # 任何参数达到 moribund → 直接濒死
    if threshold_score >= 3 or do2_score >= 3 or urine_score >= 3:
        return "moribund"

    # HR 开始下降（心脏跳不动了）+ 无尿 → 不可逆濒死
    if hr < 60 and urine_per_kg < _URINE_ANURIA:
        return "moribund"

    # 多项危重 → critical
    crit_count = sum(
        [
            threshold_score >= 2,
            do2_score >= 2,
            lactate_score >= 2,
            urine_score >= 2,
        ]
    )
    if crit_count >= 2 or do2_score >= 2:
        return "critical"

    # 单项偏离 → worsening
    if threshold_score >= 1 or do2_score >= 1 or lactate_score >= 1 or urine_score >= 1:
        return "worsening"

    return "stable"


def check_death(state: GameState, medical_phase: str) -> GameState:
    """
    死亡检测逻辑（基于医学阶段更新游戏阶段）：
    1. medical_phase 为 "moribund" 且倒计时未启动 → 启动倒计时
    2. medical_phase 为 "moribund" → 倒计时减 1
    3. 倒计时归零 → game phase = "lost"
    4. medical_phase 从 "moribund" 回到其他状态 → 清除倒计时
    """
    if medical_phase == "moribund":
        if state.death_timer is None:
            state.death_timer = MORIBUND_ACTIONS_REMAINING
            logger.info("进入濒死状态，死亡倒计时: %d 次行动", state.death_timer)
        else:
            state.death_timer -= 1
            logger.info("濒死倒计时剩余: %d 次行动", state.death_timer)
            if state.death_timer <= 0:
                state.phase = "lost"
                logger.info("死亡判定: phase=lost")
    else:
        if state.death_timer is not None:
            logger.info("脱离濒死状态，清除死亡倒计时")
            state.death_timer = None

    return state


def _engine_summary(engine: VirtualCreature, game_clock_s: float = 0.0) -> dict:
    """返回引擎当前状态的简要摘要"""
    hist = engine.history

    def _last(key: str, fallback):
        vals = hist.get(key, [])
        return vals[-1] if vals else fallback

    return {
        "HR_bpm": round(_last("HR_bpm", engine.heart.heart_rate), 1),
        "MAP_mmHg": round(_last("MAP_mmHg", engine.heart.mean_arterial_pressure), 1),
        "SpO2": round(_last("saturation", engine.blood.arterial_saturation) * 100, 1),
        "art_PO2": round(_last("art_PO2", engine.blood.arterial_PO2_mmHg), 1),
        "art_PCO2": round(_last("art_PCO2", engine.blood.arterial_PCO2_mmHg), 1),
        "pH": round(_last("pH", engine.blood.arterial_pH), 3),
        "GFR": round(_last("GFR", engine.kidney.GFR), 1),
        "RR": round(_last("RR", engine.lung.respiratory_rate), 1),
        "game_time": format_game_time(game_clock_s),
        "is_night": is_night_time(game_clock_s),
    }


def process_action(state: GameState, action_type: str, params: dict = None) -> dict:
    """
    处理一次玩家行动。

    Args:
        state: 当前游戏状态
        action_type: 行动类型
            "examine" — 做检查（需要 params["test_type"]）
            "treat"   — 治疗（params["disease_guess"]）
            "wait"    — 等待（不做任何操作，单纯消耗时间）
        params: 行动参数

    Returns:
        {
            "success": bool,
            "action_cost_min": float,
            "result": dict|None,
            "phase": str,
            "engine_summary": dict,
        }
    """
    if state.phase in ("won", "lost"):
        return {
            "success": False,
            "action_cost_min": 0.0,
            "result": None,
            "phase": state.phase,
            "medical_phase": determine_phase(state.engine),
            "engine_summary": _engine_summary(state.engine, state.game_clock_s),
        }

    params = params or {}
    result = None

    # ── 执行行动 ──
    if action_type == "examine":
        from game.test_translator import translate

        test_type = params.get("test_type", "physical")
        report = translate(test_type, state.engine)
        state.reports.append(report)
        result = report
        logger.info("行动 #%d: 检查 %s", state.action_count + 1, test_type)

    elif action_type == "treat":
        from game.treatment import apply_treatment

        disease_guess = params.get("disease_guess", "")
        state.treatment_applied = disease_guess
        treatment_result = apply_treatment(state, disease_guess)
        result = treatment_result
        # 自动更新游戏阶段
        if treatment_result["correct"]:
            state.phase = "won"
        logger.info(
            "行动 #%d: 治疗 %s → %s", state.action_count + 1, disease_guess, state.phase
        )

    elif action_type == "administer_drug":
        drug_name = params.get("drug_name", "")
        dose_mg_kg = params.get("dose_mg_kg", 0.0)
        volume_ml = params.get("volume_ml", 0.0)
        # Auto-attach pharmacology if not present
        if (
            not hasattr(state.engine, "pharmacology")
            or state.engine.pharmacology is None
        ):
            from src.pharmacology import PharmacologyState

            state.engine.pharmacology = PharmacologyState(weight_kg=state.engine.w)
        try:
            if volume_ml > 0:
                state.engine.pharmacology.administer_drug(
                    drug_name, volume_ml=volume_ml
                )
            else:
                state.engine.pharmacology.administer_drug(
                    drug_name, dose_mg_kg=dose_mg_kg
                )
            logger.info(
                "行动 #%d: 给药 %s (%.2f mg/kg)",
                state.action_count + 1,
                drug_name,
                dose_mg_kg,
            )
        except KeyError:
            logger.warning("未知药物: %s", drug_name)
            return {
                "success": False,
                "action_cost_min": 0.0,
                "result": None,
                "phase": state.phase,
                "engine_summary": _engine_summary(state.engine, state.game_clock_s),
            }

    elif action_type == "wait":
        logger.info("行动 #%d: 等待", state.action_count + 1)

    else:
        logger.warning("未知行动类型: %s", action_type)
        return {
            "success": False,
            "action_cost_min": 0.0,
            "result": None,
            "phase": state.phase,
            "engine_summary": _engine_summary(state.engine, state.game_clock_s),
        }

    # ── 推进引擎 ──
    # 行动消耗：cost=0 → 1 行动，cost>0 → cost 行动（高 cost 检查耗时更长）
    cost = _get_examine_cost(action_type, params)
    sim_seconds = K_SECONDS_PER_ACTION * cost
    state.engine.simulate(sim_seconds / 60.0)
    state.action_count += cost
    state.elapsed_time_s += sim_seconds
    state.game_clock_s += sim_seconds

    # ── 夜间修正 ──
    _apply_night_modifiers(state)

    # ── 阶段判定（医学状态） ──
    medical_phase = determine_phase(state.engine)

    # ── 死亡检测（基于医学状态更新游戏阶段） ──
    check_death(state, medical_phase)

    engine_summary = _engine_summary(state.engine, state.game_clock_s)

    logger.info(
        "行动 #%d 完成: phase=%s, HR=%.0f, MAP=%.0f, SpO2=%.1f%%",
        state.action_count,
        state.phase,
        engine_summary["HR_bpm"],
        engine_summary["MAP_mmHg"],
        engine_summary["SpO2"],
    )

    return {
        "success": True,
        "action_cost_min": K_SECONDS_PER_ACTION / 60.0,
        "result": result,
        "phase": state.phase,
        "medical_phase": medical_phase,
        "engine_summary": engine_summary,
    }


def _apply_night_modifiers(state: GameState) -> None:
    """
    应用夜间修正到引擎状态

    夜间效应：
      1. HR 生理性降低（迷走神经张力增加）— 可逆，白天恢复
      2. 疾病进展速度略降（代谢率降低）
    """
    clock_s = state.game_clock_s
    engine = state.engine
    hr_factor = get_night_hr_factor(clock_s)

    # 保存原始 HR_rest（首次进入夜间时）
    if not hasattr(state, '_original_hr_rest'):
        state._original_hr_rest = engine.heart.HR_rest

    if is_night_time(clock_s):
        # 夜间：降低 HR 基线
        night_hr_rest = max(50.0, state._original_hr_rest * hr_factor)
        engine.heart.HR_rest = night_hr_rest
        # 如果当前 HR 高于夜间基线，逐步降低
        if engine.heart.heart_rate > night_hr_rest:
            engine.heart.heart_rate = max(
                night_hr_rest,
                engine.heart.heart_rate * 0.95,  # 每步最多降 5%
            )
    else:
        # 白天：恢复原始 HR 基线
        engine.heart.HR_rest = state._original_hr_rest
        # 如果当前 HR 低于基线，逐步恢复
        if engine.heart.heart_rate < state._original_hr_rest:
            engine.heart.heart_rate = min(
                state._original_hr_rest,
                engine.heart.heart_rate * 1.05,  # 每步最多升 5%
            )

    logger.debug(
        "夜间修正已应用: is_night=%s, HR_factor=%.2f, HR_rest=%.1f, clock=%s",
        is_night_time(clock_s),
        hr_factor,
        engine.heart.HR_rest,
        format_game_time(clock_s),
    )
