"""
Pharmacology Module — PK/PD drug simulation.

One-compartment PK model:
    C(t) = Dose × e^(-k×t),  k = ln(2) / t_half

Hill equation PD model:
    E = Emax × C^n / (EC50^n + C^n)

Each drug subclass defines its own Emax, EC50, Hill coefficient,
and which ODE parameter(s) it modulates.
"""

from __future__ import annotations

import math
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.simulation import VirtualCreature
    from src.common_types import FactorCommand

logger = logging.getLogger(__name__)


class Drug:
    """
    One-compartment PK + Hill PD drug model.

    Attributes:
        name: Drug identifier.
        half_life: Elimination half-life in seconds.
        k: Elimination rate constant (ln(2)/t_half).
        concentration: Current normalised blood concentration.
        emax: Maximum pharmacodynamic effect.
        ec50: Concentration for 50% of Emax.
        hill: Hill coefficient (sigmoid steepness).
    """

    def __init__(
        self,
        name: str,
        half_life_s: float,
        emax: float = 1.0,
        ec50: float = 1.0,
        hill: float = 1.0,
    ):
        self.name = name
        self.half_life = half_life_s
        self.k = math.log(2) / half_life_s
        self.concentration = 0.0
        self.emax = emax
        self.ec50 = ec50
        self.hill = hill
        self._administered = False

    def administer(self, dose_mg_kg: float) -> None:
        """IV bolus: instant concentration increase proportional to dose."""
        self.concentration += dose_mg_kg
        self._administered = True
        logger.debug(
            "Drug administered: %s dose=%.2f mg/kg C=%.3f",
            self.name,
            dose_mg_kg,
            self.concentration,
        )

    def compute(self, dt: float) -> float:
        """
        Advance PK by dt seconds (first-order elimination).

        Returns:
            Current concentration after decay.
        """
        if self._administered:
            self.concentration *= math.exp(-self.k * dt)
            self.concentration = max(0.0, self.concentration)
        return self.concentration

    def pd_effect(self) -> float:
        """
        Hill equation: convert concentration → effect magnitude.

        Returns:
            Effect in [0, Emax].
        """
        c = self.concentration
        if c <= 0.0:
            return 0.0
        return self.emax * (c**self.hill) / (self.ec50**self.hill + c**self.hill)

    def factor_commands(self, pd_effect: float) -> list[FactorCommand]:
        """
        Convert PD effect into a list of FactorCommand instructions.

        Subclasses override this to declare which engine parameters they modify.
        Default: no effects (returns empty list).

        Args:
            pd_effect: Current PD effect magnitude from pd_effect().

        Returns:
            list[FactorCommand] instructions for the engine to apply.
        """
        return []


class Pimobendan(Drug):
    """
    PDE-III inhibitor → positive inotropy + vasodilation.
    Half-life in dogs ≈ 2 hours.
    """

    def __init__(self):
        super().__init__(
            name="pimobendan",
            half_life_s=7200.0,
            emax=0.4,  # ↑ contractility by up to 40%
            ec50=0.15,  # EC50 ≈ 0.15 mg/kg
            hill=1.5,
        )

    def factor_commands(self, pd_effect: float) -> list[FactorCommand]:
        """Pimobendan: multiply contractility_factor by (1 + pd)."""
        from src.common_types import FactorCommand
        if pd_effect <= 0.0:
            return []
        return [
            FactorCommand(target="heart.contractility_factor", op="multiply",
                          value=round(1.0 + pd_effect, 4)),
        ]


class Furosemide(Drug):
    """
    Loop diuretic → blocks Na-K-2Cl cotransporter.
    Half-life in dogs ≈ 1.5 hours.
    """

    def __init__(self):
        super().__init__(
            name="furosemide",
            half_life_s=5400.0,
            emax=5.0,  # ↑ urine output multiplier (baseline × (1 + effect))
            ec50=0.5,
            hill=1.2,
        )

    def factor_commands(self, pd_effect: float) -> list[FactorCommand]:
        """Furosemide: multiply urine_output by (1 + pd)."""
        from src.common_types import FactorCommand
        if pd_effect <= 0.0:
            return []
        return [
            FactorCommand(target="kidney.urine_output", op="multiply",
                          value=round(1.0 + pd_effect, 4)),
        ]


