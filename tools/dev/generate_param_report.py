#!/usr/bin/env python3
"""
Generate V&V (Verification & Validation) parameter report.

Exports a markdown table of all tunable engine parameters and coupling
coefficients with their literature references, derivation notes, and
verification status.

Usage:
    python tools/dev/generate_param_report.py
    python tools/dev/generate_param_report.py --output param_report.md
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def generate() -> str:
    from src.common_types import _PARAM_PATHS
    from src.parameter_refs import get_param_ref, all_param_refs
    from src.organs.coupling import CouplingEngine

    lines = []
    lines.append("# VirtualVet Parameter Literature — V&V Report")
    lines.append("")
    lines.append("> Generated automatically from `data/parameter_references.json` and `data/coupling_rules.json`")
    lines.append("> Format mirrors ode_diseases.json meta.references (PMIDs + textbooks)")
    lines.append("")
    lines.append("## 1. Engine Parameters (_PARAM_PATHS)")
    lines.append("")
    lines.append("| Parameter Path | Module | References | Notes |")
    lines.append("|---|---|---|---|")

    refs = all_param_refs()

    for path in sorted(_PARAM_PATHS.keys()):
        parts = path.split(".")
        module = parts[0]
        attr = parts[1] if len(parts) > 1 else ""
        entry = refs.get(path)
        if entry:
            ref_str = "; ".join(f"[{r['id']}] {r['text'][:80]}" for r in entry.get("references", []))
            note = entry.get("notes", "")[:120]
            status = "✓"
        else:
            ref_str = "—"
            note = "No literature reference"
            status = "✗"
        lines.append(f"| {path} | {module} | {status} {ref_str[:120]} | {note} |")

    lines.append("")
    lines.append("## 2. Coupling Rules")
    lines.append("")
    lines.append("| Rule Name | Loop | Enabled | References | Notes |")
    lines.append("|---|---|---|---|---|")

    engine = CouplingEngine()
    for rule in sorted(engine.rules, key=lambda r: (r.loop, r.name)):
        status = "✓" if rule.references else "✗"
        ref_str = "; ".join(f"[{r['id']}]" for r in rule.references) if rule.references else "—"
        note = (rule.notes or "")[:120]
        en = "Yes" if rule.enabled else "No"
        lines.append(f"| {rule.name} | {rule.loop} | {en} | {status} {ref_str} | {note} |")

    enabled_with_ref = sum(1 for r in engine.rules if r.enabled and r.references)
    enabled_total = sum(1 for r in engine.rules if r.enabled)
    lines.append("")
    lines.append(f"**Coupling rules with literature refs**: {enabled_with_ref}/{enabled_total} enabled rules")
    lines.append("")

    total = len(_PARAM_PATHS)
    with_ref = sum(1 for p in _PARAM_PATHS if p in refs)
    lines.append(f"**Engine parameters with literature refs**: {with_ref}/{total}")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate V&V parameter report")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()

    report = generate()

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"[OK] Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    sys.exit(main())