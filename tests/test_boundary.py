"""
Boundary and exception tests for the medical physiology simulation.

These tests verify that the simulation handles extreme / edge-case inputs
gracefully -- the primary requirement is NO CRASH.  Where possible we also
check that values stay within sensible clamped ranges.
"""

import sys
import math

sys.path.insert(0, "src")

import pytest

from simulation import VirtualCreature
from blood import BloodCompartment
from heart import HeartModule
from organ_health import OrganHealthTracker
from lung import LungModule
from kidney import KidneyModule
from toxicology import ToxicologyModule


# ===========================================================================
# Extreme physiological values
# ===========================================================================

class TestExtremePhysiologicalValues:
    """Test simulation handles extreme but plausible physiological values."""

    def test_zero_blood_volume(self):
        """Set heart.circulating_volume_ml=0, run step() -- should not crash."""
        v = VirtualCreature(20.0)
        v.heart.circulating_volume_ml = 0.0
        for _ in range(50):
            v.step()
        assert len(v.history["time_s"]) == 50

    def test_extreme_low_MAP(self):
        """Artificially set MAP to 20, run kidney._update_GFR() -- no crash."""
        v = VirtualCreature(20.0)
        v.heart.mean_arterial_pressure = 20.0
        # _update_GFR is called with MAP and CVP
        v.kidney._update_GFR(MAP=20.0, CVP=4.0)
        # GFR should be computed (may be very low but not crash)
        assert not math.isnan(v.kidney.GFR)
        assert not math.isinf(v.kidney.GFR)

    def test_extreme_high_MAP(self):
        """Set MAP to 250, run kidney._update_GFR() -- no crash."""
        v = VirtualCreature(20.0)
        v.kidney._update_GFR(MAP=250.0, CVP=4.0)
        assert not math.isnan(v.kidney.GFR)
        assert not math.isinf(v.kidney.GFR)

    def test_extreme_low_pH(self):
        """Set blood.arterial_pH=6.8, run simulation -- should not crash."""
        v = VirtualCreature(20.0)
        v.blood.arterial_pH = 6.8
        for _ in range(100):
            v.step()
        assert len(v.history["time_s"]) == 100

    def test_extreme_high_pH(self):
        """Set blood.arterial_pH=7.7, run simulation -- should not crash."""
        v = VirtualCreature(20.0)
        v.blood.arterial_pH = 7.7
        for _ in range(100):
            v.step()
        assert len(v.history["time_s"]) == 100

    def test_extreme_temperature_low(self):
        """Set blood.core_temperature_C=30, run step() -- should not crash."""
        v = VirtualCreature(20.0)
        v.blood.core_temperature_C = 30.0
        for _ in range(50):
            v.step()
        assert len(v.history["time_s"]) == 50

    def test_extreme_temperature_high(self):
        """Set blood.core_temperature_C=42, run step() -- should not crash."""
        v = VirtualCreature(20.0)
        v.blood.core_temperature_C = 42.0
        for _ in range(50):
            v.step()
        assert len(v.history["time_s"]) == 50

    def test_extreme_tachycardia(self):
        """Set heart.heart_rate=250, run compute() -- should clamp to HR_max."""
        v = VirtualCreature(20.0)
        v.heart.heart_rate = 250.0
        result = v.heart.compute(dt=0.1, svr_factor=1.0)
        assert result["heart_rate_bpm"] <= v.heart.HR_max, \
            f"HR {result['heart_rate_bpm']} exceeds HR_max {v.heart.HR_max}"

    def test_extreme_bradycardia(self):
        """Set heart.heart_rate=30, run compute() -- should clamp to 60."""
        v = VirtualCreature(20.0)
        v.heart.heart_rate = 30.0
        result = v.heart.compute(dt=0.1, svr_factor=1.0)
        assert result["heart_rate_bpm"] >= 60.0, \
            f"HR {result['heart_rate_bpm']} is below floor of 60"


# ===========================================================================
# Simulation stability
# ===========================================================================

