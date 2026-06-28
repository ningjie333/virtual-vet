#!/usr/bin/env python3
"""Workflow Closure Checker — 复查阶段强制校验。

防止"声明完成但实际遗漏"的两类高频问题：
  1. 错误消息分裂：gui_app.py 中 jsonify({"error": "..."}) 的静态字面量
     未走 *_MSG 常量（C7 反复发生）。
  2. 字段契约漂移：check_api_consistency.py --dry-run 的 Summary 行
     `+N 真实字段` > 0（C5 反复发生）。

设计原则：
  - 轻量：只做工具能可靠检测的项，死代码/锁安全靠人工清单（见 AGENTS.md）。
  - 可重复：每次复查跑同一命令，结果可对比。
  - 阻断：CRITICAL 退出码 1，阻断"声明完成"。

使用：
  python tools/dev/check_workflow_closure.py

退出码: 0=通过, 1=有 CRITICAL（阻断闭环）
"""

import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEV_DIR = PROJECT_ROOT / "tools" / "dev"


# ──────────────────────────────────────────────────────────────────────────
# Check 1: 错误消息统一（防 C7 复发）
# ──────────────────────────────────────────────────────────────────────────

def check_error_message_unification() -> tuple[int, list[str]]:
    """检查 gui_app.py 中 jsonify({"error": "..."}) 的静态字面量是否走常量。

    扫描规则：
      - 找所有 `*_MSG = "..."` 常量定义（如 _SESSION_NOT_FOUND_MSG）。
      - 找所有 `jsonify({"error": "..."})` 静态字面量（无 { 变量插值的）。
      - 若字面量值不在任何 *_MSG 常量中，报 CRITICAL。

    f-string（含 {var} 插值的）暂不检查（语义不同，难以常量化）。
    """
    gui_app = PROJECT_ROOT / "gui_app.py"
    if not gui_app.exists():
        return 0, ["[SKIP] gui_app.py 不存在"]
    content = gui_app.read_text(encoding="utf-8")

    # 1. 收集所有 *_MSG 常量定义
    constants: dict[str, str] = {}
    for m in re.finditer(r'^(_\w+_MSG)\s*=\s*"([^"]+)"', content, re.MULTILINE):
        constants[m.group(1)] = m.group(2)

    if not constants:
        return 1, ["[FAIL] 未找到任何 *_MSG 常量定义 — 无法校验错误消息统一"]

    # 2. 找所有 jsonify({"error": "..."}) 静态字面量
    issues: list[str] = []
    critical_count = 0
    for m in re.finditer(r'jsonify\(\{"error":\s*"([^"]+)"\}', content):
        msg = m.group(1)
        # 跳过 f-string 插值（这些是动态消息，语义不同）
        if "{" in msg:
            continue
        # 检查是否是某个常量的值
        if msg not in constants.values():
            line_num = content[:m.start()].count("\n") + 1
            issues.append(
                f"  [CRITICAL] gui_app.py:{line_num} 错误消息字面量未走常量: "
                f'"{msg}" — 应提取为 *_MSG 常量（参考已有: {", ".join(constants.keys())}）'
            )
            critical_count += 1

    # 3. 报告常量使用情况（信息性，不阻断）
    used_constants: set[str] = set()
    for const_name in constants:
        if re.search(rf'\b{re.escape(const_name)}\b', content[m.end():] if False else content):
            # 粗略统计：常量在文件中被引用（排除定义行）
            occurrences = len(re.findall(rf'\b{re.escape(const_name)}\b', content)) - 1
            if occurrences > 0:
                used_constants.add(const_name)

    status = "PASS" if critical_count == 0 else "FAIL"
    print(f"  [错误消息统一] {status} "
          f"(常量: {len(constants)} 定义 / {len(used_constants)} 使用 / {critical_count} 字面量未走常量)")

    return (1 if critical_count > 0 else 0), issues


# ──────────────────────────────────────────────────────────────────────────
# Check 2: 字段契约 dry-run（防 C5 复发）
# ──────────────────────────────────────────────────────────────────────────

