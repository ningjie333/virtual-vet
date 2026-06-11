"""
Long-horizon disease validation and natural-history regressions.

This file now keeps only the highest-value DKA regression checks so the
research-disease bundle stays focused. Lower-confidence phosphorus endurance
work lives in tests/test_phosphorus_endurance.py.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from src.diseases import create_disease
from src.simulation import VirtualCreature

pytestmark = pytest.mark.slower


class TestDKABloodVolumeCrash:
    """Protect the DKA dehydration regression fix over long horizons."""

    def test_dka_blood_volume_stays_above_50_percent(self):
        """DKA blood volume should not drop below 50% of initial over 120 min."""
        creature = VirtualCreature(body_weight_kg=20.0, record_history=False)
        initial_bv = creature.heart.circulating_volume_ml
        disease = create_disease("diabetic_ketoacidosis", severity="moderate")
        creature.attach_disease(disease)

        for _ in range(72000):
            creature.step()

        final_bv = creature.heart.circulating_volume_ml
        assert final_bv > initial_bv * 0.5, (
            f"Blood volume dropped to {final_bv:.0f} mL "
            f"({final_bv / initial_bv * 100:.1f}% of initial {initial_bv:.0f} mL); "
            f"exponential decay from dehydration multiply is still active"
        )

    def test_dka_death_time_at_least_70_minutes(self):
        """DKA should not kill the patient in less than 70 minutes (moderate)."""
        creature = VirtualCreature(body_weight_kg=20.0, record_history=False)
        disease = create_disease("diabetic_ketoacidosis", severity="moderate")
        creature.attach_disease(disease)

        death_time_min = None
        for _ in range(84000):
            creature.step()
            map_val = creature.heart.mean_arterial_pressure
            if map_val < 40:
                death_time_min = creature.current_time_s / 60
                break

        if death_time_min is not None:
            assert death_time_min >= 70, (
                f"DKA killed patient at {death_time_min:.0f} min; "
                f"expected ≥ 70 min after fix"
            )
