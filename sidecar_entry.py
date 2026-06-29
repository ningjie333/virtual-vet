"""virtual-vet sidecar 主入口：JSON-RPC over stdio 主循环。

用法（dev 模式）:
    cd virtual-vet
    set PYTHONPATH=.
    python sidecar_entry.py

Tauri 端通过 spawn 此脚本，stdin/stdout 用换行分隔的 JSON-RPC 2.0 通信，
stderr 直通便于调试。

协议方法:
    game.list_cases                → CaseSummary[]
    game.new_session               → {session_id, initial_snapshot}
    game.advance                   → snapshot
    game.administer_drug           → snapshot
    game.examine                   → snapshot
    game.diagnose                  → snapshot (含 win/lost 判定)
    game.list_drugs                → {drugs: [{drug_name, name, half_life_h, description}]}
    game.apply_gameplay            → snapshot (预留 modifier 通道)
    game.end_session               → ok
    shutdown                       → ok (清理所有会话并退出主循环)

设计原则:
  - 复用 gui_app.py 的核心函数（process_action、_get_vitals 等）保证行为一致
  - session_id 用 uuid 而非 case_id，允许同一病历多次开
  - 错误响应遵循 JSON-RPC 2.0 错误对象（code/message/data）
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

# 确保 virtual-vet 项目根在 sys.path 上（dev 模式下由 PYTHONPATH 注入；
# 这里做兜底，允许直接 `python sidecar_entry.py` 启动）
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# ── 日志配置必须在任何业务 import 之前 ──
# sidecar 协议流走 stdout，任何业务模块（如 src.vitals_config、src.exam_registry）
# 在 import 时打日志都会污染协议。强制 root logger 走 stderr。
_logging_level = os.environ.get("VET_VET_SIDECAR_LOG", "INFO").upper()
logging.basicConfig(
    level=_logging_level,
    stream=sys.stderr,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,  # 覆盖任何已存在的 handler 配置（Python 3.8+）
)

from game.action_system import process_action
from game.runtime import default_runtime
from sidecar import session_pool
from sidecar.case_loader import find_case, load_cases
from sidecar.protocol import (
    ERR_CASE_NOT_FOUND,
    ERR_GAME_ENDED,
    ERR_INTERNAL,
    ERR_INVALID_ACTION,
    ERR_INVALID_PARAMS,
    ERR_METHOD_NOT_FOUND,
    ERR_SESSION_NOT_FOUND,
    RpcError,
    make_error_response,
    make_response,
    parse_request,
)
from sidecar.snapshot_serializer import (
    serialize_case_summary_list,
    serialize_initial_snapshot,
    serialize_snapshot,
)

logger = logging.getLogger("virtual_vet.sidecar")

# 标记是否应退出主循环（shutdown 后置位）
_SHUTDOWN_REQUESTED = False


def handle_list_cases(_params: dict[str, Any]) -> Any:
    """game.list_cases — 返回所有可用病历摘要。"""
    cases = load_cases()
    return {"cases": serialize_case_summary_list(cases)}


def handle_new_session(params: dict[str, Any]) -> Any:
    """game.new_session — 根据病历创建新会话。"""
    case_id = params.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise RpcError(ERR_INVALID_PARAMS, "case_id required")

    # 验证病历存在（提前抛错，避免 new_session 失败后留下孤儿锁）
    try:
        find_case(case_id)
    except KeyError:
        raise RpcError(ERR_CASE_NOT_FOUND, f"case not found: {case_id}")

    session_id, context = session_pool.new_session(case_id)
    initial_snapshot = serialize_initial_snapshot(
        context.state, context.runtime, context.case
    )
    return {"session_id": session_id, "initial_snapshot": initial_snapshot}


def handle_advance(params: dict[str, Any]) -> Any:
    """game.advance — 推进时间（wait 动作）。

    与 gui_app.api_wait 一致：消耗 10 分钟，调用 process_action("wait")。
    """
    session_id = _require_session_id(params)
    return _run_action(session_id, "wait", {})


def handle_administer_drug(params: dict[str, Any]) -> Any:
    """game.administer_drug — 给药。

    必填: drug_name
    二选一: dose_mg_kg / volume_ml
    """
    session_id = _require_session_id(params)
    drug_name = params.get("drug_name")
    if not isinstance(drug_name, str) or not drug_name:
        raise RpcError(ERR_INVALID_PARAMS, "drug_name required")

    action_params: dict[str, Any] = {"drug_name": drug_name}
    volume_ml = params.get("volume_ml", 0.0)
    dose_mg_kg = params.get("dose_mg_kg", 0.0)
    if volume_ml and float(volume_ml) > 0:
        action_params["volume_ml"] = float(volume_ml)
    else:
        action_params["dose_mg_kg"] = float(dose_mg_kg) if dose_mg_kg else 0.0

    return _run_action(session_id, "administer_drug", action_params)


# 前端别名 → virtual-vet 金标准命名
# virtual-vet 的 data/exam_templates.json key 为命名金标准，前端可能用英文缩写别名
_EXAM_TYPE_ALIASES: dict[str, str] = {
    "cbc": "blood_routine",          # Complete Blood Count = 血常规
    "blood_chem": "blood_biochem",   # 血液生化
}


def handle_examine(params: dict[str, Any]) -> Any:
    """game.examine — 开具检查。

    必填: test_type（如 'physical' / 'blood_routine' / 'blood_biochem'）
    支持前端别名：cbc→blood_routine, blood_chem→blood_biochem。
    """
    session_id = _require_session_id(params)
    test_type = params.get("test_type")
    if not isinstance(test_type, str) or not test_type:
        raise RpcError(ERR_INVALID_PARAMS, "test_type required")
    # 别名归一化到 virtual-vet 金标准命名
    test_type = _EXAM_TYPE_ALIASES.get(test_type, test_type)
    return _run_action(session_id, "examine", {"test_type": test_type})


def handle_diagnose(params: dict[str, Any]) -> Any:
    """game.diagnose — 提交诊断 + 触发治疗（终结会话）。

    支持单病（str）或多病（list[str]），与 gui_app.api_diagnose 一致。
    """
    session_id = _require_session_id(params)
    diagnosis = params.get("diagnosis")
    if not diagnosis:
        raise RpcError(ERR_INVALID_PARAMS, "diagnosis required")

    return _run_action(
        session_id, "treat", {"disease_guess": diagnosis}
    )


def handle_apply_gameplay(params: dict[str, Any]) -> Any:
    """game.apply_gameplay — 预留通道，调用 modifier。

    当前实现仅支持 'night_modifier' 动作（R7 modifier 协议唯一已实现项）。
    该动作在 advance/administer 时已被自动调用，此接口主要用于调试。
    """
    session_id = _require_session_id(params)
    action = params.get("action", "night_modifier")

    context = session_pool.get_session(session_id)
    lock = session_pool.acquire_lock(session_id)
    with lock:
        if action == "night_modifier":
            context.runtime.modifier.apply_night_modifiers(context.state)
        else:
            raise RpcError(ERR_INVALID_ACTION, f"unknown gameplay action: {action}")

        return serialize_snapshot(context.state, context.runtime)


def handle_end_session(params: dict[str, Any]) -> Any:
    """game.end_session — 结束会话。"""
    session_id = _require_session_id(params)
    session_pool.end_session(session_id)
    return {"ok": True}


def handle_shutdown(_params: dict[str, Any]) -> Any:
    """shutdown — 清理所有会话并退出主循环。"""
    global _SHUTDOWN_REQUESTED
    cleared = session_pool.clear_all()
    _SHUTDOWN_REQUESTED = True
    logger.info("shutdown: cleared %d sessions", cleared)
    return {"ok": True, "cleared": cleared}


def handle_list_drugs(_params: dict[str, Any]) -> Any:
    """game.list_drugs — 返回所有已注册药物的元数据列表。

    供前端给药弹窗渲染下拉选项。复用 pharmacology.list_drugs()，
    保证与 Flask /api/drugs 行为一致。
    """
    from pharmacology import list_drugs

    drugs = list_drugs()
    return {"drugs": [{"drug_name": k, **v} for k, v in drugs.items()]}


# ── 方法分发表 ──
_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "game.list_cases": handle_list_cases,
    "game.new_session": handle_new_session,
    "game.advance": handle_advance,
    "game.administer_drug": handle_administer_drug,
    "game.examine": handle_examine,
    "game.diagnose": handle_diagnose,
    "game.list_drugs": handle_list_drugs,
    "game.apply_gameplay": handle_apply_gameplay,
    "game.end_session": handle_end_session,
    "shutdown": handle_shutdown,
}


def _require_session_id(params: dict[str, Any]) -> str:
    """提取并校验 session_id 参数。"""
    session_id = params.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise RpcError(ERR_INVALID_PARAMS, "session_id required")
    return session_id


def _run_action(session_id: str, action_type: str, action_params: dict[str, Any]) -> dict[str, Any]:
    """统一执行 process_action 并序列化结果。

    复用 game.action_system.process_action，保证与 Flask 应用行为一致。
    """
    context = session_pool.get_session(session_id)
    lock = session_pool.acquire_lock(session_id)
    with lock:
        result = process_action(
            context.state,
            action_type,
            action_params,
            runtime=context.runtime,
        )
        return serialize_snapshot(
            context.state,
            context.runtime,
            new_reports=result.get("new_reports", []),
            pending_count=result.get("pending_count", 0),
            last_result=result,
        )


def dispatch(method: str, params: dict[str, Any]) -> Any:
    """分发 RPC 方法。"""
    handler = _HANDLERS.get(method)
    if handler is None:
        raise RpcError(ERR_METHOD_NOT_FOUND, f"method not found: {method}")
    return handler(params)


def main_loop() -> int:
    """JSON-RPC over stdio 主循环。

    每行一个请求，每行一个响应。遇到 EOF 或 shutdown 后退出。
    返回进程退出码（0=正常，1=启动错误）。
    """
    # 标记 stdout 为 UTF-8，避免 Windows 默认 GBK 编码导致中文乱码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    # 启动就绪信号（vet-knowledge 端可据此判断 sidecar 已就绪）
    sys.stdout.write('{"jsonrpc":"2.0","method":"ready","params":{"version":1}}\n')
    sys.stdout.flush()

    while not _SHUTDOWN_REQUESTED:
        line = sys.stdin.readline()
        if not line:
            # stdin 关闭（父进程退出），强制清理并退出
            session_pool.clear_all()
            break

        line = line.strip()
        if not line:
            continue

        req_id: str | int | None = None
        try:
            req_id, method, params = parse_request(line)
        except RpcError as e:
            sys.stdout.write(
                make_error_response(None, e.code, e.message, e.data) + "\n"
            )
            sys.stdout.flush()
            continue

        try:
            result = dispatch(method, params)
            sys.stdout.write(make_response(req_id, result) + "\n")
        except RpcError as e:
            sys.stdout.write(
                make_error_response(req_id, e.code, e.message, e.data) + "\n"
            )
        except Exception as e:
            # 未预期异常 → ERR_INTERNAL，附带异常类名供调试
            logger.exception("unhandled error in method=%s", method)
            sys.stdout.write(
                make_error_response(
                    req_id,
                    ERR_INTERNAL,
                    "Internal error",
                    f"{type(e).__name__}: {e}",
                )
                + "\n"
            )
        finally:
            sys.stdout.flush()

    return 0


def main() -> int:
    """入口函数。日志已在模块顶部配置，直接进入主循环。"""
    try:
        return main_loop()
    except Exception as e:
        # 启动级致命错误（如模块导入失败）
        logger.exception("sidecar fatal: %s", e)
        sys.stderr.write(f"FATAL: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
