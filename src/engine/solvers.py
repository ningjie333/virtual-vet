"""
solvers.py — pluggable ODE solver plugins.

RATIONALE
=========
Production uses Euler (O(dt) — fast, stable for physiological timescales).
Validation uses Radau (O(dt^5) — implicit, handles stiff systems).
Future solvers (RK4, adaptive-step) slot in here without touching simulation.py.

P1-3 refactor: replaces the hard-coded if/else in step() with a injected
SolverPlugin instance.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.simulation import VirtualCreature

logger = logging.getLogger(__name__)


# ── SolverPlugin ABC ────────────────────────────────────────────────────────────

class SolverPlugin(ABC):
    """
    ABC for ODE solver plugins.

    Subclass to add a new solver:
      1. Implement step() — receives the engine, advances dt, returns result dict
      2. Implement name, order, solver_type properties
      3. Register via SolverRegistry.register()

    The engine's step() delegates entirely to self._solver.step(engine).
    """

    @abstractmethod
    def step(self, engine: "VirtualCreature") -> dict:
        """
        Advance the simulation by one time step.

        Args:
            engine: VirtualCreature instance (holds all organ modules + state)

        Returns:
            dict with per-module state summaries (same shape as before refactor)
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable solver name."""

    @property
    @abstractmethod
    def order(self) -> int:
        """
        Convergence order (exponent of dt in error term).

        Euler = 1, RK4 = 4, Radau = 5.
        Used only for solver-parity tests and documentation.
        """

    @property
    @abstractmethod
    def solver_type(self) -> Literal["explicit", "implicit"]:
        """'explicit' (Euler/RK4) or 'implicit' (Radau)."""


# ── Euler solver ────────────────────────────────────────────────────────────────

class EulerSolver(SolverPlugin):
    """
    First-order forward Euler.

    Fast, stable for physiological timescales (dt=0.1s → O(dt) error).
    Default production solver.
    """

    name = "euler"
    order = 1
    solver_type: Literal["explicit"] = "explicit"

    def step(self, engine: "VirtualCreature") -> dict:
        return engine._step_euler()


# ── Radau solver ───────────────────────────────────────────────────────────────

class RadauSolver(SolverPlugin):
    """
    5th-order implicit Radau IIA.

    Stiff-systems-ready, O(dt^5) convergence.
    Activated by RADAU_ENABLED=1 or solver='radau' kwarg.
    """

    name = "radau"
    order = 5
    solver_type: Literal["implicit"] = "implicit"

    def step(self, engine: "VirtualCreature") -> dict:
        return engine._step_radau()


# ── Solver registry ────────────────────────────────────────────────────────────

class SolverRegistry:
    """
    Global solver registry.

    Usage:
        registry = SolverRegistry()
        registry.register("euler", EulerSolver)
        registry.register("radau", RadauSolver)
        solver = registry.get("euler")
    """

    _entries: dict[str, type[SolverPlugin]] = {}

    @classmethod
    def register(cls, name: str, solver_cls: type[SolverPlugin]) -> None:
        """Register a solver class under a string key."""
        if not issubclass(solver_cls, SolverPlugin):
            raise TypeError(f"{solver_cls} must be a SolverPlugin subclass")
        cls._entries[name] = solver_cls
        logger.debug("Registered solver: %s (%s)", name, solver_cls.solver_type)

    @classmethod
    def get(cls, name: str) -> SolverPlugin:
        """Instantiate and return a solver by name."""
        if name not in cls._entries:
            available = list(cls._entries.keys())
            raise ValueError(f"Unknown solver {name!r}. Available: {available}")
        return cls._entries[name]()

    @classmethod
    def names(cls) -> list[str]:
        """List all registered solver names."""
        return list(cls._entries.keys())


# ── Register built-ins ────────────────────────────────────────────────────────

SolverRegistry.register("euler", EulerSolver)
SolverRegistry.register("radau", RadauSolver)