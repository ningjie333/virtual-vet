#!/usr/bin/env python3
"""
Clue Catalog consistency check (Wave 0).

验证 data/clue_catalog.json 与现状三个源头一致：
  - data/symptom_definitions.json  (symptom clue_id)
  - data/exam_templates.json       (clue_id 字段，递归)
  - data/diseases.json             (clue_to_test keys)

退出码: 0=无问题, 1=有 CRITICAL/HIGH, 2=仅有 MEDIUM/LOW
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

VALID_CATEGORIES = {
    "A_bedside_observational",
    "B_quantitative_abnormality",
    "C_exam_evidence",
    "D_synthesis",
    "E_deprecated_alias",
}

# Owner mapping per Q2/Q3 decisions (this is the single source of truth for
# "which owner is allowed for which category")
VALID_OWNERS_BY_CATEGORY = {
    "A_bedside_observational": {"symptom_engine"},
    "B_quantitative_abnormality": {
        "ranges_translators",  # Wave 0 seed; future Wave may split per family
    },
    "C_exam_evidence": {"exam_finding_translator"},
    "D_synthesis": {"synthesis_layer"},
    "E_deprecated_alias": {"alias_registry"},
}


def load_json(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        print(f"[ERROR] 找不到 {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── 三个源头的真实数据 ────────────────────────────────

def collect_symptom_clues(defs: dict) -> set[str]:
    """All clue_id values defined in symptom_definitions.json."""
    out = set()
    for sdef in defs.get("symptoms", {}).values():
        out.add(sdef.get("clue_id", ""))
    out.discard("")
    return out


def collect_exam_clue_ids(templates: dict) -> dict[str, list[tuple[str, str]]]:
    """All clue_id fields recursively in exam_templates.json.

    Returns {clue_id: [(exam_key, json_path), ...]}
    """
    out: dict[str, list] = {}

    def walk(obj, p="", ek=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                # Detect exam-template root by structural cue
                new_ek = ek
                if (
                    not k.startswith("_")
                    and isinstance(v, dict)
                    and ("tag_rules" in v or "findings_rules" in v)
                ):
                    new_ek = k
                walk(v, f"{p}/{k}", new_ek)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{p}[{i}]", ek)
        elif isinstance(obj, str):
            if p.endswith("/clue_id") and obj:
                out.setdefault(obj, []).append((ek, p))

    walk(templates)
    return out


def collect_diagnosis_clue_keys(diseases: dict) -> set[str]:
    """All clue IDs referenced in diseases.json clue_to_test."""
    return set(diseases.get("clue_to_test", {}).keys())


# ─── 校验函数 ────────────────────────────────────────────

def check_registry_completeness(
    catalog: dict,
    sx_clues: set[str],
    ex_clue_map: dict,
    diag_clues: set[str],
) -> list:
    """Every emitted clue must be in the catalog."""
    errors = []
    registered = {k for k in catalog if not k.startswith("_")}
    emitted = sx_clues | set(ex_clue_map) | diag_clues

    missing = sorted(emitted - registered)
    for cid in missing:
        sources = []
        if cid in sx_clues: sources.append("symptom")
        if cid in ex_clue_map: sources.append("exam")
        if cid in diag_clues: sources.append("diagnosis")
        errors.append({
            "sev": SEVERITY_HIGH,
            "msg": f"clue '{cid}' 被源头 [{','.join(sources)}] 发出但未在 catalog 注册",
        })

    # Reverse: catalog entries that no source emits (orphan). LOW — may be intentional aliases.
    orphans = sorted(registered - emitted)
    for cid in orphans:
        errors.append({
            "sev": SEVERITY_LOW,
            "msg": f"clue '{cid}' 在 catalog 注册但未被任何源头发出（可能是废弃 alias）",
        })
    return errors


def check_schema_integrity(catalog: dict) -> list:
    """Every entry must have the minimum required fields."""
    errors = []
    required = {
        "category", "owner", "canonical",
        "diagnosis_allowed", "projection_allowed_in_reports",
        "suggested_tests",
    }
    for cid, entry in catalog.items():
        if cid.startswith("_"):
            continue
        missing = required - set(entry.keys())
        if missing:
            errors.append({
                "sev": SEVERITY_HIGH,
                "msg": f"clue '{cid}' 缺少字段: {sorted(missing)}",
            })
            continue
        if entry["category"] not in VALID_CATEGORIES:
            errors.append({
                "sev": SEVERITY_HIGH,
                "msg": f"clue '{cid}' category='{entry['category']}' 非法",
            })
        allowed = VALID_OWNERS_BY_CATEGORY.get(entry["category"], set())
        if entry["owner"] not in allowed:
            errors.append({
                "sev": SEVERITY_MEDIUM,
                "msg": f"clue '{cid}' owner='{entry['owner']}' 不在 category='{entry['category']}' 的合法集合 {sorted(allowed)} 中",
            })
    return errors


def check_diagnosis_integrity(catalog: dict, diag_clues: set[str]) -> list:
    """Every diagnosis clue must be registered AND diagnosis_allowed."""
    errors = []
    for cid in sorted(diag_clues):
        entry = catalog.get(cid)
        if entry is None:
            # covered by completeness check
            continue
        if not entry.get("diagnosis_allowed", False):
            errors.append({
                "sev": SEVERITY_MEDIUM,
                "msg": f"clue '{cid}' 被 diseases.json 引用但 catalog 中 diagnosis_allowed=False",
            })
    return errors


def check_dual_owners(catalog: dict, ex_clue_map: dict) -> list:
    """7 known dual-owners must be Category A and flagged exam_projection_only."""
    DUAL_OWNERS = {
        "crackles", "arrhythmia", "pulsus_paradoxus",
        "icterus", "petechiae", "dehydration", "anuria",
    }
    errors = []
    for cid in sorted(DUAL_OWNERS & set(catalog)):
        entry = catalog[cid]
        if entry["category"] != "A_bedside_observational":
            errors.append({
                "sev": SEVERITY_HIGH,
                "msg": f"dual-owner '{cid}' 应归 Category A_bedside_observational（当前 {entry['category']}）",
            })
        if cid in ex_clue_map and not entry.get("exam_projection_only", False):
            errors.append({
                "sev": SEVERITY_MEDIUM,
                "msg": f"dual-owner '{cid}' 同时在 exam_templates 中出现但 catalog 未标记 exam_projection_only",
            })
    return errors


def check_modality_suffix(catalog: dict) -> list:
    """Category C clues must carry modality suffix (Q2 decision)."""
    errors = []
    ALLOWED_SUFFIXES = (
        "_xray", "_ct", "_us", "_usg",   # imaging + urinalysis sediment
        "_ecg",                           # ECG morphology
        "_auscultation",                  # cardiac/pulmonary auscultation
        "_inspection",                    # visual inspection / physical exam findings
        "_endoscopy",                     # endoscopic findings
        "_blood_pressure",                # blood-pressure cuff measurements
    )
    for cid, entry in catalog.items():
        if cid.startswith("_"):
            continue
        if entry["category"] != "C_exam_evidence":
            continue
        if not any(cid.endswith(s) for s in ALLOWED_SUFFIXES):
            errors.append({
                "sev": SEVERITY_LOW,
                "msg": f"Category C clue '{cid}' 缺少模态后缀 {ALLOWED_SUFFIXES}（Q2 决议）",
            })
    return errors


# ─── 入口 ────────────────────────────────────────────────

def run_check() -> int:
    print("=" * 50)
    print("Clue Catalog 一致性检查 — Wave 0")
    print("=" * 50)

    catalog = load_json("clue_catalog.json")
    sx = load_json("symptom_definitions.json")
    ex = load_json("exam_templates.json")
    dz = load_json("diseases.json")

    sx_clues = collect_symptom_clues(sx)
    ex_clue_map = collect_exam_clue_ids(ex)
    diag_clues = collect_diagnosis_clue_keys(dz)

    meta = catalog.get("_meta", {})
    print(f"catalog total: {meta.get('total', '?')}")
    print(f"  Category counts: {meta.get('category_counts', {})}")
    print(f"现状源头:")
    print(f"  symptom clue_id:    {len(sx_clues)}")
    print(f"  exam clue_id:       {len(ex_clue_map)}")
    print(f"  diagnosis (clue_to_test): {len(diag_clues)}")
    print()

    errors: list = []
    errors.extend(check_registry_completeness(catalog, sx_clues, ex_clue_map, diag_clues))
    errors.extend(check_schema_integrity(catalog))
    errors.extend(check_diagnosis_integrity(catalog, diag_clues))
    errors.extend(check_dual_owners(catalog, ex_clue_map))
    errors.extend(check_modality_suffix(catalog))

    if not errors:
        print("[OK] 所有检查通过")
        return 0

    critical = [e for e in errors if e["sev"] == SEVERITY_CRITICAL]
    high = [e for e in errors if e["sev"] == SEVERITY_HIGH]
    medium = [e for e in errors if e["sev"] == SEVERITY_MEDIUM]
    low = [e for e in errors if e["sev"] == SEVERITY_LOW]

    for err in errors:
        print(f"[{err['sev']}] {err['msg']}")

    print(f"\n共 {len(errors)} 个问题：CRITICAL={len(critical)}, HIGH={len(high)}, MEDIUM={len(medium)}, LOW={len(low)}")
    if critical or high:
        return 1
    return 2


def main():
    parser = argparse.ArgumentParser(description="Clue Catalog 一致性检查")
    args = parser.parse_args()
    sys.exit(run_check())


if __name__ == "__main__":
    main()