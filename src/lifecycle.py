"""
Lifecycle Engine — 生物老化系统 (结果驱动版)
驱动生物体从出生到死亡的完整生命周期。
阶段由器官功能状态判断，死亡由器官功能跌破阈值触发。
"""

import logging
import math
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ── Lifecycle Phases ─────────────────────────────────────────────────────────

class LifecyclePhase(Enum):
    NEONATAL = "neonatal"
    JUVENILE = "juvenile"
    YOUNG_ADULT = "young_adult"
    MATURE = "mature"
    SENIOR = "senior"
    GERIATRIC = "geriatric"
    DEAD = "dead"


# ── Species Parameters ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LifecycleParams:
    species: str
    mature_age_days: float           # 功能达到成熟水平所需的日历年龄
    mature_growth_rate: float         # Logistic 生长率常数
    # Gompertz 衰退参数：rate = ln(2) / post_maturity_years_to_half
    # 使得 post_maturity 年后 organ_function = 0.3 (GERIATRIC threshold)
    decline_rate: float             # Gompertz 衰退率 (1/yr)
    # post_maturity 年后器官功能跌至此值（触发 GERIATRIC 和死亡判断）
    end_life_function: float


# Species-specific lifecycle parameters
# 衰退率差异自然产生不同物种寿命：
# - 犬: 衰退快(post_maturity 10yr → 0.3) → 短寿(~13yr)
# - 猫: 衰退中(post_maturity 14yr → 0.3) → 中寿(~17yr)
# - 马: 衰退慢(post_maturity 19yr → 0.3) → 长寿(~25yr)
_CANINE_PARAMS = LifecycleParams(
    species="canine",
    mature_age_days=1095,      # ~3 yr
    mature_growth_rate=1.5,
    # rate = ln(2) / 10 ≈ 0.0693，使10yr后 multiplier = 0.3
    decline_rate=0.0693,
    end_life_function=0.3,
)
_FELINE_PARAMS = LifecycleParams(
    species="feline",
    mature_age_days=1095,      # ~3 yr
    mature_growth_rate=1.5,
    # rate = ln(2) / 14 ≈ 0.0495，使14yr后 multiplier = 0.3
    decline_rate=0.0495,
    end_life_function=0.3,
)
_EQUINE_PARAMS = LifecycleParams(
    species="equine",
    mature_age_days=2190,      # ~6 yr（马成熟更慢）
    mature_growth_rate=0.8,
    # rate = ln(2) / 19 ≈ 0.0365，使19yr后 multiplier = 0.3
    decline_rate=0.0365,
    end_life_function=0.3,
)
_SPECIES_PARAMS: dict[str, LifecycleParams] = {
    "canine": _CANINE_PARAMS,
    "feline": _FELINE_PARAMS,
    "equine": _EQUINE_PARAMS,
}


# ── Lifecycle State ──────────────────────────────────────────────────────────

@dataclass
class LifecycleState:
    age_days: float = 0.0
    phase: LifecyclePhase = LifecyclePhase.NEONATAL
    organ_function: dict[str, float] = field(default_factory=lambda: {
        "heart": 0.1, "lung": 0.1, "kidney": 0.1, "liver": 0.1,
        "gut": 0.1, "blood": 0.1,
    })
    organ_reserve: dict[str, float] = field(default_factory=lambda: {
        "heart": 0.0, "lung": 0.0, "kidney": 0.0, "liver": 0.0,
        "gut": 0.0, "blood": 0.0,
    })
    death_cause: str | None = None


# ── Lifecycle Engine ─────────────────────────────────────────────────────────

