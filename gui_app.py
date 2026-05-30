"""
虚拟生物 GUI - Flask Web 界面（游戏模式）
启动方式: python gui_app.py
访问地址: http://127.0.0.1:5000
"""

import sys, os
import json
import logging

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, jsonify, send_from_directory
from src.simulation import VirtualCreature
from src.parameters import (
    total_blood_volume_ml,
    base_cardiac_output_ml_min,
    stroke_volume_ml,
    gfr_ml_min,
    baseline_urine_output_ml_min,
    HEART_RATE_REST_BPM,
    MEAN_ARTERIAL_PRESSURE_MMHG,
    ARTERIAL_SATURATION_NORMAL,
    RESPIRATORY_RATE_REST,
)
from src.diseases import create_disease
from game.action_system import GameState, process_action, TIME_BUDGET_EASY, TIME_BUDGET_NORMAL, TIME_BUDGET_HARD
from game.diagnosis_engine import match_diseases, get_suggested_tests, CLUE_DESCRIPTIONS
from src.db.conn import connect
from src.db.schema import init_db
from src.db.sessions import create_session as db_create_session
from src.db.sessions import update_session_outcome as db_update_session_outcome
from src.db.sessions import update_engine_snapshot as db_update_engine_snapshot
from src.db.sessions import get_session as db_get_session
from src.db.action_log import append_action as db_append_action
from src.db.action_log import get_action_log as db_get_action_log

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates")
app.config["JSON_AS_ASCII"] = False

# Serve Vite-built assets from /static/assets/ at the /assets/ path
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory(os.path.join(STATIC_DIR, "assets"), filename)


@app.route("/favicon.svg")
def serve_favicon():
    return send_from_directory(STATIC_DIR, "favicon.svg")


# ============================================================
# 加载数据文件
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_json(filename: str) -> dict:
    with open(os.path.join(DATA_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)


EXAMINATIONS = _load_json("examinations.json")
TREATMENTS = _load_json("treatments.json")
CASES_DATA = _load_json("cases.json")
_DISEASE_NAMES: dict[str, str] = _load_json("diseases.json")["disease_names"]

# ============================================================
# SQLite persistence (multi-user session storage)
# ============================================================
_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "game_sessions.db")
_db_conn = connect(_DB_PATH)
init_db(_db_conn)


def _persist_action(state: GameState, session_id: str, action_type: str,
                      params: dict, result: dict) -> None:
    """
    Append an action row and update the engine snapshot in SQLite.
    Silently ignores errors so that SQLite failures never break gameplay.
    """
    import json
    try:
        seq = _action_seq.get(session_id, 1)
        _action_seq[session_id] = seq + 1

        params_json = json.dumps(params, ensure_ascii=False) if params else None
        snapshot = _snapshot_json(state.engine)
        medical_phase = result.get("medical_phase", "stable")
        outcome = state.phase if state.phase in ("won", "lost") else None

        db_append_action(
            conn=_db_conn,
            session_id=session_id,
            seq=seq,
            action_type=action_type,
            params=params_json,
            time_cost_min=result.get("time_cost_min"),
            engine_snapshot_json=snapshot,
            medical_phase=medical_phase,
            outcome=outcome,
        )
        db_update_engine_snapshot(_db_conn, session_id, snapshot)
    except Exception:
        pass  # Never let SQLite errors affect gameplay


def _snapshot_json(vc: VirtualCreature) -> str:
    """Serialize VirtualCreature to JSON for SQLite storage."""
    import json
    try:
        return json.dumps(vc.to_minimal_snapshot(), ensure_ascii=False)
    except Exception:
        return "{}"


# ============================================================
# 游戏会话存储（单用户，内存存储）
# ============================================================
_game_sessions: dict[str, GameState] = {}
_action_seq: dict[str, int] = {}  # session_id → next seq number
_DEFAULT_SESSION_ID = "case_001"

# ============================================================
# 辅助函数
# ============================================================