class Epinephrine(Drug):
    """
    α/β adrenergic agonist → ↑ SVR + ↑ HR + ↑ contractility.
    Very short half-life (IV bolus, rapid metabolism).
    """

    def __init__(self):
        super().__init__(
            name="epinephrine",
            half_life_s=120.0,  # ~2 min
            emax=1.5,  # ↑ SVR up to 1.5×
            ec50=0.01,
            hill=2.0,
        )

    def factor_commands(self, pd_effect: float) -> list[FactorCommand]:
        """Epinephrine: multiply SVR and heart_rate."""
        from src.common_types import FactorCommand
        if pd_effect <= 0.0:
            return []
        return [
            FactorCommand(target="heart.SVR", op="multiply",
                          value=round(1.0 + pd_effect, 4)),
            FactorCommand(target="heart.heart_rate", op="multiply",
                          value=round(1.0 + 0.3 * pd_effect, 4)),
        ]


class FluidBolus(Drug):
    """
    Crystalloid fluid bolus → direct blood volume increase.
    Not a drug per se, but modelled as instant PK (no decay during step)
    with volume distributed into the vascular compartment.
    """

    def __init__(self):
        super().__init__(
            name="fluid_bolus",
            half_life_s=1e9,  # effectively no PK decay within simulation window
            emax=1.0,
            ec50=1.0,
            hill=1.0,
        )

    def administer(self, volume_ml: float) -> None:
        """Override: dose = volume in mL, stored directly as concentration proxy."""
        self.concentration += volume_ml
        self._administered = True

    def factor_commands(self, pd_effect: float) -> list[FactorCommand]:
        """Fluid bolus: add volume to blood_volume (set concentration as add amount)."""
        from src.common_types import FactorCommand
        if self.concentration > 0:
            return [
                FactorCommand(target="heart.blood_volume", op="add",
                              value=round(self.concentration, 2)),
            ]
        return []


class AmoxicillinClavulanate(Drug):
    """
    广谱抗生素（阿莫西林克拉维酸钾）→ 增强免疫清除细菌能力。

    犬口服半衰期 ≈ 1-2 小时，取 1.5 小时。
    PD 效果：增强免疫清除率（通过 immune.antibiotic_effect FactorCommand）。

    临床用途：犬细菌性肺炎首选抗生素（Nelson & Couto 5e Ch12）。
    剂量：12.5-25 mg/kg PO q12h，取 12.5 mg/kg。
    """

    def __init__(self):
        super().__init__(
            name="amoxicillin_clavulanate",
            half_life_s=5400.0,  # 1.5 小时
            emax=0.8,  # 最多增强 80% 免疫清除
            ec50=0.1,  # EC50 ≈ 0.1 mg/kg
            hill=1.5,
        )

    def factor_commands(self, pd_effect: float) -> list[FactorCommand]:
        """抗生素：设置 immune.antibiotic_effect。"""
        from src.common_types import FactorCommand
        if pd_effect <= 0.0:
            return []
        return [
            FactorCommand(target="immune.antibiotic_effect", op="set",
                          value=round(pd_effect, 4)),
        ]


# ── Drug Registry ────────────────────────────────────────────────────────────

_DRUG_REGISTRY: dict[str, type[Drug]] = {
    "pimobendan": Pimobendan,
    "furosemide": Furosemide,
    "epinephrine": Epinephrine,
    "fluid_bolus": FluidBolus,
    "amoxicillin_clavulanate": AmoxicillinClavulanate,
}