class TestSimulationStability:
    """Test simulation remains stable under long runs and event stress."""

    def test_long_simulation_stability(self):
        """Run simulation for 60000 steps (100 min). No NaN/Inf in any history."""
        v = VirtualCreature(20.0)
        for _ in range(60000):
            v.step()
        for key, vals in v.history.items():
            for i, val in enumerate(vals):
                assert not math.isnan(val), f"NaN in '{key}' at index {i}"
                assert not math.isinf(val), f"Inf in '{key}' at index {i}"

    def test_no_crash_empty_events(self):
        """Run simulation with empty scheduled_events for 1000 steps."""
        v = VirtualCreature(20.0)
        v._scheduled_events = []
        for _ in range(1000):
            v.step()
        assert len(v.history["time_s"]) == 1000

    def test_no_crash_rapid_events(self):
        """Schedule 10 events at the same timestamp -- should not crash."""
        v = VirtualCreature(20.0)
        for i in range(10):
            v.schedule_event(1.0, "blood_loss", {"volume_ml": 10.0})
        for _ in range(200):
            v.step()
        assert len(v.history["time_s"]) == 200

    def test_negative_dt_handling(self):
        """Call step() multiple times -- time always increases monotonically."""
        v = VirtualCreature(20.0)
        for _ in range(500):
            v.step()
        times = v.history["time_s"]
        for i in range(1, len(times)):
            assert times[i] > times[i - 1], \
                f"Time decreased at index {i}: {times[i-1]} -> {times[i]}"


# ===========================================================================
# Blood compartment edge cases
# ===========================================================================

class TestBloodCompartmentEdgeCases:
    """Test BloodCompartment with edge-case parameters."""

    def test_zero_total_volume(self):
        """BloodCompartment(total_volume_ml=0) -- plasma and red_cell should be 0."""
        bc = BloodCompartment(total_volume_ml=0.0)
        assert bc.plasma_volume_ml == 0.0
        assert bc.red_cell_volume_ml == 0.0

    def test_extreme_oxygen_saturation(self):
        """_oxygen_saturation_curve: PO2=0 ~> 0, PO2=200 ~> 1.0."""
        v = VirtualCreature(20.0)
        sat_zero = v.lung._oxygen_saturation_curve(0.0)
        sat_high = v.lung._oxygen_saturation_curve(200.0)
        assert sat_zero == pytest.approx(0.0, abs=0.01), f"Sat at PO2=0 is {sat_zero}"
        assert sat_high == pytest.approx(1.0, abs=0.01), f"Sat at PO2=200 is {sat_high}"

    def test_pH_at_PCO2_zero(self):
        """_update_arterial_pH with PCO2 approaching 0 -- should be clamped."""
        v = VirtualCreature(20.0)
        v.blood.arterial_PCO2_mmHg = 0.001  # near-zero, not exactly 0
        v.lung._update_arterial_pH()
        # pH should be clamped to [7.0, 7.8]
        assert 7.0 <= v.blood.arterial_pH <= 7.8, \
            f"pH {v.blood.arterial_pH} not in clamped range [7.0, 7.8]"


# ===========================================================================
# Toxicology edge cases
# ===========================================================================

