"""
Integration / cross-module tests for VirtualCreature simulation engine.

Tests cover:
- Conservation laws (blood volume)
- Simulation stability (physiological ranges, no-crash)
- Organ health tracking
- Toxicology (cocaine two-pathway kinetics)
- Extreme value handling
- Parameter scaling by body weight
"""

import sys
import math

sys.path.insert(0, "src")

import pytest

from simulation import VirtualCreature
from organ_health import OrganHealthTracker
from parameters import total_blood_volume_ml


# ---------------------------------------------------------------------------
# Conservation law tests
# ---------------------------------------------------------------------------

class TestBloodVolumeConservation:
    """Test that blood volume changes match physiology expectations."""

    def test_blood_volume_conservation_no_events(self):
        """100 steps, no events => volume drift < 5%."""
        v = VirtualCreature(20.0)
        for _ in range(100):
            v.step()
        bv = v.history["blood_volume_ml"]
        drift_pct = abs(bv[-1] - bv[0]) / bv[0] * 100
        assert drift_pct < 5.0, f"Blood volume drifted {drift_pct:.2f}%"

    def test_blood_volume_decreases_with_blood_loss(self):
        """Blood-loss event at t=10s => volume drops."""
        v = VirtualCreature(20.0)
        v.schedule_event(1.0, "blood_loss", {"volume_ml": 200.0})
        for _ in range(20):
            v.step()
        bv = v.history["blood_volume_ml"]
        assert bv[-1] < bv[0], "Blood volume should decrease after 200mL loss"
        assert abs(bv[-1] - bv[0] + 200.0) < 10.0, \
            f"Expected ~200mL drop, got {bv[0] - bv[-1]:.1f}mL"

    def test_blood_volume_increases_with_infusion(self):
        """Fluid infusion at t=10s => volume increases."""
        v = VirtualCreature(20.0)
        v.schedule_event(1.0, "fluid_infusion", {"volume_ml": 500.0, "type": "saline"})
        for _ in range(35):
            v.step()
        bv = v.history["blood_volume_ml"]
        assert bv[-1] > bv[0], "Blood volume should increase after 500mL infusion"
        assert abs(bv[-1] - bv[0] - 500.0) < 10.0, \
            f"Expected ~500mL gain, got {bv[-1] - bv[0]:.1f}mL"

    def test_blood_volume_conservation_with_infusion_and_loss(self):
        """Blood loss at t=1s, infusion at t=3s; net ~ +300mL minus urine."""
        v = VirtualCreature(20.0)
        v.schedule_event(1.0, "blood_loss", {"volume_ml": 200.0})
        v.schedule_event(3.0, "fluid_infusion", {"volume_ml": 500.0, "type": "saline"})
        for _ in range(100):
            v.step()
        bv = v.history["blood_volume_ml"]
        net_change = bv[-1] - bv[0]
        # Expect ~300 mL gain minus small urine loss
        assert 290.0 < net_change < 310.0, \
            f"Net change {net_change:.1f}mL not in expected range [290, 310]"


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

    def test_normal_simulation_no_crash(self):
        """10 minutes (6000 steps) completes without exceptions."""
        v = VirtualCreature(20.0)
        for _ in range(6000):
            v.step()
        assert v.current_time_s == pytest.approx(600.0, abs=0.01)

    def test_history_records_all_steps(self):
        """After N steps, every history key has N entries."""
        v = VirtualCreature(20.0)
        steps = 100
        for _ in range(steps):
            v.step()
        for key, vals in v.history.items():
            assert len(vals) == steps, \
                f"History['{key}'] has {len(vals)} entries, expected {steps}"


# ---------------------------------------------------------------------------
# Organ health tests
# ---------------------------------------------------------------------------

