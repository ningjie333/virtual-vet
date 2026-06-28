"""
Action System — 玩家行动处理系统（v2：时间预算版）。

职责:
  - GameState 数据类：承载整个游戏状态（含时间预算、待出报告）
  - process_action()：处理玩家行动（检查/治疗/等待），推进游戏时间
  - check_death()：濒死倒计时 + 死亡判定

临床 phase / summary / report 一律通过 `GameRuntime.advance_and_refresh(...)`
与 `GameRuntime.interpreter` 获取，不再保留 legacy 直读入口。

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

from game.runtime import GameRuntime, default_runtime
from src.simulation import VirtualCreature
from src.exam_registry import get_exam_registry

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
    # Q1 (2026-06-14): 多病叠加 — 保留单数向后兼容，主诊断仍存 disease_name
    # 新代码请用 disease_names (list) 处理多病场景
    disease_name: str
    disease_names: list = field(default_factory=list)  # 全部疾病（合并症）
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


def _annotate_report_timing(
    report: dict,
    *,
    observed_at_s: float,
    report_basis: str,
    available_after_min: int = 0,
) -> dict:
    """Attach explicit timing semantics to an exam report payload."""
    report["timestamp_s"] = observed_at_s  # legacy field
    report["observed_at_s"] = observed_at_s
    report["report_basis"] = report_basis
    report["available_after_min"] = available_after_min
    report["available_at_s"] = observed_at_s + (available_after_min * 60.0)
    return report


def process_action(
    state: GameState,
    action_type: str,
    params: dict = None,
    runtime: Optional[GameRuntime] = None,
) -> dict:
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
    runtime = runtime or default_runtime()
    interpreter = runtime.interpreter

    if state.phase in ("won", "lost"):
        snapshot = interpreter.snapshot(state.engine)
        return {
            "success": False,
            "time_cost_min": 0,
            "time_elapsed_min": state.time_elapsed_min,
            "time_remaining_min": state.time_remaining_min,
            "result": None,
            "new_reports": [],
            "pending_count": len(state.pending_reports),
            "phase": state.phase,
            "medical_phase": interpreter.phase(snapshot),
            "engine_summary": interpreter.summary(snapshot, state.time_elapsed_min),
        }

    params = params or {}
    result = None
    time_cost = 0
    action_started_at_s = float(state.engine.current_time_s)

    if action_type == "examine":
        test_type = params.get("test_type", "physical")
        time_cost, tier, latency_min = _get_exam_config(test_type)
        report = interpreter.report(test_type, state.engine)
        report = _annotate_report_timing(
            report,
            observed_at_s=action_started_at_s,
            report_basis="pre_advance",
            available_after_min=latency_min,
        )

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
        treatment_result = apply_treatment(state, disease_guess, runtime=runtime)
        result = treatment_result
        if treatment_result["correct"]:
            state.phase = "won"
        logger.info("治疗 %s → %s", disease_guess, state.phase)
        time_cost = 5  # 治疗操作消耗5分钟

    elif action_type == "administer_drug":
        drug_name = params.get("drug_name", "")
        dose_mg_kg = params.get("dose_mg_kg", 0.0)
        volume_ml = params.get("volume_ml", 0.0)
        try:
            runtime.treatment.administer_drug(
                state.engine,
                drug_name,
                dose_mg_kg=dose_mg_kg,
                volume_ml=volume_ml,
            )
            logger.info("给药 %s (%.2f mg/kg)", drug_name, dose_mg_kg)
        except KeyError:
            logger.warning("未知药物: %s", drug_name)
            snapshot = interpreter.snapshot(state.engine)
            return {
                "success": False,
                "time_cost_min": 0,
                "time_elapsed_min": state.time_elapsed_min,
                "time_remaining_min": state.time_remaining_min,
                "result": None,
                "new_reports": [],
                "pending_count": len(state.pending_reports),
                "phase": state.phase,
                "medical_phase": interpreter.phase(snapshot),
                "engine_summary": interpreter.summary(snapshot, state.time_elapsed_min),
                "error": f"未知药物: {drug_name}",
            }
        time_cost = 5  # 给药操作消耗5分钟

    elif action_type == "wait":
        logger.info("等待观察")
        time_cost = 10  # 等待消耗10分钟

    else:
        logger.warning("未知行动类型: %s", action_type)
        snapshot = interpreter.snapshot(state.engine)
        return {
            "success": False,
            "time_cost_min": 0,
            "time_elapsed_min": state.time_elapsed_min,
            "time_remaining_min": state.time_remaining_min,
            "result": None,
            "new_reports": [],
            "pending_count": len(state.pending_reports),
            "phase": state.phase,
            "medical_phase": interpreter.phase(snapshot),
            "engine_summary": interpreter.summary(snapshot, state.time_elapsed_min),
        }

    # ── 推进游戏时间 ──
    state.time_elapsed_min += time_cost

    # ── 推进引擎模拟并刷新解释状态（按消耗的分钟数）──
    runtime.advance_and_refresh(state.engine, float(time_cost))

    # ── 处理延迟报告（时间流逝后检查是否有报告到期）──
    new_reports = _process_pending_reports(state, time_cost)

    # ── 夜间修正（通过 modifier 协议，灰区 #1 收纳）──
    runtime.modifier.apply_night_modifiers(state)

    # ── 阶段判定 ──
    snapshot = interpreter.snapshot(state.engine)
    medical_phase = interpreter.phase(snapshot)

    # ── 死亡检测 ──
    check_death(state, medical_phase)

    # ── 时间耗尽检测 ──
    if state.time_remaining_min <= 0 and state.phase == "playing":
        state.phase = "lost"
        logger.info("时间耗尽，患犬未能得到及时诊治")

    engine_summary = interpreter.summary(snapshot, state.time_elapsed_min)

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
        "action_started_at_s": action_started_at_s,
        "state_time_s": float(state.engine.current_time_s),
        "result": result,
        "new_reports": new_reports,
        "pending_count": len(state.pending_reports),
        "phase": state.phase,
        "medical_phase": medical_phase,
        "engine_summary": engine_summary,
    }
