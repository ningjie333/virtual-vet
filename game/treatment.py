"""
Treatment — 治疗判定与药物协议执行。

职责:
  - 验证玩家的诊断选择是否匹配实际疾病
  - 诊断正确 → 执行对应药物协议（而非直接宣布胜利）
  - 诊断错误 → 返回误诊提示
  - 支持治疗 → 补液，不结束游戏
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.action_system import GameState

logger = logging.getLogger(__name__)

# ── 疾病 → 药物协议映射 ──────────────────────────────────────────────────────
# 每种疾病对应一个药物列表，按顺序给药
_DRGUG_PROTOCOL: dict[str, list[dict]] = {
    "dilated_cardiomyopathy": [
        {"drug_name": "pimobendan", "dose_mg_kg": 0.25},
        {"drug_name": "furosemide", "dose_mg_kg": 1.0},
    ],
    "pneumonia": [
        {"drug_name": "fluid_bolus", "volume_ml": 200.0},
    ],
    "acute_renal_failure": [
        {"drug_name": "fluid_bolus", "volume_ml": 300.0},
    ],
}


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
    protocol = _DRGUG_PROTOCOL.get(disease_name, [])
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
    判断治疗选择是否匹配实际疾病。

    Args:
        game_state: 当前游戏状态
        disease_guess: 玩家选择的疾病名称

    Returns:
        True 如果猜对了
    """
    return disease_guess == game_state.disease_name


def apply_treatment(game_state: GameState, disease_guess: str) -> dict:
    """
    应用治疗，判定胜负。

    诊断正确 → 执行对应药物协议（给药物，推进引擎让玩家看到生理改善）
    诊断错误 → 返回误诊提示
    支持治疗 → 补液 200 mL

    Args:
        game_state: 当前游戏状态
        disease_guess: 玩家选择的疾病名称

    Returns:
        {
            "success": True,
            "correct": bool,
            "actual_disease": str,
            "chosen_disease": str,
            "phase": str,       # "won" 或 "playing"
            "message": str,     # 中文结果描述
            "drugs_given": list, # 已给药物列表（新增）
        }
    """
    correct = is_correct_treatment(game_state, disease_guess)
    actual = game_state.disease_name

    if correct:
        drugs_given = _administer_protocol(game_state.engine, actual)
        message = _win_message(actual)
        phase = "won"
        logger.info("治疗正确: %s → 给药 %s → phase=won", actual, drugs_given)
    elif disease_guess == "supportive_care":
        # 支持治疗：静脉补液 200 mL
        _apply_supportive_care(game_state)
        drugs_given = ["fluid_bolus"]
        message = "支持治疗已执行：静脉补液 200 mL。患犬暂时感觉好了一些，但根本问题仍未解决。建议继续检查明确诊断。"
        phase = "playing"
        logger.info("支持治疗: 补液 200mL")
    else:
        drugs_given = []
        message = _loss_message(actual)
        phase = "playing"
        logger.info("治疗误诊: 猜测=%s, 实际=%s", disease_guess, actual)

    return {
        "success": True,
        "correct": correct,
        "actual_disease": actual,
        "chosen_disease": disease_guess,
        "phase": phase,
        "message": message,
        "drugs_given": drugs_given,
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
    """治愈消息"""
    messages = {
        "pneumonia": "正确诊断！补液治疗后，患犬的循环状态和氧合逐渐改善。",
        "acute_renal_failure": "正确诊断！积极补液恢复肾灌注后，患犬的肾功能指标开始好转。",
        "dilated_cardiomyopathy": "正确诊断！强心（匹莫苯丹）+ 利尿（呋塞米）治疗后，患犬心功能逐渐改善，呼吸困难缓解。",
    }
    return messages.get(disease_name, f"治疗正确！{disease_name} 得到有效控制。")


def _loss_message(disease_name: str) -> str:
    """误诊消息 — 不直接暴露疾病名，给出模糊提示"""
    hints = {
        "pneumonia": "误诊！患犬的呼吸系统症状提示存在感染性病变，请重新评估肺部检查。",
        "acute_renal_failure": "误诊！患犬的氮质血症和电解质紊乱提示泌尿系统出了问题，请复查肾功能和尿液。",
        "dilated_cardiomyopathy": "误诊！患犬的心脏扩大伴收缩功能下降，提示心肌病变，请复查心脏超声和心电图。",
    }
    return hints.get(disease_name, "误诊！患者的体征与你的诊断不符，请继续检查。")
