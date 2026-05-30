"""
Diagnosis Engine — 线索匹配 + 置信度计算。

职责:
  - 从检查报告中提取线索 ID
  - 按线索匹配疾病，计算置信度
  - 维护鉴别诊断列表，建议下一步检查
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── 从 data/diseases.json 加载疾病数据 ──
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
with open(os.path.join(_DATA_DIR, "diseases.json"), encoding="utf-8") as _f:
    _DISEASE_DATA: dict = json.load(_f)

_DISEASE_CLUES: dict[str, list[str]] = _DISEASE_DATA["clues"]
CLUE_DESCRIPTIONS: dict[str, str] = _DISEASE_DATA["clue_descriptions"]
_CLUE_TO_TEST: dict[str, str] = _DISEASE_DATA["clue_to_test"]

# ── 从 data/disease_references.json 加载文献引用 ──
_REF_PATH = os.path.join(_DATA_DIR, "disease_references.json")
if os.path.exists(_REF_PATH):
    with open(_REF_PATH, encoding="utf-8") as _f:
        _DISEASE_REFERENCES: dict[str, dict] = json.load(_f)
else:
    _DISEASE_REFERENCES: dict[str, dict] = {}
    logger.warning("disease_references.json not found, references disabled")


def _extract_clues_from_report(report: dict) -> list[str]:
    """
    从一份检查报告中提取线索 ID 列表。

    从报告的 tags 字段读取结构化线索（report_engine 生成报告时已填充）。
    """
    return list(report.get("tags", []))


def extract_clues(reports: list[dict]) -> list[str]:
    """
    从多份检查报告中提取所有线索 ID（去重）。

    Args:
        reports: translate() 返回的检查报告列表

    Returns:
        去重后的线索 ID 列表
    """
    all_clues: list[str] = []
    for report in reports:
        all_clues.extend(_extract_clues_from_report(report))
    # 去重保序
    seen = set()
    unique = []
    for c in all_clues:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def match_diseases(reports: list[dict], known_clues: list[str] = None) -> list[dict]:
    """
    根据已有检查报告匹配可能的疾病，计算置信度。

    Args:
        reports: translate() 返回的检查报告列表
        known_clues: 已发现的线索 ID 列表（为 None 时自动从 reports 提取）

    Returns:
        按 confidence 降序排列的匹配结果列表:
        [
            {
                "disease": "pneumonia",
                "confidence": 0.75,
                "matched_clues": ["PaO2_low", "crackles", ...],
                "missed_clues": ["PaCO2_high", ...],
                "matched_count": 6,
                "total_clues": 8,
            },
            ...
        ]
    """
    if known_clues is None:
        known_clues = extract_clues(reports)

    matches = []
    for disease_name, disease_clues in _DISEASE_CLUES.items():
        matched = [c for c in disease_clues if c in known_clues]
        missed = [c for c in disease_clues if c not in known_clues]
        total = len(disease_clues)
        confidence = len(matched) / total if total > 0 else 0.0

        matches.append({
            "disease": disease_name,
            "confidence": round(confidence, 4),
            "matched_clues": matched,
            "missed_clues": missed,
            "matched_count": len(matched),
            "total_clues": total,
        })

    matches.sort(key=lambda m: m["confidence"], reverse=True)
    return matches


def get_diagnosis_summary(matches: list[dict], top_n: int = 3) -> str:
    """
    返回诊断摘要文字（给 UI 显示）。

    Args:
        matches: match_diseases() 的返回值
        top_n: 显示前 N 个候选疾病

    Returns:
        多行字符串，每行一个候选疾病及其置信度
    """
    if not matches:
        return "暂无诊断线索，请先进行检查。"

    lines = []
    for m in matches[:top_n]:
        pct = m["confidence"] * 100
        lines.append(f"  {m['disease']}: {pct:.0f}%（{m['matched_count']}/{m['total_clues']}）")
    return "\n".join(lines)


def get_suggested_tests(matches: list[dict]) -> list[str]:
    """
    根据未匹配的线索，建议下一步检查类型。

    在 top 2 疾病中，找它们有但还没查出来的线索，
    映射到对应的检查类型。

    Args:
        matches: match_diseases() 的返回值

    Returns:
        建议的检查类型列表（去重）
    """
    suggested = []
    seen_tests = set()

    for m in matches[:2]:
        for clue in m.get("missed_clues", []):
            test = _CLUE_TO_TEST.get(clue)
            if test and test not in seen_tests:
                seen_tests.add(test)
                suggested.append(test)

    return suggested


def get_clue_description(clue_id: str) -> str:
    """
    返回线索 ID 的人类可读描述。

    Args:
        clue_id: 线索 ID

    Returns:
        中文描述，未找到时返回 clue_id 本身
    """
    return CLUE_DESCRIPTIONS.get(clue_id, clue_id)


def register_disease_clues(disease_name: str, clues: list[str]) -> None:
    """
    注册新疾病的线索定义（供扩展模块调用）。

    Args:
        disease_name: 疾病名称
        clues: 线索 ID 列表
    """
    _DISEASE_CLUES[disease_name] = clues
    logger.info("注册疾病线索: %s → %d 条", disease_name, len(clues))


def get_disease_references(disease_name: str) -> dict | None:
    """
    返回指定疾病的文献引用数据。

    Args:
        disease_name: 疾病名称 (如 "pneumonia", "acute_renal_failure")

    Returns:
        引用数据字典，包含 guidelines, criteria, mechanism 等
    """
    return _DISEASE_REFERENCES.get(disease_name)


def get_disease_references_with_clues(disease_name: str, matched_clues: list[str]) -> dict:
    """
    返回疾病的引用数据，仅包含已匹配线索的诊断依据。

    Args:
        disease_name: 疾病名称
        matched_clues: 已匹配的线索 ID 列表

    Returns:
        包含 guidelines 和 matched_criteria 的字典
    """
    ref = _DISEASE_REFERENCES.get(disease_name)
    if not ref:
        return {"guidelines": [], "matched_criteria": {}}

    # 只返回已匹配线索的引用
    all_criteria = ref.get("criteria", {})
    matched_criteria = {
        clue: all_criteria[clue]
        for clue in matched_clues
        if clue in all_criteria
    }

    return {
        "guidelines": ref.get("guidelines", []),
        "matched_criteria": matched_criteria,
    }
