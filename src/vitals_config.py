"""
VitalsConfig — 生理参数配置加载器。

从 data/vitals_ranges.json 加载所有生理参数的参考范围、危急值和线索标志映射，
替代 test_translator.py 中的 NORMAL_RANGES / CRITICAL_THRESHOLDS / clue_map 硬编码字典。

使用方式：
    from src.vitals_config import get_vitals_config
    vc = get_vitals_config()
    lo, hi = vc.get_normal("HR")          # (60, 120)
    unit = vc.get_unit("HR")              # "bpm"
    crit_lo, crit_hi = vc.get_critical("HR")  # (40, 180)
    flag = vc.get_clue_id("HR", "high")   # "hr_high"
    flag = vc.classify("HR", 150)         # "high"
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .logger_config import get_logger

logger = get_logger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_CONFIG_FILE = _DATA_DIR / "vitals_ranges.json"

_instance: Optional["VitalsConfig"] = None


class VitalsConfig:
    """生理参数配置，从 JSON 加载，运行时只读。"""

    def __init__(self, raw: dict):
        # 过滤掉注释键
        self._params: dict[str, dict] = {
            k: v for k, v in raw.items() if not k.startswith("_")
        }
        # 预生成 clue_map: (param, flag) -> clue_id
        self._clue_map: dict[tuple[str, str], str] = {}
        for param, conf in self._params.items():
            for flag, clue_id in conf.get("clue_flags", {}).items():
                self._clue_map[(param, flag)] = clue_id
        logger.info("VitalsConfig loaded: %d params", len(self._params))

    # ── 查询接口 ──

    def get_normal(self, param: str) -> tuple[float, float]:
        """返回 (lo, hi) 正常范围。"""
        return tuple(self._params[param]["normal"])  # type: ignore

    def get_unit(self, param: str) -> str:
        """返回单位字符串。"""
        return self._params[param]["unit"]

    def get_critical(self, param: str) -> Optional[tuple[float, float]]:
        """返回 (lo, hi) 危急值，无危急值定义时返回 None。"""
        crit = self._params[param].get("critical")
        return tuple(crit) if crit is not None else None

    def get_clue_id(self, param: str, flag: str) -> Optional[str]:
        """根据参数名和 flag 返回线索 ID，无映射时返回 None。"""
        return self._clue_map.get((param, flag))

    def classify(self, param: str, value: float) -> str:
        """
        根据正常范围和危急值返回分类: "normal" / "low" / "high" / "critical"
        与 test_translator._flag() 逻辑完全一致。
        """
        lo, hi = self.get_normal(param)
        if value < lo:
            direction = "low"
        elif value > hi:
            direction = "high"
        else:
            return "normal"
        crit = self.get_critical(param)
        if crit is not None:
            crit_lo, crit_hi = crit
            if value < crit_lo or value > crit_hi:
                return "critical"
        return direction

    @property
    def params(self) -> list[str]:
        """返回所有参数名列表。"""
        return list(self._params.keys())


def get_vitals_config(reload: bool = False) -> VitalsConfig:
    """获取全局单例 VitalsConfig。"""
    global _instance
    if _instance is None or reload:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _instance = VitalsConfig(raw)
    return _instance