def get_normal_value(metric_key: str, weight_kg: float = 20.0) -> float:
    """返回指定指标的正常值（默认基于 20 kg 犬）。"""
    defaults = {
        "HR_bpm": HEART_RATE_REST_BPM,
        "MAP_mmHg": MEAN_ARTERIAL_PRESSURE_MMHG,
        "CO_ml_min": base_cardiac_output_ml_min(weight_kg),
        "blood_volume_ml": total_blood_volume_ml(weight_kg),
        "saturation": ARTERIAL_SATURATION_NORMAL,
        "RR": RESPIRATORY_RATE_REST,
        "GFR": gfr_ml_min(weight_kg),
        "urine_ml_min": baseline_urine_output_ml_min(weight_kg),
        "BUN": 15.0,
        "pH": 7.40,
    }
    return defaults.get(metric_key, 0.0)


def _get_time_budget(difficulty: int) -> int:
    """根据难度返回时间预算（分钟）。"""
    return {1: TIME_BUDGET_EASY, 2: TIME_BUDGET_NORMAL, 3: TIME_BUDGET_HARD}.get(difficulty, TIME_BUDGET_NORMAL)


# ============================================================
# 路由 — 页面
# ============================================================


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ============================================================
# 路由 — 游戏 API
# ============================================================


@app.route("/api/cases", methods=["GET"])
def api_cases():
    """返回所有可用病例"""
    return jsonify(CASES_DATA["cases"])


@app.route("/api/examinations", methods=["GET"])
def api_examinations():
    """返回所有检查项目定义"""
    return jsonify(EXAMINATIONS)


@app.route("/api/treatments", methods=["GET"])
def api_treatments():
    """返回所有治疗方案"""
    return jsonify(TREATMENTS)


@app.route("/api/drugs", methods=["GET"])
def api_drugs():
    """返回所有可用药物及其元信息"""
    from src.pharmacology import list_drugs

    return jsonify(list_drugs())


@app.route("/api/new-game", methods=["POST"])
def api_new_game():
    """
    开始新病例
    POST body: {"case_id": "case_001"}
    返回: 初始游戏状态
    """
    data = request.get_json() or {}
    case_id = data.get("case_id", _DEFAULT_SESSION_ID)

    # 查找病例
    case = None
    for c in CASES_DATA["cases"]:
        if c["id"] == case_id:
            case = c
            break
    if not case:
        return jsonify({"error": f"未知病例: {case_id}"}), 404

    animal = case["animal"]
    weight_kg = animal["weight_kg"]

    # 创建虚拟生物
    vc = VirtualCreature(body_weight_kg=weight_kg)

    # 注入疾病
    disease_name = case["disease"]
    disease = create_disease(disease_name)
    vc.attach_disease(disease)

    # 创建游戏状态
    species = animal.get("species", "犬")
    difficulty = case.get("difficulty", 2)
    time_budget = _get_time_budget(difficulty)
    state = GameState(
        engine=vc,
        disease_name=disease_name,
        species=species,
        time_budget_min=time_budget,
    )

    # 用 case_id 作为 session id（单用户原型）
    session_id = case_id
    _game_sessions[session_id] = state

    # Persist to SQLite
    db_create_session(
        conn=_db_conn,
        session_id=session_id,
        case_id=case_id,
        species=species,
        difficulty=difficulty,
        disease_name=disease_name,
    )

    from game.time_manager import format_game_time, is_night_time

    return jsonify(
        {
            "session_id": session_id,
            "case": case,
            "game_state": {
                "phase": state.phase,
                "time_elapsed_min": 0,
                "time_budget_min": state.time_budget_min,
                "medical_phase": "stable",
                "death_timer": state.death_timer,
            },
            "game_time": format_game_time(0),
            "is_night": is_night_time(0),
            "vitals": _get_vitals(vc, 0),
            "time_budget_min": state.time_budget_min,
            "pending_reports": 0,
        }
    )


