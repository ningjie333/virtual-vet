"""
Long-horizon Euler endurance validation.

Radau endurance and cross-solver drift now live in their own benchmark files
so the solver bundle can be split more precisely by runtime.
"""

import sys

sys.path.insert(0, "src")

import pytest

from simulation import VirtualCreature
from tests._solver_assertions import assert_engine_state_finite

pytestmark = pytest.mark.slower


class TestLongDurationStability:
    """Verify long-horizon Euler solver stability."""

    def test_100min_euler_no_nan(self):
        """60000 steps (100 min) Euler — key engine state stays finite."""
        vc = VirtualCreature(
            body_weight_kg=20.0,
            species="canine",
            dt=0.1,
            solver="euler",
            record_history=False,
        )
        for step_idx in range(60000):
            vc.step()
            assert_engine_state_finite(vc, step_idx)

    def test_10min_euler_no_nan(self):
        """6000 steps (10 min) Euler — key engine state stays finite."""
        vc = VirtualCreature(
            body_weight_kg=20.0,
            species="canine",
            dt=0.1,
            solver="euler",
            record_history=False,
        )
        for step_idx in range(6000):
            vc.step()
            assert_engine_state_finite(vc, step_idx)
