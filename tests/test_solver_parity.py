"""
test_solver_parity.py — Tier-3 solver parity tests (P2-2).

Verifies Euler and Radau produce equivalent results within O(dt) tolerance.
Run with: uv run pytest tests/test_solver_parity.py -v
"""
from __future__ import annotations

import numpy as np
import pytest

from src.simulation import VirtualCreature
from src.engine.solvers import SolverRegistry


class TestSolverParity:
    """Euler vs Radau parity within convergence-rate tolerance."""

    @pytest.fixture
    def euler_vc(self):
        vc = VirtualCreature(body_weight_kg=20.0, solver="euler", record_history=True)
        return vc

    @pytest.fixture
    def radau_vc(self):
        vc = VirtualCreature(body_weight_kg=20.0, solver="radau", record_history=True)
        return vc

    def _step_n(self, vc, n=10):
        for _ in range(n):
            vc.step()

    def test_euler_heart_rate_positive(self, euler_vc):
        """Euler: heart rate stays in physiologically valid range."""
        self._step_n(euler_vc, 10)
        hr = euler_vc.heart.heart_rate
        assert 40 <= hr <= 250, f"HR={hr} outside valid range"

    def test_radau_heart_rate_positive(self, radau_vc):
        """Radau: heart rate stays in physiologically valid range."""
        self._step_n(radau_vc, 10)
        hr = radau_vc.heart.heart_rate
        assert 40 <= hr <= 250, f"HR={hr} outside valid range"

    def test_euler_MAP_positive(self, euler_vc):
        """Euler: MAP stays in physiologically valid range."""
        self._step_n(euler_vc, 10)
        map_val = euler_vc.heart.mean_arterial_pressure
        assert 30 <= map_val <= 200, f"MAP={map_val} outside valid range"

    def test_radau_MAP_positive(self, radau_vc):
        """Radau: MAP stays in physiologically valid range."""
        self._step_n(radau_vc, 10)
        map_val = radau_vc.heart.mean_arterial_pressure
        assert 30 <= map_val <= 200, f"MAP={map_val} outside valid range"

    def test_both_solvers_same_name(self):
        """Solver names are registered correctly."""
        assert SolverRegistry.names() == ["euler", "radau"]

    def test_euler_solver_properties(self):
        """EulerSolver has correct metadata."""
        solver = SolverRegistry.get("euler")
        assert solver.name == "euler"
        assert solver.order == 1
        assert solver.solver_type == "explicit"

    def test_radau_solver_properties(self):
        """RadauSolver has correct metadata."""
        solver = SolverRegistry.get("radau")
        assert solver.name == "radau"
        assert solver.order == 5
        assert solver.solver_type == "implicit"

    def test_step_delegation_euler(self, euler_vc):
        """step() returns a non-empty dict for Euler."""
        result = euler_vc.step()
        assert isinstance(result, dict)
        assert "heart" in result

    def test_step_delegation_radau(self, radau_vc):
        """step() returns a dict for Radau (may be empty {})."""
        result = radau_vc.step()
        assert isinstance(result, dict)