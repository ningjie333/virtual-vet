"""
Cross-solver drift validation.

Separated from raw endurance runs so the expensive "dual instance, dual
solver" comparison can be scheduled independently.
"""

import sys

sys.path.insert(0, "src")

import pytest

from simulation import VirtualCreature

pytestmark = pytest.mark.slower


def _relative_diff(a, b):
    """Return |a-b| / max(|a|, |b|, 1e-9)."""
    return abs(a - b) / max(max(abs(a), abs(b)), 1e-9)


class TestSolverDrift:
    """Verify bounded drift between Euler and Radau over 10 min."""

    def test_solver_drift_bounded(self):
        """After 10 min, Euler vs Radau differ by < 5% on every vital."""
        common_kw = dict(body_weight_kg=20.0, species="canine", dt=0.1)
        vc_e = VirtualCreature(solver="euler", record_history=False, **common_kw)
        vc_r = VirtualCreature(solver="radau", record_history=False, **common_kw)

        for _ in range(6000):
            vc_e.step()
            vc_r.step()

        final_pairs = {
            "MAP_mmHg": (vc_e.heart.mean_arterial_pressure, vc_r.heart.mean_arterial_pressure),
            "HR_bpm": (vc_e.heart.heart_rate, vc_r.heart.heart_rate),
            "CO_ml_min": (vc_e.heart.cardiac_output, vc_r.heart.cardiac_output),
            "GFR": (vc_e.kidney.GFR, vc_r.kidney.GFR),
            "blood_volume_ml": (vc_e.heart.circulating_volume_ml, vc_r.heart.circulating_volume_ml),
        }
        for key, (e_val, r_val) in final_pairs.items():
            rd = _relative_diff(e_val, r_val)
            assert rd < 0.05, (
                f"[10min] {key}: Euler={e_val:.4f}, Radau={r_val:.4f}, "
                f"rel_diff={rd:.4f} (max allowed 0.05)"
            )