def create_drug(name: str, **kwargs) -> Drug:
    """
    Factory: instantiate a drug by registered name.

    Args:
        name: Drug identifier (must be in registry).
        **kwargs: Passed to drug constructor.

    Returns:
        Drug instance.

    Raises:
        KeyError: If drug name is not registered.
    """
    cls = _DRUG_REGISTRY.get(name)
    if cls is None:
        raise KeyError(
            f"Drug '{name}' not registered. Available: {list(_DRUG_REGISTRY.keys())}"
        )
    return cls(**kwargs)


def register_drug(name: str, cls: type[Drug]) -> None:
    """Register a new drug class in the factory."""
    _DRUG_REGISTRY[name] = cls


def list_drugs() -> dict[str, dict]:
    """
    Return metadata for all registered drugs.

    Returns:
        Dict of {drug_name: {name, half_life_h, description}}.
    """
    _descriptions: dict[str, str] = {
        "pimobendan": "PDE-III抑制剂 → 正性肌力 + 血管扩张",
        "furosemide": "袢利尿剂 → 抑制Na-K-2Cl共转运体",
        "epinephrine": "α/β肾上腺素能激动剂 → ↑SVR + ↑HR + ↑收缩力",
        "fluid_bolus": "晶体液冲击 → 直接增加血容量",
    }
    result: dict[str, dict] = {}
    for name, cls in _DRUG_REGISTRY.items():
        tmp = cls()
        result[name] = {
            "name": tmp.name,
            "half_life_h": round(tmp.half_life / 3600.0, 2),
            "description": _descriptions.get(name, ""),
        }
    return result


# ── PharmacologyState ────────────────────────────────────────────────────────


class PharmacologyState:
    """
    Holds all active drugs for one VirtualCreature.

    Each simulation step:
      1. Compute PK decay for all active drugs.
      2. Apply PD effects to ODE parameters.
    """

    def __init__(self, weight_kg: float):
        self.w = weight_kg
        self.active_drugs: list[Drug] = []

    def administer_drug(
        self, name: str, dose_mg_kg: float = 0.0, volume_ml: float = 0.0
    ) -> None:
        """
        Administer a drug to the creature.

        Args:
            name: Drug identifier.
            dose_mg_kg: Dose in mg/kg (for standard drugs).
            volume_ml: Volume in mL (for fluid bolus).
        """
        drug = create_drug(name)
        if isinstance(drug, FluidBolus):
            drug.administer(volume_ml)
        else:
            drug.administer(dose_mg_kg)
        self.active_drugs.append(drug)
        logger.info("Pharmacology: administered %s (dose=%.2f mg/kg)", name, dose_mg_kg)

    def compute(self, dt: float, creature: VirtualCreature) -> list[FactorCommand]:
        """
        Advance all drugs by dt, return FactorCommand instructions for engine to apply.

        Each drug's PD effect is converted to FactorCommand instructions.
        The engine applies these via apply_factor(), ensuring a unified write path.

        FluidBolus volume is consumed after one step (concentration reset to 0).

        Args:
            dt: Time step in seconds.
            creature: VirtualCreature instance (for apply_factor target).

        Returns:
            list[FactorCommand] instructions for all active drugs this step.
        """
        all_commands: list[FactorCommand] = []
        for drug in self.active_drugs:
            # Step 1: PK 一阶衰减（浓度的自然减少）
            drug.compute(dt)

            # Step 2: 肝脏 CYP450 首过代谢（如果有 active drug 且肝脏可用）
            if (
                not isinstance(drug, FluidBolus)
                and drug.concentration > 0
                and hasattr(creature, "liver")
                and creature.liver is not None
            ):
                hepatic_cleared = creature.liver.compute_drug_clearance(
                    dt, drug.concentration
                )
                drug.concentration = max(0.0, drug.concentration - hepatic_cleared)

            pd = drug.pd_effect()
            cmds = drug.factor_commands(pd)
            all_commands.extend(cmds)

            # FluidBolus: consume volume after first application
            if isinstance(drug, FluidBolus) and drug.concentration > 0:
                drug.concentration = 0.0

        return all_commands
