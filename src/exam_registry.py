"""
ExamRegistry — 检查类型注册表。

从 data/examinations.json 加载所有检查类型的元数据，替代 action_system.py 中的
_EXAM_CONFIG 硬编码字典。

使用方式：
    from src.exam_registry import get_exam_registry
    reg = get_exam_registry()
    ap_cost, tier, latency = reg.get_exam("blood_gas")  # (3, 3, 1)
    meta = reg.get_meta("blood_gas")   # 完整元数据 dict
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .logger_config import get_logger

logger = get_logger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_CONFIG_FILE = _DATA_DIR / "examinations.json"

_instance: Optional["ExamRegistry"] = None


class ExamRegistry:
    """检查类型注册表，从 JSON 加载，运行时只读。"""

    def __init__(self, raw: dict):
        self._exams: dict[str, dict] = {
            k: v for k, v in raw.items() if not k.startswith("_")
        }
        logger.info("ExamRegistry loaded: %d exam types", len(self._exams))

    def get_meta(self, test_type: str) -> Optional[dict]:
        """返回完整元数据 dict，不存在时返回 None。"""
        return self._exams.get(test_type)

    def get_exam(self, test_type: str) -> tuple[int, int, int]:
        """
        返回 (ap_cost, tier, latency_turns)。
        未知检查默认 (2, 2, 0)。
        """
        meta = self._exams.get(test_type)
        if meta is None:
            return (2, 2, 0)
        ap_cost = meta.get("cost", 0)
        tier = meta.get("tier", 2)
        latency = meta.get("latency_turns", 0)
        return (ap_cost, tier, latency)

    @property
    def exam_types(self) -> list[str]:
        """返回所有检查类型 ID 列表。"""
        return list(self._exams.keys())


def get_exam_registry(reload: bool = False) -> ExamRegistry:
    """获取全局单例 ExamRegistry。"""
    global _instance
    if _instance is None or reload:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _instance = ExamRegistry(raw)
    return _instance
