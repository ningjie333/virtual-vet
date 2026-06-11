"""Cheap solver fallback contract tests."""

import sys

import numpy as np

sys.path.insert(0, "src")

from simulation import VirtualCreature


class TestRadauFallback:
    """
    Verify that when solve_ivp(method='Radau') fails, the engine falls back
    to Euler cleanly, advances time, and produces finite vital signs.
    """

    def test_radau_failure_falls_back_to_euler(self):
        """Monkey-patching solve_ivp to fail triggers Euler fallback."""
        import scipy.integrate

        original = scipy.integrate.solve_ivp
        try:
            def fake_solve_ivp(*args, **kwargs):
                class FakeResult:
                    status = -1
                    success = False
                    message = "Artificial failure"
                    y = kwargs.get("y0", kwargs.get("y", None))
                    if y is not None:
                        y = np.array(y, dtype=float)

                return FakeResult()

            scipy.integrate.solve_ivp = fake_solve_ivp

            vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1, solver="radau")
            for _ in range(10):
                vc.step()

            assert vc.current_time_s > 0

            for key, vals in vc.history.items():
                for val in vals:
                    assert not (val != val), f"NaN in history['{key}']"
                    assert abs(val) < 1e9, f"Inf in history['{key}']"
        finally:
            scipy.integrate.solve_ivp = original