class LifecycleEngine:
    """
    管理生物体从出生到死亡的生命周期。

    核心原则:
    - 生长/衰老由器官功能状态判断，非日历年龄
    - 死亡由器官功能跌破 end_life_function 阈值触发
    - Species 差异由 Gompertz 衰退率自然产生
    """

    # 器官 → (FactorCommand target, 模块属性名)
    _ORGAN_PARAMS: dict[str, list[tuple[str, str]]] = {
        "heart": [
            ("heart.contractility_factor", "contractility_factor"),
        ],
        "lung": [
            ("lung.diffusion_coefficient", "diffusion_coefficient"),
        ],
        "kidney": [
            ("kidney.GFR", "GFR"),
        ],
        "liver": [
            ("liver.metabolic_activity",  "metabolic_activity"),
            ("liver.detox_capacity",      "detox_capacity"),
            ("liver.cyp450_activity",     "cyp450_activity"),
        ],
        "gut": [
            ("gut.motility",              "gut_motility"),
            ("gut.barrier_integrity",     "barrier_integrity"),
            ("gut.microbiome_activity",   "microbiome_activity"),
        ],
        "blood": [
            ("blood.PLT", "PLT"),
        ],
    }

    def __init__(self, species: str = "canine", initial_age_days: float = 0.0):
        params = _SPECIES_PARAMS.get(species.lower(), _CANINE_PARAMS)
        object.__setattr__(self, "params", params)
        self.state = LifecycleState(age_days=initial_age_days)
        # 原始峰值基准值：首次 apply_age_factors() 时捕获
        self._original_baselines: dict[str, float] = {}
        # 初始化器官状态（根据出生时年龄设置正确的 function 值）
        self._sync_organ_function()

    def _sync_organ_function(self) -> None:
        """根据当前年龄同步化器官功能状态（在 __init__ 和 advance_time 时调用）。"""
        self._update_phase()
        for organ in self.state.organ_function:
            self.state.organ_function[organ] = round(self.organ_multiplier(organ), 6)
            self.state.organ_reserve[organ] = round(self.organ_reserve_pct(organ), 6)

    # ── Growth Factor ─────────────────────────────────────────────────────

    def growth_factor(self) -> float:
        """
        生长因子：出生时 ~0.1（10%成熟功能），成熟时 ~1.0。

        f(t) = min(1.0, 1 - (1-k) * exp(-r*t))
        k=0.1（出生时约10%成熟功能），r=生长率（物种特异性）

        当 t=0 时 f=k=0.1
        当 t→∞ 时 f→1.0
        """
        k = 0.1
        r = self.params.mature_growth_rate
        t = self.state.age_days / 365.0
        return min(1.0, 1.0 - (1.0 - k) * math.exp(-r * t))

    # ── Decline Factor (Gompertz-like) ───────────────────────────────────

    def _decline_multiplier(self) -> float:
        """
        Gompertz 衰退乘数：成熟后按指数衰减。

        multiplier = exp(-rate * elapsed_years)
        rate = ln(2) / post_maturity_years_to_half

        特点：初期衰退快（相对比例高），晚年衰退看似"变缓"（但 Gompertz
        死亡危险率其实一直在增加），最终 multiplier → 0 时触发死亡。

        对于犬（rate=0.0693）：
          3yr (mature): multiplier = 1.0
          8yr (5yr elapsed): multiplier = exp(-0.0693*5) ≈ 0.71
          13yr (10yr elapsed): multiplier = exp(-0.0693*10) = 0.50
          约20yr (17yr elapsed): multiplier = exp(-0.0693*17) ≈ 0.31 (死亡)
        """
        if self.state.age_days <= self.params.mature_age_days:
            return 1.0
        elapsed_years = (self.state.age_days - self.params.mature_age_days) / 365.0
        return math.exp(-self.params.decline_rate * elapsed_years)

    # ── Organ Multiplier ─────────────────────────────────────────────────

    def organ_multiplier(self, organ: str) -> float:
        """综合年龄因子 = 生长因子 × 衰退乘数。"""
        return self.growth_factor() * self._decline_multiplier()

    def organ_reserve_pct(self, organ: str) -> float:
        """器官储备 = 功能% - end_life_function（生存阈值）。"""
        return max(0.0, self.organ_multiplier(organ) - self.params.end_life_function)

    # ── Phase Determination (结果驱动) ─────────────────────────────────

    def _update_phase(self) -> None:
        """
        根据器官功能状态（growth_factor 和 _decline_multiplier）判断阶段。
        死亡判断独立于阶段之外，由 death_check() 处理。
        """
        gf = self.growth_factor()
        dm = self._decline_multiplier()

        if self.state.phase == LifecyclePhase.DEAD:
            return  # 保持 DEAD 状态不变

        # 按功能状态判断阶段：
        # - 若 gf >= 0.98 且尚未开始衰退(dm >= 0.98) → MATURE
        # - 若已衰退(dm < 0.98) → 按衰退程度判断 SENIOR/GERIATRIC
        # - 否则按生长因子判断 JUVENILE / NEONATAL / YOUNG_ADULT
        if gf >= 0.96 and dm >= 0.85:
            self.state.phase = LifecyclePhase.MATURE
        elif dm < 0.6:
            # GERIATRIC: dm < 0.6 ≈ ~9yr post-mature for canine (~12yr total)
            # 死亡阈值(end_life_function=0.3)更低，GERIATRIC 先于死亡
            self.state.phase = LifecyclePhase.GERIATRIC
        elif dm < 0.85:
            # SENIOR: 衰退已经开始，但尚未进入 GERIATRIC
            self.state.phase = LifecyclePhase.SENIOR
        elif gf >= 0.8:
            self.state.phase = LifecyclePhase.YOUNG_ADULT
        elif gf >= 0.5:
            self.state.phase = LifecyclePhase.JUVENILE
        else:
            self.state.phase = LifecyclePhase.NEONATAL

    # ── Time Advance ────────────────────────────────────────────────────

    def advance_time(self, delta_days: float) -> None:
        """游戏动作后推进年龄，同步更新器官功能状态。"""
        self.state.age_days += delta_days
        self._sync_organ_function()

    # ── Apply Age Factors ────────────────────────────────────────────────

    def apply_age_factors(self, creature) -> None:
        """
        Pre-step 钩子：通过 FactorCommand 将年龄缩放因子应用到引擎参数。

        首次调用时捕获各参数的原始峰值基准值，
        后续调用设置: original_baseline × organ_multiplier(organ)。
        """
        # Import here to avoid circular dependency
        from simulation import _PARAM_PATHS, FactorCommand

        for organ, params in self._ORGAN_PARAMS.items():
            mult = self.organ_multiplier(organ)
            for target, attr_name in params:
                key = f"{organ}.{attr_name}"
                if key not in self._original_baselines:
                    path = _PARAM_PATHS.get(target)
                    if path is None:
                        logger.warning(
                            "Lifecycle: target '%s' not in _PARAM_PATHS", target
                        )
                        continue
                    module_name, _ = path
                    self._original_baselines[key] = getattr(
                        getattr(creature, module_name), attr_name
                    )
                    logger.debug(
                        "Lifecycle captured baseline %s = %.4f", key,
                        self._original_baselines[key]
                    )

                original = self._original_baselines[key]
                cmd = FactorCommand(target=target, op="set", value=original * mult)
                creature.apply_factor(cmd)

    # ── Death Check (结果驱动) ─────────────────────────────────────────

    def is_dead(self) -> bool:
        return self.state.phase == LifecyclePhase.DEAD

    def death_check(self) -> str | None:
        """
        检查是否死亡：_decline_multiplier < end_life_function 时触发。
        不依赖硬编码寿命。
        """
        if self._decline_multiplier() < self.params.end_life_function:
            self.state.phase = LifecyclePhase.DEAD
            # 找到衰退最快的器官作为死因
            slowest_organ = min(
                self.state.organ_function, key=self.state.organ_function.get
            )
            self.state.death_cause = f"{slowest_organ}_senescence"
            return self.state.death_cause
        return None

    # ── Serialization ─────────────────────────────────────────────────

    def serialize(self) -> dict:
        """持久化到快照。"""
        return {
            "age_days": round(self.state.age_days, 4),
            "phase": self.state.phase.value,
            "species": self.params.species,
            "organ_function": {k: round(v, 4) for k, v in self.state.organ_function.items()},
            "organ_reserve": {k: round(v, 4) for k, v in self.state.organ_reserve.items()},
            "death_cause": self.state.death_cause,
            "_original_baselines": {k: round(v, 6) for k, v in self._original_baselines.items()},
        }

    @classmethod
    def deserialize(cls, data: dict) -> "LifecycleEngine":
        """从快照恢复。"""
        engine = cls(species=data["species"], initial_age_days=data["age_days"])
        engine.state.phase = LifecyclePhase(data["phase"])
        engine.state.organ_function = data["organ_function"]
        engine.state.organ_reserve = data["organ_reserve"]
        engine.state.death_cause = data.get("death_cause")
        engine._original_baselines = data.get("_original_baselines", {})
        return engine
