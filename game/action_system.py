"""
Action System — 玩家行动处理系统（5-Tier AP 版）。

职责:
  - GameState 数据类：承载整个游戏状态（含 AP 池、压力值、待出报告）
  - process_action()：处理玩家行动（检查/治疗/等待），推进引擎时间
  - determine_phase()：基于引擎数值自动判定病情阶段
  - check_death()：濒死倒计时 + 死亡判定

AP 系统设计:
  Tier 1 (0 AP): 基础观察 — 体格检查/听诊/视诊（仍消耗 1 行动）
  Tier 2 (2 AP): 快速检查 — 心电图/血常规/尿液分析/血压
  Tier 3 (3 AP): 核心诊断 — 生化/血气/X光
  Tier 4 (4-5 AP): 影像学 — 超声(4)/CT(5)
  Tier 5 (8 AP): 金标准 — 组织病理/超声心动图/穿刺等

  特性:
    - AP 池 + 每回合恢复机制
    - 组合折扣：相关检查一起开有 AP 减免
    - 结果延迟：高 tier 检查需要等待才出结果
    - 压力系统：高 tier 操作增加患畜压力
    - 物种修正：不同物种检查难度不同
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
K_SECONDS_PER_ACTION = _K["seconds_per_action"]
MORIBUND_ACTIONS_REMAINING = _K["moribund_actions_remaining"]

# ── AP 系统常量 ──
_AP = _GC["ap_system"]
AP_DEFAULT_MAX = _AP["default_max"]
AP_REGEN_PER_WAIT = _AP["regen_per_wait"]
AP_REGEN_PER_TURN = _AP["regen_per_turn"]
AP_COMBO_WINDOW = _AP["combo_window"]

# ── 检查类型注册表（从 data/examinations.json 加载） ──
_exam_reg = get_exam_registry()

# ── 组合折扣规则（从 game_config.json 加载） ──
_COMBO_BONUSES: list[tuple[set[str], int, str]] = [
    (set(cb["tests"]), cb["discount"], cb["description"])
    for cb in _GC["combo_bonuses"]
]

# ── 压力系统常量（从 game_config.json 加载） ──
_ST = _GC["stress"]
_STRESS_PER_TIER: dict[int, int] = {int(k): v for k, v in _ST["per_tier"].items()}
_STRESS_RECOVERY_PER_WAIT = _ST["recovery_per_wait"]
_STRESS_DANGER_THRESHOLD = _ST["danger_threshold"]
_STRESS_CRITICAL_THRESHOLD = _ST["critical_threshold"]
_STRESS_DECOMPENSATION_RATE = _ST["decompensation_rate"]

# ── 物种修正系数（从 game_config.json 加载） ──
_SPECIES_AP_MODIFIERS: dict[str, dict[int, int]] = {
    sp: {int(k): v for k, v in mods.items()}
    for sp, mods in _GC["species_ap_modifiers"].items()
}


def _get_exam_config(test_type: str) -> tuple[int, int, int]:
    """返回 (ap_cost, tier, latency_turns)，未知检查默认 (2, 2, 0)。"""
    return _exam_reg.get_exam(test_type)


def _get_examine_cost(action_type: str, params: dict, species: str = "犬") -> int:
    """返回行动消耗 AP 数。cost=0 返回 1（至少消耗 1 行动次数）。"""
    if action_type in ("treat", "wait", "administer_drug"):
        return 1
    test_type = params.get("test_type", "physical")
    ap_cost, tier, _ = _get_exam_config(test_type)
    species_mods = _SPECIES_AP_MODIFIERS.get(species, {})
    ap_cost += species_mods.get(tier, 0)
    return max(1, ap_cost)


def _calc_combo_discount(recent_exams: list[str]) -> tuple[int, str]:
    """
    根据最近检查历史计算组合折扣。
    返回 (discount_ap, description)。
    """
    exam_set = set(recent_exams)
    best_discount = 0
    best_desc = ""
    for required_set, discount, desc in _COMBO_BONUSES:
        if required_set.issubset(exam_set) and discount > best_discount:
            best_discount = discount
            best_desc = desc
    return best_discount, best_desc


# ── 病情阶段判定阈值（从 game_config.json 加载） ──
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


@dataclass
class PendingReport:
    """延迟报告：高 tier 检查的结果需要等待若干回合后才出现。"""
    test_type: str
    report: dict
    turns_remaining: int  # 剩余等待回合数


@dataclass
class GameState:
    """游戏状态数据类（含 AP 池、压力系统、延迟报告）。"""

    engine: VirtualCreature
    disease_name: str
    phase: str = "playing"  # "playing" | "won" | "lost"
    death_timer: Optional[int] = None
    reports: list = field(default_factory=list)
    treatment_applied: Optional[str] = None

    # ── AP 系统（AP = 时间预算）──
    current_ap: int = AP_DEFAULT_MAX
    max_ap: int = AP_DEFAULT_MAX
    total_ap_spent: int = 0  # 累计消耗 AP → 游戏时间 = total_ap_spent × 60s
    species: str = "犬"

    # ── 压力系统 ──
    stress_level: float = 0.0  # 0-100

    # ── 延迟报告队列 ──
    pending_reports: list = field(default_factory=list)  # list[PendingReport]

    # ── 组合折扣追踪 ──
    recent_exam_types: list = field(default_factory=list)  # 最近 AP_COMBO_WINDOW 次检查类型

    # ── 夜间 HR 修正 ──
    _original_hr_rest: Optional[float] = None


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


def _engine_summary(engine: VirtualCreature, total_ap_spent: int = 0) -> dict:
    """返回引擎当前状态的简要摘要。游戏时间从累计 AP 消耗计算。"""
    hist = engine.history

    def _last(key: str, fallback):
        vals = hist.get(key, [])
        return vals[-1] if vals else fallback

    game_clock_s = total_ap_spent * K_SECONDS_PER_ACTION
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


def _process_pending_reports(state: GameState) -> list[dict]:
    """处理延迟报告队列，将到期报告移入正式报告列表。返回本次新出现的报告列表。"""
    newly_available = []
    still_pending = []
    for pr in state.pending_reports:
        pr.turns_remaining -= 1
        if pr.turns_remaining <= 0:
            state.reports.append(pr.report)
            newly_available.append(pr.report)
            logger.info("延迟报告已出: %s", pr.test_type)
        else:
            still_pending.append(pr)
    state.pending_reports = still_pending
    return newly_available


def _apply_stress(state: GameState, tier: int) -> None:
    """根据检查 tier 增加压力值。"""
    stress_add = _STRESS_PER_TIER.get(tier, 0)
    if stress_add > 0:
        old_stress = state.stress_level
        state.stress_level = min(100.0, state.stress_level + stress_add)
        logger.debug("压力变化: %.0f → %.0f (+%d, tier %d)", old_stress, state.stress_level, stress_add, tier)

    # 超高压力加速恶化
    if state.stress_level >= _STRESS_CRITICAL_THRESHOLD:
        engine = state.engine
        # 压力导致交感衰竭 → HR 额外下降
        if engine.heart.heart_rate > 40:
            engine.heart.heart_rate *= (1.0 - _STRESS_DECOMPENSATION_RATE)
        logger.warning("患畜压力过高 (%.0f)，出现代偿失调！", state.stress_level)


def _recover_stress(state: GameState) -> None:
    """等待时恢复压力。"""
    if state.stress_level > 0:
        old = state.stress_level
        state.stress_level = max(0.0, state.stress_level - _STRESS_RECOVERY_PER_WAIT)
        logger.debug("压力恢复: %.0f → %.0f", old, state.stress_level)


def _apply_night_modifiers(state: GameState) -> None:
    """应用夜间修正到引擎状态。"""
    clock_s = state.total_ap_spent * K_SECONDS_PER_ACTION
    engine = state.engine
    hr_factor = get_night_hr_factor(clock_s)

    if state._original_hr_rest is None:
        state._original_hr_rest = engine.heart.HR_rest

    if is_night_time(clock_s):
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
        is_night_time(clock_s),
        hr_factor,
        engine.heart.HR_rest,
        format_game_time(clock_s),
    )


def process_action(state: GameState, action_type: str, params: dict = None) -> dict:
    """
    处理一次玩家行动（5-Tier AP 版）。

    AP 消耗:
      - examine: 消耗 AP（根据 tier），0 AP 的检查仍消耗 1 行动次数
      - treat / administer_drug / wait: 消耗 1 行动次数，不消耗 AP

    返回:
        {
            "success": bool,
            "action_cost_min": float,
            "ap_cost": int,
            "ap_remaining": int,
            "stress_level": float,
            "result": dict|None,
            "new_reports": list,       # 本次新出的报告（含延迟到期的）
            "pending_count": int,      # 待出报告数量
            "phase": str,
            "engine_summary": dict,
            "combo_bonus": str | None, # 组合折扣描述
        }
    """
    if state.phase in ("won", "lost"):
        return {
            "success": False,
            "action_cost_min": 0.0,
            "ap_cost": 0,
            "ap_remaining": state.current_ap,
            "stress_level": round(state.stress_level, 1),
            "result": None,
            "new_reports": [],
            "pending_count": len(state.pending_reports),
            "phase": state.phase,
            "medical_phase": determine_phase(state.engine),
            "engine_summary": _engine_summary(state.engine, state.total_ap_spent),
            "combo_bonus": None,
        }

    params = params or {}
    result = None
    ap_cost = 0
    combo_desc = None

    # ── 检查 AP 是否足够 ──
    if action_type == "examine":
        test_type = params.get("test_type", "physical")
        ap_cost, tier, latency = _get_exam_config(test_type)
        # 物种修正
        species_mods = _SPECIES_AP_MODIFIERS.get(state.species, {})
        ap_cost += species_mods.get(tier, 0)
        ap_cost = max(0, ap_cost)

        if ap_cost > state.current_ap:
            return {
                "success": False,
                "action_cost_min": 0.0,
                "ap_cost": 0,
                "ap_remaining": state.current_ap,
                "stress_level": round(state.stress_level, 1),
                "result": None,
                "new_reports": [],
                "pending_count": len(state.pending_reports),
                "phase": state.phase,
                "medical_phase": determine_phase(state.engine),
                "engine_summary": _engine_summary(state.engine, state.total_ap_spent),
                "combo_bonus": None,
                "error": f"AP 不足（需要 {ap_cost}，剩余 {state.current_ap}）",
            }

        # 组合折扣检查
        discount, combo_desc = _calc_combo_discount(state.recent_exam_types + [test_type])
        effective_ap = max(0, ap_cost - discount)
        # 实际消耗 AP（折扣后）
        actual_ap = min(effective_ap, state.current_ap)

        from game.test_translator import translate
        report = translate(test_type, state.engine)

        # 压力系统
        _apply_stress(state, tier)

        # 延迟报告处理
        if latency > 0:
            state.pending_reports.append(PendingReport(
                test_type=test_type,
                report=report,
                turns_remaining=latency,
            ))
            logger.info("检查 %s 已采样，报告将在 %d 回合后出具", test_type, latency)
        else:
            state.reports.append(report)

        # 更新最近检查历史（用于组合折扣）
        state.recent_exam_types.append(test_type)
        if len(state.recent_exam_types) > AP_COMBO_WINDOW:
            state.recent_exam_types = state.recent_exam_types[-AP_COMBO_WINDOW:]

        result = report
        ap_cost = actual_ap
        state.current_ap -= ap_cost
        logger.info("检查 %s (AP -%d, 剩余 %d)",
                     test_type, ap_cost, state.current_ap)

    elif action_type == "treat":
        from game.treatment import apply_treatment
        disease_guess = params.get("disease_guess", "")
        state.treatment_applied = disease_guess
        treatment_result = apply_treatment(state, disease_guess)
        result = treatment_result
        if treatment_result["correct"]:
            state.phase = "won"
        logger.info("治疗 %s → %s", disease_guess, state.phase)

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
                "action_cost_min": 0.0,
                "ap_cost": 0,
                "ap_remaining": state.current_ap,
                "stress_level": round(state.stress_level, 1),
                "result": None,
                "new_reports": [],
                "pending_count": len(state.pending_reports),
                "phase": state.phase,
                "medical_phase": determine_phase(state.engine),
                "engine_summary": _engine_summary(state.engine, state.total_ap_spent),
                "combo_bonus": None,
                "error": f"未知药物: {drug_name}",
            }

    elif action_type == "wait":
        logger.info("等待")
        # 等待恢复 AP 和压力
        state.current_ap = min(state.max_ap, state.current_ap + AP_REGEN_PER_WAIT)
        _recover_stress(state)
    else:
        logger.warning("未知行动类型: %s", action_type)
        return {
            "success": False,
            "action_cost_min": 0.0,
            "ap_cost": 0,
            "ap_remaining": state.current_ap,
            "stress_level": round(state.stress_level, 1),
            "result": None,
            "new_reports": [],
            "pending_count": len(state.pending_reports),
            "phase": state.phase,
            "medical_phase": determine_phase(state.engine),
            "engine_summary": _engine_summary(state.engine, state.total_ap_spent),
            "combo_bonus": None,
        }

    # ── 推进引擎时间 ──
    # AP = 时间预算：任何行动都消耗时间（total_ap_spent += time_cost）
    # examine 同时消耗 AP 资源（已在上面扣除），非 examine 只消耗时间
    time_cost = _get_examine_cost(action_type, params, state.species)
    sim_seconds = K_SECONDS_PER_ACTION * time_cost
    state.engine.simulate(sim_seconds / 60.0)
    state.total_ap_spent += time_cost

    # ── 每回合自动恢复少量 AP ──
    if action_type != "wait":  # wait 已经恢复过了
        state.current_ap = min(state.max_ap, state.current_ap + AP_REGEN_PER_WAIT)

    # ── 夜间修正 ──
    _apply_night_modifiers(state)

    # ── 处理延迟报告 ──
    new_reports = _process_pending_reports(state)

    # ── 阶段判定 ──
    medical_phase = determine_phase(state.engine)

    # ── 死亡检测 ──
    check_death(state, medical_phase)

    engine_summary = _engine_summary(state.engine, state.total_ap_spent)

    logger.info(
        "完成: phase=%s, AP=%d/%d, 已用时间=%d, 压力=%.0f, HR=%.0f, MAP=%.0f",
        state.phase,
        state.current_ap,
        state.max_ap,
        state.total_ap_spent,
        state.stress_level,
        engine_summary["HR_bpm"],
        engine_summary["MAP_mmHg"],
    )

    return {
        "success": True,
        "action_cost_min": K_SECONDS_PER_ACTION / 60.0,
        "ap_cost": ap_cost,
        "ap_remaining": state.current_ap,
        "stress_level": round(state.stress_level, 1),
        "result": result,
        "new_reports": new_reports,
        "pending_count": len(state.pending_reports),
        "phase": state.phase,
        "medical_phase": medical_phase,
        "engine_summary": engine_summary,
        "combo_bonus": combo_desc,
    }