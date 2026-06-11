"""
Integration / cross-module tests for VirtualCreature simulation engine.

Tests cover:
- Simulation stability (physiological ranges)
- Organ health tracking (normal conditions)
- Toxicology (cocaine two-pathway kinetics, Liu et al. 1993)
- Extreme value handling

Noble/Purkinje fiber tests: see test_noble_purkinje.py
Blood volume conservation: see test_blood_volume_conservation.py
Weight scaling: see test_species_specific.py
Organ health under stress: see test_organ_health.py
"""

import sys
import math

sys.path.insert(0, "src")

import pytest

from simulation import VirtualCreature
from organ_health import OrganHealthTracker


# ---------------------------------------------------------------------------
# Simulation stability tests
# ---------------------------------------------------------------------------

class TestSimulationStability:
    """Test that simulation stays stable and in physiological ranges."""

    def test_normal_simulation_stability(self):
        """20 kg dog, 600 steps (60 s), all vitals in physiological range."""
        v = VirtualCreature(20.0)
        for _ in range(600):
            v.step()
        hr = v.history["HR_bpm"]
        map_ = v.history["MAP_mmHg"]
        spo2 = v.history["saturation"]
        ph = v.history["pH"]

        for val in hr:
            assert 60.0 <= val <= 180.0, f"HR {val} out of range [60, 180]"
        for val in map_:
            assert 50.0 <= val <= 180.0, f"MAP {val} out of range [50, 180]"
        for val in spo2:
            assert 0.80 <= val <= 1.01, f"SpO2 {val} out of range [0.80, 1.01]"
        for val in ph:
            assert 7.20 <= val <= 7.60, f"pH {val} out of range [7.20, 7.60]"


# ---------------------------------------------------------------------------
# Organ health tests (normal conditions)
# ---------------------------------------------------------------------------

class TestOrganHealth:
    """Test organ health tracking under normal conditions."""

    def test_organ_health_stable_under_normal(self):
        """Normal simulation 600 steps => all organ health at 1.0."""
        v = VirtualCreature(20.0)
        for _ in range(600):
            v.step()
        assert all(h == 1.0 for h in v.history["heart_health"]), \
            "Heart health should remain 1.0 in normal conditions"
        assert all(h == 1.0 for h in v.history["lung_health"]), \
            "Lung health should remain 1.0 in normal conditions"
        assert all(h == 1.0 for h in v.history["kidney_health"]), \
            "Kidney health should remain 1.0 in normal conditions"


# ---------------------------------------------------------------------------
# Toxicology tests
# ---------------------------------------------------------------------------

class TestToxicology:
    """Test cocaine two-pathway kinetics (Liu et al. 1993)."""

    @pytest.mark.slower
    def test_cocaine_contractility_decay(self):
        """Cocaine => contractility_factor < 1.0 initially, recovers to 1.0."""
        v = VirtualCreature(20.0)
        v.schedule_event(1.0, "cocaine", {"dose_mg_kg": 3.0})
        # Event fires at t=1.0s (step 10); run enough steps past it
        for _ in range(20):
            v.step()
        cf_initial = v.history["contractility_factor"][-1]
        assert cf_initial < 1.0, \
            f"Contractility should be depressed, got {cf_initial}"

        # Run for a long time (30 min = 18000 steps) => recovery
        steps_to_30min = int(30 * 60.0 / v.dt)
        for _ in range(steps_to_30min):
            v.step()
        cf_recovered = v.history["contractility_factor"][-1]
        assert cf_recovered > cf_initial, \
            f"Contractility should recover: {cf_initial} -> {cf_recovered}"

    def test_cocaine_SVR_increase(self):
        """Cocaine => SVR factor rises above 1.0."""
        v = VirtualCreature(20.0)
        v.schedule_event(1.0, "cocaine", {"dose_mg_kg": 3.0})
        # Event fires at t=1.0s (step 10); need steps past it
        for _ in range(20):
            v.step()
        svr = v.history["svr_factor"][-1]
        assert svr > 1.0, f"SVR factor should increase, got {svr}"

    @pytest.mark.slower
    def test_cocaine_SVR_persists_longer_than_contractility(self):
        """
        At t=15 min post-injection, SVR effect > contractility effect.
        tau_SVR=30min > tau_contractility=5min => SVR decays slower.
        """
        v = VirtualCreature(20.0)
        v.schedule_event(1.0, "cocaine", {"dose_mg_kg": 3.0})
        # 15 min = 900 s = 9000 steps after injection; injection at t=1s
        # so simulate to ~901 s = 9010 steps total
        steps_needed = int(901.0 / v.dt) + 1
        for _ in range(steps_needed):
            v.step()

        # Find index nearest to 901s
        target_t = 901.0
        idx = min(range(len(v.history["time_s"])),
                  key=lambda i: abs(v.history["time_s"][i] - target_t))
        actual_t = v.history["time_s"][idx]

        cf = v.history["contractility_factor"][idx]
        svr = v.history["svr_factor"][idx]

        # Distance from baseline
        contractility_distance = 1.0 - cf  # positive = depressed
        svr_distance = svr - 1.0           # positive = elevated

        assert svr_distance > contractility_distance, \
            f"At t={actual_t:.1f}s: SVR distance ({svr_distance:.4f}) should exceed " \
            f"contractility distance ({contractility_distance:.4f})"

    def test_no_cocaine_no_effect(self):
        """
        Without cocaine, contractility and SVR factors should be
        predominantly at their baseline values.

        contractility_factor from heart.compute() includes pH and coronary
        perfusion multipliers. The VdP-driven respiratory rhythm induces
        small periodic pH oscillations (normal physiology), causing minor
        fluctuations in the pH-contractility effect. We verify the overall
        response stays within a reasonable physiological floor.
        """
        v = VirtualCreature(20.0)
        for _ in range(100):
            v.step()

        cf = v.history["contractility_factor"]
        # Accept small periodic dips from respiratory pH oscillation (≥0.9)
        assert min(cf) >= 0.9, \
            f"contractility_factor should stay >= 0.9, got min={min(cf):.4f}"
        # Most values should be at or near 1.0
        near_1_count = sum(1 for c in cf if c == pytest.approx(1.0))
        assert near_1_count >= 50, \
            f"Expected >= 50 steps with cf ≈ 1.0, got {near_1_count}"

        assert all(s == pytest.approx(1.0) for s in v.history["svr_factor"]), \
            "SVR factor should remain 1.0 without cocaine"


# ---------------------------------------------------------------------------
# Extreme value tests (blood compartment-specific edge cases)
# ---------------------------------------------------------------------------

class TestBloodCompartmentEdgeCases:
    """BloodCompartment-specific edge cases — not covered by test_boundary.py."""

    def test_zero_blood_volume(self):
        """Zero circulating volume => no crash, MAP at floor."""
        v = VirtualCreature(20.0)
        v.heart.circulating_volume_ml = 0.0
        for _ in range(50):
            v.step()
        # MAP should not crash, and be reasonable
        assert all(30.0 <= m <= 180.0 for m in v.history["MAP_mmHg"]), \
            "MAP should stay within clamped range even at zero volume"

    def test_extreme_temperature(self):
        """Extreme temperatures (30 C or 45 C) => no crash."""
        for temp in [30.0, 45.0]:
            v = VirtualCreature(20.0)
            v.blood.core_temperature_C = temp
            for _ in range(50):
                v.step()
            # Just verify no crash; simulation completes
            assert len(v.history["time_s"]) == 50
