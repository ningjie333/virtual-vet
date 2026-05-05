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

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from src.simulation import VirtualCreature
from src.parameters import base_cardiac_output_ml_min, ARTERIAL_SATURATION_NORMAL
from game.time_manager import (
    is_night_time,
    get_night_hr_factor,
    get_night_progression_factor,
    format_game_time,
)

logger = logging.getLogger(__name__)

# ── 基础常量 ──
K_SECONDS_PER_ACTION = 60  # 1 次基础行动 = 60 秒 ODE 仿真
MORIBUND_ACTIONS_REMAINING = 3  # 进入濒死后还能做的行动次数

# ── AP 系统常量 ──
AP_DEFAULT_MAX = 10  # 默认 AP 上限
AP_REGEN_PER_WAIT = 2  # 每次等待恢复 AP 数
AP_REGEN_PER_TURN = 1  # 每回合（任何行动后）自动恢复 AP 数
AP_COMBO_WINDOW = 3  # 组合折扣窗口（连续 N 次检查内）

# ── Tier 定义 ──
# cost=0 的检查仍消耗 1 行动次数，但不消耗 AP
_TIER_COSTS: dict[int, int] = {
    1: 0,   # 基础观察
    2: 2,   # 快速检查
    3: 3,   # 核心诊断
    4: 4,   # 影像学（超声）
    5: 8,   # 金标准
}

# ── 检查项目 AP cost 表（与 data/examinations.json 同步） ──
# 格式: test_type -> (ap_cost, tier, latency_turns)
# latency_turns: 报告延迟几个行动后出现（0=即时）
_EXAM_CONFIG: dict[str, tuple[int, int, int]] = {
    # Tier 1: 基础观察，即时出结果，不耗 AP
    "physical":      (0, 1, 0),
    "auscultation":  (0, 1, 0),
    "inspection":    (0, 1, 0),
    # Tier 2: 快速检查，即时出结果，2 AP
    "ecg":           (2, 2, 0),
    "blood_routine": (2, 2, 0),
    "urinalysis":    (2, 2, 0),
    "blood_pressure":(2, 2, 0),
    # Tier 3: 核心诊断，1 回合延迟，3 AP
    "blood_biochem": (3, 3, 1),
    "blood_gas":     (3, 3, 1),
    "chest_xray":    (3, 3, 1),
    # Tier 4: 影像学，2 回合延迟
    "ultrasound":    (4, 4, 2),
    "ct":            (5, 4, 2),
    # Tier 5: 金标准，3 回合延迟，8 AP
    "cytology":          (8, 5, 3),
    "snap_test":         (8, 5, 3),
    "fna":               (8, 5, 3),
    "abdominocentesis":  (8, 5, 3),
    "thoracocentesis":   (8, 5, 3),
    "echocardiography":  (8, 5, 3),
    "endoscopy":         (8, 5, 3),
    "mri":               (8, 5, 3),
    "histopathology":    (8, 5, 3),
}

# ── 组合折扣规则 ──
# 格式: (test_type_set, discount_ap, description)
# 当窗口期内同时做了集合内的所有检查时，最便宜的一个减免 discount_ap
_COMBO_BONUSES: list[tuple[set[str], int, str]] = [
    ({"chest_xray", "ultrasound"}, 1, "影像组合：X光+超声"),
    ({"blood_routine", "blood_biochem"}, 1, "血液组合：血常规+生化"),
    ({"blood_routine", "blood_biochem", "blood_gas"}, 2, "全面血液：血常规+生化+血气"),
    ({"ecg", "echocardiography"}, 1, "心脏组合：心电图+超声心动"),
    ({"physical", "auscultation", "inspection"}, 0, "基础体格套餐（无折扣，仅标记）"),
    ({"ct", "chest_xray"}, 1, "进阶影像：替代X光，CT减免"),
]

# ── 压力系统常量 ──
_STRESS_PER_TIER: dict[int, int] = {
    1: 0,   # 基础：无压力
    2: 2,   # 快速：轻微压力
    3: 5,   # 核心：中等压力
    4: 10,  # 影像：显著压力
    5: 15,  # 金标：高压力
}
_STRESS_RECOVERY_PER_WAIT = 8  # 每次等待恢复压力
_STRESS_DANGER_THRESHOLD = 50  # 压力 > 50 时体征不可靠
_STRESS_CRITICAL_THRESHOLD = 80  # 压力 > 80 时加速恶化
_STRESS_DECOMPENSATION_RATE = 0.05  # 超高压力下每回合额外恶化概率