def check_field_contract() -> tuple[int, list[str]]:
    """检查前后端字段契约：解析 check_api_consistency.py --dry-run 的 Summary 行。

    dry-run 对比 AST 提取的真实字段 vs BACKEND_RESPONSE_FIELDS 手抄字典：
      +N 真实字段 = 后端真实返回但手抄字典未记录的字段
      -N 幽灵字段 = 手抄字典有但后端不返回的字段

    判定规则（C6 决策：手抄字典保留为 dry-run 对照组，刻意不更新）：
      +N > 0 → WARN（手抄字典差异，需人工确认 types.ts 是否已声明同名字段）
      -N > 0 → WARN（幽灵字段，已知债务）
      无法解析 Summary → CRITICAL（检查器与 check_api_consistency.py 输出格式脱节）

    注：真正的 C5 防护（AST vs types.ts 直接对比）需要 TypeScript AST 解析，
    超出轻量工具范围。当前靠人工对照（AGENTS.md Stage 3 清单）。
    """
    script = DEV_DIR / "check_api_consistency.py"
    if not script.exists():
        return 0, ["[SKIP] check_api_consistency.py 不存在"]

    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )

    # 解析 Summary 行
    issues: list[str] = []
    critical_count = 0
    warn_count = 0

    summary_match = re.search(
        r'Summary:\s*\+(\d+)\s*真实字段.*?-(\d+)\s*幽灵字段',
        result.stdout,
    )
    if not summary_match:
        return 1, ["  [CRITICAL] 无法解析 dry-run Summary 行 — check_api_consistency.py 输出格式可能已变更，需更新 check_workflow_closure.py 的正则"]

    added = int(summary_match.group(1))
    removed = int(summary_match.group(2))

    # 解析每个 endpoint 的 DIFF，提取 + 行的真实字段名（供人工对照 types.ts）
    current_endpoint = None
    missing_fields: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        diff_match = re.match(r'\s*\[DIFF\]\s+(\S+)\s+\(pattern=', line)
        if diff_match:
            current_endpoint = diff_match.group(1)
            missing_fields[current_endpoint] = []
            continue
        if current_endpoint and "AST adds" in line:
            fields = re.findall(r"'([^']+)'", line)
            missing_fields[current_endpoint].extend(fields)

    if added > 0:
        issues.append(
            f"  [WARN] {added} 个真实字段未在 BACKEND_RESPONSE_FIELDS 记录 — "
            "请人工对照 types.ts 确认这些字段已在对应 interface 声明"
        )
        warn_count += added
        for endpoint, fields in missing_fields.items():
            if fields:
                issues.append(f"    {endpoint}: {fields}")

    if removed > 0:
        issues.append(
            f"  [WARN] {removed} 个幽灵字段在手抄字典但后端不返回（已知债务）"
        )
        warn_count += removed

    status = "PASS" if critical_count == 0 else "FAIL"
    print(f"  [字段契约] {status} "
          f"(+{added} 真实字段需人工对照 / -{removed} 幽灵字段已知)")

    return (1 if critical_count > 0 else 0), issues


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 60)
    print("Workflow Closure Checker — 复查阶段强制校验")
    print("=" * 60)
    print("检测两类高频「首尾不对应」问题：错误消息分裂 + 字段契约漂移")
    print("详见 AGENTS.md → Workflow Closure 章节")
    print("=" * 60)

    max_code = 0
    all_issues: list[str] = []

    print("\n[1/2] 错误消息统一检查（防 C7 复发）...")
    code, issues = check_error_message_unification()
    max_code = max(max_code, code)
    all_issues.extend(issues)

    print("\n[2/2] 字段契约 dry-run 检查（防 C5 复发）...")
    code, issues = check_field_contract()
    max_code = max(max_code, code)
    all_issues.extend(issues)

    print("\n" + "=" * 60)
    if max_code == 0:
        print("[PASS] 工作流闭环检查通过 ✓")
        print("  （注: 死代码/锁安全/命名一致性靠人工清单，见 AGENTS.md Stage 3）")
    else:
        print("[FAIL] 发现 CRITICAL 问题 — 未达闭环标准，禁止声明'完成'")
        print("\n问题清单：")
        for issue in all_issues:
            if issue.startswith("  [CRITICAL]") or issue.startswith("    "):
                print(issue)
    print("=" * 60)

    return max_code


if __name__ == "__main__":
    sys.exit(main())