@app.route("/api/examine", methods=["POST"])
def api_examine():
    """
    开具检查
    POST body: {"session_id": "case_001", "test_type": "physical"}
    返回: 检查报告 + 更新后的游戏状态
    """
    data = request.get_json() or {}
    session_id = data.get("session_id", _DEFAULT_SESSION_ID)
    test_type = data.get("test_type", "physical")

    state = _game_sessions.get(session_id)
    if not state:
        return jsonify({"error": "游戏会话不存在，请先开始新游戏"}), 404

    if state.phase in ("won", "lost"):
        return jsonify({"error": f"游戏已结束: {state.phase}"}), 400

    # 使用 action_system 的 process_action
    result = process_action(state, "examine", {"test_type": test_type})

    engine_summary = result.get("engine_summary", {})
    response = {
        "success": result["success"],
        "phase": result["phase"],
        "medical_phase": result.get("medical_phase", "stable"),
        "time_elapsed_min": result.get("time_elapsed_min", state.time_elapsed_min),
        "time_budget_min": state.time_budget_min,
        "time_remaining_min": result.get("time_remaining_min", state.time_remaining_min),
        "death_timer": state.death_timer,
        "report": result.get("result"),
        "new_reports": result.get("new_reports", []),
        "pending_reports": result.get("pending_count", 0),
        "vitals": _get_vitals(state.engine, state.time_elapsed_min),
        "game_log": _build_game_log(state),
        "game_time": engine_summary.get("game_time", "08:00"),
        "is_night": engine_summary.get("is_night", False),
        "time_cost_min": result.get("time_cost_min", 0),
    }

    if not result["success"] and result.get("error"):
        response["error"] = result["error"]

    if state.phase == "lost":
        response["game_over"] = {
            "reason": "患犬未能挺过危机，抢救无效。",
            "actual_disease": state.disease_name,
        }

    # Persist to SQLite (best-effort)
    _persist_action(state, session_id, "examine", {"test_type": test_type}, result)

    return jsonify(response)


@app.route("/api/administer-drug", methods=["POST"])
def api_administer_drug():
    """
    给药治疗
    POST body: {"session_id": "case_001", "drug_name": "pimobendan", "dose_mg_kg": 0.25}
    或: {"session_id": "case_001", "drug_name": "fluid_bolus", "volume_ml": 200}
    返回: 更新后的游戏状态 + 生命体征
    """
    data = request.get_json() or {}
    session_id = data.get("session_id", _DEFAULT_SESSION_ID)
    drug_name = data.get("drug_name", "")
    dose_mg_kg = data.get("dose_mg_kg", 0.0)
    volume_ml = data.get("volume_ml", 0.0)

    state = _game_sessions.get(session_id)
    if not state:
        return jsonify({"error": "游戏会话不存在，请先开始新游戏"}), 404

    if state.phase in ("won", "lost"):
        return jsonify({"error": f"游戏已结束: {state.phase}"}), 400

    # 构建 process_action 参数
    params = {"drug_name": drug_name}
    if volume_ml > 0:
        params["volume_ml"] = volume_ml
    else:
        params["dose_mg_kg"] = dose_mg_kg

    result = process_action(state, "administer_drug", params)
    engine_summary = result.get("engine_summary", {})

    response = {
        "success": result["success"],
        "phase": result["phase"],
        "medical_phase": result.get("medical_phase", "stable"),
        "time_elapsed_min": result.get("time_elapsed_min", state.time_elapsed_min),
        "time_budget_min": state.time_budget_min,
        "time_remaining_min": result.get("time_remaining_min", state.time_remaining_min),
        "death_timer": state.death_timer,
        "new_reports": result.get("new_reports", []),
        "pending_reports": result.get("pending_count", 0),
        "vitals": _get_vitals(state.engine, state.time_elapsed_min),
        "game_log": _build_game_log(state),
        "game_time": engine_summary.get("game_time", "08:00"),
        "is_night": engine_summary.get("is_night", False),
        "time_cost_min": result.get("time_cost_min", 0),
    }

    if not result["success"]:
        response["error"] = f"给药失败：药物 '{drug_name}' 未注册"

    # Persist to SQLite (best-effort)
    _persist_action(state, session_id, "administer_drug", params, result)

    return jsonify(response)


