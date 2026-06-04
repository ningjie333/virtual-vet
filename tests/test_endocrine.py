"""
EndocrineModule unit tests — thyroid, pancreas, adrenal, growth axes.

Covers src/endocrine.py (615 lines) which has:
  - 5 hormone axes: thyroid (T3/T4), pancreas (insulin/glucagon),
    adrenal (cortisol), growth (GH/IGF-1), parathyroid (PTH/Ca²⁺)
  - derivatives() API for ODE state integration
  - Key outputs: T3_factor, metabolic_rate, insulin_factor, glucagon_factor,
    cortisol_factor
"""

import sys
sys.path.insert(0, "src")

import pytest
from endocrine import EndocrineModule
from blood import BloodCompartment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_endocrine():
    """Fresh EndocrineModule, 20 kg canine."""
    blood = BloodCompartment(total_volume_ml=1720.0, plasma_fraction=0.55)
    return EndocrineModule(weight_kg=20.0, blood=blood)


# ---------------------------------------------------------------------------
# TestThyroidAxis
# ---------------------------------------------------------------------------

class TestThyroidAxis:
    """T3/T4 axis: metabolic_rate, T3_factor output."""

    def test_T3_at_baseline_normal_metabolic_rate(self):
        """Fresh module → T3 ≈ baseline, metabolic_rate ≈ 1.0."""
        e = make_endocrine()
        assert 80.0 <= e.T3_ng_dL <= 120.0, f"T3={e.T3_ng_dL}, expected ~100"
        assert e.metabolic_rate == pytest.approx(1.0, abs=0.2)

    def test_T3_factor_equals_baseline_at_rest(self):
        """T3_factor ≈ 1.0 at baseline."""
        e = make_endocrine()
        assert e.T3_factor == pytest.approx(1.0, abs=0.1)

    def test_T3_factor_output_key_exists(self):
        """summary() includes T3_factor."""
        e = make_endocrine()
        summary = e.summary()
        assert "T3_factor" in summary, f"Missing T3_factor in {summary.keys()}"


# ---------------------------------------------------------------------------
# TestPancreasAxis
# ---------------------------------------------------------------------------

class TestPancreasAxis:
    """Insulin / glucagon axis: blood glucose drives secretion."""

    def test_insulin_baseline(self):
        """Fresh module → insulin ≈ baseline (8-16 uU/mL)."""
        e = make_endocrine()
        assert 8.0 <= e.insulin_uU_mL <= 16.0, f"insulin={e.insulin_uU_mL}"

    def test_insulin_rises_with_high_glucose(self):
        """Blood glucose=20 mmol/L → insulin rises."""
        e = make_endocrine()
        e.blood.glucose_mmol_L = 20.0
        for _ in range(300):
            e.derivatives(dt=0.1)
        assert e.insulin_uU_mL > 15.0, \
            f"High glucose should raise insulin, got {e.insulin_uU_mL}"

    def test_glucagon_rises_with_low_glucose(self):
        """Blood glucose=3 mmol/L → glucagon rises above baseline."""
        e = make_endocrine()
        baseline = e.glucagon_pg_mL
        e.blood.glucose_mmol_L = 3.0
        for _ in range(300):
            e.derivatives(dt=0.1)
        assert e.glucagon_pg_mL > baseline, \
            f"Low glucose should raise glucagon above {baseline}, got {e.glucagon_pg_mL}"

    def test_insulin_and_glucagon_inversely_coupled(self):
        """At high glucose: insulin_factor rises, glucagon_factor falls."""
        e = make_endocrine()
        e.blood.glucose_mmol_L = 20.0
        for _ in range(300):
            e.derivatives(dt=0.1)
        assert e.insulin_factor >= 1.0, \
            f"High glucose: insulin_factor >=1, got {e.insulin_factor}"
        assert e.glucagon_factor <= 1.0, \
            f"High glucose: glucagon_factor <=1, got {e.glucagon_factor}"


# ---------------------------------------------------------------------------
# TestAdrenalAxis
# ---------------------------------------------------------------------------

class TestAdrenalAxis:
    """Cortisol axis: stress → HPA activation → cortisol rise."""

    def test_cortisol_baseline(self):
        """Fresh module → cortisol ≈ baseline (2-10 ug/dL)."""
        e = make_endocrine()
        assert 2.0 <= e.cortisol_ug_dL <= 10.0, f"cortisol={e.cortisol_ug_dL}"

    def test_cortisol_rises_with_stress(self):
        """add_stress() → cortisol rises above baseline."""
        e = make_endocrine()
        baseline = e.cortisol_ug_dL
        e.add_stress(0.5)
        for _ in range(300):
            e.derivatives(dt=0.1)
        assert e.cortisol_ug_dL > baseline, \
            f"Stress should raise cortisol above {baseline}, got {e.cortisol_ug_dL}"

    def test_cortisol_factor_in_summary(self):
        """summary() includes cortisol_factor."""
        e = make_endocrine()
        summary = e.summary()
        assert "cortisol_factor" in summary


# ---------------------------------------------------------------------------
# TestEndocrineOutputs
# ---------------------------------------------------------------------------

class TestEndocrineOutputs:
    """derivatives() and summary() return all expected keys."""

    def test_derivatives_returns_two_tuple(self):
        """derivatives() returns (dydt, outputs)."""
        e = make_endocrine()
        result = e.derivatives(dt=0.0)
        assert isinstance(result, tuple) and len(result) == 2

    def test_summary_keys(self):
        """summary() includes all key hormone values."""
        e = make_endocrine()
        s = e.summary()
        for key in ["T3_ng_dL", "metabolic_rate", "T3_factor",
                    "insulin_uU_mL", "glucagon_pg_mL", "cortisol_ug_dL"]:
            assert key in s, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# TestEndocrineIntegration
# ---------------------------------------------------------------------------

class TestEndocrineIntegration:
    """Full integration: EndocrineModule + VirtualCreature."""

    @pytest.mark.slow
    def test_hypothyroid_T3_low_decreases_metabolic_rate(self):
        """Force T3 very low on creature → metabolic_rate < 1.0."""
        from simulation import VirtualCreature
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        for _ in range(50):
            vc.step()

        # Reduce T3 to hypothyroid range (~30 ng/dL = 70% below baseline)
        vc.endocrine.T3_ng_dL = 30.0
        for _ in range(300):
            vc.endocrine.derivatives(dt=0.1)
            vc.endocrine.compute(dt=0.1)

        assert vc.endocrine.metabolic_rate < 0.9, \
            f"Hypothyroid should reduce metabolic_rate, got {vc.endocrine.metabolic_rate}"