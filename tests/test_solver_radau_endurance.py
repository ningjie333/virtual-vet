"""
Long-horizon Radau endurance validation.

This file is isolated because Radau runtime is materially higher than the
Euler-only endurance checks and should be triggerable as its own bundle.
"""

import sys

sys.path.insert(0, "src")

import pytest

from simulation import VirtualCreature
from tests._solver_assertions import assert_engine_state_finite

pytestmark = pytest.mark.slower


class TestRadauDurationStability:
    """Verify long-horizon Radau solver stability."""

    def test_10min_radau_no_nan(self):
        """6000 steps (10 min) Radau — key engine state stays finite."""
        vc = VirtualCreature(
            body_weight_kg=20.0,
            species="canine",
            dt=0.1,
            solver="radau",
            record_history=False,
        )
        for step_idx in range(6000):
            vc.step()
            assert_engine_state_finite(vc, step_idx)