@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    """
    提交诊断 + 治疗
    POST body: {"session_id": "case_001", "diagnosis": "pneumonia"}
    返回: 治疗结果 + 游戏状态
    """
    data = request.get_json() or {}
    session_id = data.get("session_id", _DEFAULT_SESSION_ID)
    diagnosis = data.get("diagnosis", "")

    state = _game_sessions.get(session_id)
    if not state:
        return jsonify({"error": "游戏会话不存在，请先开始新游戏"}), 404

    if state.phase in ("won", "lost"):
        return jsonify({"error": f"游戏已结束: {state.phase}"}), 400

    # 使用 action_system 的 process_action
    result = process_action(state, "treat", {"disease_guess": diagnosis})
    engine_summary = result.get("engine_summary", {})

    response = {
        "success": result["success"],
        "phase": result["phase"],
        "medical_phase": result.get("medical_phase", "stable"),
        "time_elapsed_min": result.get("time_elapsed_min", state.time_elapsed_min),
        "time_budget_min": state.time_budget_min,
        "time_remaining_min": result.get("time_remaining_min", state.time_remaining_min),
        "death_timer": state.death_timer,
        "treatment_result": result.get("result"),
        "new_reports": result.get("new_reports", []),
        "pending_reports": result.get("pending_count", 0),
        "vitals": _get_vitals(state.engine, state.time_elapsed_min),
        "game_log": _build_game_log(state),
        "game_time": engine_summary.get("game_time", "08:00"),
        "is_night": engine_summary.get("is_night", False),
        "time_cost_min": result.get("time_cost_min", 0),
    }

    if state.phase == "won":
        response["game_over"] = {
            "reason": "诊断正确，治疗有效！患犬正在康复。",
            "actual_disease": state.disease_name,
            "score": _calc_score(state),
        }
    elif state.phase == "lost":
        response["game_over"] = {
            "reason": "患犬未能挺过危机，抢救无效。",
            "actual_disease": state.disease_name,
        }

    # Persist to SQLite; also record final outcome
    _persist_action(state, session_id, "treat", {"disease_guess": diagnosis}, result)
    if state.phase in ("won", "lost"):
        db_update_session_outcome(
            _db_conn, session_id, state.phase, state.time_elapsed_min,
        )

    return jsonify(response)


@app.route("/api/wait", methods=["POST"])
def api_wait():
    """
    等待（不操作，推进时间）
    POST body: {"session_id": "case_001"}
    """
    data = request.get_json() or {}
    session_id = data.get("session_id", _DEFAULT_SESSION_ID)

    state = _game_sessions.get(session_id)
    if not state:
        return jsonify({"error": "游戏会话不存在"}), 404

    result = process_action(state, "wait", {})
    engine_summary = result.get("engine_summary", {})

    response = {
        "success": result["success"],
        "phase": result["phase"],
        "medical_phase": result.get("medical_phase", "stable"),
        "time_elapsed_min": result.get("time_elapsed_min", state.time_elapsed_min),
        "time_budget_min": state.time_budget_min,
        "time_remaining_min": result.get("time_remaining_min", state.time_remaining_min),
        "death_timer": state.death_timer,
        "new_reports": result.get("new_reports", []),
        "pending_reports": result.get("pending_count", 0),
        "vitals": _get_vitals(state.engine, state.time_elapsed_min),
        "game_log": _build_game_log(state),
        "game_time": engine_summary.get("game_time", "08:00"),
        "is_night": engine_summary.get("is_night", False),
        "time_cost_min": result.get("time_cost_min", 0),
    }

    if state.phase == "lost":
        response["game_over"] = {
            "reason": "患犬未能挺过危机，抢救无效。",
            "actual_disease": state.disease_name,
        }

    # Persist to SQLite (best-effort)
    _persist_action(state, session_id, "wait", {}, result)

    return jsonify(response)


