"""
OrganHealthTracker unit tests — multi-organ failure tracking.

Covers src/organ_health.py (193 lines):
  - State: heart_health, lung_health, kidney_health (0 to 1.0)
  - Failure thresholds: HEART_FAILURE_AT=0.3, LUNG_FAILURE_AT=0.2, KIDNEY_FAILURE_AT=0.15
  - track() method: accumulates damage when organ stress exceeds threshold
  - any_failure: boolean — true if any organ below failure threshold
"""

import sys
sys.path.insert(0, "src")

import pytest
from organ_health import OrganHealthTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tracker():
    """Fresh OrganHealthTracker (no constructor args)."""
    return OrganHealthTracker()


# ---------------------------------------------------------------------------
# TestHealthDepletion
# ---------------------------------------------------------------------------

class TestHealthDepletion:
    """Prolonged organ stress → health declines (irreversible)."""

    def test_heart_health_drops_with_prolonged_low_map(self):
        """MAP=50 for 1000s → heart_health < 1.0."""
        ot = make_tracker()
        heart_state = {"MAP_mmHg": 50.0, "heart_rate_bpm": 100.0}
        lung_state = {"arterial_PO2": 95.0, "respiratory_rate": 18.0}
        kidney_state = {"GFR_ml_min": 30.0}

        for _ in range(10000):
            ot.track(dt=0.1, heart_state=heart_state,
                    lung_state=lung_state, kidney_state=kidney_state)

        assert ot.heart_health < 1.0, \
            f"Prolonged low MAP should reduce heart_health, got {ot.heart_health}"

    def test_lung_health_drops_with_prolonged_hypoxia(self):
        """PaO2=55 for 1000s → lung_health declines."""
        ot = make_tracker()
        heart_state = {"MAP_mmHg": 100.0, "heart_rate_bpm": 85.0}
        lung_state = {"arterial_PO2": 55.0, "respiratory_rate": 30.0}
        kidney_state = {"GFR_ml_min": 60.0}

        for _ in range(10000):
            ot.track(dt=0.1, heart_state=heart_state,
                    lung_state=lung_state, kidney_state=kidney_state)

        assert ot.lung_health < 1.0, \
            f"Prolonged hypoxia should reduce lung_health, got {ot.lung_health}"

    def test_kidney_health_drops_with_low_map(self):
        """MAP < 65 mmHg for prolonged period → kidney_health declines."""
        ot = make_tracker()
        # NOTE: kidney_health track() uses MAP < 65 (not GFR) as stress signal
        heart_state = {"MAP_mmHg": 50.0, "heart_rate_bpm": 85.0}
        lung_state = {"arterial_PO2": 95.0, "respiratory_rate": 18.0}
        kidney_state = {"GFR_ml_min": 15.0}

        for _ in range(10000):  # 1000s of MAP=50
            ot.track(dt=0.1, heart_state=heart_state,
                    lung_state=lung_state, kidney_state=kidney_state)

        assert ot.kidney_health < 1.0, \
            f"MAP=50 should reduce kidney_health, got {ot.kidney_health}"


# ---------------------------------------------------------------------------
# TestHealthRecovery
# ---------------------------------------------------------------------------

class TestHealthRecovery:
    """Health is irreversible — normal conditions do not restore it."""

    def test_health_is_irreversible(self):
        """After damage, normal conditions do NOT restore health."""
        ot = make_tracker()

        # Inflict damage with bad conditions
        bad = {"MAP_mmHg": 50.0, "heart_rate_bpm": 100.0}
        bad_lung = {"arterial_PO2": 55.0, "respiratory_rate": 30.0}
        bad_kidney = {"GFR_ml_min": 15.0}
        for _ in range(5000):
            ot.track(dt=0.1, heart_state=bad,
                    lung_state=bad_lung, kidney_state=bad_kidney)
        damaged = ot.heart_health

        # Restore normal conditions
        healthy = {"MAP_mmHg": 100.0, "heart_rate_bpm": 85.0}
        healthy_lung = {"arterial_PO2": 95.0, "respiratory_rate": 18.0}
        healthy_kidney = {"GFR_ml_min": 60.0}
        for _ in range(1000):
            ot.track(dt=0.1, heart_state=healthy,
                    lung_state=healthy_lung, kidney_state=healthy_kidney)

        # Health should NOT recover (irreversible damage model)
        assert ot.heart_health <= damaged, \
            "Health is irreversible — should not increase"


