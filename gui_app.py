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
from game.action_system import GameState, process_action
from game.diagnosis_engine import match_diseases, get_suggested_tests, CLUE_DESCRIPTIONS

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
# 游戏会话存储（单用户，内存存储）
# ============================================================
# 生产环境应使用 session +数据库，单用户原型用全局变量即可
_game_sessions: dict[str, GameState] = {}
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
    # 根据难度设置 AP 上限
    difficulty = case.get("difficulty", 1)
    max_ap = {1: 12, 2: 10, 3: 8}.get(difficulty, 10)
    state = GameState(
        engine=vc,
        disease_name=disease_name,
        species=species,
        current_ap=max_ap,
        max_ap=max_ap,
    )

    # 用 case_id 作为 session id（单用户原型）
    session_id = case_id
    _game_sessions[session_id] = state

    from game.time_manager import format_game_time, is_night_time

    return jsonify(
        {
            "session_id": session_id,
            "case": case,
            "game_state": {
                "phase": state.phase,
                "action_count": state.action_count,
                "elapsed_time_s": state.elapsed_time_s,
                "medical_phase": "stable",
                "death_timer": state.death_timer,
            },
            "game_time": format_game_time(state.game_clock_s),
            "is_night": is_night_time(state.game_clock_s),
            "vitals": _get_vitals(vc),
            "ap": state.current_ap,
            "max_ap": state.max_ap,
            "stress": round(state.stress_level, 1),
            "pending_reports": len(state.pending_reports),
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
        "action_count": state.action_count,
        "elapsed_time_s": state.elapsed_time_s,
        "death_timer": state.death_timer,
        "report": result.get("result"),
        "new_reports": result.get("new_reports", []),
        "pending_reports": result.get("pending_count", 0),
        "vitals": _get_vitals(state.engine, state.game_clock_s),
        "game_log": _build_game_log(state),
        "game_time": engine_summary.get("game_time", "08:00"),
        "is_night": engine_summary.get("is_night", False),
        "ap": result.get("ap_remaining", state.current_ap),
        "max_ap": state.max_ap,
        "ap_cost": result.get("ap_cost", 0),
        "stress": result.get("stress_level", round(state.stress_level, 1)),
        "combo_bonus": result.get("combo_bonus", None),
    }

    if not result["success"] and result.get("error"):
        response["error"] = result["error"]

    if state.phase == "lost":
        response["game_over"] = {
            "reason": "患犬未能挺过危机，抢救无效。",
            "actual_disease": state.disease_name,
        }

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
        "action_count": state.action_count,
        "elapsed_time_s": state.elapsed_time_s,
        "death_timer": state.death_timer,
        "new_reports": result.get("new_reports", []),
        "pending_reports": result.get("pending_count", 0),
        "vitals": _get_vitals(state.engine, state.game_clock_s),
        "game_log": _build_game_log(state),
        "game_time": engine_summary.get("game_time", "08:00"),
        "is_night": engine_summary.get("is_night", False),
        "ap": result.get("ap_remaining", state.current_ap),
        "max_ap": state.max_ap,
        "stress": result.get("stress_level", round(state.stress_level, 1)),
    }

    if not result["success"]:
        response["error"] = f"给药失败：药物 '{drug_name}' 未注册"

    return jsonify(response)


@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    """
    提交诊断 + 治疗
    POST body: {"session_id": "case_001", "diagnosis": "pneumonia", "treatment": "antibiotics"}
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
        "action_count": state.action_count,
        "elapsed_time_s": state.elapsed_time_s,
        "death_timer": state.death_timer,
        "treatment_result": result.get("result"),
        "new_reports": result.get("new_reports", []),
        "pending_reports": result.get("pending_count", 0),
        "vitals": _get_vitals(state.engine, state.game_clock_s),
        "game_log": _build_game_log(state),
        "game_time": engine_summary.get("game_time", "08:00"),
        "is_night": engine_summary.get("is_night", False),
        "ap": result.get("ap_remaining", state.current_ap),
        "max_ap": state.max_ap,
        "stress": result.get("stress_level", round(state.stress_level, 1)),
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
        "action_count": state.action_count,
        "elapsed_time_s": state.elapsed_time_s,
        "death_timer": state.death_timer,
        "new_reports": result.get("new_reports", []),
        "pending_reports": result.get("pending_count", 0),
        "vitals": _get_vitals(state.engine, state.game_clock_s),
        "game_log": _build_game_log(state),
        "game_time": engine_summary.get("game_time", "08:00"),
        "is_night": engine_summary.get("is_night", False),
        "ap": result.get("ap_remaining", state.current_ap),
        "max_ap": state.max_ap,
        "stress": result.get("stress_level", round(state.stress_level, 1)),
    }

    if state.phase == "lost":
        response["game_over"] = {
            "reason": "患犬未能挺过危机，抢救无效。",
            "actual_disease": state.disease_name,
        }

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
            "action_count": state.action_count,
            "elapsed_time_s": state.elapsed_time_s,
            "death_timer": state.death_timer,
            "game_time": format_game_time(state.game_clock_s),
            "is_night": is_night_time(state.game_clock_s),
            "vitals": _get_vitals(state.engine, state.game_clock_s),
            "reports_count": len(state.reports),
            "pending_reports": len(state.pending_reports),
            "game_log": _build_game_log(state),
            "ap": state.current_ap,
            "max_ap": state.max_ap,
            "stress": round(state.stress_level, 1),
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
        }
    """
    session_id = request.args.get("session_id", _DEFAULT_SESSION_ID)
    state = _game_sessions.get(session_id)
    if not state:
        return jsonify({"error": "游戏会话不存在"}), 404

    matches = match_diseases(state.reports)
    suggested = get_suggested_tests(matches)

    return jsonify(
        {
            "matches": matches,
            "suggested_tests": suggested,
        }
    )


# ============================================================
# 内部辅助
# ============================================================


def _get_vitals(vc: VirtualCreature, game_clock_s: float = 0.0) -> dict:
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
        "action_count": 0,  # 由调用方填充
        "game_time": format_game_time(game_clock_s),
        "is_night": is_night_time(game_clock_s),
    }


def _build_game_log(state: GameState) -> list[str]:
    """构建可读的诊疗日志"""
    log = []
    for i, report in enumerate(state.reports):
        name = report.get("name", "未知检查")
        summary = report.get("summary", "")
        log.append(f"[行动{i + 1}] {name}：{summary[:80]}")
    return log


# ── 评分参数 ──
_SCORE_BASE = 100
_SCORE_ACTION_PENALTY = 3
_SCORE_MAX_PENALTY = 80
_SCORE_MIN = 20
_GRADE_THRESHOLDS = [
    (90, "S"),
    (75, "A"),
    (60, "B"),
    (40, "C"),
]
_GRADE_DEFAULT = "D"


def _calc_score(state: GameState) -> dict:
    """计算最终评分"""
    action_penalty = min(_SCORE_MAX_PENALTY, state.action_count * _SCORE_ACTION_PENALTY)
    score = max(_SCORE_MIN, _SCORE_BASE - action_penalty)

    grade = _GRADE_DEFAULT
    for threshold, g in _GRADE_THRESHOLDS:
        if score >= threshold:
            grade = g
            break

    return {
        "total": score,
        "grade": grade,
        "actions_used": state.action_count,
    }


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
