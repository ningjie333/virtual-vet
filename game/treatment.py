"""
Treatment — 治疗判定与药物协议执行。

职责:
  - 验证玩家的诊断选择是否匹配实际疾病
  - 诊断正确 → 执行对应药物协议（而非直接宣布胜利）
  - 诊断错误 → 返回误诊提示
  - 支持治疗 → 补液，不结束游戏
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.action_system import GameState

logger = logging.getLogger(__name__)

# ── 从 data/diseases.json 加载治疗协议和消息 ──
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
with open(os.path.join(_DATA_DIR, "diseases.json"), encoding="utf-8") as _f:
    _DISEASE_DATA: dict = json.load(_f)

_DRUG_PROTOCOL: dict[str, list[dict]] = _DISEASE_DATA["treatment_protocols"]
_WIN_MESSAGES: dict[str, str] = _DISEASE_DATA["messages"]["win"]
_LOSS_MESSAGES: dict[str, str] = _DISEASE_DATA["messages"]["loss"]


def _ensure_pharmacology(engine) -> None:
    """确保引擎已挂载 PharmacologyState。"""
    from src.pharmacology import PharmacologyState

    if not hasattr(engine, "pharmacology") or engine.pharmacology is None:
        engine.pharmacology = PharmacologyState(weight_kg=engine.w)


def _administer_protocol(engine, disease_name: str) -> list[str]:
    """
    根据疾病名称执行对应的药物协议。

    Returns:
        已给药物名称列表。
    """
    _ensure_pharmacology(engine)
    protocol = _DRUG_PROTOCOL.get(disease_name, [])
    given: list[str] = []
    for entry in protocol:
        if "volume_ml" in entry:
            engine.pharmacology.administer_drug(
                entry["drug_name"], volume_ml=entry["volume_ml"]
            )
        else:
            engine.pharmacology.administer_drug(
                entry["drug_name"], dose_mg_kg=entry["dose_mg_kg"]
            )
        given.append(entry["drug_name"])
    return given


def is_correct_treatment(game_state: GameState, disease_guess: str) -> bool:
    """
    判断治疗选择是否匹配实际疾病（向后兼容单病接口）。

    Q4.2 (2026-06-14): 主诊断必须对。合并症是 bonus。
    """
    return disease_guess == game_state.disease_name


def _resolve_guesses(disease_guess: str | list[str]) -> list[str]:
    """Normalize disease_guess to a list (Q4.1=C: 支持 list 或 str 输入)。"""
    if isinstance(disease_guess, list):
        return [g for g in disease_guess if g]
    return [disease_guess] if disease_guess else []


def apply_treatment(game_state: GameState, disease_guess: str | list[str]) -> dict:
    """
    应用治疗，判定胜负（Q4: 多病支持）。

    Q4.1=C (auto-infer): disease_guess 可以是 list（多病）或 str（单病向后兼容）。
        系统自动对 list 中每个 guess admin 对应 protocol（Q4.3=B: 运行时合并）。
    Q4.2=B (主诊断必须对): win 条件 = game_state.disease_name (主诊断) 在 guess list 中。
        合并症猜对 → bonus 消息；猜错 → 不影响 win 判定。
    Q4.3=B (运行时合并): 按 guess list 顺序依次 admin 单病 protocol。

    Args:
        game_state: 当前游戏状态
        disease_guess: 玩家选择的疾病名称（str 或 list[str]）

    Returns:
        {
            "success": True,
            "correct": bool,        # 主诊断是否猜对
            "actual_disease": str,   # 主诊断
            "chosen_disease": str | list[str],  # 玩家猜的
            "phase": str,            # "won" 或 "playing"
            "message": str,          # 中文结果描述
            "drugs_given": list,     # 已给药物列表
            "comorbidity_correct": bool | None,  # 合并症是否猜对 (None=无合并症)
        }
    """
    guesses = _resolve_guesses(disease_guess)
    primary = game_state.disease_name
    all_targets = game_state.disease_names  # [primary, comorbidity1, ...]

    # Q4.2: 主诊断必须在 guess list 中才算 correct
    primary_correct = primary in guesses

    # 合并症判定（仅当有多病时有意义）
    comorbidity_correct: bool | None = None
    if len(all_targets) > 1:
        comorbidities = all_targets[1:]  # 除主诊断外的所有疾病
        comorbidity_correct = all(c in guesses for c in comorbidities)

    # ── supportive_care 特殊处理 ──
    if len(guesses) == 1 and guesses[0] == "supportive_care":
        _apply_supportive_care(game_state)
        return {
            "success": True,
            "correct": False,
            "actual_disease": primary,
            "chosen_disease": "supportive_care",
            "phase": "playing",
            "message": "支持治疗已执行：静脉补液 200 mL。患犬暂时感觉好了一些，但根本问题仍未解决。建议继续检查明确诊断。",
            "drugs_given": ["fluid_bolus"],
            "comorbidity_correct": None,
        }

    # ── Q4.3=B: 运行时合并 — 按 guess list 顺序依次 admin 单病 protocol ──
    drugs_given: list[str] = []
    for guess in guesses:
        if guess in _DRUG_PROTOCOL:
            drugs_given.extend(_administer_protocol(game_state.engine, guess))

    # ── Q4.2=B: win 判定 — 主诊断必须对 ──
    if primary_correct:
        if comorbidity_correct is True:
            # 全对：主诊断 + 合并症都猜对
            message = _win_message(primary)
            message += "\n\n🎉 额外奖励：合并症也正确识别！诊断全面准确。"
        elif comorbidity_correct is False:
            # 主诊断对，合并症错
            message = _win_message(primary)
            message += "\n\n💡 提示：合并症未正确识别，但主诊断正确，治疗有效。"
        else:
            # 单病 case，无合并症
            message = _win_message(primary)
        phase = "won"
        logger.info("治疗正确: 主诊断=%s, 合并症=%s, 给药=%s → phase=won",
                     primary, comorbidity_correct, drugs_given)
    else:
        # 主诊断错
        message = _loss_message(primary)
        phase = "playing"
        logger.info("治疗误诊: 猜测=%s, 主诊断=%s", guesses, primary)

    return {
        "success": True,
        "correct": primary_correct,
        "actual_disease": primary,
        "chosen_disease": disease_guess,
        "phase": phase,
        "message": message,
        "drugs_given": drugs_given,
        "comorbidity_correct": comorbidity_correct,
    }


def _apply_supportive_care(game_state: GameState) -> None:
    """
    支持治疗：静脉补液 200 mL。

    生理效应:
      - 增加循环血容量 → Frank-Starling 机制提升 SV → MAP 暂时改善
      - 肾脏灌注可能短暂改善 → 尿量可能略增
      - 不解决根本疾病，引擎继续推进疾病进程
    """
    _ensure_pharmacology(game_state.engine)
    game_state.engine.pharmacology.administer_drug("fluid_bolus", volume_ml=200.0)
    logger.info("支持治疗: 补液 200mL")


def _win_message(disease_name: str) -> str:
    return _WIN_MESSAGES.get(disease_name, f"治疗正确！{disease_name} 得到有效控制。")


def _loss_message(disease_name: str) -> str:
    return _LOSS_MESSAGES.get(disease_name, "误诊！患者的体征与你的诊断不符，请继续检查。")
