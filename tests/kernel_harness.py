"""KernelTestHarness — isolated simulation handle for Tier1/2/3 tests.

Tier1 (trivial):   h = KernelHarness(); h.step(10); assert h.get('heart.heart_rate') > 0
Tier2 (accessible):  h.set('kidney.GFR', 30.0); h.step(10)
Tier3 (solver):     compare Euler vs Radau parity
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

from src.simulation import VirtualCreature
from src.common_types import FactorCommand


@dataclass
class KernelHarness:
    """Thin wrapper over VirtualCreature for test authoring."""

    body_weight_kg: float = 20.0
    species: str = "canine"
    solver: Literal["euler", "radau"] = "euler"
    dt: float = 5.0
    record_history: bool = False

    _vc: VirtualCreature = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._vc = VirtualCreature(
            body_weight_kg=self.body_weight_kg,
            species=self.species,
            dt=self.dt,
            record_history=self.record_history,
        )

    def step(self, n: int = 1):
        """Advance n steps. Returns list of step return values."""
        results = []
        for _ in range(n):
            results.append(self._vc.step())
        return results

    def get(self, path: str) -> float:
        """Read a parameter by dot-path (e.g. 'heart.heart_rate')."""
        module, _, attr = path.partition(".")
        return getattr(getattr(self._vc, module), attr)

    def set(self, path: str, value: float) -> None:
        """Write a parameter by dot-path via apply_factor."""
        module, _, attr = path.partition(".")
        target = f"{module}.{attr}"
        self._vc.apply_factor(FactorCommand(target=target, op="set", value=value))

    def attach_disease(self, disease_name: str, severity: str = "moderate") -> None:
        """Attach a disease by name."""
        from src.diseases import create_disease
        d = create_disease(disease_name, severity=severity)
        self._vc.attach_disease(d)

    @property
    def vc(self) -> VirtualCreature:
        """Direct engine access for advanced test needs."""
        return self._vc