class TestOrganHealth:
    """Test organ health tracking under normal and stress conditions."""

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

    def test_organ_health_decreases_under_stress(self):
        """Severe blood loss causing MAP < 65 => organ health drops."""
        v = VirtualCreature(20.0)
        # Lose ~81% of blood volume; simulation runs long enough for MAP to
        # eventually cross the 65 mmHg threshold and accumulate damage.
        v.schedule_event(1.0, "blood_loss", {"volume_ml": 1400.0})
        for _ in range(2000):
            v.step()
        # Heart health should have decreased by end of simulation
        assert v.history["heart_health"][-1] < 1.0, \
            f"Heart health should drop under severe stress, got {v.history['heart_health'][-1]}"

    def test_sigmoid_acceleration(self):
        """_sigmoid_acceleration: ratio=0 => 1.0, ratio>1 => >1.0."""
        # ratio = 0 => 1.0 (no acceleration)
        assert OrganHealthTracker._sigmoid_acceleration(0) == pytest.approx(1.0)

        # ratio > 1.0 => steeply accelerated
        accel = OrganHealthTracker._sigmoid_acceleration(1.0)
        assert accel > 1.0, f"Expected > 1.0 but got {accel}"

        # ratio = 0.5 => moderate acceleration (> 1.0)
        accel_mid = OrganHealthTracker._sigmoid_acceleration(0.5)
        assert accel_mid > 1.0, f"Expected > 1.0 but got {accel_mid}"
        # 0.5 should accelerate more than 0 (but less than 1.0+)
        assert accel > accel_mid > 1.0


# ---------------------------------------------------------------------------
# Toxicology tests
# ---------------------------------------------------------------------------

class TestToxicology:
    """Test cocaine two-pathway kinetics (Liu et al. 1993)."""

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
        """Without cocaine, contractility and SVR factors stay at 1.0."""
        v = VirtualCreature(20.0)
        for _ in range(100):
            v.step()
        assert all(cf == pytest.approx(1.0) for cf in v.history["contractility_factor"]), \
            "Contractility factor should remain 1.0 without cocaine"
        assert all(s == pytest.approx(1.0) for s in v.history["svr_factor"]), \
            "SVR factor should remain 1.0 without cocaine"


# ---------------------------------------------------------------------------
# Extreme value tests
# ---------------------------------------------------------------------------

class TestExtremeValues:
    """Test simulation handles edge cases gracefully."""

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

    def test_negative_step_does_not_crash(self):
        """Never produces NaN or Inf in any history value over 6000 steps."""
        v = VirtualCreature(20.0)
        for _ in range(6000):
            v.step()
        for key, vals in v.history.items():
            for i, val in enumerate(vals):
                assert not math.isnan(val), f"NaN in '{key}' at index {i}"
                assert not math.isinf(val), f"Inf in '{key}' at index {i}"


# ---------------------------------------------------------------------------
# Parameter scaling tests
# ---------------------------------------------------------------------------

class TestWeightScaling:
    """Test that parameters scale correctly with body weight."""

    def test_weight_scaling(self):
        """30 kg dog > 10 kg dog in absolute BV, SV, and CO."""
        dog_10 = VirtualCreature(10.0)
        dog_30 = VirtualCreature(30.0)

        # Step both to get stable CO
        for _ in range(10):
            dog_10.step()
            dog_30.step()

        # Blood volume: 30kg should be ~3x 10kg
        bv_10 = dog_10.heart.total_BV
        bv_30 = dog_30.heart.total_BV
        assert bv_30 > bv_10, f"30kg BV ({bv_30}) should exceed 10kg BV ({bv_10})"

        # Stroke volume: 30kg should be ~3x 10kg
        sv_10 = dog_10.heart.stroke_volume
        sv_30 = dog_30.heart.stroke_volume
        assert sv_30 > sv_10, f"30kg SV ({sv_30}) should exceed 10kg SV ({sv_10})"

        # Cardiac output: 30kg should exceed 10kg
        co_10 = dog_10.heart.cardiac_output
        co_30 = dog_30.heart.cardiac_output
        assert co_30 > co_10, f"30kg CO ({co_30}) should exceed 10kg CO ({co_10})"
