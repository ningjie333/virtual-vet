"""Test suite effectiveness collector.

Runs pytest for a given lane/bundle, parses junit-xml + coverage.xml,
and emits a JSON report with:

  * per-test timing and status
  * per-file aggregates (count, mean, median, p95, p99, max, slowest)
  * top-20 hotspot ledger
  * optional line/branch coverage summary (when --cov passed)
  * fail/timeout/skip statistics

Output: results/test_effectiveness/<YYYYMMDD-HHMMSS>_<lane>.json

Usage:
    uv run python tools/dev/check_test_effectiveness.py --lane fast --cov
    uv run python tools/dev/check_test_effectiveness.py --lane core --cov
    uv run python tools/dev/check_test_effectiveness.py --lane heavy
    uv run python tools/dev/check_test_effectiveness.py --lane fast --bundle fast-engine
    uv run python tools/dev/check_test_effectiveness.py --lane core --compare results/test_effectiveness/prev.json
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "tests" / "test_manifest.json"
RESULTS_DIR = PROJECT_ROOT / "results" / "test_effectiveness"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestItemRecord:
    name: str
    classname: str
    file: str
    lane: str
    bundle: str
    time_s: float
    status: str


@dataclass(frozen=True)
class FileAggregate:
    file: str
    lane: str
    bundle: str
    test_count: int
    total_time_s: float
    mean_time_s: float
    median_time_s: float
    p95_time_s: float
    p99_time_s: float
    max_time_s: float
    pass_count: int
    fail_count: int
    error_count: int
    skip_count: int
    slowest_test: str


@dataclass(frozen=True)
class CoverageSummary:
    total_statements: int
    covered_statements: int
    missing_statements: int
    line_pct: float
    total_branches: int
    covered_branches: int
    branch_pct: float
    per_file: dict


@dataclass
class EffectivenessReport:
    generated_at: str
    python_version: str
    pytest_cov_version: str
    lane: str
    bundles: list
    duration_s: float
    test_count: int
    pass_count: int
    fail_count: int
    error_count: int
    skip_count: int
    test_items: list
    file_aggregates: list
    hotspot_top20: list
    coverage: Optional[dict]
    fail_summary: dict
    pytest_exit_code: int


# ---------------------------------------------------------------------------
# Manifest loading (mirrors tools/dev/generate_test_manifest_report.py)
# ---------------------------------------------------------------------------


def load_manifest() -> dict:
    """Return {filename: {lane, bundle}} from tests/test_manifest.json."""
    if not MANIFEST_PATH.exists():
        return {}
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    files = data.get("files", {})
    if not isinstance(files, dict):
        return {}
    return {
        name: {"lane": meta.get("lane", ""), "bundle": meta.get("bundle", "")}
        for name, meta in files.items()
    }


MANIFEST = load_manifest()


# ---------------------------------------------------------------------------
# Percentile helper
# ---------------------------------------------------------------------------


def _percentile(values: list, pct: float) -> float:
    """Linear-interpolation percentile (numpy-style)."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


# ---------------------------------------------------------------------------
# junit-xml parsing
# ---------------------------------------------------------------------------


def parse_junit_xml(xml_path: Path) -> list:
    """Parse junit-xml into a list of TestItemRecord."""
    tree = ElementTree.parse(xml_path)
    root = tree.getroot()
    items = []

    # junit-xml nests <testsuite> under <testsuites> (or root is <testsuite>)
    suites = root.findall(".//testsuite") if root.tag == "testsuites" else [root]

    for suite in suites:
        for tc in suite.findall("testcase"):
            name = tc.get("name", "<unnamed>")
            classname = tc.get("classname", "")
            time_s = float(tc.get("time", "0") or "0")

            # Determine status
            failure = tc.find("failure")
            error = tc.find("error")
            skipped = tc.find("skipped")
            if error is not None:
                status = "error"
            elif failure is not None:
                status = "fail"
            elif skipped is not None:
                status = "skip"
            else:
                status = "pass"

            # Derive file name from classname: tests.test_heart.TestHeart -> test_heart.py
            # JUnit classname often is "tests.test_heart.TestClassName"
            file_name = _derive_file(classname)
            meta = MANIFEST.get(file_name, {"lane": "", "bundle": ""})
            items.append(
                TestItemRecord(
                    name=name,
                    classname=classname,
                    file=file_name,
                    lane=meta["lane"],
                    bundle=meta["bundle"],
                    time_s=time_s,
                    status=status,
                )
            )
    return items


