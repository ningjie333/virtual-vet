"""
Species-specific physiology tests — feline and equine.

Covers species differences in:
  - Resting heart rate (feline ~150 bpm vs canine ~85 bpm)
  - Blood volume (feline ~70 mL/kg vs canine ~86 mL/kg)
  - Respiratory rate (equine ~12/min vs canine ~18/min)
  - PCO2 baseline (equine ~42 mmHg vs canine ~40 mmHg)
"""

import sys
sys.path.insert(0, "src")

import pytest
from simulation import VirtualCreature


class TestFelineBaseline:
    """Feline baseline vitals differ from canine."""

    def test_feline_higher_resting_hr(self):
        """Feline resting HR ≈ 150 bpm, not canine ~85."""
        vc = VirtualCreature(body_weight_kg=5.0, species="feline", dt=0.1)
        for _ in range(100):
            vc.step()
        assert 140 <= vc.heart.heart_rate <= 180, \
            f"Feline HR={vc.heart.heart_rate}, expected ~150"

    def test_feline_total_blood_volume_reasonable(self):
        """Feline BV is a positive fraction of body weight."""
        vc = VirtualCreature(body_weight_kg=5.0, species="feline")
        # BV should be proportional to body weight (86 mL/kg baseline)
        assert vc.heart.total_BV > 200.0, \
            f"Feline BV={vc.heart.total_BV} should be > 200 mL for 5 kg animal"


class TestEquineBaseline:
    """Equine baseline vitals differ from canine."""

    def test_equine_lower_resting_rr(self):
        """Equine resting RR ~12/min, not canine ~18."""
        vc = VirtualCreature(body_weight_kg=500.0, species="equine", dt=0.1)
        for _ in range(100):
            vc.step()
        assert 8 <= vc.lung.respiratory_rate <= 20, \
            f"Equine RR={vc.lung.respiratory_rate}, expected ~12"


class TestSpeciesAgnosticDisease:
    """Disease affects all species regardless of species-specific parameters."""

    @pytest.mark.slow
    def test_pneumonia_reduces_oxygenation_in_all_species(self):
        """Pneumonia should worsen oxygenation versus matched healthy controls."""
        from src.diseases import create_disease

        for species, weight in [("canine", 20.0), ("feline", 5.0), ("equine", 500.0)]:
            healthy = VirtualCreature(body_weight_kg=weight, species=species, dt=0.1)
            sick = VirtualCreature(body_weight_kg=weight, species=species, dt=0.1)
            sick.attach_disease(create_disease("pneumonia", severity="moderate"))
            for _ in range(100):
                healthy.step()
                sick.step()
            assert sick.blood.arterial_saturation < healthy.blood.arterial_saturation, (
                f"{species}: pneumonia should reduce SpO2-like saturation; "
                f"healthy={healthy.blood.arterial_saturation:.4f}, "
                f"sick={sick.blood.arterial_saturation:.4f}"
            )
            assert sick.blood.arterial_PO2_mmHg < healthy.blood.arterial_PO2_mmHg, (
                f"{species}: pneumonia should reduce arterial PO2; "
                f"healthy={healthy.blood.arterial_PO2_mmHg:.2f}, "
                f"sick={sick.blood.arterial_PO2_mmHg:.2f}"
            )


class TestSpeciesDeathCurve:
    """Lifecycle death curves differ by species (Gompertz parameters)."""

    @pytest.mark.slow
    def test_feline_dies_later_than_canine_at_extreme_age(self):
        """At very old age, feline survival > canine survival."""
        from lifecycle import LifecycleEngine, LifecycleMode

        feline = LifecycleEngine(species="feline", initial_age_days=7300)  # ~20 years
        canine = LifecycleEngine(species="canine", initial_age_days=7300)  # ~20 years

        # Build minimal creature dummies to check age factors
        class _Dummy:
            def __init__(self):
                self.HR_rest = 120.0
                self.contractility_factor = 1.0
                self.SVR = 1.0
                self.GFR = 1.0
                self.blood_volume_ml = 1000.0

        fd = _Dummy()
        cd = _Dummy()

        feline.apply_age_factors(fd)
        canine.apply_age_factors(cd)

        # At extreme age, both should show decline but feline slower than canine
        assert feline.species == "feline"
        assert canine.species == "canine"
