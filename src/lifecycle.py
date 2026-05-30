"""
Lifecycle 模块 — 双轨架构：
  旧实现（向后兼容）：LifecycleEngine 类提供旧 API（growth_factor/decline_multiplier/apply_age_factors）
  新架构（插件化）：LifecycleSpeciesProfile + LifecycleMode（lifecycle_profiles.py）

文献来源：
  器官发育：Kawalek 1990 AJVR, Tavoloni 1985 Biol Neonate, Tanaka 1998 Xenobiotica
  GFR 定量：Laroute 2005 Res Vet Sci, Hall 2016 J Nutr Health Aging
  心脏参数：Chetboul 2025 Front Vet Sci, Bagardi 2025 J Vet Med Sci
  免疫衰老：Holder 2017 PLoS ONE, Day 2010 J Comp Pathol, McKenzie 2025 JVIM
  EPO 肝脏→肾脏：Caiado 1986 犬肝脏灌注实验（PMID 3768502）
  骨骼/行为成熟：Geiger 2016 Zool Letters, Harvey 2021 Front Vet Sci
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING

# 新架构
from lifecycle_curves import CurveType, maturation_curve, decline_curve
from lifecycle_profiles import (
    LifecycleMode,
    LifePhase,
    LifecycleOrganConfig,
    LifecycleSpeciesProfile,
    LifecycleProfileLoader,
)

if TYPE_CHECKING:
    from simulation import FactorCommand, VirtualCreature

logger = logging.getLogger(__name__)

__all__ = [
    "LifecycleEngine",
    "LifecyclePhase",
    "LifecycleMode",
    "LifePhase",
    "LifecycleSpeciesProfile",
    "LifecycleProfileLoader",
    "lifecycle_curves",
    "lifecycle_profiles",
]


# ── LifecyclePhase（旧名，向后兼容）────────────────────────────────────

class LifecyclePhase(Enum):
    NEONATAL = "neonatal"
    JUVENILE = "juvenile"
    YOUNG_ADULT = "young_adult"
    MATURE = "mature"
    SENIOR = "senior"
    GERIATRIC = "geriatric"
    DEAD = "dead"


# ── LifecycleParams（旧结构，保留向后兼容）────────────────────────────────────

@dataclass(frozen=True)
class LifecycleParams:
    """旧参数结构。向后兼容用。"""
    species: str
    mature_age_days: float
    mature_growth_rate: float
    decline_rate: float
    end_life_function: float


_CANINE_PARAMS = LifecycleParams(
    species="canine",
    mature_age_days=1095.0,
    mature_growth_rate=1.5,
    decline_rate=0.0693,
    end_life_function=0.3,
)
_FELINE_PARAMS = LifecycleParams(
    species="feline",
    mature_age_days=1095.0,
    mature_growth_rate=1.5,
    decline_rate=0.0495,
    end_life_function=0.3,
)
_EQUINE_PARAMS = LifecycleParams(
    species="equine",
    mature_age_days=2190.0,
    mature_growth_rate=0.8,
    decline_rate=0.0365,
    end_life_function=0.3,
)
_SPECIES_PARAMS = {
    "canine": _CANINE_PARAMS,
    "feline": _FELINE_PARAMS,
    "equine": _EQUINE_PARAMS,
}


# ── 内部状态（兼容旧 LifecycleState）──────────────────────────────────

@dataclass
class _LifecycleState:
    age_days: float
    phase: LifecyclePhase | LifePhase  # 旧轨用 LifecyclePhase，新轨用 LifePhase
    organ_function: dict[str, float]
    organ_reserve: dict[str, float]
    death_cause: str | None = None


# ── LifecycleEngine（双轨实现）────────────────────────────────────────

class LifecycleEngine:
    """
    双轨生命周期引擎。

    旧轨（BYPASS/默认）：
      - 使用旧 growth_factor/decline_multiplier 实现（向后兼容）
      - 所有旧测试通过
      - 零开销

    新轨（GROWTH/SENESCENCE/FULL）：
      - 使用 LifecycleSpeciesProfile（可配置发育/衰退曲线）
      - 支持幼年/老年仿真
      - 品种大小差异（小型犬 vs 大型犬衰老速率）
    """

    # 旧 _ORGAN_PARAMS（向后兼容用，不含 contractility_factor）
    _ORGAN_PARAMS = {
        "heart": [],
        "lung": [("lung.diffusion_coefficient", "diffusion_coefficient")],
        "kidney": [("kidney.GFR", "GFR")],
        "liver": [
            ("liver.metabolic_activity", "metabolic_activity"),
            ("liver.detox_capacity", "detox_capacity"),
            ("liver.cyp450_activity", "cyp450_activity"),
        ],
        "gut": [
            ("gut.gut_motility", "gut_motility"),
            ("gut.barrier_integrity", "barrier_integrity"),
            ("gut.microbiome_activity", "microbiome_activity"),
        ],
        "blood": [("blood.PLT", "PLT")],
    }

    def __init__(
        self,
        species: str = "canine",
        initial_age_days: float = 0.0,
        mode: LifecycleMode = LifecycleMode.BYPASS,
        profile: LifecycleSpeciesProfile | None = None,
        size_category: str = "medium",
    ):
        self.mode = mode
        self.species = species

        if mode == LifecycleMode.BYPASS:
            # 旧轨：使用旧的 growth/decline 逻辑（向后兼容）
            self._params = _SPECIES_PARAMS.get(species.lower(), _CANINE_PARAMS)
            self.params = self._params  # 向后兼容：旧测试访问 eng.params.species
            self._profile = None  # 新轨不使用
            self._state = _LifecycleState(
                age_days=initial_age_days,
                phase=LifecyclePhase.NEONATAL,
                organ_function={k: 0.1 for k in self._ORGAN_PARAMS},
                organ_reserve={k: 0.0 for k in self._ORGAN_PARAMS},
            )
            self._original_baselines: dict[str, float] = {}
            self._sync_organ_function()
            return

        # 新轨：使用 LifecycleSpeciesProfile
        self._profile = profile or LifecycleProfileLoader.get(species)
        self._geriatric_days = (
            self._profile.geriatric_age_days_by_size.get(size_category, 2555.0)
            if self._profile else 2555.0
        )
        self._state = _LifecycleState(
            age_days=initial_age_days,
            phase=LifePhase.NEONATAL,
            organ_function={},
            organ_reserve={},
        )
        self._original_baselines: dict[str, float] = {}
        self._update_phase_new()

    # ── 旧 API（向后兼容）─────────────────────────────────────────

    @property
    def state(self) -> _LifecycleState:
        """旧接口：兼容 state 属性访问。"""
        return self._state

    def growth_factor(self) -> float:
        """旧接口：返回生长因子（0.1~1.0）。"""
        if self.mode != LifecycleMode.BYPASS:
            return 1.0  # 新轨不暴露此方法
        k = 0.1
        r = self._params.mature_growth_rate
        t = self._state.age_days / 365.0
        return min(1.0, 1.0 - (1.0 - k) * math.exp(-r * t))

    def _decline_multiplier(self) -> float:
        """旧接口：返回 Gompertz 衰退乘数。"""
        if self.mode != LifecycleMode.BYPASS:
            return 1.0
        if self._state.age_days <= self._params.mature_age_days:
            return 1.0
        elapsed_years = (self._state.age_days - self._params.mature_age_days) / 365.0
        return math.exp(-self._params.decline_rate * elapsed_years)

    def organ_multiplier(self, organ: str) -> float:
        """旧接口：综合生长×衰退。"""
        if self.mode != LifecycleMode.BYPASS:
            return 1.0
        return self.growth_factor() * self._decline_multiplier()

    def organ_reserve_pct(self, organ: str) -> float:
        """旧接口：器官储备 = multiplier - end_life_threshold。"""
        if self.mode != LifecycleMode.BYPASS:
            return max(0.0, 1.0 - self._params.end_life_function)
        return max(0.0, self.organ_multiplier(organ) - self._params.end_life_function)

    def is_dead(self) -> bool:
        return self._state.phase == LifecyclePhase.DEAD

    def death_check(self) -> str | None:
        """旧接口：死亡检测。"""
        if self.mode != LifecycleMode.BYPASS:
            return None
        if self._decline_multiplier() < self._params.end_life_function:
            self._state.phase = LifecyclePhase.DEAD
            # 找最慢器官
            slowest = min(
                self._state.organ_function,
                key=self._state.organ_function.get,
            )
            self._state.death_cause = f"{slowest}_senescence"
            return self._state.death_cause
        return None

    def advance_time(self, delta_days: float) -> None:
        if self.mode == LifecycleMode.BYPASS:
            self._state.age_days += delta_days
            self._sync_organ_function()
        else:
            self._state.age_days += delta_days
            self._update_phase_new()

    def _sync_organ_function(self) -> None:
        """旧：同步器官状态。"""
        self._update_phase_old()
        for organ in self._state.organ_function:
            self._state.organ_function[organ] = round(self.organ_multiplier(organ), 6)
            self._state.organ_reserve[organ] = round(self.organ_reserve_pct(organ), 6)

    def _update_phase_old(self) -> None:
        """旧：基于 Gompertz 计算阶段。"""
        gf = self.growth_factor()
        dm = self._decline_multiplier()
        p = self._state.phase
        if p == LifecyclePhase.DEAD:
            return
        if gf >= 0.96 and dm >= 0.85:
            self._state.phase = LifecyclePhase.MATURE
        elif dm < 0.6:
            self._state.phase = LifecyclePhase.GERIATRIC
        elif dm < 0.85:
            self._state.phase = LifecyclePhase.SENIOR
        elif gf >= 0.8:
            self._state.phase = LifecyclePhase.YOUNG_ADULT
        elif gf >= 0.5:
            self._state.phase = LifecyclePhase.JUVENILE
        else:
            self._state.phase = LifecyclePhase.NEONATAL

    def capture_baselines(self, creature) -> None:
        """新接口：在引擎初始化后捕获器官基准值。"""
        from simulation import _PARAM_PATHS, FactorCommand
        for organ, params in self._ORGAN_PARAMS.items():
            for target, attr_name in params:
                key = f"{organ}.{attr_name}"
                if key in self._original_baselines:
                    continue
                path = _PARAM_PATHS.get(target)
                if path is None:
                    logger.debug("Lifecycle: %s not in _PARAM_PATHS", target)
                    continue
                mod_name, _ = path
                self._original_baselines[key] = getattr(
                    getattr(creature, mod_name), attr_name
                )
                logger.debug("captured %s = %.4f", key, self._original_baselines[key])

    def apply_age_factors(self, creature) -> None:
        """新接口：应用生命阶段因子到引擎（在 tox/pharma/coupling 之前调用）。"""
        from simulation import _PARAM_PATHS, FactorCommand
        if self.mode == LifecycleMode.BYPASS:
            for organ, params in self._ORGAN_PARAMS.items():
                mult = self.organ_multiplier(organ)
                for target, attr_name in params:
                    key = f"{organ}.{attr_name}"
                    if key not in self._original_baselines:
                        continue
                    original = self._original_baselines[key]
                    setattr(getattr(creature, organ), attr_name, original * mult)
        else:
            # 新轨：使用 profile 曲线
            self.apply(creature)

    def apply(self, creature) -> None:
        """新轨：将 profile 配置的发育/衰退因子应用到引擎。"""
        if self._profile is None:
            return
        for organ, cfg in self._profile.organs.items():
            mat = cfg.maturation.evaluate(self._state.age_days)
            dec = cfg.decline.evaluate(self._state.age_days)
            factor = mat * dec
            TARGETS = {
                "kidney": "GFR",
                "liver": "metabolic_activity",
            }
            attr = TARGETS.get(organ)
            if not attr:
                continue
            if not hasattr(creature, organ):
                continue
            mod = getattr(creature, organ)
            if not hasattr(mod, attr):
                continue
            baseline = getattr(mod, attr)
            setattr(mod, attr, baseline * factor)

    # ── 新轨内部方法 ──────────────────────────────────────────

    def _update_phase_new(self) -> None:
        """新轨：根据 profile 更新阶段。"""
        if self._profile is None:
            self._state.phase = LifePhase.ADULT
            return
        age = self._state.age_days
        if age < 14:
            self._state.phase = LifePhase.NEONATAL
        elif age < 60:
            self._state.phase = LifePhase.JUVENILE
        elif age < self._geriatric_days:
            self._state.phase = LifePhase.ADULT
        elif age < self._geriatric_days * 1.3:
            self._state.phase = LifePhase.SENIOR
        else:
            self._state.phase = LifePhase.GERIATRIC

    # ── 序列化（向后兼容）─────────────────────────────────

    def serialize(self) -> dict:
        return {
            "age_days": round(self._state.age_days, 4),
            "phase": self._state.phase.value,
            "species": self.species,
            "mode": self.mode.value,
            "organ_function": {k: round(v, 4) for k, v in self._state.organ_function.items()},
            "organ_reserve": {k: round(v, 4) for k, v in self._state.organ_reserve.items()},
            "death_cause": self._state.death_cause,
            "_original_baselines": {k: round(v, 6) for k, v in self._original_baselines.items()},
        }

    @classmethod
    def deserialize(cls, data: dict) -> "LifecycleEngine":
        mode = LifecycleMode(data.get("mode", "bypass"))
        profile = LifecycleProfileLoader.get(data.get("species", "canine"))
        inst = cls(
            species=data.get("species", "canine"),
            initial_age_days=data.get("age_days", 0.0),
            mode=mode,
            profile=profile,
        )
        inst._state.age_days = data.get("age_days", 0.0)
        # 根据模式选择正确的枚举
        phase_str = data.get("phase", "mature" if mode == LifecycleMode.BYPASS else "adult")
        if mode == LifecycleMode.BYPASS:
            inst._state.phase = LifecyclePhase(phase_str)
        else:
            inst._state.phase = LifePhase(phase_str)
        inst._state.organ_function = data.get("organ_function", {})
        inst._state.organ_reserve = data.get("organ_reserve", {})
        inst._state.death_cause = data.get("death_cause")
        inst._original_baselines = data.get("_original_baselines", {})
        return inst
