#!/usr/bin/env python3
"""
检查 1：API 端点一致性 + 类型同步

验证前端 api.ts 调用的每个端点，后端 gui_app.py 是否都注册了对应的路由。
--fix 模式：自动将后端返回字段同步到前端 types.ts 的 interface 中。

退出码: 0=无问题, 1=有 CRITICAL, 2=仅有 LOW
"""

import ast
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUI_APP = PROJECT_ROOT / "gui_app.py"
API_TS = PROJECT_ROOT / "vet-game-frontend" / "vite-project" / "src" / "api.ts"

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_LOW = "LOW"


def parse_flask_routes(filepath: Path) -> list[dict]:
    """用 ast 解析 gui_app.py，提取所有 @app.route 路由。"""
    src = filepath.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(filepath))
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not (isinstance(func, ast.Attribute) and func.attr == "route"):
                continue
            # 提取路径
            if not dec.args:
                continue
            path_node = dec.args[0]
            if isinstance(path_node, ast.Constant):
                path = path_node.value
            else:
                continue
            # 提取 methods
            methods = ["GET"]
            for kw in dec.keywords:
                if kw.arg == "methods" and isinstance(kw.value, ast.List):
                    methods = [
                        elt.value
                        for elt in kw.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]
            routes.append(
                {
                    "path": path,
                    "methods": [m.upper() for m in methods],
                    "func_name": node.name,
                    "line": node.lineno,
                }
            )
    return routes


def parse_api_ts_calls(filepath: Path) -> list[dict]:
    """用正则解析 api.ts，提取所有 request() 调用。

    api.ts 使用 BASE = "/api" 前缀拼接，所以前端写 "/cases" 实际调用 "/api/cases"。
    模板字符串路径（含 ${}）标记为 dynamic。
    字符串拼接路径（如 "/sessions/" + sessionId + "/replay"）也标记为 dynamic。
    """
    src = filepath.read_text(encoding="utf-8")
    calls = []

    # 先提取 BASE 常量
    base_match = re.search(r'const\s+BASE\s*=\s*["\x27]([^"\x27]+)["\x27]', src)
    base_prefix = base_match.group(1) if base_match else "/api"

    # 匹配 request("METHOD", "path") 和 request("METHOD", `path`)
    # 处理嵌套泛型如 request<Record<string, { name: string }>>("GET", ...)
    # 策略：找到 "request" 后，跳过所有 <...>（含嵌套），再匹配 ("METHOD",
    pattern = re.compile(
        r'request\s*(?:<(?:[^<>]|<[^>]*>)*>)?\s*\(\s*["\x27](\w+)["\x27]\s*,\s*(?:["\x27]([^"\x27]+)["\x27]|`([^`]+)`)',
    )
    for m in pattern.finditer(src):
        method = m.group(1).upper()
        path = m.group(2) or m.group(3) or ""
        is_template = m.group(3) is not None
        has_path_variable = False
        # 检查路径部分（不含 query string）是否含变量
        path_part = path.split("?")[0] if "?" in path else path
        if "${" in path_part:
            has_path_variable = True
        # 检测字符串拼接模式（如 "/sessions/" + sessionId + "/replay"）。
        # 正则 [^"\x27]+ 在第一个 " 后停止，无法捕获完整拼接路径。
        # 在完整行中找到 method 第二个引号后的内容，检查是否有 +
        line_start = src[: m.start()].rfind("\n") + 1
        line_end = src.find("\n", m.end())
        full_line = src[line_start:line_end] if line_end != -1 else src[line_start:]
        # 找 method 参数后的 path 字符串起始位置：第一个 , 后的第二个 " 开始
        comma_pos = full_line.find(",")
        if comma_pos != -1:
            second_quote_pos = full_line.find('"', comma_pos + 1)
            if second_quote_pos != -1:
                after_second_quote = full_line[second_quote_pos + 1:]
                if " + " in after_second_quote:
                    has_path_variable = True
        # 去掉 query string
        clean_path = path.split("?")[0]
        # 拼接 BASE 前缀得到完整路径
        if not clean_path.startswith("/"):
            clean_path = "/" + clean_path
        full_path = base_prefix + clean_path
        calls.append(
            {
                "method": method,
                "path": full_path,
                "raw_path": path,
                "line": src[: m.start()].count("\n") + 1,
                "dynamic": has_path_variable,
            }
        )
    return calls


def match_route(api_path: str, routes: list[dict]) -> dict | None:
    """将前端路径与后端路由匹配。

    支持精确匹配和 Flask 路径参数转换:
    /api/cases/{id} <-> /api/cases/:id
    """
    # 先把前端可能用的 :id 和模板字符串 ${...} 风格转成占位符。
    normalized = re.sub(r":(\w+)", r"{\1}", api_path)
    normalized = re.sub(r"\$\{[^}]+\}", r"{}", normalized)
    for r in routes:
        r_normalized = re.sub(r"<[^>]+>", r"{}", r["path"])
        if normalized == r_normalized:
            return r
        # 也直接比较
        if api_path == r["path"]:
            return r
    return None


