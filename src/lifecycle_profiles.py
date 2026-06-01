"""
Lifecycle Profiles — 物种特异性生命周期配置。

文献来源：
- 器官发育：Kawalek 1990 AJVR, Tavoloni 1985 Biol Neonate, Tanaka 1998 Xenobiotica
- GFR定量：Laroute 2005 Res Vet Sci, Hall 2016 J Nutr Health Aging, Bexfield 2008 JVIM
- 心脏参数：Chetboul 2025 Front Vet Sci, Bagardi 2025 J Vet Med Sci
- 免疫衰老：Holder 2017 PLoS ONE, Day 2010 J Comp Pathol, McKenzie 2025 JVIM
- EPO：Caiado 1986 犬肝脏灌注（PMID 3768502）
- 骨骼/性成熟：Geiger 2016 Zool Letters, Harvey 2021 Front Vet Sci
"""

from __future__ import annotations

import json
import math
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from lifecycle_curves import CurveType, maturation_curve, decline_curve

logger = logging.getLogger(__name__)


# ── 生命周期模式 ───────────────────────────────────────────────────────────


class LifecycleMode(Enum):
    """
    生命周期引擎接入模式。

    - BYPASS:  禁用生命周期（默认）。引擎使用内建成年基准值。
    - GROWTH:   从幼龄开始，跟踪发育过程（不施加衰退）。
    - SENESCENCE: 从成年开始，跟踪衰退过程（不显式发育期）。
    - FULL:     完整生命周期：发育 + 衰退。
    """

    BYPASS = "bypass"
    GROWTH = "growth"
    SENESCENCE = "senescence"
    FULL = "full"


# ── 生命阶段 ────────────────────────────────────────────────────────────────


class LifePhase(Enum):
    NEONATAL = "neonatal"      # 新生（<2周）
    JUVENILE = "juvenile"        # 幼年（2周~性成熟）
    ADULT = "adult"             # 成年（器官功能完全成熟）
    SENIOR = "senior"           # 老年（开始衰退）
    GERIATRIC = "geriatric"     # 高龄（严重衰退）
    DEAD = "dead"               # 死亡


# ── 配置数据结构 ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MaturationConfig:
    """发育曲线配置。"""

    curve: str               # "sigmoid" | "linear_saturate" | "sigmoid_three_phase" | "constant"
    # sigmoid
    k: float | None = None
    midpoint_days: float | None = None
    # linear_saturate
    max_days: float | None = None
    # sigmoid_three_phase
    k_rise: float | None = None
    k_fall: float | None = None
    peak_days: float | None = None
    peak_value: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> MaturationConfig:
        return cls(
            curve=d.get("curve", "constant"),
            k=d.get("k"),
            midpoint_days=d.get("midpoint_days"),
            max_days=d.get("max_days"),
            k_rise=d.get("k_rise"),
            k_fall=d.get("k_fall"),
            peak_days=d.get("peak_days"),
            peak_value=d.get("peak_value"),
        )

    def evaluate(self, age_days: float) -> float:
        return maturation_curve(
            self.curve,
            age_days,
            k=self.k or 0.0,
            midpoint_days=self.midpoint_days or 0.0,
            max_days=self.max_days or 0.0,
            k_rise=self.k_rise or 0.0,
            k_fall=self.k_fall or 0.0,
            peak_days=self.peak_days or 0.0,
            peak_value=self.peak_value or 1.0,
        )


@dataclass(frozen=True)
class DeclineConfig:
    """衰退曲线配置。"""

    curve: str               # "gompertz" | "linear" | "constant"
    # gompertz
    onset_days: float | None = None
    rate_per_day: float | None = None
    # size-dependent onset (覆盖 onset_days)
    onset_days_by_size: dict[str, float] | None = None
    # linear
    min_factor: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> DeclineConfig:
        return cls(
            curve=d.get("curve", "constant"),
            onset_days=d.get("onset_days"),
            rate_per_day=d.get("rate_per_day"),
            onset_days_by_size=d.get("onset_days_by_size"),
            min_factor=d.get("min_factor"),
        )

    def evaluate(self, age_days: float, size_category: str | None = None) -> float:
        # 优先使用 size-specific onset_days
        if self.onset_days_by_size and size_category:
            onset = self.onset_days_by_size.get(size_category, self.onset_days or 0.0)
        else:
            onset = self.onset_days or 0.0
        return decline_curve(
            self.curve,
            age_days,
            onset_days=onset,
            rate_per_day=self.rate_per_day or 0.0,
            min_factor=self.min_factor or 0.3,
        )


