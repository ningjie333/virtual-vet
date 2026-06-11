#!/usr/bin/env python3
"""Project harness runner for repeatable validation profiles."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = PROJECT_ROOT / "vet-game-frontend" / "vite-project"
DEFAULT_REPORT = PROJECT_ROOT / "results" / "harness" / "latest.json"
PROFILE_BUDGET_SECONDS = {
    "quick": 5.0,
    "contract": 15.0,
    "frontend": 10.0,
    "api": 20.0,
    "app": 60.0,
    "core": 70.0,
    "release": 85.0,
}


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]
    cwd: Path = PROJECT_ROOT


def _vue_tsc_command() -> tuple[str, ...]:
    suffix = ".cmd" if sys.platform == "win32" else ""
    local = FRONTEND_ROOT / "node_modules" / ".bin" / f"vue-tsc{suffix}"
    if local.exists():
        return (str(local), "-b")
    return ("npx", "vue-tsc", "-b")


PROFILES: dict[str, tuple[Step, ...]] = {
    "quick": (
        Step("gate quick", (sys.executable, "tools/dev/gate_check.py", "--quick")),
    ),
    "contract": (
        Step("gate quick", (sys.executable, "tools/dev/gate_check.py", "--quick")),
        Step(
            "contract rules",
            (
                sys.executable,
                "-m",
                "pytest",
                "tests/test_gate_contract.py::TestApiGateRules",
                "tests/test_interface.py::TestErrorHandling::test_session_endpoints_require_lock",
                "-q",
            ),
        ),
    ),
    "frontend": (
        Step("frontend typecheck", _vue_tsc_command(), FRONTEND_ROOT),
    ),
    "api": (
        Step("gate quick", (sys.executable, "tools/dev/gate_check.py", "--quick")),
        Step(
            "api contracts",
            (
                sys.executable,
                "-m",
                "pytest",
                "tests/test_interface.py::TestStaticApiEndpoints",
                "tests/test_interface.py::TestNewGame",
                "tests/test_interface.py::TestExamine",
                "tests/test_interface.py::TestDiagnose",
                "tests/test_interface.py::TestWait",
                "tests/test_interface.py::TestGameState",
                "tests/test_interface.py::TestHint",
                "tests/test_interface.py::TestResponseFormat",
                "tests/test_interface.py::TestErrorHandling",
                "tests/test_interface.py::TestAllRoutesNo500",
                "tests/test_gate_contract.py::TestApiGateRules",
                "-q",
            ),
        ),
    ),
    "app": (
        Step("gate quick", (sys.executable, "tools/dev/gate_check.py", "--quick")),
        Step(
            "app api workflow",
            (
                sys.executable,
                "-m",
                "pytest",
                "tests/test_interface.py::TestSessionPersistence",
                "tests/test_pharmacology.py::TestApiAdministerDrug",
                "tests/test_pharmacology.py::TestApiDrugs",
                "tests/test_pharmacology.py::TestE2EGameFlow",
                "-q",
            ),
        ),
        Step("frontend typecheck", _vue_tsc_command(), FRONTEND_ROOT),
    ),
    "core": (
        Step("gate quick", (sys.executable, "tools/dev/gate_check.py", "--quick")),
        Step("core channel", (sys.executable, "-m", "pytest", "--channel", "core", "-q")),
    ),
    "release": (
        Step("gate quick", (sys.executable, "tools/dev/gate_check.py", "--quick")),
        Step("core channel", (sys.executable, "-m", "pytest", "--channel", "core", "-q")),
        Step("frontend typecheck", _vue_tsc_command(), FRONTEND_ROOT),
    ),
}


def _git_value(args: tuple[str, ...]) -> str | None:
    result = subprocess.run(
        ("git",) + args,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        shell=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git_metadata() -> dict[str, object]:
    status = _git_value(("status", "--porcelain")) or ""
    return {
        "branch": _git_value(("branch", "--show-current")),
        "commit": _git_value(("rev-parse", "--short", "HEAD")),
        "dirty": bool(status),
    }


def _display_command(step: Step) -> str:
    try:
        cwd = step.cwd.relative_to(PROJECT_ROOT)
    except ValueError:
        cwd = step.cwd
    return f"(cd {cwd}; {' '.join(step.command)})"


def _write_report(report: dict[str, object], report_path: Path | None) -> None:
    if report_path is None:
        return
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[REPORT] {report_path}")
    except OSError as exc:
        print(f"[WARN] failed to write harness report: {exc}")


def run_profile(
    profile: str,
    *,
    dry_run: bool = False,
    continue_on_fail: bool = False,
    report_path: Path | None = DEFAULT_REPORT,
) -> int:
    steps = PROFILES[profile]
    print("=" * 60)
    print(f"Virtual Vet Harness — {profile}")
    print("=" * 60)

    max_code = 0
    started = time.time()
    report_steps: list[dict[str, object]] = []
    for idx, step in enumerate(steps, start=1):
        print(f"\n[{idx}/{len(steps)}] {step.name}")
        print(f"  {_display_command(step)}")
        step_report: dict[str, object] = {
            "name": step.name,
            "command": list(step.command),
            "cwd": str(step.cwd.relative_to(PROJECT_ROOT)),
            "dry_run": dry_run,
        }
        if dry_run:
            step_report.update({"status": "SKIPPED", "exit_code": None, "duration_s": 0.0})
            report_steps.append(step_report)
            continue
        t0 = time.time()
        result = subprocess.run(step.command, cwd=step.cwd, shell=False)
        elapsed = time.time() - t0
        max_code = max(max_code, result.returncode)
        status = "PASS" if result.returncode == 0 else f"FAIL({result.returncode})"
        print(f"  [{status}] {elapsed:.1f}s")
        step_report.update(
            {
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "exit_code": result.returncode,
                "duration_s": round(elapsed, 3),
            }
        )
        report_steps.append(step_report)
        if result.returncode != 0 and not continue_on_fail:
            break

    total = time.time() - started
    budget_s = PROFILE_BUDGET_SECONDS.get(profile)
    over_budget = budget_s is not None and total > budget_s
    report = {
        "profile": profile,
        "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "duration_s": round(total, 3),
        "budget_s": budget_s,
        "over_budget": over_budget,
        "exit_code": max_code,
        "status": "PASS" if max_code == 0 else "FAIL",
        "dry_run": dry_run,
        "continue_on_fail": continue_on_fail,
        "git": _git_metadata(),
        "steps": report_steps,
    }

    print("\n" + "=" * 60)
    if dry_run:
        print("[DRY RUN] No commands executed")
    elif max_code == 0:
        print(f"[PASS] Harness profile '{profile}' passed in {total:.1f}s")
    else:
        print(f"[FAIL] Harness profile '{profile}' failed with code {max_code}")
    if over_budget:
        print(f"[WARN] Profile exceeded budget: {total:.1f}s > {budget_s:.1f}s")
    print("=" * 60)
    _write_report(report, report_path)
    return max_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Virtual Vet validation harness profiles.")
    parser.add_argument(
        "profile",
        nargs="?",
        default="quick",
        choices=sorted(PROFILES),
        help="Validation profile to run.",
    )
    parser.add_argument("--list", action="store_true", help="List profiles and commands.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument("--continue-on-fail", action="store_true", help="Run all steps even after a failure.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Write JSON report to this path.")
    parser.add_argument("--no-report", action="store_true", help="Do not write a JSON report.")
    args = parser.parse_args()

    if args.list:
        for name, steps in sorted(PROFILES.items()):
            print(f"{name}:")
            for step in steps:
                print(f"  - {step.name}: {_display_command(step)}")
        return 0

    return run_profile(
        args.profile,
        dry_run=args.dry_run,
        continue_on_fail=args.continue_on_fail,
        report_path=None if args.no_report else args.report,
    )


if __name__ == "__main__":
    sys.exit(main())
