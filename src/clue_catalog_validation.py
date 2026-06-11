from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


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

VALID_OWNERS_BY_CATEGORY = {
    "A_bedside_observational": {"symptom_engine"},
    "B_quantitative_abnormality": {"ranges_translators"},
    "C_exam_evidence": {"exam_finding_translator"},
    "D_synthesis": {"synthesis_layer"},
    "E_deprecated_alias": {"alias_registry"},
}


@dataclass(frozen=True)
class ClueCatalogIssue:
    severity: str
    path: str
    message: str


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_symptom_clues(defs: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sign_id, sign_def in defs.get("symptoms", {}).items():
        clue_id = sign_def.get("clue_id")
        if not clue_id:
            continue
        out.setdefault(clue_id, []).append(f"symptoms.{sign_id}.clue_id")
    return out


def collect_exam_clue_ids(templates: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}

    def walk(obj, path="root"):
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                if key == "clue_id" and isinstance(value, str) and value:
                    out.setdefault(value, []).append(new_path)
                walk(value, new_path)
            return
        if isinstance(obj, list):
            for idx, value in enumerate(obj):
                walk(value, f"{path}[{idx}]")

    walk(templates)
    return out


def collect_diagnosis_clues(diseases: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for disease_name, clue_ids in diseases.get("clues", {}).items():
        if not isinstance(clue_ids, list):
            continue
        for idx, clue_id in enumerate(clue_ids):
            if isinstance(clue_id, str) and clue_id:
                out.setdefault(clue_id, []).append(f"clues.{disease_name}[{idx}]")
    return out


def check_registry_completeness(
    catalog: dict,
    symptom_clues: dict[str, list[str]],
    exam_clues: dict[str, list[str]],
    diagnosis_clues: dict[str, list[str]],
) -> list[ClueCatalogIssue]:
    issues: list[ClueCatalogIssue] = []
    registered = {k for k in catalog if not k.startswith("_")}
    emitted = set(symptom_clues) | set(exam_clues) | set(diagnosis_clues)

    missing = sorted(emitted - registered)
    for clue_id in missing:
        sources = []
        if clue_id in symptom_clues:
            sources.append("symptom")
        if clue_id in exam_clues:
            sources.append("exam")
        if clue_id in diagnosis_clues:
            sources.append("diagnosis")
        issue_path = (
            symptom_clues.get(clue_id, [])
            or exam_clues.get(clue_id, [])
            or diagnosis_clues.get(clue_id, [])
            or ["root"]
        )[0]
        issues.append(
            ClueCatalogIssue(
                severity=SEVERITY_HIGH,
                path=issue_path,
                message=f"clue '{clue_id}' is emitted by [{','.join(sources)}] but is not registered in clue_catalog.json",
            )
        )

    orphans = sorted(registered - emitted)
    for clue_id in orphans:
        issues.append(
            ClueCatalogIssue(
                severity=SEVERITY_LOW,
                path=clue_id,
                message=f"clue '{clue_id}' is registered in clue_catalog.json but not emitted by symptoms, exam templates, or diagnosis config",
            )
        )
    return issues


def check_schema_integrity(catalog: dict) -> list[ClueCatalogIssue]:
    issues: list[ClueCatalogIssue] = []
    required = {
        "category",
        "owner",
        "canonical",
        "diagnosis_allowed",
        "projection_allowed_in_reports",
        "suggested_tests",
    }
    for clue_id, entry in catalog.items():
        if clue_id.startswith("_"):
            continue
        missing = required - set(entry.keys())
        if missing:
            issues.append(
                ClueCatalogIssue(
                    severity=SEVERITY_HIGH,
                    path=clue_id,
                    message=f"clue '{clue_id}' is missing required fields: {sorted(missing)}",
                )
            )
            continue
        category = entry["category"]
        owner = entry["owner"]
        if category not in VALID_CATEGORIES:
            issues.append(
                ClueCatalogIssue(
                    severity=SEVERITY_HIGH,
                    path=f"{clue_id}.category",
                    message=f"clue '{clue_id}' has invalid category '{category}'",
                )
            )
        else:
            allowed_owners = VALID_OWNERS_BY_CATEGORY.get(category, set())
            if owner not in allowed_owners:
                issues.append(
                    ClueCatalogIssue(
                        severity=SEVERITY_MEDIUM,
                        path=f"{clue_id}.owner",
                        message=f"clue '{clue_id}' owner '{owner}' is not allowed for category '{category}'",
                    )
                )
        if not isinstance(entry["suggested_tests"], list):
            issues.append(
                ClueCatalogIssue(
                    severity=SEVERITY_HIGH,
                    path=f"{clue_id}.suggested_tests",
                    message=f"clue '{clue_id}' suggested_tests must be a list",
                )
            )
        elif any((not isinstance(test, str)) or (not test) for test in entry["suggested_tests"]):
            issues.append(
                ClueCatalogIssue(
                    severity=SEVERITY_HIGH,
                    path=f"{clue_id}.suggested_tests",
                    message=f"clue '{clue_id}' suggested_tests must contain only non-empty strings",
                )
            )
    return issues


def check_diagnosis_integrity(
    catalog: dict,
    diagnosis_clues: dict[str, list[str]],
) -> list[ClueCatalogIssue]:
    issues: list[ClueCatalogIssue] = []
    for clue_id, paths in sorted(diagnosis_clues.items()):
        entry = catalog.get(clue_id)
        if entry is None:
            continue
        if not entry.get("diagnosis_allowed", False):
            issues.append(
                ClueCatalogIssue(
                    severity=SEVERITY_MEDIUM,
                    path=paths[0],
                    message=f"clue '{clue_id}' is referenced by diagnosis config but diagnosis_allowed is false in clue_catalog.json",
                )
            )
    return issues


def check_dual_owners(catalog: dict, exam_clues: dict[str, list[str]]) -> list[ClueCatalogIssue]:
    issues: list[ClueCatalogIssue] = []
    dual_owners = {
        "crackles",
        "arrhythmia",
        "pulsus_paradoxus",
        "icterus",
        "petechiae",
        "dehydration",
        "anuria",
    }
    for clue_id in sorted(dual_owners & set(catalog)):
        entry = catalog[clue_id]
        if entry.get("category") != "A_bedside_observational":
            issues.append(
                ClueCatalogIssue(
                    severity=SEVERITY_HIGH,
                    path=f"{clue_id}.category",
                    message=f"dual-owner clue '{clue_id}' must remain Category A_bedside_observational",
                )
            )
        if clue_id in exam_clues and not entry.get("exam_projection_only", False):
            issues.append(
                ClueCatalogIssue(
                    severity=SEVERITY_MEDIUM,
                    path=exam_clues[clue_id][0],
                    message=f"dual-owner clue '{clue_id}' still appears in exam templates without exam_projection_only marker",
                )
            )
    return issues


def check_modality_suffix(catalog: dict) -> list[ClueCatalogIssue]:
    issues: list[ClueCatalogIssue] = []
    allowed_suffixes = (
        "_xray",
        "_ct",
        "_us",
        "_usg",
        "_ecg",
        "_auscultation",
        "_inspection",
        "_endoscopy",
        "_blood_pressure",
    )
    for clue_id, entry in catalog.items():
        if clue_id.startswith("_"):
            continue
        if entry.get("category") != "C_exam_evidence":
            continue
        if not any(clue_id.endswith(suffix) for suffix in allowed_suffixes):
            issues.append(
                ClueCatalogIssue(
                    severity=SEVERITY_LOW,
                    path=clue_id,
                    message=f"Category C clue '{clue_id}' is missing a modality suffix",
                )
            )
    return issues


def validate_clue_catalog_consistency(
    catalog: dict,
    symptom_definitions: dict,
    exam_templates: dict,
    diseases: dict,
) -> list[ClueCatalogIssue]:
    symptom_clues = collect_symptom_clues(symptom_definitions)
    exam_clues = collect_exam_clue_ids(exam_templates)
    diagnosis_clues = collect_diagnosis_clues(diseases)

    issues: list[ClueCatalogIssue] = []
    issues.extend(check_registry_completeness(catalog, symptom_clues, exam_clues, diagnosis_clues))
    issues.extend(check_schema_integrity(catalog))
    issues.extend(check_diagnosis_integrity(catalog, diagnosis_clues))
    issues.extend(check_dual_owners(catalog, exam_clues))
    issues.extend(check_modality_suffix(catalog))
    return issues
