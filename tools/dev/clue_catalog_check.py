#!/usr/bin/env python3
"""
Clue Catalog consistency check.

This CLI reuses the same project-level validation contract as
src/config_validation.py so the dev check and the formal validation path do not
drift apart.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clue_catalog_validation import (  # noqa: E402
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    load_json,
    validate_clue_catalog_consistency,
)

DATA_DIR = PROJECT_ROOT / "data"


def run_check() -> int:
    print("=" * 50)
    print("Clue Catalog consistency check")
    print("=" * 50)

    catalog = load_json(DATA_DIR / "clue_catalog.json")
    symptom_definitions = load_json(DATA_DIR / "symptom_definitions.json")
    exam_templates = load_json(DATA_DIR / "exam_templates.json")
    diseases = load_json(DATA_DIR / "diseases.json")

    meta = catalog.get("_meta", {})
    print(f"catalog total: {meta.get('total', '?')}")
    print(f"  category counts: {meta.get('category_counts', {})}")
    print()

    issues = validate_clue_catalog_consistency(
        catalog,
        symptom_definitions,
        exam_templates,
        diseases,
    )
    if not issues:
        print("[OK] all checks passed")
        return 0

    critical = [issue for issue in issues if issue.severity == SEVERITY_CRITICAL]
    high = [issue for issue in issues if issue.severity == SEVERITY_HIGH]
    medium = [issue for issue in issues if issue.severity == SEVERITY_MEDIUM]
    low = [issue for issue in issues if issue.severity == SEVERITY_LOW]

    for issue in issues:
        print(f"[{issue.severity}] {issue.path}: {issue.message}")

    print(
        f"\n{len(issues)} issue(s): "
        f"CRITICAL={len(critical)}, HIGH={len(high)}, "
        f"MEDIUM={len(medium)}, LOW={len(low)}"
    )
    if critical or high:
        return 1
    return 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Clue Catalog consistency check")
    parser.parse_args()
    sys.exit(run_check())


if __name__ == "__main__":
    main()