@app.route("/api/game-state", methods=["GET"])
def api_game_state():
    """获取当前游戏状态（用于刷新/轮询）"""
    session_id = request.args.get("session_id", _DEFAULT_SESSION_ID)
    state = _game_sessions.get(session_id)
    if not state:
        return jsonify({"error": "游戏会话不存在"}), 404

    from game.action_system import determine_phase

    medical_phase = determine_phase(state.engine)

    from game.time_manager import format_game_time, is_night_time

    return jsonify(
        {
            "phase": state.phase,
            "medical_phase": medical_phase,
            "time_elapsed_min": state.time_elapsed_min,
            "time_budget_min": state.time_budget_min,
            "time_remaining_min": state.time_remaining_min,
            "death_timer": state.death_timer,
            "game_time": format_game_time(state.time_elapsed_min),
            "is_night": is_night_time(state.time_elapsed_min),
            "vitals": _get_vitals(state.engine, state.time_elapsed_min),
            "reports_count": len(state.reports),
            "pending_reports": len(state.pending_reports),
            "game_log": _build_game_log(state),
        }
    )


@app.route("/api/hint", methods=["GET"])
def api_hint():
    """根据已获取的报告给出诊断提示"""
    session_id = request.args.get("session_id", _DEFAULT_SESSION_ID)
    state = _game_sessions.get(session_id)
    if not state:
        return jsonify({"error": "游戏会话不存在"}), 404

    if not state.reports:
        return jsonify({"hint": "请先开具检查，获取检查报告后再来查看提示。"})

    matches = match_diseases(state.reports)
    if not matches:
        return jsonify({"hint": "目前检查数据不足以匹配任何已知疾病，建议进一步检查。"})

    top = matches[0]
    disease_display = _DISEASE_NAMES.get(top["disease"], top["disease"])

    matched_desc = [CLUE_DESCRIPTIONS.get(c, c) for c in top["matched_clues"][:5]]
    missed_desc = [CLUE_DESCRIPTIONS.get(c, c) for c in top["missed_clues"][:3]]

    hint = f"最可能的疾病：**{disease_display}**（置信度 {top['confidence'] * 100:.0f}%）\n\n"
    hint += f"已匹配线索：{'、'.join(matched_desc)}\n"
    if missed_desc:
        hint += f"未确认线索：{'、'.join(missed_desc)}"

    return jsonify({"hint": hint})


@app.route("/api/diagnosis", methods=["GET"])
def api_diagnosis():
    """
    返回结构化诊断匹配数据（置信度面板用）。
    返回:
        {
            "matches": [...],          # match_diseases() 结果，按 confidence 降序
            "suggested_tests": [...],  # get_suggested_tests() 结果
            "references": {...},       # 疾病文献引用 (仅 top 3)
        }
    """
    from game.diagnosis_engine import get_disease_references_with_clues

    session_id = request.args.get("session_id", _DEFAULT_SESSION_ID)
    state = _game_sessions.get(session_id)
    if not state:
        return jsonify({"error": "游戏会话不存在"}), 404

    matches = match_diseases(state.reports)
    suggested = get_suggested_tests(matches)

    # 为 top 3 候选疾病添加文献引用
    references = {}
    for m in matches[:3]:
        disease = m["disease"]
        refs = get_disease_references_with_clues(disease, m["matched_clues"])
        if refs["guidelines"] or refs["matched_criteria"]:
            references[disease] = refs

    return jsonify(
        {
            "matches": matches,
            "suggested_tests": suggested,
            "references": references,
        }
    )


@app.route("/api/disease-references/<disease_name>", methods=["GET"])
def api_disease_references(disease_name):
    """
    返回指定疾病的完整文献引用数据。

    Args:
        disease_name: 疾病名称 (如 "pneumonia")

    Returns:
        {
            "guidelines": [...],
            "criteria": {...},
            ...
        }
    """
    from game.diagnosis_engine import get_disease_references

    ref = get_disease_references(disease_name)
    if ref is None:
        return jsonify({"error": "未找到该疾病的引用数据"}), 404
    return jsonify(ref)


# ============================================================
# 内部辅助
# ============================================================


