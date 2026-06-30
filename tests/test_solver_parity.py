"""
test_solver_parity.py — Tier-3 solver parity tests (P2-2).

Verifies the Euler solver produces physiologically valid results.
Run with: uv run pytest tests/test_solver_parity.py -v

P2-3 Tier markers:
- tier0: fast (no engine setup, metadata only)
- tier3: slow (full simulation)
"""
from __future__ import annotations

import pytest

from src.simulation import VirtualCreature
from src.engine.solvers import SolverRegistry


@pytest.mark.tier3
class TestSolverParity:
    """Euler solver produces physiologically valid results."""

    @pytest.fixture
    def euler_vc(self):
        vc = VirtualCreature(body_weight_kg=20.0, solver="euler", record_history=True)
        return vc

    def _step_n(self, vc, n=10):
        for _ in range(n):
            vc.step()

    def test_euler_heart_rate_positive(self, euler_vc):
        """Euler: heart rate stays in physiologically valid range."""
        self._step_n(euler_vc, 10)
        hr = euler_vc.heart.heart_rate
        assert 40 <= hr <= 250, f"HR={hr} outside valid range"

    def test_euler_MAP_positive(self, euler_vc):
        """Euler: MAP stays in physiologically valid range."""
        self._step_n(euler_vc, 10)
        map_val = euler_vc.heart.mean_arterial_pressure
        assert 30 <= map_val <= 200, f"MAP={map_val} outside valid range"

    def test_euler_step_delegation(self, euler_vc):
        """step() returns a non-empty dict for Euler."""
        result = euler_vc.step()
        assert isinstance(result, dict)
        assert "heart" in result


@pytest.mark.tier0
class TestSolverRegistry:
    """Pure metadata checks — no engine setup, runs in <1s."""

    def test_euler_solver_registered(self):
        """Euler solver is registered correctly."""
        assert SolverRegistry.names() == ["euler"]

    def test_euler_solver_properties(self):
        """EulerSolver has correct metadata."""
        solver = SolverRegistry.get("euler")
        assert solver.name == "euler"
        assert solver.order == 1
        assert solver.solver_type == "explicit"

    def test_unknown_solver_raises(self):
        """Unknown solver name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown solver"):
            SolverRegistry.get("not_a_solver")