def _derive_file(classname: str) -> str:
    """tests.test_heart.TestHeart -> test_heart.py"""
    if not classname:
        return ""
    # Strip leading "tests." prefix
    if classname.startswith("tests."):
        classname = classname[len("tests."):]
    # Take first dot-separated token (the module name)
    module = classname.split(".", 1)[0]
    if not module:
        return ""
    return module + ".py"


# ---------------------------------------------------------------------------
# File aggregation
# ---------------------------------------------------------------------------


def aggregate_by_file(items: list) -> list:
    """Group test items by file and compute statistics."""
    by_file = {}
    for it in items:
        by_file.setdefault(it.file, []).append(it)

    aggs = []
    for file_name, file_items in by_file.items():
        times = [it.time_s for it in file_items]
        meta = MANIFEST.get(file_name, {"lane": "", "bundle": ""})
        aggs.append(
            FileAggregate(
                file=file_name,
                lane=meta["lane"],
                bundle=meta["bundle"],
                test_count=len(file_items),
                total_time_s=sum(times),
                mean_time_s=statistics.mean(times) if times else 0.0,
                median_time_s=statistics.median(times) if times else 0.0,
                p95_time_s=_percentile(times, 95),
                p99_time_s=_percentile(times, 99),
                max_time_s=max(times) if times else 0.0,
                pass_count=sum(1 for it in file_items if it.status == "pass"),
                fail_count=sum(1 for it in file_items if it.status == "fail"),
                error_count=sum(1 for it in file_items if it.status == "error"),
                skip_count=sum(1 for it in file_items if it.status == "skip"),
                slowest_test=max(file_items, key=lambda x: x.time_s).name
                if file_items
                else "",
            )
        )
    # Sort by total_time descending
    aggs.sort(key=lambda a: a.total_time_s, reverse=True)
    return aggs


# ---------------------------------------------------------------------------
# coverage.xml parsing (Cobertura format emitted by pytest-cov)
# ---------------------------------------------------------------------------


