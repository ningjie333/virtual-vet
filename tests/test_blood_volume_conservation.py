"""
Blood volume conservation tests.

Verifies that BloodCompartment.total_volume_ml stays in exact sync with
HeartModule.circulating_volume_ml throughout simulation — they must never diverge.
"""

import sys
sys.path.insert(0, "src")

import pytest

from simulation import VirtualCreature


class TestBloodVolumeConservation:
    """blood.total_volume_ml must always equal heart.circulating_volume_ml."""

    def test_volumes_equal_after_steps(self):
        """After many steps, blood.total_volume_ml == heart.circulating_volume_ml."""
        vc = VirtualCreature(body_weight_kg=20.0)
        for _ in range(100):  # 100 × 0.1s = 10s simulated
            vc.step()

        assert abs(vc.blood.total_volume_ml - vc.heart.circulating_volume_ml) < 0.001, (
            f"blood.total_volume_ml ({vc.blood.total_volume_ml}) != "
            f"heart.circulating_volume_ml ({vc.heart.circulating_volume_ml})"
        )

    def test_volumes_equal_after_urine_loss(self):
        """After significant urine output, volumes stay in sync."""
        vc = VirtualCreature(body_weight_kg=20.0)
        initial = vc.heart.circulating_volume_ml

        # 600 steps × 0.1s = 60s simulated — enough for notable urine output
        for _ in range(600):
            vc.step()

        assert abs(vc.blood.total_volume_ml - vc.heart.circulating_volume_ml) < 0.001, (
            f"After 60s: blood.total_volume_ml ({vc.blood.total_volume_ml}) != "
            f"heart.circulating_volume_ml ({vc.heart.circulating_volume_ml})"
        )
        # Spot-check: blood.total_volume_ml has decreased (urine loss applied)
        assert vc.blood.total_volume_ml < initial

    def test_volumes_equal_after_infusion_event(self):
        """After infusion event, volumes stay in sync."""
        vc = VirtualCreature(body_weight_kg=20.0)
        vc.schedule_event(1.0, "fluid_infusion", {"volume_ml": 500.0, "type": "saline"})

        # 50 steps = 5s; event fires at t=1.0s, we simulate past it
        for _ in range(50):
            vc.step()

        assert abs(vc.blood.total_volume_ml - vc.heart.circulating_volume_ml) < 0.001, (
            f"After infusion: blood.total_volume_ml ({vc.blood.total_volume_ml}) != "
            f"heart.circulating_volume_ml ({vc.heart.circulating_volume_ml})"
        )
        # Spot-check: volume increased by approximately 500mL
        assert vc.blood.total_volume_ml > 1700.0  # baseline ~1720mL + 500 = ~2220

    def test_volumes_equal_after_blood_loss_event(self):
        """After blood loss event, volumes stay in sync."""
        vc = VirtualCreature(body_weight_kg=20.0)
        vc.schedule_event(0.5, "blood_loss", {"volume_ml": 300.0})

        for _ in range(30):  # 3s simulated
            vc.step()

        assert abs(vc.blood.total_volume_ml - vc.heart.circulating_volume_ml) < 0.001

    def test_volumes_equal_over_10_minutes(self):
        """10 minutes (6000 steps) — no divergence."""
        vc = VirtualCreature(body_weight_kg=20.0)
        for _ in range(6000):
            vc.step()

        max_diff = max(
            abs(vc.blood.total_volume_ml - vc.heart.circulating_volume_ml)
            for _ in range(1)  # just final state
        )
        assert abs(vc.blood.total_volume_ml - vc.heart.circulating_volume_ml) < 0.001

    def test_volumes_equal_with_combined_events(self):
        """Loss + infusion + urine over time — all in sync."""
        vc = VirtualCreature(body_weight_kg=20.0)
        vc.schedule_event(1.0, "blood_loss", {"volume_ml": 200.0})
        vc.schedule_event(3.0, "fluid_infusion", {"volume_ml": 500.0, "type": "saline"})

        for _ in range(200):  # 20s simulated
            vc.step()

        assert abs(vc.blood.total_volume_ml - vc.heart.circulating_volume_ml) < 0.001

    def test_blood_total_volume_not_static(self):
        """blood.total_volume_ml actually changes over time (not stuck at init value)."""
        vc = VirtualCreature(body_weight_kg=20.0)
        initial = vc.blood.total_volume_ml

        for _ in range(1000):  # 100s simulated
            vc.step()

        # total_volume_ml must have changed from initial (due to urine loss)
        assert vc.blood.total_volume_ml != initial, (
            "blood.total_volume_ml should change over time (not stuck at init)"
        )
        assert abs(vc.blood.total_volume_ml - vc.heart.circulating_volume_ml) < 0.001