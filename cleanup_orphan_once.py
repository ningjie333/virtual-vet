#!/usr/bin/env python3
"""一次性清理 cwd 顶层特定的 D：dev-cache：npm 全角冒号孤儿目录。

目标路径（UTF-8 字节）：
  b'D\xef\x80\xba\xef\x81\x9cdev-cache\xef\x81\x9cnpm'
  = U+FF3A (：) + U+FF5C (＼) + dev-cache + U+FF1C (＼) + npm

这是 npm 在 Git Bash 下被 mingw 转换的产物（6/13 事件），
与项目代码完全无关。删它对其他任何东西都无影响。

用法：uv run python cleanup_orphan_once.py
"""
import os
import shutil
import sys
from pathlib import Path

TARGET_BYTES = b"D\xef\x80\xba\xef\x81\x9cdev-cache\xef\x81\x9cnpm"


def main() -> int:
    cwd = Path(".")
    found = None
    for p in cwd.iterdir():
        try:
            raw = os.fsencode(p.name)
        except UnicodeEncodeError:
            continue
        if raw == TARGET_BYTES:
            found = p
            break

    if found is None:
        print("[OK] cwd 顶层无 D:：dev-cache：npm 孤儿（已干净）")
        return 0

    print(f"[FOUND] {found.name!r}")
    print(f"        bytes: {os.fsencode(found.name)!r}")
    print(f"        size : {found.stat().st_size} bytes")
    try:
        contents = list(found.iterdir())
        print(f"        contents ({len(contents)} items)")
        for c in contents[:5]:
            print(f"          - {c.name}")
    except Exception as e:
        print(f"        iterdir error: {e}")

    print()
    print("确认删除？[y/N] ", end="", flush=True)
    try:
        ans = input().strip().lower()
    except EOFError:
        ans = ""
    if ans != "y":
        print("[ABORT] 未删除")
        return 1

    try:
        shutil.rmtree(found)
        print(f"[DELETED] {found.name!r}")
    except Exception as e:
        print(f"[FAIL] {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
