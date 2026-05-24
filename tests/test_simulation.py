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
from noble_purkinje import NoblePurkinjeFiber
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


# ---------------------------------------------------------------------------
# Three-model integration tests (VdP + HH + Noble)
# ---------------------------------------------------------------------------

class TestThreeModelIntegration:
    """
    Integration tests verifying Van der Pol + HH + Noble models work together.

    These tests simulate realistic clinical scenarios where all three models
    interact: respiratory rhythm → blood gases → cardiac electrophysiology.
    """

    def test_normal_all_models_stable(self):
        """All three models should produce stable, normal values at baseline."""
        v = VirtualCreature(20.0)
        for _ in range(200):
            v.step()

        # VdP: RR should be ~15/min (2026-05-22: corrected for PaCO2=40)
        rr = v.lung.respiratory_rate
        assert 13.0 <= rr <= 17.0, f"RR={rr}, expected ~15/min"

        # HH: K⁺ toxicity factor should be ~1.0 (normal K⁺)
        k_tox = v.heart.hh.k_toxicity_factor
        assert 0.95 <= k_tox <= 1.0, f"k_tox={k_tox}, expected ~1.0"

        # Noble: conduction should be normal
        cv = v.heart.hh.conduction_velocity
        assert cv > 3.5, f"CV={cv}, expected > 3.5 m/s"
        assert v.heart.hh.av_block_degree == 0, \
            f"AV block={v.heart.hh.av_block_degree}, expected 0"

    def test_hyperkalemia_all_models(self):
        """
        High K⁺ scenario: all three models should respond coherently.

        With K⁺=8.0:
        - VdP: RR should increase (acidosis from K⁺ shift)
        - HH: K⁺ toxicity factor should drop significantly
        - Noble: conduction velocity should decrease, AV block may appear
        """
        v = VirtualCreature(20.0)
        # Simulate hyperkalemia by directly setting K⁺
        v.blood.potassium_mEq_L = 8.0
        for _ in range(200):
            v.step()

        # HH: significant K⁺ toxicity
        k_tox = v.heart.hh.k_toxicity_factor
        assert k_tox < 0.5, f"k_tox={k_tox}, expected < 0.5 at K⁺=8"

        # Noble: conduction slowed
        cv = v.heart.hh.conduction_velocity
        assert cv < 3.0, f"CV={cv}, expected < 3.0 m/s at K⁺=8"

        # Noble: some degree of AV block
        assert v.heart.hh.av_block_degree >= 1, \
            f"AV block={v.heart.hh.av_block_degree}, expected >= 1 at K⁺=8"

    def test_three_model_coexistence(self):
        """
        All three models should coexist without interfering with each other
        under normal conditions.

        VdP produces respiratory rhythm → blood gases affect HH/Noble
        but at normal values, all should remain at baseline.
        """
        v = VirtualCreature(20.0)
        for _ in range(200):
            v.step()

        # VdP: stable RR ~15/min (2026-05-22: corrected from ~18)
        rr = v.lung.respiratory_rate
        assert 13.0 <= rr <= 17.0, f"RR={rr}, expected ~15/min"

        # VdP: oscillating (not stuck)
        vdp_state = v.lung._vdp.get_state()
        assert vdp_state["amplitude"] > 0.5, \
            f"VdP amplitude={vdp_state['amplitude']}, expected > 0.5"

        # HH: normal K⁺ toxicity
        assert 0.95 <= v.heart.hh.k_toxicity_factor <= 1.0

        # Noble: normal conduction
        assert v.heart.hh.conduction_velocity > 3.5
        assert v.heart.hh.av_block_degree == 0

        # Noble: PR and QRS in normal range
        assert v.heart.hh.pr_interval_ms < 120
        assert v.heart.hh.qrs_width_ms < 100

    def test_severe_hyperkalemia_av_progression(self):
        """
        Progressive AV block with increasing K⁺ (Noble model).

        K⁺ 4.2 → normal conduction
        K⁺ 6.5 → first-degree AVB (PR prolongation)
        K⁺ 8.0 → second-degree AVB
        K⁺ 9.0 → near-complete block
        """
        degrees = []
        for k_ext in [4.2, 6.5, 8.0, 9.0]:
            noble = NoblePurkinjeFiber()
            for _ in range(200):
                noble.update(dt=0.1, heart_rate_bpm=85, k_ext=k_ext)
            degrees.append(noble.av_block_degree)

        # AV block should worsen with increasing K⁺
        assert degrees[0] == 0, f"K⁺=4.2: AV={degrees[0]}, expected 0"
        assert degrees[1] >= 1, f"K⁺=6.5: AV={degrees[1]}, expected >= 1"
        assert degrees[2] >= degrees[1], \
            f"K⁺=8.0: AV={degrees[2]}, should be >= K⁺=6.5: AV={degrees[1]}"
        assert degrees[3] >= 2, f"K⁺=9.0: AV={degrees[3]}, expected >= 2"

    def test_noble_inherits_hh_k_toxicity(self):
        """
        Noble's parent HH k_toxicity_factor should still affect heart rate.

        This verifies the inheritance chain works: Noble → HH → k_toxicity.
        """
        v = VirtualCreature(20.0)
        v.blood.potassium_mEq_L = 9.0
        for _ in range(200):
            v.step()

        # Heart rate should be suppressed by HH k_toxicity
        hr = v.heart.heart_rate
        assert hr < 60, f"HR={hr}, expected < 60 bpm at K⁺=9 (HH toxicity)"

    def test_vdp_noble_independent(self):
        """
        VdP and Noble should respond to different stimuli independently.

        VdP responds to PCO2/PO2/pH
        Noble responds to K⁺
        """
        # Normal creature (baseline)
        v0 = VirtualCreature(20.0)
        for _ in range(200):
            v0.step()
        rr_normal = v0.lung.respiratory_rate
        cv_normal = v0.heart.hh.conduction_velocity

        # High K⁺ → Noble slows conduction, minimal VdP effect
        v_k = VirtualCreature(20.0)
        v_k.blood.potassium_mEq_L = 8.5
        for _ in range(300):
            v_k.step()

        # Noble effect: high K⁺ should slow conduction
        assert v_k.heart.hh.conduction_velocity < cv_normal, \
            f"Noble: CV(K⁺)={v_k.heart.hh.conduction_velocity} should be < CV(normal)={cv_normal}"

        # VdP: RR should be similar (K⁺ doesn't directly affect respiration much)
        # Allow some tolerance for indirect effects
        assert abs(v_k.lung.respiratory_rate - rr_normal) < 5.0, \
            f"VdP: RR(K⁺)={v_k.lung.respiratory_rate} should be close to RR(normal)={rr_normal}"
