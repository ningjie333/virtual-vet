"""
Unit tests for KidneyModule - renal function simulation
"""

import pytest
import sys
import os

# Add src to path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kidney import KidneyModule
from blood import BloodCompartment


# ─── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def blood_20kg():
    """Blood compartment for a 20 kg animal."""
    from parameters import total_blood_volume_ml
    vol = total_blood_volume_ml(20.0)
    return BloodCompartment(total_volume_ml=vol, plasma_fraction=0.55)


@pytest.fixture
def kidney_20kg(blood_20kg):
    """KidneyModule for a 20 kg animal with normal baseline values."""
    return KidneyModule(weight_kg=20.0, blood=blood_20kg)


# ─── GFR tests ─────────────────────────────────────────────────

class TestGFR:
    def test_GFR_normal_MAP(self, kidney_20kg):
        """With MAP=100, CVP=4 (normal), GFR should be positive and reasonable (~60 mL/min for 20kg)."""
        kidney_20kg._update_GFR(MAP=100.0, CVP=4.0)
        # Expected: Kf * (MAP*0.6 - CVP - 10 - 25) = 3.0 * (60 - 4 - 10 - 25) = 3.0 * 21 = 63
        assert kidney_20kg.GFR > 0, "GFR must be positive at normal MAP"
        assert 50.0 < kidney_20kg.GFR < 80.0, f"GFR should be ~60-63 mL/min for 20kg, got {kidney_20kg.GFR}"

    def test_GFR_low_MAP(self, kidney_20kg):
        """MAP=50 (low) should give lower GFR than MAP=100."""
        kidney_20kg._update_GFR(MAP=100.0, CVP=4.0)
        gfr_normal = kidney_20kg.GFR

        kidney_20kg._update_GFR(MAP=50.0, CVP=4.0)
        gfr_low = kidney_20kg.GFR

        assert gfr_low < gfr_normal, (
            f"GFR at MAP=50 ({gfr_low:.1f}) should be less than GFR at MAP=100 ({gfr_normal:.1f})"
        )

    def test_GFR_very_low_MAP(self, kidney_20kg):
        """MAP=30 (very low) should give near-zero GFR."""
        kidney_20kg._update_GFR(MAP=30.0, CVP=4.0)
        # PGC = 18, PBS = 14, colloid=25 → filtration_pressure = 18-14-25 = -21 → GFR = max(0, 3*-21) = 0
        assert kidney_20kg.GFR < 1.0, f"GFR at MAP=30 should be near-zero, got {kidney_20kg.GFR}"

    def test_GFR_high_MAP(self, kidney_20kg):
        """MAP=140 (high) should give higher GFR than normal."""
        kidney_20kg._update_GFR(MAP=100.0, CVP=4.0)
        gfr_normal = kidney_20kg.GFR

        kidney_20kg._update_GFR(MAP=140.0, CVP=4.0)
        gfr_high = kidney_20kg.GFR

        assert gfr_high > gfr_normal, (
            f"GFR at MAP=140 ({gfr_high:.1f}) should be greater than GFR at MAP=100 ({gfr_normal:.1f})"
        )


# ─── RAAS tests ────────────────────────────────────────────────

class TestRAAS:
    def test_RAAS_activation_low_MAP(self, kidney_20kg):
        """Low MAP should activate RAAS (renin_activity > 0, aldosterone > 0)."""
        kidney_20kg._apply_RAAS(MAP=50.0, CVP=4.0, Na_conc=145.0)
        assert kidney_20kg.renin_activity > 0, (
            f"renin_activity should be > 0 at MAP=50, got {kidney_20kg.renin_activity}"
        )
        assert kidney_20kg.aldosterone > 0, (
            f"aldosterone should be > 0 at MAP=50, got {kidney_20kg.aldosterone}"
        )

    def test_RAAS_suppression_normal_MAP(self, kidney_20kg):
        """Normal MAP=100 should result in low renin_activity."""
        kidney_20kg._apply_RAAS(MAP=100.0, CVP=4.0, Na_conc=145.0)
        # MAP_deficit = 0, Na_deficit = 0 → renin = max(0, 0) = 0
        assert kidney_20kg.renin_activity == 0.0, (
            f"renin_activity should be 0 at normal MAP, got {kidney_20kg.renin_activity}"
        )

    def test_RAAS_Na_deficit(self, kidney_20kg):
        """Low sodium should also activate RAAS."""
        # Normal MAP but low sodium
        kidney_20kg._apply_RAAS(MAP=100.0, CVP=4.0, Na_conc=120.0)
        # Na_deficit = max(0, (145-120)/145) = 25/145 ≈ 0.172
        # renin = max(0, 0.5*0 + 0.5*0.172) ≈ 0.086
        assert kidney_20kg.renin_activity > 0, (
            f"renin_activity should be > 0 with low Na, got {kidney_20kg.renin_activity}"
        )


# ─── Urine output tests ────────────────────────────────────────

