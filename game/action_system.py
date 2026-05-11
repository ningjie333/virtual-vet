"""
Action System — 玩家行动处理系统（v2：时间预算版）。

职责:
  - GameState 数据类：承载整个游戏状态（含时间预算、待出报告）
  - process_action()：处理玩家行动（检查/治疗/等待），推进游戏时间
  - determine_phase()：基于引擎数值自动判定病情阶段
  - check_death()：濒死倒计时 + 死亡判定

时间系统（v2）:
  - 删除 AP 系统，改用真实时间预算（分钟）
  - 每个检查消耗真实时间（time_cost_min）
  - 报告延迟使用真实分钟（latency_min），在等待/做其他检查时流逝
  - 难度决定时间预算：★☆☆=120min, ★★☆=90min, ★★★=60min
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.simulation import VirtualCreature
from src.parameters import base_cardiac_output_ml_min, ARTERIAL_SATURATION_NORMAL
from src.exam_registry import get_exam_registry
from game.time_manager import (
    is_night_time,
    get_night_hr_factor,
    get_night_progression_factor,
    format_game_time,
)

logger = logging.getLogger(__name__)

# ── 游戏配置（从 data/game_config.json 加载） ──
_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_game_config() -> dict:
    """加载 data/game_config.json，返回原始 dict。"""
    with open(_DATA_DIR / "game_config.json", "r", encoding="utf-8") as f:
        return json.load(f)


_GC = _load_game_config()

# ── 基础常量 ──
_K = _GC["time"]
MORIBUND_TURNS_REMAINING = _K["moribund_turns_remaining"]

# ── 时间预算（分钟）──
_TB = _GC["time_budget"]
TIME_BUDGET_EASY = _TB["easy_min"]
TIME_BUDGET_NORMAL = _TB["normal_min"]
TIME_BUDGET_HARD = _TB["hard_min"]

# ── 检查类型注册表（从 data/examinations.json 加载） ──
_exam_reg = get_exam_registry()

# ── 病情阶段判定阈值 ──
_PT = _GC["phase_thresholds"]
_THRESHOLDS = {
    "MAP": (
        _PT["MAP"]["low_moribund"], _PT["MAP"]["low_critical"],
        _PT["MAP"]["low_worsening"], _PT["MAP"]["high_worsening"],
        _PT["MAP"]["high_critical"], _PT["MAP"]["high_moribund"],
    ),
    "SpO2": (
        _PT["SpO2"]["low_moribund"], _PT["SpO2"]["low_critical"],
        _PT["SpO2"]["low_worsening"], _PT["SpO2"]["high_worsening"],
        _PT["SpO2"]["high_critical"], _PT["SpO2"]["high_moribund"],
    ),
    "HR": (
        _PT["HR"]["low_moribund"], _PT["HR"]["low_critical"],
        _PT["HR"]["low_worsening"], _PT["HR"]["high_worsening"],
        _PT["HR"]["high_critical"], _PT["HR"]["high_moribund"],
    ),
    "pH": (
        _PT["pH"]["low_moribund"], _PT["pH"]["low_critical"],
        _PT["pH"]["low_worsening"], _PT["pH"]["high_worsening"],
        _PT["pH"]["high_critical"], _PT["pH"]["high_moribund"],
    ),
}

_DO2_WARN = _PT["DO2"]["warn"]
_DO2_CRIT = _PT["DO2"]["critical"]
_DO2_MORIB = _PT["DO2"]["moribund"]

_LACTATE_WARN = _PT["lactate"]["warn"]
_LACTATE_CRIT = _PT["lactate"]["critical"]

_URINE_OLIGURIA = _PT["urine"]["oliguria"]
_URINE_ANURIA = _PT["urine"]["anuria"]


def _get_exam_config(test_type: str) -> tuple[int, int, int]:
    """返回 (time_cost_min, tier, latency_turns)，未知检查默认 (5, 2, 0)。"""
    return _exam_reg.get_exam(test_type)


# ── 结果延迟报告 ──

@dataclass
class PendingReport:
    """延迟报告：高 tier 检查的结果需要等待若干分钟后出现。"""
    test_type: str
    report: dict
    minutes_remaining: int  # 剩余等待分钟数


@dataclass
class GameState:
    """游戏状态数据类（v2：时间预算版）。"""

    engine: VirtualCreature
    disease_name: str
    phase: str = "playing"  # "playing" | "won" | "lost"
    death_timer: Optional[int] = None
    reports: list = field(default_factory=list)
    treatment_applied: Optional[str] = None

    # ── 时间系统 ──
    time_elapsed_min: int = 0       # 已消耗的诊疗时间（分钟）
    time_budget_min: int = TIME_BUDGET_NORMAL  # 总时间预算（分钟）
    species: str = "犬"

    # ── 延迟报告队列 ──
    pending_reports: list = field(default_factory=list)  # list[PendingReport]

    # ── 夜间 HR 修正 ──
    _original_hr_rest: Optional[float] = None

    @property
    def time_remaining_min(self) -> int:
        """剩余时间（分钟）。"""
        return max(0, self.time_budget_min - self.time_elapsed_min)


def compute_DO2(engine: VirtualCreature) -> float:
    """计算氧输送指数 DO₂（相对值，健康犬 ≈ 1.0）。"""
    hist = engine.history

    def _last(key: str, fallback):
        vals = hist.get(key, [])
        return vals[-1] if vals else fallback

    weight_kg = engine.w
    normal_co = base_cardiac_output_ml_min(weight_kg)
    co = _last("CO_ml_min", normal_co)
    sao2 = _last("saturation", ARTERIAL_SATURATION_NORMAL)
    do2 = (co / normal_co) * sao2
    return max(0.0, min(1.0, do2))


def determine_phase(engine: VirtualCreature) -> str:
    """
    根据引擎当前状态判定病情阶段。

    综合评分:
    1. 传统阈值（MAP/SpO2/HR/pH）
    2. DO₂ 氧输送指数
    3. 乳酸
    4. 尿量

    返回: "stable" | "worsening" | "critical" | "moribund"
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

    if do2 <= _DO2_MORIB:
        do2_score = 3
    elif do2 <= _DO2_CRIT:
        do2_score = 2
    elif do2 <= _DO2_WARN:
        do2_score = 1
    else:
        do2_score = 0

    if lactate >= _LACTATE_CRIT:
        lactate_score = 2
    elif lactate >= _LACTATE_WARN:
        lactate_score = 1
    else:
        lactate_score = 0

    if urine_per_kg < _URINE_ANURIA:
        urine_score = 3
    elif urine_per_kg < _URINE_OLIGURIA:
        urine_score = 2
    else:
        urine_score = 0

    if threshold_score >= 3 or do2_score >= 3 or urine_score >= 3:
        return "moribund"

    if hr < 60 and urine_per_kg < _URINE_ANURIA:
        return "moribund"

    crit_count = sum([
        threshold_score >= 2,
        do2_score >= 2,
        lactate_score >= 2,
        urine_score >= 2,
    ])
    if crit_count >= 2 or do2_score >= 2:
        return "critical"

    if threshold_score >= 1 or do2_score >= 1 or lactate_score >= 1 or urine_score >= 1:
        return "worsening"

    return "stable"