def run() -> int:
    errors: list[tuple[str, str, int]] = []  # (severity, message, exit_code)

    if not GUI_APP.exists():
        print(f"[ERROR] 找不到 {GUI_APP}")
        return 1
    if not API_TS.exists():
        print(f"[ERROR] 找不到 {API_TS}")
        return 1

    routes = parse_flask_routes(GUI_APP)
    calls = parse_api_ts_calls(API_TS)

    if not routes:
        print("[WARN] 未从 gui_app.py 解析到任何路由，请检查 ast 解析逻辑")
    if not calls:
        print("[WARN] 未从 api.ts 解析到任何调用，请检查正则逻辑")

    # 只检查 /api/ 开头的路由
    api_routes = [r for r in routes if r["path"].startswith("/api/")]
    api_calls = [c for c in calls if c["path"].startswith("/api/") or c.get("dynamic")]

    # 前端调用了但后端没注册
    frontend_paths: dict[str, dict] = {}
    for c in api_calls:
        key = f"{c['method']} {c['path']}"
        frontend_paths[key] = c

    for key, c in frontend_paths.items():
        route = match_route(c["path"], api_routes)
        if route is None:
            if c.get("dynamic"):
                # 动态路径无法静态确认，降级为 LOW
                errors.append((SEVERITY_LOW, f"api.ts:{c['line']} → {key} 动态路径，需人工确认后端是否注册", 2))
            else:
                errors.append((SEVERITY_CRITICAL, f"api.ts:{c['line']} → {key} 后端未注册", 1))
        else:
            # 检查 HTTP 方法
            if c["method"] not in route["methods"]:
                errors.append(
                    (
                        SEVERITY_CRITICAL,
                        f"api.ts:{c['line']} → {key} 方法不一致，后端注册为 {route['methods']}",
                        1,
                    )
                )

    # 后端有但前端没调用（排除静态文件路由）
    backend_api_paths = {r["path"] for r in api_routes}
    frontend_api_paths = {c["path"] for c in api_calls}
    # 标准化后比较
    normalized_frontend = {
        re.sub(r"\$\{[^}]+\}", r"{}", re.sub(r":(\w+)", r"{\1}", p))
        for p in frontend_api_paths
    }
    for r in api_routes:
        r_norm = re.sub(r"<[^>]+>", r"{}", r["path"])
        if r_norm not in normalized_frontend and r["path"] not in frontend_api_paths:
            # 排除已知的静态路由
            if r["path"] in ("/assets/<path:filename>",):
                continue
            # 排除已知的前端动态调用路由（前端已实现但无法静态验证）
            if r["path"] == "/api/sessions/<session_id>/replay":
                continue
            errors.append(
                (
                    SEVERITY_LOW,
                    f"gui_app.py:{r['line']} → {r['methods'][0]} {r['path']} 前端从未调用",
                    2,
                )
            )

    # 输出
    if not errors:
        print("[OK] API 端点一致性检查通过")
        print(f"  后端路由: {len(api_routes)} 个，前端调用: {len(api_calls)} 个")
        return 0

    critical = [e for e in errors if e[0] == SEVERITY_CRITICAL]
    low = [e for e in errors if e[0] == SEVERITY_LOW]

    for sev, msg, _ in errors:
        print(f"[{sev}] {msg}")

    print(f"\n共 {len(errors)} 个问题：CRITICAL={len(critical)}, LOW={len(low)}")
    return 1 if critical else 2


# ─── 类型同步：后端返回字段 → 前端 types.ts ──────────────────

# 后端 API 返回字段映射（从 gui_app.py 的 response dict 提取）
# key: api.ts 中 request<T> 的泛型参数名（通过 api 函数名推断）
BACKEND_RESPONSE_FIELDS: dict[str, list[str]] = {
    "api_administer_drug": [
        "success", "phase", "medical_phase", "time_used", "death_timer",
        "new_reports", "pending_reports", "vitals", "game_log",
        "game_time", "is_night", "ap", "max_ap", "stress", "error",
    ],
    "api_examine": [
        "success", "phase", "medical_phase", "time_used", "death_timer",
        "report", "new_reports", "pending_reports", "vitals", "game_log",
        "game_time", "is_night", "ap", "max_ap", "ap_cost", "stress",
        "combo_bonus", "error",
    ],
    "api_diagnose": [
        "success", "phase", "medical_phase", "time_used", "death_timer",
        "treatment_result", "new_reports", "pending_reports", "vitals",
        "game_log", "game_time", "is_night", "ap", "max_ap", "stress",
    ],
    "api_wait": [
        "success", "phase", "medical_phase", "time_used", "death_timer",
        "new_reports", "pending_reports", "vitals", "game_log",
        "game_time", "is_night", "ap", "max_ap", "stress",
    ],
    "api_game_state": [
        "phase", "medical_phase", "time_used", "death_timer",
        "game_time", "is_night", "vitals", "reports_count",
        "pending_reports", "game_log", "ap", "max_ap", "stress",
    ],
    "api_new_game": [
        "session_id", "case", "game_state", "game_time", "is_night",
        "vitals", "ap", "max_ap", "stress", "pending_reports",
    ],
}

