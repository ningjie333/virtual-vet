#!/usr/bin/env python3
"""
Virtual Vet Gate Check — 提交前一致性检查

串联所有检查脚本，支持两档模式：
  --quick    API + 数据检查，<5s
  --full    全套检查（含类型检查），<10s
  --install-hook  安装 Git pre-commit hook

退出码: 0=通过, 1=有 CRITICAL/HIGH, 2=仅有 MEDIUM/LOW
环境变量: GATE_SKIP=1 跳过所有检查
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEV_DIR = PROJECT_ROOT / "tools" / "dev"


def run_checker(name: str, script: str, args: list[str] | None = None) -> int:
    """运行一个检查脚本，返回退出码。"""
    script_path = DEV_DIR / script
    if not script_path.exists():
        print(f"[SKIP] {name}: 找不到 {script_path}")
        return 0
    cmd = [sys.executable, str(script_path)] + (args or [])
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=False)
    elapsed = time.time() - t0
    status = "通过" if result.returncode == 0 else f"失败({result.returncode})"
    print(f"  [{name}] {status} ({elapsed:.1f}s)")
    return result.returncode


def install_hook():
    """安装 Git pre-commit hook。"""
    hook_path = PROJECT_ROOT / ".git" / "hooks" / "pre-commit"
    hook_content = """#!/bin/sh
# Virtual Vet Gate Check — pre-commit hook
# 由 tools/dev/gate_check.py --install-hook 自动生成

if [ "$GATE_SKIP" = "1" ]; then
    echo "[GATE SKIPPED]"
    exit 0
fi

cd "$(git rev-parse --show-toplevel)"
python tools/dev/gate_check.py --quick
exit $?
"""
    hook_path.write_text(hook_content, encoding="utf-8")
    # 在 Unix 系统上需要 chmod +x，Windows 上不需要
    if sys.platform != "win32":
        os.chmod(str(hook_path), 0o755)
    print(f"[OK] pre-commit hook 已安装到 {hook_path}")
    print("  提示: GATE_SKIP=1 git commit -m '...' 可跳过检查")
    print("        git commit --no-verify -m '...' 强制跳过")


def run_fix() -> int:
    """自动修复模式：数据 + 类型。"""
    print("=" * 50)
    print("Virtual Vet Gate Check — 自动修复模式")
    print("=" * 50)

    # 1. 修复 JSON 数据
    print("\n[1/2] 数据一致性修复...")
    code = run_checker("数据修复", "check_data_consistency.py", ["--fix"])

    # 2. 同步类型到 types.ts
    print("\n[2/2] 类型同步...")
    code2 = run_checker("类型同步", "check_api_consistency.py", ["--fix"])

    print("\n" + "=" * 50)
    print("[DONE] 修复完成。请检查修改后重新提交。")
    print("=" * 50)
    return 0


def run_schema() -> int:
    """JSON Schema 验证：所有四个配置文件。"""
    print("=" * 50)
    print("Virtual Vet Gate Check — Schema 验证")
    print("=" * 50)

    # Import from project root (add both project root and src/ like conftest.py does)
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from src.config_validation import validate_all

    results = validate_all()
    max_code = 0

    for filename, errors in results.items():
        if not errors:
            print(f"  [{filename}] 通过")
        else:
            max_code = 1
            print(f"  [{filename}] 失败 ({len(errors)} 个错误):")
            for err in errors:
                print(f"    {err.path}: {err.message}")

    print("=" * 50)
    if max_code == 0:
        print("[PASS] 所有 Schema 验证通过")
    else:
        print("[FAIL] Schema 验证失败")
    print("=" * 50)
    return max_code


def run_verify_refs() -> int:
    """验证所有 _PARAM_PATHS 和 coupling_rules 有文献溯源。"""
    import json
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

    print("=" * 50)
    print("Virtual Vet Gate Check — 文献溯源验证")
    print("=" * 50)

    from src.simulation import _PARAM_PATHS
    from src.parameter_refs import all_param_refs
    from src.organs.coupling import CouplingEngine

    refs = all_param_refs()
    params_missing = []
    for path in _PARAM_PATHS:
        if path not in refs:
            params_missing.append(path)

    # Coupling rules
    engine = CouplingEngine()
    couplings_missing = []
    for rule in engine.rules:
        if rule.enabled and not rule.references:
            couplings_missing.append(rule.name)

    unverified = len(params_missing) + len(couplings_missing)

    if params_missing:
        print(f"\n  [params] {len(params_missing)} 个 _PARAM_PATHS 缺少文献溯源:")
        for p in params_missing[:10]:
            print(f"    - {p}")
        if len(params_missing) > 10:
            print(f"    ... 及其余 {len(params_missing) - 10} 个")

    if couplings_missing:
        print(f"\n  [coupling] {len(couplings_missing)} 条 enabled 规则缺少文献溯源:")
        for n in couplings_missing:
            print(f"    - {n}")

    total = len(_PARAM_PATHS) + len([r for r in engine.rules if r.enabled])
    pct = round((total - unverified) / total * 100) if total else 100

    print(f"\n  覆盖率: {total - unverified}/{total} ({pct}%)")

    print("=" * 50)
    if unverified == 0:
        print(f"[PASS] 所有参数和耦合规则均有文献溯源 ✓")
    else:
        print(f"[WARN] {unverified} 个项目缺少文献溯源")
    print("=" * 50)

    return 2 if unverified > 0 else 0


def run_quick() -> int:
    """全套检查：API + 数据 + 类型。"""
    print("=" * 50)
    print("Virtual Vet Gate Check — 快速检查")
    print("=" * 50)

    max_code = 0

    code = run_checker("API 一致性", "check_api_consistency.py")
    max_code = max(max_code, code)

    code = run_checker("数据一致性", "check_data_consistency.py")
    max_code = max(max_code, code)

    # 类型检查（如果脚本存在）
    type_script = DEV_DIR / "check_type_consistency.py"
    if type_script.exists():
        code = run_checker("类型一致性", "check_type_consistency.py")
        max_code = max(max_code, code)
    else:
        print("  [类型一致性] 未实现（Phase B）")

    print("=" * 50)
    if max_code == 0:
        print("[PASS] 所有检查通过 ✓")
    elif max_code == 1:
        print("[FAIL] 发现 CRITICAL/HIGH 问题，请修复后重试")
    else:
        print("[WARN] 发现 MEDIUM/LOW 问题，建议修复")
    print("=" * 50)

    return max_code


def main():
    parser = argparse.ArgumentParser(
        description="Virtual Vet Gate Check — 提交前一致性检查"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--quick", action="store_true", help="快速模式（默认）")
    group.add_argument("--full", action="store_true", help="完整模式")
    group.add_argument("--fix", action="store_true", help="自动修复可修复的问题")
    group.add_argument("--schema", action="store_true", help="JSON Schema 验证")
    group.add_argument("--verify-refs", action="store_true", help="验证参数文献溯源覆盖率")
    group.add_argument("--install-hook", action="store_true", help="安装 Git pre-commit hook")
    args = parser.parse_args()

    # 跳过检查
    if os.environ.get("GATE_SKIP") == "1":
        print("[GATE SKIPPED]")
        return 0

    if args.install_hook:
        install_hook()
        return 0

    if args.fix:
        return run_fix()
    elif args.schema:
        return run_schema()
    elif args.verify_refs:
        return run_verify_refs()
    elif args.full:
        return run_quick()
    else:
        return run_quick()


if __name__ == "__main__":
    sys.exit(main())