def check_death(state: GameState, medical_phase: str) -> GameState:
    """死亡检测逻辑（基于医学阶段更新游戏阶段）。"""
    if medical_phase == "moribund":
        if state.death_timer is None:
            state.death_timer = MORIBUND_TURNS_REMAINING
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


def _engine_summary(engine: VirtualCreature, elapsed_min: int = 0) -> dict:
    """返回引擎当前状态的简要摘要。"""
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
        "game_time": format_game_time(elapsed_min),
        "is_night": is_night_time(elapsed_min),
    }


def _process_pending_reports(state: GameState, elapsed_min: int) -> list[dict]:
    """
    处理延迟报告队列，将到期报告移入正式报告列表。
    每次调用时递减剩余时间（按本次消耗的分钟数）。
    返回本次新出现的报告列表。
    """
    newly_available = []
    still_pending = []
    for pr in state.pending_reports:
        pr.minutes_remaining -= elapsed_min
        if pr.minutes_remaining <= 0:
            state.reports.append(pr.report)
            newly_available.append(pr.report)
            logger.info("延迟报告已出: %s", pr.test_type)
        else:
            still_pending.append(pr)
    state.pending_reports = still_pending
    return newly_available


def _apply_night_modifiers(state: GameState) -> None:
    """应用夜间修正到引擎状态。"""
    clock_min = state.time_elapsed_min
    engine = state.engine
    hr_factor = get_night_hr_factor(clock_min)

    if state._original_hr_rest is None:
        state._original_hr_rest = engine.heart.HR_rest

    if is_night_time(clock_min):
        night_hr_rest = max(50.0, state._original_hr_rest * hr_factor)
        engine.heart.HR_rest = night_hr_rest
        if engine.heart.heart_rate > night_hr_rest:
            engine.heart.heart_rate = max(
                night_hr_rest,
                engine.heart.heart_rate * 0.95,
            )
    else:
        engine.heart.HR_rest = state._original_hr_rest
        if engine.heart.heart_rate < state._original_hr_rest:
            engine.heart.heart_rate = min(
                state._original_hr_rest,
                engine.heart.heart_rate * 1.05,
            )

    logger.debug(
        "夜间修正: is_night=%s, HR_factor=%.2f, HR_rest=%.1f, clock=%s",
        is_night_time(clock_min),
        hr_factor,
        engine.heart.HR_rest,
        format_game_time(clock_min),
    )