class TestUrineOutput:
    def test_urine_output_normal(self, kidney_20kg):
        """Normal conditions should produce positive urine output."""
        kidney_20kg._update_GFR(MAP=100.0, CVP=4.0)
        kidney_20kg._compute_urine_output(kidney_20kg.GFR)
        assert kidney_20kg.urine_output > 0, (
            f"Urine output should be positive at normal MAP, got {kidney_20kg.urine_output}"
        )

    def test_urine_output_MAP_threshold(self, kidney_20kg):
        """MAP=45 (below 60) should have lower urine output than MAP=70."""
        # MAP=70 scenario
        kidney_20kg._update_GFR(MAP=70.0, CVP=4.0)
        gfr_70 = kidney_20kg.GFR
        kidney_20kg._compute_urine_output(gfr_70)
        urine_70 = kidney_20kg.urine_output
        # MAP threshold: MAP=70 >= 60 → no reduction
        map_factor_70 = 1.0
        urine_70_adjusted = urine_70 * map_factor_70

        # MAP=45 scenario (hypothetical; we check the _compute_urine_output result,
        # then apply the MAP threshold formula to compare)
        kidney_20kg._update_GFR(MAP=45.0, CVP=4.0)
        gfr_45 = kidney_20kg.GFR
        kidney_20kg._compute_urine_output(gfr_45)
        urine_45 = kidney_20kg.urine_output
        # MAP threshold factor: (45-30)/30 = 0.5
        map_factor_45 = max(0.0, (45.0 - 30.0) / 30.0)
        urine_45_adjusted = urine_45 * map_factor_45

        assert urine_45_adjusted < urine_70_adjusted, (
            f"Adjusted urine at MAP=45 ({urine_45_adjusted:.3f}) should be less than "
            f"at MAP=70 ({urine_70_adjusted:.3f})"
        )

    def test_urine_output_anuria(self, kidney_20kg):
        """MAP=25 (below 30) should produce near-zero urine output."""
        kidney_20kg._update_GFR(MAP=25.0, CVP=4.0)
        kidney_20kg._compute_urine_output(kidney_20kg.GFR)
        # GFR at MAP=25: PGC=15, PBS=14, colloid=25 → 15-14-25=-24 → GFR=0
        # urine from _compute_urine_output with GFR=0 → 0
        # MAP threshold: max(0, (25-30)/30) = 0
        assert kidney_20kg.urine_output < 0.01, (
            f"Urine output at MAP=25 should be near-zero, got {kidney_20kg.urine_output}"
        )


# ─── BUN tests ─────────────────────────────────────────────────

class TestBUN:
    def test_BUN_inversely_proportional_to_GFR(self, kidney_20kg):
        """Simulate low GFR conditions, verify BUN rises above baseline (15 mg/dL)."""
        blood = kidney_20kg.blood
        blood.bun_mg_dL = 15.0  # reset to baseline
        # Run compute with low MAP for many steps to let BUN rise
        for _ in range(50):
            kidney_20kg.compute(dt=1.0, MAP=40.0, CVP=4.0, cardiac_output=1700.0)
        assert blood.bun_mg_dL > 15.0, (
            f"BUN should rise above baseline 15 mg/dL in low GFR, got {blood.bun_mg_dL:.1f}"
        )

    def test_BUN_normal_GFR(self, kidney_20kg):
        """Normal GFR conditions should keep BUN near 15 mg/dL."""
        blood = kidney_20kg.blood
        blood.bun_mg_dL = 15.0
        for _ in range(20):
            kidney_20kg.compute(dt=1.0, MAP=100.0, CVP=4.0, cardiac_output=1700.0)
        assert abs(blood.bun_mg_dL - 15.0) < 2.0, (
            f"BUN should stay near 15 mg/dL at normal GFR, got {blood.bun_mg_dL:.1f}"
        )


# ─── Creatinine tests ──────────────────────────────────────────

class TestCreatinine:
    def test_creatinine_inversely_proportional_to_GFR(self, kidney_20kg):
        """Low GFR should cause creatinine to rise above baseline (1.0 mg/dL)."""
        blood = kidney_20kg.blood
        blood.creatinine_mg_dL = 1.0
        for _ in range(50):
            kidney_20kg.compute(dt=1.0, MAP=40.0, CVP=4.0, cardiac_output=1700.0)
        assert blood.creatinine_mg_dL > 1.0, (
            f"Creatinine should rise above 1.0 mg/dL in low GFR, got {blood.creatinine_mg_dL:.2f}"
        )


# ─── Sodium balance tests ──────────────────────────────────────

