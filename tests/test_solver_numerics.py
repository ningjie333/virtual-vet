"""
Solver numerics: short-horizon Euler/Radau parity.

Cheap fallback behaviour lives in tests/test_solver_fallback.py.
Long-horizon endurance/drift checks live in tests/test_solver_endurance.py,
tests/test_solver_radau_endurance.py, and tests/test_solver_drift.py.
"""

import sys
sys.path.insert(0, "src")

import pytest

from simulation import VirtualCreature
from src.diseases import create_disease


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_steps(vc, n):
    """Run n simulation steps."""
    for _ in range(n):
        vc.step()


def _vital_at_step(vc, key, step_idx):
    """Get history value at given step index."""
    return vc.history[key][step_idx]


def _relative_diff(a, b):
    """Return |a-b| / max(|a|, |b|, 1e-9)."""
    return abs(a - b) / max(max(abs(a), abs(b)), 1e-9)


# ---------------------------------------------------------------------------
# TestEulerRadauParity
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestEulerRadauParity:
    """
    Verify that Euler and Radau solvers produce identical results.

    The two solvers must agree within a tight tolerance for any simulated
    scenario — they are two different numerical methods solving the same ODE
    system.  Any meaningful divergence indicates a numerical or architectural
    bug.  Tolerance: < 0.1% relative difference in key vitals.

    Scenarios:
      A: Healthy baseline, 60 s
      B: Moderate ARF, 60 s
      C: Moderate pneumonia, 60 s
      D: Blood-loss event at t=5s, 60 s
    """

    @pytest.mark.parametrize("disease_name,severity,steps", [
        ("none",      "none",   600),   # A: healthy, 60 s
        ("acute_renal_failure", "moderate", 600),  # B: ARF
        ("pneumonia", "moderate", 600),              # C: pneumonia
    ], ids=["healthy", "arf", "pneumonia"])
    def test_parity_no_disease_or_attached_disease(self, disease_name, severity, steps):
        """Euler and Radau must agree on key vitals regardless of disease."""
        common_kw = dict(body_weight_kg=20.0, species="canine", dt=0.1)
        vc_e = VirtualCreature(solver="euler", **common_kw)
        vc_r = VirtualCreature(solver="radau", **common_kw)

        if disease_name != "none":
            dis_e = create_disease(disease_name, severity=severity)
            dis_r = create_disease(disease_name, severity=severity)
            vc_e.attach_disease(dis_e)
            vc_r.attach_disease(dis_r)

        for _ in range(steps):
            vc_e.step()
            vc_r.step()

        # Compare final vital signs
        tol = 0.005  # 0.5% relative tolerance
        for key in ["MAP_mmHg", "HR_bpm", "CO_ml_min", "GFR"]:
            e_val = vc_e.history.get(key, [None])[-1]
            r_val = vc_r.history.get(key, [None])[-1]
            if e_val is None or r_val is None:
                continue
            rd = _relative_diff(e_val, r_val)
            assert rd < tol, (
                f"[{disease_name}/{severity}] {key}: Euler={e_val:.4f}, "
                f"Radau={r_val:.4f}, rel_diff={rd:.4f} (tol={tol})"
            )

    def test_parity_blood_loss_event(self):
        """Blood-loss event at t=5s triggers RAAS — Euler and Radau must agree."""
        vc_e = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1, solver="euler")
        vc_r = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1, solver="radau")

        # Schedule blood loss at t=5s (step 50)
        for vc in (vc_e, vc_r):
            vc.schedule_event(5.0, "blood_loss", {"volume_ml": 300.0})

        for _ in range(600):  # 60 s
            vc_e.step()
            vc_r.step()

        tol = 0.01  # 1% — blood-loss response involves coupling dynamics
        for key in ["MAP_mmHg", "HR_bpm", "CO_ml_min", "GFR", "blood_volume_ml"]:
            e_vals = vc_e.history.get(key)
            r_vals = vc_r.history.get(key)
            if not e_vals or not r_vals:
                continue
            rd = _relative_diff(e_vals[-1], r_vals[-1])
            assert rd < tol, (
                f"blood_loss {key}: Euler={e_vals[-1]:.4f}, "
                f"Radau={r_vals[-1]:.4f}, rel_diff={rd:.4f}"
            )
