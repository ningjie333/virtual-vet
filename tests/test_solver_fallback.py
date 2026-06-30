"""Cheap solver fallback contract tests."""

import sys

sys.path.insert(0, "src")

from simulation import VirtualCreature


def test_euler_never_marks_fallback():
    """Euler is the primary method, not a fallback. Count must stay 0."""
    vc = VirtualCreature(body_weight_kg=20.0, solver="euler", record_history=False)
    for _ in range(5):
        vc.step()
    assert vc._solver_fallback_count == 0
    assert vc._solver_last_method_used == "primary"