def parse_coverage_xml(xml_path: Path) -> Optional[dict]:
    """Parse coverage.xml into a CoverageSummary dict."""
    if not xml_path.exists():
        return None
    try:
        tree = ElementTree.parse(xml_path)
        root = tree.getroot()
        # Root is <coverage> with attributes line-rate, branch-rate
        line_rate = float(root.get("line-rate", "0") or "0")
        branch_rate = float(root.get("branch-rate", "0") or "0")
        lines_valid = int(root.get("lines-valid", "0") or "0")
        lines_covered = int(root.get("lines-covered", "0") or "0")
        branches_valid = int(root.get("branches-valid", "0") or "0")
        branches_covered = int(root.get("branches-covered", "0") or "0")

        per_file = {}
        for cls in root.findall(".//class"):
            filename = cls.get("filename", "")
            if not filename:
                continue
            f_line_rate = float(cls.get("line-rate", "0") or "0")
            f_branch_rate = float(cls.get("branch-rate", "0") or "0")
            # Collect missing line numbers from <line> elements with hits=0
            missing_lines = []
            for line_el in cls.findall("lines/line"):
                hits = int(line_el.get("hits", "0") or "0")
                if hits == 0:
                    ln = line_el.get("number", "")
                    if ln:
                        missing_lines.append(int(ln))
            per_file[filename] = {
                "line_pct": round(f_line_rate * 100, 2),
                "branch_pct": round(f_branch_rate * 100, 2),
                "missing_lines": missing_lines[:30],  # cap to first 30
                "missing_count": len(missing_lines),
            }

        return asdict(
            CoverageSummary(
                total_statements=lines_valid,
                covered_statements=lines_covered,
                missing_statements=lines_valid - lines_covered,
                line_pct=round(line_rate * 100, 2),
                total_branches=branches_valid,
                covered_branches=branches_covered,
                branch_pct=round(branch_rate * 100, 2),
                per_file=per_file,
            )
        )
    except Exception as exc:
        return {"error": f"coverage.xml parse failed: {exc}"}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def get_pytest_cov_version() -> str:
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import pytest_cov; print(pytest_cov.__version__)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def run_pytest(
    lane: str, bundles: list, junit_path: Path, with_cov: bool, timeout: Optional[int]
) -> tuple[int, str, str]:
    """Run pytest via uv run, return (exit_code, stdout, stderr)."""
    cmd = ["uv", "run", "python", "-m", "pytest", f"--channel={lane}", "--durations=0"]
    if junit_path:
        cmd.append(f"--junit-xml={junit_path}")
    for b in bundles:
        cmd.append(f"--bundle={b}")
    if with_cov:
        cmd.extend(
            [
                "--cov",
                "--cov-report=",
                f"--cov-report=xml:{RESULTS_DIR / 'coverage.xml'}",
                "--cov-report=term-missing",
            ]
        )
    if timeout is not None:
        cmd.append(f"--timeout={timeout}")
    cmd.append("-q")

    print(f"[check_test_effectiveness] running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    return result.returncode, result.stdout, result.stderr


def build_report(
    lane: str,
    bundles: list,
    junit_path: Path,
    cov_path: Optional[Path],
    pytest_exit_code: int,
    duration_s: float,
) -> dict:
    items = parse_junit_xml(junit_path)
    file_aggs = aggregate_by_file(items)

    # Hotspot top 20 by time descending
    hotspot = sorted(items, key=lambda x: x.time_s, reverse=True)[:20]

    # Status counts
    pass_count = sum(1 for it in items if it.status == "pass")
    fail_count = sum(1 for it in items if it.status == "fail")
    error_count = sum(1 for it in items if it.status == "error")
    skip_count = sum(1 for it in items if it.status == "skip")

    fail_summary = {
        "failures": [
            {"name": it.name, "file": it.file, "time_s": it.time_s}
            for it in items
            if it.status in ("fail", "error")
        ],
        "skips": [
            {"name": it.name, "file": it.file}
            for it in items
            if it.status == "skip"
        ],
    }

    coverage = None
    if cov_path:
        coverage = parse_coverage_xml(cov_path)

    report = EffectivenessReport(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        python_version=platform.python_version(),
        pytest_cov_version=get_pytest_cov_version(),
        lane=lane,
        bundles=bundles,
        duration_s=round(duration_s, 2),
        test_count=len(items),
        pass_count=pass_count,
        fail_count=fail_count,
        error_count=error_count,
        skip_count=skip_count,
        test_items=[asdict(it) for it in items],
        file_aggregates=[asdict(a) for a in file_aggs],
        hotspot_top20=[asdict(it) for it in hotspot],
        coverage=coverage,
        fail_summary=fail_summary,
        pytest_exit_code=pytest_exit_code,
    )
    return asdict(report)


def print_summary(report: dict) -> None:
    """Print human-readable summary to stderr."""
    print("", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"Lane: {report['lane']}  Bundles: {report['bundles'] or '(all)'}", file=sys.stderr)
    print(
        f"Tests: {report['test_count']} "
        f"(pass={report['pass_count']} fail={report['fail_count']} "
        f"error={report['error_count']} skip={report['skip_count']})",
        file=sys.stderr,
    )
    print(
        f"Duration: {report['duration_s']:.2f}s  pytest exit: {report['pytest_exit_code']}",
        file=sys.stderr,
    )

    if report["coverage"] and "error" not in report["coverage"]:
        cov = report["coverage"]
        print(
            f"Coverage: line={cov['line_pct']}% branch={cov['branch_pct']}% "
            f"({cov['covered_statements']}/{cov['total_statements']} statements)",
            file=sys.stderr,
        )

    print("\nTop 10 slowest files:", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    print(
        f"{'file':<40} {'tests':>6} {'total_s':>10} {'mean_ms':>10} {'max_ms':>10}",
        file=sys.stderr,
    )
    for agg in report["file_aggregates"][:10]:
        print(
            f"{agg['file']:<40} {agg['test_count']:>6} "
            f"{agg['total_time_s']:>10.2f} "
            f"{agg['mean_time_s'] * 1000:>10.1f} "
            f"{agg['max_time_s'] * 1000:>10.1f}",
            file=sys.stderr,
        )

    print("\nTop 20 slowest individual tests (hotspot ledger):", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    for i, it in enumerate(report["hotspot_top20"], 1):
        print(
            f"{i:>3}. {it['file']:<35} {it['name']:<35} {it['time_s']:>7.3f}s",
            file=sys.stderr,
        )

    if report["fail_summary"]["failures"]:
        print("\nFailures/errors:", file=sys.stderr)
        for f in report["fail_summary"]["failures"][:20]:
            print(f"  - {f['file']}::{f['name']} ({f['time_s']:.3f}s)", file=sys.stderr)

    print("=" * 70, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Collect test effectiveness data (timing + coverage) for a lane."
    )
    parser.add_argument(
        "--lane",
        choices=["fast", "core", "heavy", "benchmark", "research", "all"],
        default="fast",
    )
    parser.add_argument("--bundle", action="append", default=[], help="Bundle filter (repeatable)")
    parser.add_argument("--cov", action="store_true", help="Also collect pytest-cov coverage")
    parser.add_argument("--timeout", type=int, default=None, help="Per-test timeout (seconds)")
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: results/test_effectiveness/<timestamp>_<lane>.json)",
    )
    parser.add_argument("--compare", default=None, help="Compare with previous report path")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = (
        Path(args.output)
        if args.output
        else RESULTS_DIR / f"{timestamp}_{args.lane}.json"
    )

    # Use a temp junit-xml file (pytest requires a path it can write to)
    with tempfile.NamedTemporaryFile(
        suffix=".xml", delete=False, prefix="junit_"
    ) as tmp:
        junit_path = Path(tmp.name)

    cov_path = RESULTS_DIR / "coverage.xml" if args.cov else None

    start = time.time()
    exit_code, stdout, stderr = run_pytest(
        lane=args.lane,
        bundles=args.bundle,
        junit_path=junit_path,
        with_cov=args.cov,
        timeout=args.timeout,
    )
    duration = time.time() - start

    # If stdout has content of interest, save a snippet
    if stdout:
        (RESULTS_DIR / f"{timestamp}_{args.lane}_stdout.txt").write_text(
            stdout[-8000:], encoding="utf-8"
        )

    try:
        report = build_report(
            lane=args.lane,
            bundles=args.bundle,
            junit_path=junit_path,
            cov_path=cov_path,
            pytest_exit_code=exit_code,
            duration_s=duration,
        )
    finally:
        # Cleanup temp junit file
        try:
            junit_path.unlink(missing_ok=True)
        except Exception:
            pass

    print_summary(report)

    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n[check_test_effectiveness] report written to: {output_path}", file=sys.stderr)

    # Optional compare
    if args.compare:
        prev_path = Path(args.compare)
        if prev_path.exists():
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
            print("\nComparison with previous report:", file=sys.stderr)
            print(f"  previous: {prev.get('generated_at', '?')} lane={prev.get('lane', '?')}", file=sys.stderr)
            print(
                f"  test_count:    {prev.get('test_count', 0)} -> {report['test_count']}",
                file=sys.stderr,
            )
            print(
                f"  duration:      {prev.get('duration_s', 0):.2f}s -> {report['duration_s']:.2f}s",
                file=sys.stderr,
            )
            if report.get("coverage") and prev.get("coverage"):
                if "error" not in report["coverage"] and "error" not in prev["coverage"]:
                    print(
                        f"  line coverage: {prev['coverage']['line_pct']}% -> {report['coverage']['line_pct']}%",
                        file=sys.stderr,
                    )
                    print(
                        f"  branch cov:    {prev['coverage']['branch_pct']}% -> {report['coverage']['branch_pct']}%",
                        file=sys.stderr,
                    )
        else:
            print(f"\n[compare] previous report not found: {prev_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