# ---------------------------------------------------------------------------
# TestFailureThresholds
# ---------------------------------------------------------------------------

class TestFailureThresholds:
    """any_failure = True when any organ drops below its failure threshold."""

    def test_any_failure_at_exact_threshold(self):
        """Heart health = HEART_FAILURE_AT → any_failure is True."""
        ot = make_tracker()
        ot.heart_health = ot.HEART_FAILURE_AT
        assert ot.any_failure is True

    def test_any_failure_false_just_above_threshold(self):
        """All organs just above thresholds → any_failure is False."""
        ot = make_tracker()
        ot.heart_health = ot.HEART_FAILURE_AT + 0.01
        ot.lung_health = ot.LUNG_FAILURE_AT + 0.01
        ot.kidney_health = ot.KIDNEY_FAILURE_AT + 0.01
        assert ot.any_failure is False

    def test_lung_failure_at_threshold(self):
        """Lung health = LUNG_FAILURE_AT → any_failure is True."""
        ot = make_tracker()
        ot.lung_health = ot.LUNG_FAILURE_AT
        ot.heart_health = 1.0
        ot.kidney_health = 1.0
        assert ot.any_failure is True

    def test_kidney_failure_at_threshold(self):
        """Kidney health = KIDNEY_FAILURE_AT → any_failure is True."""
        ot = make_tracker()
        ot.kidney_health = ot.KIDNEY_FAILURE_AT
        ot.heart_health = 1.0
        ot.lung_health = 1.0
        assert ot.any_failure is True


# ---------------------------------------------------------------------------
# TestOrganHealthIntegration
# ---------------------------------------------------------------------------

class TestOrganHealthIntegration:
    """Full integration: OrganHealthTracker + VirtualCreature."""

    @pytest.mark.slow
    def test_failure_triggers_in_creature(self):
        """Severe blood loss → any_failure becomes True on creature."""
        from simulation import VirtualCreature

        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vc.schedule_event(1.0, "blood_loss", {"volume_ml": 1500.0})

        any_failure_seen = False
        for _ in range(20000):
            vc.step()
            if vc.organ_health.any_failure:
                any_failure_seen = True
                break

        assert any_failure_seen, \
            "Severe blood loss should trigger organ failure within 2000s"

    def test_organ_health_in_creature_summary(self):
        """creature.organ_health.summary() includes all three organ values."""
        from simulation import VirtualCreature
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        s = vc.organ_health.summary()
        for key in ["heart_health", "lung_health", "kidney_health", "any_failure"]:
            assert key in s, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# TestSigmoidAcceleration
# ---------------------------------------------------------------------------

class TestSigmoidAcceleration:
    """_sigmoid_acceleration: ratio=0 → 1.0, ratio>1 → steep acceleration."""

    def test_zero_ratio_is_one(self):
        assert OrganHealthTracker._sigmoid_acceleration(0) == pytest.approx(1.0)

    def test_positive_ratio_above_one(self):
        assert OrganHealthTracker._sigmoid_acceleration(1.0) > 1.0

    def test_ratio_ordering(self):
        s0 = OrganHealthTracker._sigmoid_acceleration(0.0)
        s1 = OrganHealthTracker._sigmoid_acceleration(0.5)
        s2 = OrganHealthTracker._sigmoid_acceleration(1.5)
        assert s2 > s1 > s0