# api.ts 函数名 → types.ts interface 名 映射
API_FUNC_TO_INTERFACE: dict[str, str] = {
    "administerDrug": "AdministerDrugResponse",
    "examine":        "ExamineResponse",       # 内联类型，不单独修复
    "diagnose":       "DiagnoseResponse",      # 内联类型
    "wait":           "WaitResponse",          # 内联类型
    "getGameState":   "GameStateResponse",     # 内联类型
    "newGame":        "NewGameResponse",       # 内联类型
}

# 已知 TypeScript 类型映射（后端字段名 → TS 类型）
FIELD_TYPE_MAP: dict[str, str] = {
    "success": "boolean", "phase": "string", "medical_phase": "string",
    "time_used": "number", "death_timer": "number | null",
    "new_reports": "Report[]", "pending_reports": "number",
    "vitals": "Vitals", "game_log": "string[]",
    "game_time": "string", "is_night": "boolean",
    "ap": "number", "max_ap": "number", "stress": "number",
    "ap_cost": "number", "combo_bonus": "string | null",
    "error": "string", "report": "Report",
    "treatment_result": "TreatmentResult",
    "reports_count": "number", "session_id": "string",
    "case": "Case", "game_state": "GameState",
}


def parse_types_ts_interfaces(filepath: Path) -> dict[str, list[str]]:
    """用正则解析 types.ts，提取所有 interface 的字段名。"""
    src = filepath.read_text(encoding="utf-8")
    interfaces = {}
    current_iface = None
    depth = 0

    for line in src.split("\n"):
        # 检测 interface 开始
        m = re.match(r'\s*export\s+interface\s+(\w+)', line)
        if m:
            current_iface = m.group(1)
            interfaces[current_iface] = []
            depth = line.count("{") - line.count("}")
            if depth <= 0 and "}" in line:
                current_iface = None
            continue

        if current_iface is not None:
            depth += line.count("{") - line.count("}")
            # 提取字段名
            fm = re.match(r'\s+(\w+)\??:\s*', line)
            if fm:
                interfaces[current_iface].append(fm.group(1))
            if depth <= 0:
                current_iface = None

    return interfaces


def fix_types_ts(filepath: Path) -> int:
    """将后端返回字段同步到 types.ts 中缺失的可选字段。返回修复数量。"""
    src = filepath.read_text(encoding="utf-8")
    interfaces = parse_types_ts_interfaces(filepath)
    fixed = 0

    for api_func, interface_name in API_FUNC_TO_INTERFACE.items():
        if interface_name not in interfaces:
            continue
        backend_fields = BACKEND_RESPONSE_FIELDS.get(f"api_{api_func}", [])
        existing_fields = set(interfaces[interface_name])
        missing = [f for f in backend_fields if f not in existing_fields]

        if not missing:
            continue

        # 在 interface 末尾（最后一个 } 之前）插入缺失字段
        # 找 interface 的结束位置
        pattern = re.compile(
            rf'(export\s+interface\s+{re.escape(interface_name)}\s*\{{)'
            r'(.*?)'
            r'(\n\}})',
            re.DOTALL,
        )
        m = pattern.search(src)
        if not m:
            continue

        insert_pos = m.end(3) - len(m.group(3))  # 在最后一个 } 之前
        new_lines = []
        for field in missing:
            ts_type = FIELD_TYPE_MAP.get(field, "unknown")
            new_lines.append(f"  {field}?: {ts_type};")

        insertion = "\n" + "\n".join(new_lines)
        src = src[:insert_pos] + insertion + src[insert_pos:]
        fixed += len(missing)
        print(f"  [FIX] {interface_name}: 新增字段 {missing}")

    if fixed > 0:
        filepath.write_text(src, encoding="utf-8")
        print(f"  [FIX] 已写入 {filepath}")

    return fixed


# ─── 主入口 ─────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="API 端点一致性检查 + 类型同步")
    parser.add_argument("--fix", action="store_true", help="自动同步后端返回字段到 types.ts")
    args = parser.parse_args()

    if args.fix:
        print("=" * 50)
        print("API 类型同步 — 修复模式")
        print("=" * 50)
        n = fix_types_ts(API_TS)
        if n == 0:
            print("[OK] 所有 interface 字段已同步，无需修复")
        else:
            print(f"\n[FIXED] 共同步 {n} 个字段")
        return 0
    else:
        return run()


if __name__ == "__main__":
    sys.exit(main())