def process_action(state: GameState, action_type: str, params: dict = None) -> dict:
    """
    处理一次玩家行动（v2：时间预算版）。

    时间消耗:
      - examine: 消耗 time_cost_min（真实分钟）
      - treat / administer_drug / wait: 消耗 5 分钟

    返回:
        {
            "success": bool,
            "time_cost_min": int,
            "time_elapsed_min": int,
            "time_remaining_min": int,
            "result": dict|None,
            "new_reports": list,       # 本次新出的报告（含延迟到期的）
            "pending_count": int,      # 待出报告数量
            "phase": str,
            "medical_phase": str,
            "engine_summary": dict,
        }
    """
    if state.phase in ("won", "lost"):
        return {
            "success": False,
            "time_cost_min": 0,
            "time_elapsed_min": state.time_elapsed_min,
            "time_remaining_min": state.time_remaining_min,
            "result": None,
            "new_reports": [],
            "pending_count": len(state.pending_reports),
            "phase": state.phase,
            "medical_phase": determine_phase(state.engine),
            "engine_summary": _engine_summary(state.engine, state.time_elapsed_min),
        }

    params = params or {}
    result = None
    time_cost = 0

    if action_type == "examine":
        test_type = params.get("test_type", "physical")
        time_cost, tier, latency_min = _get_exam_config(test_type)

        from game.test_translator import translate
        report = translate(test_type, state.engine)

        # 延迟报告处理
        if latency_min > 0:
            state.pending_reports.append(PendingReport(
                test_type=test_type,
                report=report,
                minutes_remaining=latency_min,
            ))
            logger.info("检查 %s 已采样，报告将在 %d 分钟后出具", test_type, latency_min)
        else:
            state.reports.append(report)

        result = report
        logger.info("检查 %s (%d 分钟)", test_type, time_cost)

    elif action_type == "treat":
        from game.treatment import apply_treatment
        disease_guess = params.get("disease_guess", "")
        state.treatment_applied = disease_guess
        treatment_result = apply_treatment(state, disease_guess)
        result = treatment_result
        if treatment_result["correct"]:
            state.phase = "won"
        logger.info("治疗 %s → %s", disease_guess, state.phase)
        time_cost = 5  # 治疗操作消耗5分钟

    elif action_type == "administer_drug":
        drug_name = params.get("drug_name", "")
        dose_mg_kg = params.get("dose_mg_kg", 0.0)
        volume_ml = params.get("volume_ml", 0.0)
        if (
            not hasattr(state.engine, "pharmacology")
            or state.engine.pharmacology is None
        ):
            from src.pharmacology import PharmacologyState
            state.engine.pharmacology = PharmacologyState(weight_kg=state.engine.w)
        try:
            if volume_ml > 0:
                state.engine.pharmacology.administer_drug(drug_name, volume_ml=volume_ml)
            else:
                state.engine.pharmacology.administer_drug(drug_name, dose_mg_kg=dose_mg_kg)
            logger.info("给药 %s (%.2f mg/kg)", drug_name, dose_mg_kg)
        except KeyError:
            logger.warning("未知药物: %s", drug_name)
            return {
                "success": False,
                "time_cost_min": 0,
                "time_elapsed_min": state.time_elapsed_min,
                "time_remaining_min": state.time_remaining_min,
                "result": None,
                "new_reports": [],
                "pending_count": len(state.pending_reports),
                "phase": state.phase,
                "medical_phase": determine_phase(state.engine),
                "engine_summary": _engine_summary(state.engine, state.time_elapsed_min),
                "error": f"未知药物: {drug_name}",
            }
        time_cost = 5  # 给药操作消耗5分钟

    elif action_type == "wait":
        logger.info("等待观察")
        time_cost = 10  # 等待消耗10分钟

    else:
        logger.warning("未知行动类型: %s", action_type)
        return {
            "success": False,
            "time_cost_min": 0,
            "time_elapsed_min": state.time_elapsed_min,
            "time_remaining_min": state.time_remaining_min,
            "result": None,
            "new_reports": [],
            "pending_count": len(state.pending_reports),
            "phase": state.phase,
            "medical_phase": determine_phase(state.engine),
            "engine_summary": _engine_summary(state.engine, state.time_elapsed_min),
        }

    # ── 推进游戏时间 ──
    state.time_elapsed_min += time_cost

    # ── 推进引擎模拟（按消耗的分钟数）──
    state.engine.simulate(float(time_cost))

    # ── 处理延迟报告（时间流逝后检查是否有报告到期）──
    new_reports = _process_pending_reports(state, time_cost)

    # ── 夜间修正 ──
    _apply_night_modifiers(state)

    # ── 阶段判定 ──
    medical_phase = determine_phase(state.engine)

    # ── 死亡检测 ──
    check_death(state, medical_phase)

    # ── 时间耗尽检测 ──
    if state.time_remaining_min <= 0 and state.phase == "playing":
        state.phase = "lost"
        logger.info("时间耗尽，患犬未能得到及时诊治")

    engine_summary = _engine_summary(state.engine, state.time_elapsed_min)

    logger.info(
        "完成: phase=%s, 已用时间=%d/%d min, HR=%.0f, MAP=%.0f",
        state.phase,
        state.time_elapsed_min,
        state.time_budget_min,
        engine_summary["HR_bpm"],
        engine_summary["MAP_mmHg"],
    )

    return {
        "success": True,
        "time_cost_min": time_cost,
        "time_elapsed_min": state.time_elapsed_min,
        "time_remaining_min": state.time_remaining_min,
        "result": result,
        "new_reports": new_reports,
        "pending_count": len(state.pending_reports),
        "phase": state.phase,
        "medical_phase": medical_phase,
        "engine_summary": engine_summary,
    }
