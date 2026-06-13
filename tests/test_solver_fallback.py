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

    def test_radau_failure_returns_dict_not_none(self):
        """P0 0a: fallback path must return dict, not None (contract violation).

        Pre-fix bug: when solve_ivp failed, _step_radau called _step_euler() but
        discarded its return value, then returned None. This broke the step()
        return-type contract and could silently self-compare Euler in twin-run.
        """
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
            result = vc.step()
            assert result is not None, "Radau fallback returned None — P0 0a regression"
            assert isinstance(result, dict), f"Expected dict, got {type(result).__name__}"
        finally:
            scipy.integrate.solve_ivp = original

    def test_fallback_count_increments(self):
        """P0 0a: fallback must be detectable via _solver_fallback_count."""
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
            assert vc._solver_fallback_count == 0
            assert vc._solver_last_method_used == "primary"

            for _ in range(5):
                vc.step()

            assert vc._solver_fallback_count == 5, f"Expected 5 fallbacks, got {vc._solver_fallback_count}"
            assert vc._solver_last_method_used == "euler_fallback"
        finally:
            scipy.integrate.solve_ivp = original

    def test_euler_never_marks_fallback(self):
        """Euler is the primary method, not a fallback. Count must stay 0."""
        vc = VirtualCreature(body_weight_kg=20.0, solver="euler", record_history=False)
        for _ in range(5):
            vc.step()
        assert vc._solver_fallback_count == 0
        assert vc._solver_last_method_used == "primary"