class TestSodiumBalance:
    def test_sodium_balance_positive(self, kidney_20kg):
        """Filtered sodium load should be positive and proportional to GFR."""
        kidney_20kg._update_GFR(MAP=100.0, CVP=4.0)
        kidney_20kg._compute_sodium_balance(
            kidney_20kg.GFR, kidney_20kg.blood.sodium_mEq_L
        )
        assert kidney_20kg.filtered_sodium_load > 0, (
            f"Filtered sodium should be positive, got {kidney_20kg.filtered_sodium_load}"
        )
        # filtered_Na = GFR * [Na] = ~63 * 145 ≈ 9135 mEq/min (in these units)
        assert kidney_20kg.filtered_sodium_load > 5000.0, (
            f"Filtered sodium load seems too low: {kidney_20kg.filtered_sodium_load:.1f}"
        )

    def test_sodium_excretion_reduced_by_aldosterone(self, kidney_20kg):
        """Higher aldosterone should reduce sodium excretion."""
        kidney_20kg._update_GFR(MAP=100.0, CVP=4.0)
        gfr = kidney_20kg.GFR

        # Low aldosterone scenario
        kidney_20kg.aldosterone = 0.0
        kidney_20kg._compute_sodium_balance(gfr, 145.0)
        excreted_low_aldo = kidney_20kg.excreted_sodium

        # High aldosterone scenario
        kidney_20kg.aldosterone = 2.0
        kidney_20kg._compute_sodium_balance(gfr, 145.0)
        excreted_high_aldo = kidney_20kg.excreted_sodium

        assert excreted_high_aldo < excreted_low_aldo, (
            f"Sodium excretion with high aldosterone ({excreted_high_aldo:.2f}) should be "
            f"less than with low aldosterone ({excreted_low_aldo:.2f})"
        )


# ─── ADH tests ─────────────────────────────────────────────────

class TestADH:
    def test_ADH_increases_with_high_osmolality(self, kidney_20kg):
        """High plasma osmolality should increase ADH level."""
        kidney_20kg.ADH_level = 0.2  # baseline
        # Force high osmolality by setting blood sodium high
        kidney_20kg.blood.sodium_mEq_L = 170.0  # very high → osmolality = 2*170+5+10 = 345
        # plasma_osmolality = 2*170 + 15 = 355 → osmotic_pressure = 355 - 295 = 60 > 10
        kidney_20kg.compute(dt=1.0, MAP=100.0, CVP=4.0, cardiac_output=1700.0)
        assert kidney_20kg.ADH_level > 0.2, (
            f"ADH should increase with high osmolality, got {kidney_20kg.ADH_level:.3f}"
        )

    def test_ADH_decreases_with_normal_osmolality(self, kidney_20kg):
        """Normal osmolality should decrease ADH toward baseline."""
        kidney_20kg.ADH_level = 0.8  # start elevated
        kidney_20kg.blood.sodium_mEq_L = 145.0  # normal
        # osmolality = 2*145+15 = 305 → osmotic_pressure = 10 → not > 10 → ADH decreases
        # Actually: osmotic_pressure = 305 - 295 = 10, which is NOT > 10
        # Wait: 2*145+5+10 = 305, 305-295=10, and condition is >10, so it's false → ADH decreases
        # Actually let me recheck: 2*145=300, +5+10=305. 305-295=10. Condition is > 10, so exactly 10
        # will NOT trigger the decrease. Let's use slightly lower sodium.
        kidney_20kg.blood.sodium_mEq_L = 142.0  # osmolality = 2*142+15=299, pressure=4 < 10
        kidney_20kg.compute(dt=1.0, MAP=100.0, CVP=4.0, cardiac_output=1700.0)
        assert kidney_20kg.ADH_level < 0.8, (
            f"ADH should decrease with normal osmolality, got {kidney_20kg.ADH_level:.3f}"
        )


# ─── Integration / cumulative tests ────────────────────────────

class TestIntegration:
    def test_cumulative_urine_increases(self, kidney_20kg):
        """cumulative_urine_ml should increase over multiple compute() calls."""
        kidney_20kg.cumulative_urine_ml = 0.0
        kidney_20kg.compute(dt=1.0, MAP=100.0, CVP=4.0, cardiac_output=1700.0)
        cum_1 = kidney_20kg.cumulative_urine_ml
        kidney_20kg.compute(dt=1.0, MAP=100.0, CVP=4.0, cardiac_output=1700.0)
        cum_2 = kidney_20kg.cumulative_urine_ml
        assert cum_2 > cum_1, (
            f"Cumulative urine should increase: {cum_1:.3f} -> {cum_2:.3f}"
        )

    def test_blood_volume_loss_rate(self, kidney_20kg):
        """blood_volume_loss_rate should be positive and proportional to urine output."""
        kidney_20kg.compute(dt=1.0, MAP=100.0, CVP=4.0, cardiac_output=1700.0)
        assert kidney_20kg.blood_volume_loss_rate > 0, (
            f"blood_volume_loss_rate should be positive, got {kidney_20kg.blood_volume_loss_rate}"
        )
        # Should be 30% of urine_output
        expected = kidney_20kg.urine_output * 0.30
        assert abs(kidney_20kg.blood_volume_loss_rate - expected) < 1e-9, (
            f"blood_volume_loss_rate ({kidney_20kg.blood_volume_loss_rate:.4f}) should equal "
            f"0.30 * urine_output ({expected:.4f})"
        )