class TestToxicologyEdgeCases:
    """Test ToxicologyModule with edge-case doses and timing."""

    def test_cocaine_zero_dose(self):
        """administer_cocaine(dose_mg_kg=0) -- should have minimal effect."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=0.0)
        result = tox.compute(dt=0.1)
        assert result["contractility_factor"] == pytest.approx(1.0, abs=0.01), \
            f"Zero dose contractility: {result['contractility_factor']}"
        assert result["svr_factor"] == pytest.approx(1.0, abs=0.01), \
            f"Zero dose SVR: {result['svr_factor']}"

    def test_cocaine_very_high_dose(self):
        """administer_cocaine(dose_mg_kg=100) -- should be capped at safe max."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=100.0)
        # Max depression is capped at 60% so contractility_factor >= 0.4
        assert tox._max_depression >= -0.60, \
            f"Max depression {tox._max_depression} exceeds 60% cap"
        # SVR factor capped at 3.5
        assert tox._max_svr_factor <= 3.5, \
            f"SVR factor {tox._max_svr_factor} exceeds 3.5 cap"

    def test_cocaine_double_inject(self):
        """Administer cocaine twice -- second injection resets timer."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)
        # Advance 5 minutes (300s = 3000 steps at dt=0.1)
        for _ in range(3000):
            tox.compute(dt=0.1)
        t_first = tox._t_since_injection_min

        # Second injection -- timer resets
        tox.administer_cocaine(dose_mg_kg=3.0)
        assert tox._t_since_injection_min == 0.0, \
            f"Timer not reset: {tox._t_since_injection_min}"
        assert tox._t_since_injection_min < t_first

    def test_cocaine_recovery(self):
        """After cocaine wears off (t >> 30min), contractility_factor ~> 1.0."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)
        # Simulate 2 hours = 7200s = 72000 steps at dt=0.1
        total_steps = int(120 * 60.0 / 0.1)
        for _ in range(total_steps):
            result = tox.compute(dt=0.1)
        assert result["contractility_factor"] == pytest.approx(1.0, abs=0.05), \
            f"Contractility {result['contractility_factor']} not recovered after 2h"
        assert result["svr_factor"] == pytest.approx(1.0, abs=0.1), \
            f"SVR {result['svr_factor']} not recovered after 2h"


# ===========================================================================
# Organ health edge cases
# ===========================================================================

class TestOrganHealthEdgeCases:
    """Test OrganHealthTracker at boundary conditions."""

    def test_organ_health_at_floor(self):
        """Set heart_health to failure threshold -- any_failure is True."""
        oh = OrganHealthTracker()
        oh.heart_health = OrganHealthTracker.HEART_FAILURE_AT  # exactly at threshold
        assert oh.any_failure is True

    def test_sigmoid_at_zero_ratio(self):
        """_sigmoid_acceleration(0) should return 1.0."""
        result = OrganHealthTracker._sigmoid_acceleration(0)
        assert result == pytest.approx(1.0), f"Expected 1.0, got {result}"

    def test_sigmoid_at_high_ratio(self):
        """_sigmoid_acceleration(10) should return large value."""
        result = OrganHealthTracker._sigmoid_acceleration(10)
        assert result > 5.0, f"Expected large value, got {result}"

    def test_organ_health_recovery(self):
        """When stress is removed, exposure should decrease (recovery)."""
        oh = OrganHealthTracker()
        # Simulate stress: MAP < 65 for 100s
        heart_state = {"MAP_mmHg": 50.0, "heart_rate_bpm": 100.0}
        lung_state = {"arterial_PO2": 70.0}
        kidney_state = {}
        for _ in range(1000):
            oh.track(0.1, heart_state, lung_state, kidney_state)

        # Now remove stress: MAP normal
        heart_state["MAP_mmHg"] = 100.0
        exposure_before = oh._heart_exposure
        for _ in range(100):
            oh.track(0.1, heart_state, lung_state, kidney_state)
        assert oh._heart_exposure < exposure_before, \
            f"Exposure should decrease after stress removal: {exposure_before} -> {oh._heart_exposure}"


# ===========================================================================
# Parameter boundary tests
# ===========================================================================

class TestParameterBoundaries:
    """Test VirtualCreature with extreme body weights."""

    def test_very_small_dog(self):
        """VirtualCreature(weight_kg=1.0) -- should work without crash."""
        v = VirtualCreature(1.0)
        for _ in range(100):
            v.step()
        assert len(v.history["time_s"]) == 100

    def test_very_large_dog(self):
        """VirtualCreature(weight_kg=80.0) -- should work without crash."""
        v = VirtualCreature(80.0)
        for _ in range(100):
            v.step()
        assert len(v.history["time_s"]) == 100

    def test_minimal_blood_volume(self):
        """VirtualCreature with weight_kg=0.5 -- should handle."""
        v = VirtualCreature(0.5)
        for _ in range(100):
            v.step()
        assert len(v.history["time_s"]) == 100