@app.route("/api/sessions/<session_id>/replay", methods=["GET"])
def api_session_replay(session_id):
    """
    Return a completed session's data for instructor review.

    Returns the session metadata, final engine snapshot, and the
    full action sequence in chronological order.
    """
    session = db_get_session(_db_conn, session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    actions = db_get_action_log(_db_conn, session_id)
    return jsonify({"session": session, "actions": actions})


# ============================================================


def _get_vitals(vc: VirtualCreature, elapsed_min: float = 0.0) -> dict:
    """从引擎提取当前生命体征"""
    h = vc.history

    def _last(key, fallback):
        vals = h.get(key, [])
        return vals[-1] if vals else fallback

    from game.time_manager import format_game_time, is_night_time

    return {
        "HR_bpm": round(_last("HR_bpm", vc.heart.heart_rate), 1),
        "MAP_mmHg": round(_last("MAP_mmHg", vc.heart.mean_arterial_pressure), 1),
        "SpO2": round(_last("saturation", vc.blood.arterial_saturation) * 100, 1),
        "RR": round(_last("RR", vc.lung.respiratory_rate), 1),
        "Temp": round(_last("Temp", vc.blood.core_temperature_C), 1),
        "GFR": round(_last("GFR", vc.kidney.GFR), 1),
        "pH": round(_last("pH", vc.blood.arterial_pH), 3),
        "game_time": format_game_time(int(elapsed_min)),
        "is_night": is_night_time(int(elapsed_min)),
    }


def _build_game_log(state: GameState) -> list[str]:
    """构建可读的诊疗日志"""
    from game.time_manager import format_game_time
    log = []
    cumulative_min = 0
    for report in state.reports:
        name = report.get("name", "未知检查")
        summary = report.get("summary", "")
        cumulative_min += 5  # 近似累计
        log.append(f"[{format_game_time(cumulative_min)}] {name}：{summary[:80]}")
    return log


# ── 评分参数 ──
_SCORE_BASE = 100
_SCORE_TIME_PENALTY_PER_MIN = 0.5
_SCORE_MAX_PENALTY = 60
_SCORE_MIN = 20
_GRADE_THRESHOLDS = [
    (90, "S"),
    (75, "A"),
    (60, "B"),
    (40, "C"),
]
_GRADE_DEFAULT = "D"


def _calc_score(state: GameState) -> dict:
    """计算最终评分（时间越少越好）"""
    time_penalty = min(_SCORE_MAX_PENALTY, state.time_elapsed_min * _SCORE_TIME_PENALTY_PER_MIN)
    score = max(_SCORE_MIN, _SCORE_BASE - time_penalty)

    grade = _GRADE_DEFAULT
    for threshold, g in _GRADE_THRESHOLDS:
        if score >= threshold:
            grade = g
            break

    return {
        "total": score,
        "grade": grade,
        "time_used": state.time_elapsed_min,
    }


# ============================================================
# 调试路由（独立于游戏逻辑）
# ============================================================


@app.route("/api/debug/species", methods=["GET"])
def api_debug_species():
    """返回可用的物种、品种和体重范围。"""
    from src.debug_params import get_available_species
    return jsonify(get_available_species())


@app.route("/api/debug/params", methods=["POST"])
def api_debug_params():
    """
    计算指定物种/品种/年龄的生理参数。

    POST body: {"species": "canine", "breed": "labrador", "age_days": 1095, "weight_kg": 30.0}
    """
    data = request.get_json(force=True) or {}
    species = data.get("species", "canine")
    breed = data.get("breed", "mixed")
    age_days = float(data.get("age_days", 1095.0))
    weight_kg = data.get("weight_kg")
    if weight_kg is not None:
        weight_kg = float(weight_kg)

    from src.debug_params import compute_debug_params
    result = compute_debug_params(
        species=species,
        breed=breed,
        age_days=age_days,
        weight_kg=weight_kg,
    )
    return jsonify(result)


# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  虚拟生物 · 兽医诊断游戏 - 启动中...")
    print("  访问: http://127.0.0.1:5000")
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    app.run(debug=True, port=5000)
