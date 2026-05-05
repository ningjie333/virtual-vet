"""
Unit tests for LungModule — pulmonary gas exchange simulation.

Covers:
- Alveolar gas equation
- O2/CO2 diffusion directionality
- Oxygen saturation curve (Hill equation)
- Respiratory compensation (hypercapnia / hypoxia / normal)
- pH calculation (Henderson-Hasselbalch)
- A-a gradient
- V/Q ratio effect
"""

import sys
import os
import math
import pytest

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lung import LungModule
from blood import BloodCompartment
from parameters import (
    LUNG_DIFFUSION_COEFFICIENT,
    RESPIRATORY_RATE_REST,
    RESPIRATORY_RATE_STRESS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def blood():
    """Standard ~20 kg canine blood compartment."""
    bv = 86.0 * 20.0  # total_blood_volume_ml
    return BloodCompartment(bv)


@pytest.fixture
def lung(blood):
    """Standard lung module (20 kg canine)."""
    return LungModule(
        weight_kg=20.0,
        blood=blood,
        diffusion_coef=LUNG_DIFFUSION_COEFFICIENT,
    )


# ---------------------------------------------------------------------------
# Alveolar gas equation tests
# ---------------------------------------------------------------------------

class TestAlveolarGasEquation:
    def test_normal(self, lung):
        """With normal inputs (FiO2=0.21, PACO2=40, R=0.8), PAO2 ~100 mmHg."""
        PAO2 = lung._alveolar_gas_equation(RR=18, Vt=240, PACO2=40)
        assert 95 <= PAO2 <= 105, f"PAO2={PAO2}, expected ~100 mmHg"

    def test_high_PACO2(self, lung):
        """Higher PACO2 should result in lower PAO2 (inverse relationship)."""
        PAO2_normal = lung._alveolar_gas_equation(RR=18, Vt=240, PACO2=40)
        PAO2_high = lung._alveolar_gas_equation(RR=18, Vt=240, PACO2=60)
        assert PAO2_high < PAO2_normal, (
            f"PAO2 at PACO2=60 ({PAO2_high}) should be < PAO2 at PACO2=40 ({PAO2_normal})"
        )

    def test_clamped(self, lung):
        """PAO2 should be clamped between 50-150 mmHg."""
        # Extreme PACO2 values to attempt to push PAO2 out of range
        PAO2_low = lung._alveolar_gas_equation(RR=18, Vt=240, PACO2=200)
        PAO2_high = lung._alveolar_gas_equation(RR=18, Vt=240, PACO2=0)
        assert 50 <= PAO2_low <= 150, f"PAO2={PAO2_low} not in [50, 150]"
        assert 50 <= PAO2_high <= 150, f"PAO2={PAO2_high} not in [50, 150]"


# ---------------------------------------------------------------------------
# Oxygen saturation curve tests
# ---------------------------------------------------------------------------

class TestOxygenSaturationCurve:
    def test_high_PO2(self, lung):
        """PO2=95 should give saturation ~0.97 (normal arterial)."""
        sat = lung._oxygen_saturation_curve(95)
        assert 0.95 <= sat <= 0.99, f"Sat at PO2=95: {sat}, expected ~0.97"

    def test_low_PO2(self, lung):
        """PO2=40 should give saturation ~0.73-0.78 (mixed venous).

        With P50=26.6, n=2.8, PO2=40 yields ~0.758 via Hill equation.
        """
        sat = lung._oxygen_saturation_curve(40)
        assert 0.73 <= sat <= 0.78, f"Sat at PO2=40: {sat}, expected 0.73-0.78"

    def test_P50(self, lung):
        """PO2=26.6 (P50) should give saturation ≈ 0.50."""
        sat = lung._oxygen_saturation_curve(26.6)
        assert 0.48 <= sat <= 0.52, f"Sat at P50: {sat}, expected ~0.50"

    def test_clamped(self, lung):
        """Saturation should be between 0.0 and 1.0."""
        sat_zero = lung._oxygen_saturation_curve(0)
        sat_high = lung._oxygen_saturation_curve(1000)
        assert 0.0 <= sat_zero <= 1.0, f"Sat at PO2=0: {sat_zero}"
        assert 0.0 <= sat_high <= 1.0, f"Sat at PO2=1000: {sat_high}"
        # PO2=0 should be essentially zero saturation
        assert sat_zero == 0.0, f"Sat at PO2=0 should be 0, got {sat_zero}"


# ---------------------------------------------------------------------------
# Gas diffusion directionality tests
# ---------------------------------------------------------------------------

class TestDiffusionDirectionality:
    def test_oxygen_diffusion_direction(self, lung, blood):
        """When alveolar_PO2 > arterial_PO2, O2 should diffuse into blood (positive VO2)."""
        lung.alveolar_PO2 = 100.0
        blood.arterial_PO2_mmHg = 40.0
        VO2 = lung._compute_oxygen_diffusion()
        assert VO2 > 0, f"VO2={VO2}, expected positive (alveolar 100 > arterial 40)"

    def test_CO2_diffusion_direction(self, lung, blood):
        """When venous_PCO2 > alveolar_PCO2, CO2 should diffuse into alveoli (positive VCO2)."""
        blood.venous_PCO2_mmHg = 46.0
        lung.alveolar_PCO2 = 40.0
        VCO2 = lung._compute_CO2_diffusion()
        assert VCO2 > 0, f"VCO2={VCO2}, expected positive (venous 46 > alveolar 40)"


# ---------------------------------------------------------------------------
# Respiratory compensation tests
# ---------------------------------------------------------------------------

class TestRespiratoryCompensation:
    def test_high_PCO2(self, lung, blood):
        """PCO2=50 (above target 40) should increase RR."""
        blood.arterial_PCO2_mmHg = 50.0
        blood.arterial_PO2_mmHg = 95.0  # normal PO2
        rr_before = lung.respiratory_rate
        lung._respiratory_compensation(
            arterial_PCO2=50.0, arterial_PO2=95.0, dt=60.0
        )
        assert lung.respiratory_rate > rr_before, (
            f"RR did not increase: {rr_before} -> {lung.respiratory_rate}"
        )

    def test_low_PO2(self, lung, blood):
        """PO2=60 (below 80 threshold) should increase RR (hypoxic drive)."""
        blood.arterial_PCO2_mmHg = 40.0  # normal PCO2
        blood.arterial_PO2_mmHg = 60.0
        rr_before = lung.respiratory_rate
        lung._respiratory_compensation(
            arterial_PCO2=40.0, arterial_PO2=60.0, dt=60.0
        )
        assert lung.respiratory_rate > rr_before, (
            f"RR did not increase: {rr_before} -> {lung.respiratory_rate}"
        )

    def test_normal(self, lung, blood):
        """PCO2=40, PO2=95 should not significantly change RR."""
        blood.arterial_PCO2_mmHg = 40.0
        blood.arterial_PO2_mmHg = 95.0
        lung.respiratory_rate = RESPIRATORY_RATE_REST
        rr_before = lung.respiratory_rate
        lung._respiratory_compensation(
            arterial_PCO2=40.0, arterial_PO2=95.0, dt=60.0
        )
        # Allow at most 0.5 /min drift due to floating-point
        assert abs(lung.respiratory_rate - rr_before) < 0.5, (
            f"RR changed significantly: {rr_before} -> {lung.respiratory_rate}"
        )


# ---------------------------------------------------------------------------
# pH calculation tests
# ---------------------------------------------------------------------------

class TestPHCalculation:
    def test_normal(self, lung, blood):
        """PCO2=40, HCO3=24 should give pH ≈ 7.40."""
        blood.arterial_PCO2_mmHg = 40.0
        lung._update_arterial_pH()
        assert 7.38 <= blood.arterial_pH <= 7.42, (
            f"pH={blood.arterial_pH}, expected ~7.40"
        )

    def test_respiratory_acidosis(self, lung, blood):
        """PCO2=60 should give pH < 7.40 (acute respiratory acidosis)."""
        blood.arterial_PCO2_mmHg = 60.0
        lung._update_arterial_pH()
        assert blood.arterial_pH < 7.40, (
            f"pH={blood.arterial_pH}, expected < 7.40 for PCO2=60"
        )

    def test_respiratory_alkalosis(self, lung, blood):
        """PCO2=25 should give pH > 7.40 (respiratory alkalosis)."""
        blood.arterial_PCO2_mmHg = 25.0
        lung._update_arterial_pH()
        assert blood.arterial_pH > 7.40, (
            f"pH={blood.arterial_pH}, expected > 7.40 for PCO2=25"
        )

    def test_clamped(self, lung, blood):
        """pH should be between 7.0 and 7.8."""
        # Extreme PCO2 values
        blood.arterial_PCO2_mmHg = 200.0
        lung._update_arterial_pH()
        assert 7.0 <= blood.arterial_pH <= 7.8, (
            f"pH={blood.arterial_pH} not in [7.0, 7.8] for PCO2=200"
        )

        blood.arterial_PCO2_mmHg = 1.0
        lung._update_arterial_pH()
        assert 7.0 <= blood.arterial_pH <= 7.8, (
            f"pH={blood.arterial_pH} not in [7.0, 7.8] for PCO2=1"
        )


# ---------------------------------------------------------------------------
# A-a gradient test
# ---------------------------------------------------------------------------

class TestAAGradient:
    def test_positive_and_reasonable(self, lung, blood):
        """A-a gradient should be positive and in reasonable range (5-40 mmHg)."""
        lung.compute(dt=60.0, cardiac_output=1700.0)
        gradient = lung.alveolar_PO2 - blood.arterial_PO2_mmHg
        assert gradient > 0, (
            f"A-a gradient={gradient}, should be positive (alveolar > arterial)"
        )
        assert 5 <= gradient <= 40, (
            f"A-a gradient={gradient} mmHg, expected 5-40 range"
        )


# ---------------------------------------------------------------------------
# V/Q ratio effect test
# ---------------------------------------------------------------------------

class TestVQRatioEffect:
    def test_VQ_ratio_reduces_efficiency(self, lung, blood):
        """Lower V/Q ratio should reduce gas exchange efficiency."""
        # Normal V/Q
        lung.VQ_ratio = 0.8
        lung.alveolar_PO2 = 100.0
        lung.alveolar_PCO2 = 40.0
        blood.arterial_PO2_mmHg = 40.0
        blood.venous_PCO2_mmHg = 46.0
        VO2_normal = lung._compute_oxygen_diffusion()
        VCO2_normal = lung._compute_CO2_diffusion()

        # Low V/Q
        lung.VQ_ratio = 0.3
        VO2_low = lung._compute_oxygen_diffusion()
        VCO2_low = lung._compute_CO2_diffusion()

        assert VO2_low < VO2_normal, (
            f"VO2 at low V/Q ({VO2_low}) should be < VO2 at normal V/Q ({VO2_normal})"
        )
        assert VCO2_low < VCO2_normal, (
            f"VCO2 at low V/Q ({VCO2_low}) should be < VCO2 at normal V/Q ({VCO2_normal})"
        )