@dataclass(frozen=True)
class LifecycleOrganConfig:
    """单个器官的生命周期配置。"""

    maturation: MaturationConfig
    decline: DeclineConfig


@dataclass(frozen=True)
class LifecycleSpeciesProfile:
    """
    单个物种的完整生命周期配置。

    从 data/lifecycle_profiles.json 加载。
    """

    species: str                                   # "canine", "feline" 等
    size_category: str                             # "small" | "medium" | "large" | "giant"
    maturity_age_days: float                       # 器官功能完全成熟的年龄
    geriatric_age_days: float                     # 老年起始年龄（品种相关）
    geriatric_age_days_by_size: dict[str, float] = field(default_factory=dict)  # 品种大小相关

    # 器官配置：organ_name → LifecycleOrganConfig
    organs: dict[str, LifecycleOrganConfig] = field(default_factory=dict)

    # 特殊系统
    hematology: dict[str, Any] | None = None   # EPO source 切换等

    # 成年参考值（用于日志）
    adult_references: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, species: str, d: dict) -> LifecycleSpeciesProfile:
        organs = {}
        for name, od in d.get("organs", {}).items():
            organs[name] = LifecycleOrganConfig(
                maturation=MaturationConfig.from_dict(od.get("maturation", {})),
                decline=DeclineConfig.from_dict(od.get("decline", {})),
            )

        return cls(
            species=species,
            size_category=d.get("size_category", "medium"),
            maturity_age_days=d.get("maturity_age_days", 84.0),
            geriatric_age_days=d.get("geriatric_age_days", 2555.0),
            geriatric_age_days_by_size=d.get("geriatric_age_days_by_size", {}),
            organs=organs,
            hematology=d.get("hematology"),
            adult_references=d.get("adult_references", {}),
        )

    def get_organ_function(self, organ: str, age_days: float, size_category: str | None = None) -> float:
        """
        综合发育×衰退 = 当前器官功能因子（0~1）。

        1.0 = 完全功能（成年基准）
        <1.0 = 发育未完成 或 衰老衰退

        Args:
            organ: 器官名
            age_days: 年龄（天）
            size_category: 品种大小（small/medium/large/giant），用于 size-specific 衰退
        """
        cfg = self.organs.get(organ)
        if cfg is None:
            return 1.0  # 未配置的器官：默认完全功能

        size = size_category or self.size_category
        mat = cfg.maturation.evaluate(age_days)
        dec = cfg.decline.evaluate(age_days, size_category=size)
        return mat * dec


# ── 全局配置加载 ────────────────────────────────────────────────────────────


class LifecycleProfileLoader:
    """从 data/lifecycle_profiles.json 加载所有物种配置。"""

    _profiles: dict[str, LifecycleSpeciesProfile] = {}

    @classmethod
    def load(cls, data_dir: Path | str | None = None) -> dict[str, LifecycleSpeciesProfile]:
        if cls._profiles:
            return cls._profiles  # 缓存

        if data_dir is None:
            src_dir = Path(__file__).parent.parent
            data_dir = src_dir / "data"

        path = Path(data_dir) / "lifecycle_profiles.json"
        if not path.exists():
            logger.warning("lifecycle_profiles.json not found at %s", path)
            return {}

        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        for species, spec in raw.get("species", {}).items():
            cls._profiles[species] = LifecycleSpeciesProfile.from_dict(species, spec)

        logger.info("Loaded lifecycle profiles for %d species", len(cls._profiles))
        return cls._profiles

    @classmethod
    def get(cls, species: str) -> LifecycleSpeciesProfile | None:
        if not cls._profiles:
            cls.load()
        return cls._profiles.get(species.lower())
