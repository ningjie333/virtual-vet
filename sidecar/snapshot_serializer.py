"""Snapshot 序列化器：将引擎状态转为 vet-knowledge 前端可消费的 JSON。

设计原则:
  - 前端只看 snapshot，不感知 engine 内部状态（与 R7 interpreter 只读契约对齐）
  - 体征字段与 gui_app._get_vitals 对齐，避免重复定义
  - active_signs 提供 display_name，供 vet-knowledge 本地 infer_diagnosis 使用

字段映射决策:
  - 显示 vitals（HR/MAP/SpO2/RR/Temp/GFR/pH/game_time/is_night）
  - 显示 active_signs（sign_id/display_name/severity/organ_system）
  - 显示 medical_phase（stable/worsening/critical/moribund）
  - 显示游戏元信息（time_elapsed_min/time_budget_min/death_timer/phase）
  - 不显示 disease_name（诊断考验：玩家自己判断）
  - 不显示 matched_symptoms / missing_key_symptoms（vet-knowledge 本地处理）
"""
from __future__ import annotations

from typing import Any

from game.action_system import GameState
from game.runtime import GameRuntime
from src.clinical_snapshot import ClinicalSnapshot


def serialize_snapshot(
    state: GameState,
    runtime: GameRuntime,
    *,
    new_reports: list[dict] | None = None,
    pending_count: int = 0,
    last_result: dict | None = None,
) -> dict[str, Any]:
    """序列化当前会话状态为前端可消费的 snapshot 字典。

    Args:
        state: GameState（含 phase / time_elapsed_min / death_timer / reports）
        runtime: R7 五协作者 GameRuntime
        new_reports: 本次行动产生的新报告（延迟到期的也算）
        pending_count: 待出报告数
        last_result: 最近一次 process_action 的返回值（用于携带 action_started_at_s 等元信息）
    """
    engine = state.engine
    snapshot = runtime.interpreter.snapshot(engine)
    summary = runtime.interpreter.summary(snapshot, state.time_elapsed_min)

    vitals = {
        "hr_bpm": round(snapshot.hr_bpm, 1),
        "map_mmhg": round(snapshot.map_mmhg, 1),
        "spo2_pct": round(snapshot.spo2_pct, 1),
        "rr_bpm": round(snapshot.rr_bpm, 1),
        "temp_c": round(snapshot.temperature_c, 1),
        "gfr_ml_min": round(snapshot.gfr_ml_min, 1),
        "ph": round(snapshot.ph, 3),
        "co_ml_min": round(snapshot.co_ml_min, 1),
        "blood_volume_ml": round(snapshot.blood_volume_ml, 0),
        "lactate_mmol_l": round(snapshot.lactate_mmol_l, 2),
        "bun_mg_dl": round(snapshot.bun_mg_dl, 1),
        "game_time": summary["game_time"],
        "is_night": summary["is_night"],
    }

    active_signs = [
        {
            "sign_id": s.sign_id,
            "display_name": s.display_name,
            "severity": s.severity,
            "organ_system": s.organ_system,
            "clue_id": s.clue_id,
            "localizing_value": s.localizing_value,
        }
        for s in runtime.interpreter.active_signs(engine)
        if s.active
    ]

    out: dict[str, Any] = {
        "phase": state.phase,
        "medical_phase": runtime.interpreter.phase(snapshot),
        "time_elapsed_min": state.time_elapsed_min,
        "time_budget_min": state.time_budget_min,
        "time_remaining_min": state.time_remaining_min,
        "death_timer": state.death_timer,
        "vitals": vitals,
        "active_signs": active_signs,
        "new_reports": new_reports or [],
        "pending_reports": pending_count,
    }

    if last_result is not None:
        # 透传 action 元信息（不暴露 disease_name）
        for key in ("action_started_at_s", "state_time_s", "time_cost_min", "success"):
            if key in last_result:
                out[key] = last_result[key]
        # 给药失败的 error 透传
        if not last_result.get("success", True) and "error" in last_result:
            out["error"] = last_result["error"]

    return out


def serialize_initial_snapshot(
    state: GameState,
    runtime: GameRuntime,
    case: dict[str, Any],
) -> dict[str, Any]:
    """新会话首次序列化：附带病历外壳信息（无诊断细节）。"""
    snap = serialize_snapshot(state, runtime)
    animal = case["animal"]
    snap["case"] = {
        "id": case["id"],
        "title": case.get("title", case["id"]),
        "difficulty": case.get("difficulty", 2),
        "difficulty_label": case.get("difficulty_label", ""),
        "animal": {
            "species": animal.get("species", "犬"),
            "breed": animal.get("breed", ""),
            "name": animal.get("name", ""),
            "age": animal.get("age", ""),
            "weight_kg": float(animal.get("weight_kg", 20.0)),
            "sex": animal.get("sex", ""),
        },
        "chief_complaint": case.get("chief_complaint", ""),
        "history": case.get("history", ""),
        "time_budget_min": state.time_budget_min,
        "starting_hints": case.get("starting_hints", []),
    }
    return snap


def serialize_case_summary_list(cases) -> list[dict[str, Any]]:
    """批量序列化病历摘要（list_cases 接口用）。"""
    return [c.to_dict() for c in cases]