# ── 物种修正系数 ──
# 格式: species -> {tier -> ap_modifier}
# 猫：小体型，高 tier 检查更难（+1 AP for tier >= 3）
# 马：大体型，基础检查更难但影像更容易
_SPECIES_AP_MODIFIERS: dict[str, dict[int, int]] = {
    "犬": {},  # 基准，无修正
    "猫": {3: 1, 4: 1, 5: 2},  # 高 tier 更难
    "马": {1: 1, 2: 1, 4: -1, 5: -1},  # 基础更难，影像更易
}


def _get_exam_config(test_type: str) -> tuple[int, int, int]:
    """返回 (ap_cost, tier, latency_turns)，未知检查默认 (2, 2, 0)。"""
    return _EXAM_CONFIG.get(test_type, (2, 2, 0))


def _get_examine_cost(action_type: str, params: dict, species: str = "犬") -> int:
    """返回行动消耗 AP 数。cost=0 返回 1（至少消耗 1 行动次数）。"""
    if action_type in ("treat", "wait", "administer_drug"):
        return 1  # 行动次数消耗，不消耗 AP
    test_type = params.get("test_type", "physical")
    ap_cost, tier, _ = _get_exam_config(test_type)
    # 物种修正
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


# ── 病情阶段判定阈值 ──
# 元组格式: (low_moribund, low_critical, low_worsening, high_worsening, high_critical, high_moribund)
_THRESHOLDS = {
    "MAP": (40, 50, 60, 150, 160, 180),
    "SpO2": (70, 80, 90, 100, 100, 100),
    "HR": (40, 50, 60, 160, 180, 200),
    "pH": (7.0, 7.1, 7.2, 7.6, 7.7, 7.8),
}

# ── DO₂ 阶段判定阈值（相对值，健康犬归一化 ≈ 1.0） ──
_DO2_WARN = 0.6
_DO2_CRIT = 0.4
_DO2_MORIB = 0.25

# 乳酸阈值（mmol/L）
_LACTATE_WARN = 3.0
_LACTATE_CRIT = 5.0

# 尿量阈值（mL/min/kg），低于此值为少尿
_URINE_OLIGURIA = 0.008
_URINE_ANURIA = 0.002


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
    action_count: int = 0
    elapsed_time_s: float = 0.0
    phase: str = "playing"  # "playing" | "won" | "lost"
    death_timer: Optional[int] = None
    reports: list = field(default_factory=list)
    treatment_applied: Optional[str] = None
    game_clock_s: float = 0.0

    # ── AP 系统 ──
    current_ap: int = AP_DEFAULT_MAX
    max_ap: int = AP_DEFAULT_MAX
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


def _engine_summary(engine: VirtualCreature, game_clock_s: float = 0.0) -> dict:
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
    clock_s = state.game_clock_s
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
            "engine_summary": _engine_summary(state.engine, state.game_clock_s),
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
                "engine_summary": _engine_summary(state.engine, state.game_clock_s),
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
        logger.info("行动 #%d: 检查 %s (AP -%d, 剩余 %d)",
                     state.action_count + 1, test_type, ap_cost, state.current_ap)

    elif action_type == "treat":
        from game.treatment import apply_treatment
        disease_guess = params.get("disease_guess", "")
        state.treatment_applied = disease_guess
        treatment_result = apply_treatment(state, disease_guess)
        result = treatment_result
        if treatment_result["correct"]:
            state.phase = "won"
        logger.info("行动 #%d: 治疗 %s → %s",
                     state.action_count + 1, disease_guess, state.phase)

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
            logger.info("行动 #%d: 给药 %s (%.2f mg/kg)",
                         state.action_count + 1, drug_name, dose_mg_kg)
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
                "engine_summary": _engine_summary(state.engine, state.game_clock_s),
                "combo_bonus": None,
                "error": f"未知药物: {drug_name}",
            }

    elif action_type == "wait":
        logger.info("行动 #%d: 等待", state.action_count + 1)
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
            "engine_summary": _engine_summary(state.engine, state.game_clock_s),
            "combo_bonus": None,
        }

    # ── 推进引擎时间 ──
    # 行动次数消耗：0 AP 检查仍消耗 1 次，高 AP 检查消耗更多
    action_cost = _get_examine_cost(action_type, params, state.species)
    sim_seconds = K_SECONDS_PER_ACTION * action_cost
    state.engine.simulate(sim_seconds / 60.0)
    state.action_count += action_cost
    state.elapsed_time_s += sim_seconds
    state.game_clock_s += sim_seconds

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

    engine_summary = _engine_summary(state.engine, state.game_clock_s)

    logger.info(
        "行动 #%d 完成: phase=%s, AP=%d/%d, 压力=%.0f, HR=%.0f, MAP=%.0f",
        state.action_count,
        state.phase,
        state.current_ap,
        state.max_ap,
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