"""
Unit tests for HeartModule class in src/heart.py
"""

from src.blood import BloodCompartment
from src.heart import HeartModule
from src.noble_purkinje import NoblePurkinjeFiber


def _make_heart(weight_kg=20.0):
    """Helper: create a BloodCompartment + HeartModule for a given weight."""
    bv = 86.0 * weight_kg  # total_blood_volume_ml
    blood = BloodCompartment(total_volume_ml=bv)
    heart = HeartModule(weight_kg=weight_kg, blood=blood)
    return heart


def _stabilize(heart, steps=50, dt=0.1, svr_factor=1.0):
    """Run compute() for `steps` iterations to let state settle."""
    result = None
    for _ in range(steps):
        result = heart.compute(dt=dt, svr_factor=svr_factor)
    return result


def test_normal_steady_state():
    """20kg dog at rest: HR ~85 bpm, MAP ~100 mmHg, CO in 1500-2000 mL/min."""
    heart = _make_heart(weight_kg=20.0)
    result = _stabilize(heart, steps=60)

    assert 75 <= result["heart_rate_bpm"] <= 100, (
        f"HR {result['heart_rate_bpm']} bpm outside expected ~85 range"
    )
    assert 90 <= result["MAP_mmHg"] <= 115, (
        f"MAP {result['MAP_mmHg']} mmHg outside expected ~100 range"
    )
    assert 1500 <= result["cardiac_output_ml_min"] <= 2500, (
        f"CO {result['cardiac_output_ml_min']} mL/min outside reasonable range"
    )


def test_frank_starling_low_volume():
    """Reducing blood volume to 50% should decrease SV compared to normal."""
    # Normal heart
    heart_normal = _make_heart(weight_kg=20.0)
    _stabilize(heart_normal, steps=50)
    sv_normal = heart_normal.stroke_volume

    # Low-volume heart
    heart_low = _make_heart(weight_kg=20.0)
    heart_low.circulating_volume_ml = heart_low.total_BV * 0.5
    _stabilize(heart_low, steps=50)
    sv_low = heart_low.stroke_volume

    assert sv_low < sv_normal, (
        f"SV at 50% volume ({sv_low:.2f}) should be less than normal SV ({sv_normal:.2f})"
    )


def test_frank_starling_high_volume():
    """Increasing blood volume to 110% should increase SV compared to normal."""
    # Normal heart
    heart_normal = _make_heart(weight_kg=20.0)
    _stabilize(heart_normal, steps=50)
    sv_normal = heart_normal.stroke_volume

    # High-volume heart
    heart_high = _make_heart(weight_kg=20.0)
    heart_high.circulating_volume_ml = heart_high.total_BV * 1.1
    _stabilize(heart_high, steps=50)
    sv_high = heart_high.stroke_volume

    assert sv_high > sv_normal, (
        f"SV at 110% volume ({sv_high:.2f}) should exceed normal SV ({sv_normal:.2f})"
    )


def test_baroreceptor_low_map():
    """Artificially low MAP (60) should trigger sympathetic response: HR and SVR increase."""
    heart = _make_heart(weight_kg=20.0)
    _stabilize(heart, steps=50)

    hr_before = heart.heart_rate
    svr_before = heart.SVR

    # Feed a low MAP; use large dt so feedback has visible effect
    heart._baroreceptor_feedback(MAP=60.0, dt=5.0)

    assert heart.heart_rate > hr_before, (
        f"HR should increase after low MAP stimulus: before={hr_before:.1f}, after={heart.heart_rate:.1f}"
    )
    assert heart.SVR > svr_before, (
        f"SVR should increase after low MAP stimulus: before={svr_before:.3f}, after={heart.SVR:.3f}"
    )


def test_baroreceptor_high_map():
    """Artificially high MAP (140) should decrease HR (parasympathetic response)."""
    heart = _make_heart(weight_kg=20.0)
    _stabilize(heart, steps=50)

    hr_before = heart.heart_rate

    # Feed a high MAP
    heart._baroreceptor_feedback(MAP=140.0, dt=5.0)

    assert heart.heart_rate < hr_before, (
        f"HR should decrease after high MAP stimulus: before={hr_before:.1f}, after={heart.heart_rate:.1f}"
    )


def test_blood_volume_change_negative():
    """blood_volume_change(-200) should reduce circulating_volume_ml."""
    heart = _make_heart(weight_kg=20.0)
    initial = heart.circulating_volume_ml

    heart.blood_volume_change(-200.0)

    assert heart.circulating_volume_ml == initial - 200.0, (
        f"Expected {initial - 200.0}, got {heart.circulating_volume_ml}"
    )
    assert heart.blood_loss_ml == 200.0, (
        f"Expected blood_loss_ml=200.0, got {heart.blood_loss_ml}"
    )


def test_blood_volume_change_positive():
    """blood_volume_change(+300) should increase circulating_volume and track fluid_infused_ml."""
    heart = _make_heart(weight_kg=20.0)
    initial = heart.circulating_volume_ml

    heart.blood_volume_change(300.0)

    assert heart.circulating_volume_ml == initial + 300.0, (
        f"Expected {initial + 300.0}, got {heart.circulating_volume_ml}"
    )
    assert heart.fluid_infused_ml == 300.0, (
        f"Expected fluid_infused_ml=300.0, got {heart.fluid_infused_ml}"
    )


def test_blood_volume_floor():
    """blood_volume_change() should not let circulating_volume_ml go below 0."""
    heart = _make_heart(weight_kg=20.0)
    heart.circulating_volume_ml = 100.0

    heart.blood_volume_change(-500.0)

    assert heart.circulating_volume_ml == 0.0, (
        f"Expected floor of 0.0, got {heart.circulating_volume_ml}"
    )


def test_contractility_factor():
    """Setting contractility_factor to 0.5 should reduce SV vs normal (1.0)."""
    # Normal contractility
    heart_normal = _make_heart(weight_kg=20.0)
    _stabilize(heart_normal, steps=50)
    sv_normal = heart_normal.stroke_volume

    # Reduced contractility
    heart_weak = _make_heart(weight_kg=20.0)
    heart_weak.contractility_factor = 0.5
    _stabilize(heart_weak, steps=50)
    sv_weak = heart_weak.stroke_volume

    assert sv_weak < sv_normal, (
        f"SV with contractility 0.5 ({sv_weak:.2f}) should be less than normal ({sv_normal:.2f})"
    )


def test_svr_external_factor():
    """compute(dt, svr_factor=2.0) should produce higher MAP than svr_factor=1.0."""
    # Normal SVR factor
    heart1 = _make_heart(weight_kg=20.0)
    _stabilize(heart1, steps=50, svr_factor=1.0)
    map1 = heart1.mean_arterial_pressure

    # Elevated SVR factor
    heart2 = _make_heart(weight_kg=20.0)
    _stabilize(heart2, steps=50, svr_factor=2.0)
    map2 = heart2.mean_arterial_pressure

    assert map2 > map1, (
        f"MAP with SVR factor 2.0 ({map2:.1f}) should exceed MAP with factor 1.0 ({map1:.1f})"
    )


def test_hr_bounds():
    """HR should stay within 60-180 bpm even under extreme conditions."""
    heart = _make_heart(weight_kg=20.0)
    heart.circulating_volume_ml = heart.total_BV * 0.3  # extreme hypovolemia

    # Push with aggressive low-MAP feedback steps
    for _ in range(100):
        heart.compute(dt=0.1)
        heart._baroreceptor_feedback(MAP=40.0, dt=5.0)

    assert 60.0 <= heart.heart_rate <= 180.0, (
        f"HR {heart.heart_rate:.1f} bpm outside allowed bounds [60, 180]"
    )


def test_map_bounds():
    """MAP should stay within 30-180 mmHg (clamped in compute)."""
    heart = _make_heart(weight_kg=20.0)

    # Extreme SVR factor to push MAP hard
    result = _stabilize(heart, steps=20, svr_factor=10.0)

    assert 30.0 <= result["MAP_mmHg"] <= 180.0, (
        f"MAP {result['MAP_mmHg']} mmHg outside allowed bounds [30, 180]"
    )


# =============================================================================
#  正反馈回路测试：死亡螺旋 (Death Spiral)
# =============================================================================

class TestAcidosisContractilityFeedback:
    """pH < 7.2 时应抑制心肌收缩力，形成正反馈：酸中毒 → 收缩力↓ → MAP↓ → 乳酸↑ → pH↓↓"""

    def test_normal_ph_full_contractility(self):
        """pH = 7.4 时收缩力因子应为 1.0（无抑制）"""
        heart = _make_heart(weight_kg=20.0)
        heart.blood.arterial_pH = 7.40
        result = _stabilize(heart, steps=50)
        assert result["contractility_factor"] == 1.0

    def test_mild_acidosis_moderate_depression(self):
        """pH = 7.2 时收缩力应开始下降（约 70%）"""
        heart = _make_heart(weight_kg=20.0)
        heart.blood.arterial_pH = 7.20
        result = _stabilize(heart, steps=50)
        assert result["contractility_factor"] < 0.8

    def test_severe_acidosis_severe_depression(self):
        """pH = 7.0 时收缩力应严重抑制（约 30-40%）"""
        heart = _make_heart(weight_kg=20.0)
        heart.blood.arterial_pH = 7.00
        result = _stabilize(heart, steps=50)
        assert result["contractility_factor"] < 0.5

    def test_critical_acidosis_near_arrest(self):
        """pH = 6.8 时收缩力应接近最低值（约 10-20%）"""
        heart = _make_heart(weight_kg=20.0)
        heart.blood.arterial_pH = 6.80
        result = _stabilize(heart, steps=50)
        assert result["contractility_factor"] < 0.3

    def test_acidosis_reduces_map(self):
        """酸中毒心脏的 MAP 应显著低于正常心脏"""
        heart_normal = _make_heart(weight_kg=20.0)
        heart_normal.blood.arterial_pH = 7.40
        _stabilize(heart_normal, steps=50)

        heart_acid = _make_heart(weight_kg=20.0)
        heart_acid.blood.arterial_pH = 7.00
        _stabilize(heart_acid, steps=50)

        assert heart_acid.mean_arterial_pressure < heart_normal.mean_arterial_pressure, (
            f"Acidotic MAP ({heart_acid.mean_arterial_pressure:.1f}) should be < "
            f"normal MAP ({heart_normal.mean_arterial_pressure:.1f})"
        )

    def test_acidosis_reduces_sv(self):
        """酸中毒心脏的 SV 应显著低于正常心脏"""
        heart_normal = _make_heart(weight_kg=20.0)
        heart_normal.blood.arterial_pH = 7.40
        _stabilize(heart_normal, steps=50)

        heart_acid = _make_heart(weight_kg=20.0)
        heart_acid.blood.arterial_pH = 7.00
        _stabilize(heart_acid, steps=50)

        assert heart_acid.stroke_volume < heart_normal.stroke_volume, (
            f"Acidotic SV ({heart_acid.stroke_volume:.1f}) should be < "
            f"normal SV ({heart_normal.stroke_volume:.1f})"
        )


class TestHyperkalemiaCardiacToxicity:
    """K⁺ > 6.5 时应导致心动过缓，> 8.0 时停搏风险"""

    def test_normal_k_no_effect(self):
        """K⁺ = 4.2 时心率应正常"""
        heart = _make_heart(weight_kg=20.0)
        heart.blood.potassium_mEq_L = 4.2
        result = _stabilize(heart, steps=50)
        assert 75 <= result["heart_rate_bpm"] <= 100

    def test_moderate_hyperkalemia_mild_bradycardia(self):
        """K⁺ = 6.0 时心率应轻度下降"""
        heart_normal = _make_heart(weight_kg=20.0)
        heart_normal.blood.potassium_mEq_L = 4.2
        _stabilize(heart_normal, steps=50)

        heart_high_k = _make_heart(weight_kg=20.0)
        heart_high_k.blood.potassium_mEq_L = 6.0
        _stabilize(heart_high_k, steps=50)

        assert heart_high_k.heart_rate < heart_normal.heart_rate, (
            f"High K HR ({heart_high_k.heart_rate:.1f}) should be < "
            f"normal K HR ({heart_normal.heart_rate:.1f})"
        )

    def test_severe_hyperkalemia_bradycardia(self):
        """K⁺ = 7.5 时心率应明显过缓（< 60 bpm）"""
        heart = _make_heart(weight_kg=20.0)
        heart.blood.potassium_mEq_L = 7.5
        _stabilize(heart, steps=50)
        assert heart.heart_rate < 60, (
            f"K⁺=7.5 HR {heart.heart_rate:.1f} should be < 60 bpm"
        )

    def test_critical_hyperkalemia_near_asystole(self):
        """K⁺ = 9.0 时心率应接近停搏（< 20 bpm）"""
        heart = _make_heart(weight_kg=20.0)
        heart.blood.potassium_mEq_L = 9.0
        _stabilize(heart, steps=50)
        assert heart.heart_rate < 30, (
            f"K⁺=9.0 HR {heart.heart_rate:.1f} should be < 30 bpm"
        )


class TestCoronaryPerfusionFeedback:
    """MAP < 60 时冠脉灌注下降 → 心肌缺血 → 收缩力↓"""

    def test_normal_map_full_coronary_flow(self):
        """MAP > 60 时冠脉灌注因子应为 1.0"""
        heart = _make_heart(weight_kg=20.0)
        _stabilize(heart, steps=50)
        # MAP should be ~100, well above 60
        assert heart.mean_arterial_pressure > 60

    def test_hypovolemia_coronary_perfusion_reduces_contractility(self):
        """严重低血容量时冠脉灌注不足应降低收缩力"""
        heart_normal = _make_heart(weight_kg=20.0)
        _stabilize(heart_normal, steps=50)
        map_normal = heart_normal.mean_arterial_pressure

        heart_hypo = _make_heart(weight_kg=20.0)
        heart_hypo.circulating_volume_ml = heart_hypo.total_BV * 0.35
        _stabilize(heart_hypo, steps=50)
        map_hypo = heart_hypo.mean_arterial_pressure

        # 低血容量 MAP 应显著降低
        assert map_hypo < map_normal, (
            f"Hypovolemic MAP ({map_hypo:.1f}) should be < normal MAP ({map_normal:.1f})"
        )
        # 低血容量 SV 应降低
        assert heart_hypo.stroke_volume < heart_normal.stroke_volume

    def test_death_spiral_positive_feedback(self):
        """
        集成正反馈测试：酸中毒 + 低 MAP 应导致收缩力崩溃。
        模拟死亡螺旋：MAP↓ → 乳酸↑ → pH↓ → 收缩力↓ → MAP↓↓
        """
        # 正常心脏
        heart_normal = _make_heart(weight_kg=20.0)
        heart_normal.blood.arterial_pH = 7.40
        heart_normal.blood.lactate_mmol_L = 1.0
        _stabilize(heart_normal, steps=50)

        # 死亡螺旋心脏：低血容量 + 酸中毒 + 高乳酸
        heart_spiral = _make_heart(weight_kg=20.0)
        heart_spiral.circulating_volume_ml = heart_spiral.total_BV * 0.45
        heart_spiral.blood.arterial_pH = 7.05
        heart_spiral.blood.lactate_mmol_L = 6.0
        _stabilize(heart_spiral, steps=50)

        # 死亡螺旋心脏的 MAP 应显著低于正常
        assert heart_spiral.mean_arterial_pressure < heart_normal.mean_arterial_pressure * 0.7, (
            f"Spiral MAP ({heart_spiral.mean_arterial_pressure:.1f}) should be < 70% of "
            f"normal MAP ({heart_normal.mean_arterial_pressure:.1f})"
        )
        # 死亡螺旋心脏的 CO 应显著降低
        assert heart_spiral.cardiac_output < heart_normal.cardiac_output * 0.7


# ---------------------------------------------------------------------------
# Noble 1962 Purkinje Fiber tests
# ---------------------------------------------------------------------------

class TestNoblePurkinjeFiber:
    """Test the Noble 1962 Purkinje fiber electrophysiology model."""

    def _make_heart_with_noble(self, weight_kg=20.0):
        """Create a heart with NoblePurkinjeFiber electrophysiology."""
        bv = 86.0 * weight_kg
        blood = BloodCompartment(total_volume_ml=bv)
        heart = HeartModule(weight_kg=weight_kg, blood=blood)
        # Ensure the HH module is NoblePurkinjeFiber
        assert isinstance(heart.hh, NoblePurkinjeFiber), \
            f"Expected NoblePurkinjeFiber, got {type(heart.hh)}"
        return heart

    def test_noble_normal_conduction(self):
        """At normal K⁺, conduction velocity should be near maximum."""
        heart = self._make_heart_with_noble()
        noble = heart.hh
        # Run a few steps to stabilize
        for _ in range(50):
            noble.update(dt=0.1, heart_rate_bpm=85, k_ext=4.2)
        assert noble.conduction_velocity > 3.5, \
            f"CV={noble.conduction_velocity}, expected > 3.5 m/s at normal K⁺"
        assert noble.av_block_degree == 0, \
            f"AV block={noble.av_block_degree}, expected 0 (normal)"
        assert noble.pr_interval_ms < 120, \
            f"PR={noble.pr_interval_ms}, expected < 120ms at normal K⁺"

    def test_noble_hyperkalemia_slows_conduction(self):
        """High K⁺=7.5 should slow conduction velocity."""
        heart = self._make_heart_with_noble()
        noble = heart.hh
        for _ in range(100):
            noble.update(dt=0.1, heart_rate_bpm=85, k_ext=7.5)
        assert noble.conduction_velocity < 3.0, \
            f"CV={noble.conduction_velocity}, expected < 3.0 m/s at K⁺=7.5"
        assert noble.av_block_degree >= 1, \
            f"AV block={noble.av_block_degree}, expected >= 1 at K⁺=7.5"

    def test_noble_severe_hyperkalemia_av_block(self):
        """K⁺=9.0 should cause high-grade AV block."""
        heart = self._make_heart_with_noble()
        noble = heart.hh
        for _ in range(100):
            noble.update(dt=0.1, heart_rate_bpm=85, k_ext=9.0)
        assert noble.av_block_degree >= 2, \
            f"AV block={noble.av_block_degree}, expected >= 2 at K⁺=9.0"
        assert noble.pr_interval_ms > 120, \
            f"PR={noble.pr_interval_ms}, expected > 120ms at K⁺=9.0"

    def test_noble_pr_prolongation_with_k(self):
        """PR interval should lengthen as K⁺ increases."""
        heart = self._make_heart_with_noble()
        noble = heart.hh

        # Normal K⁺
        for _ in range(100):
            noble.update(dt=0.1, heart_rate_bpm=85, k_ext=4.2)
        pr_normal = noble.pr_interval_ms

        # High K⁺
        noble2 = NoblePurkinjeFiber()
        for _ in range(100):
            noble2.update(dt=0.1, heart_rate_bpm=85, k_ext=8.0)
        pr_high = noble2.pr_interval_ms

        assert pr_high > pr_normal, \
            f"PR at K⁺=8 ({pr_high}) should be > PR at K⁺=4.2 ({pr_normal})"

    def test_noble_qrs_widening_with_k(self):
        """QRS width should increase as K⁺ increases."""
        heart = self._make_heart_with_noble()
        noble = heart.hh

        for _ in range(100):
            noble.update(dt=0.1, heart_rate_bpm=85, k_ext=4.2)
        qrs_normal = noble.qrs_width_ms

        noble2 = NoblePurkinjeFiber()
        for _ in range(100):
            noble2.update(dt=0.1, heart_rate_bpm=85, k_ext=8.0)
        qrs_high = noble2.qrs_width_ms

        assert qrs_high > qrs_normal, \
            f"QRS at K⁺=8 ({qrs_high}) should be > QRS at K⁺=4.2 ({qrs_normal})"

    def test_noble_purkinje_intrinsic_rate(self):
        """Purkinje intrinsic rate should be ~30 bpm and decrease with high K⁺."""
        noble = NoblePurkinjeFiber()
        for _ in range(100):
            noble.update(dt=0.1, heart_rate_bpm=85, k_ext=4.2)
        rate_normal = noble._intrinsic_rate_hz * 60.0

        noble2 = NoblePurkinjeFiber()
        for _ in range(100):
            noble2.update(dt=0.1, heart_rate_bpm=85, k_ext=9.0)
        rate_high = noble2._intrinsic_rate_hz * 60.0

        assert 10 < rate_normal < 40, \
            f"Intrinsic rate={rate_normal}, expected 10-40 bpm"
        assert rate_high < rate_normal, \
            f"Rate at K⁺=9 ({rate_high}) should be < rate at K⁺=4.2 ({rate_normal})"

    def test_noble_av_interpretation(self):
        """get_av_interpretation() should return valid fields."""
        noble = NoblePurkinjeFiber()
        for _ in range(50):
            noble.update(dt=0.1, heart_rate_bpm=85, k_ext=4.2)
        interp = noble.get_av_interpretation(4.2)
        assert "conduction_velocity" in interp
        assert "pr_interval_ms" in interp
        assert "qrs_width_ms" in interp
        assert "av_block_degree" in interp
        assert interp["av_block_description"] in [
            "normal_conduction", "first_degree_avb",
            "second_degree_avb", "third_degree_avb",
        ]
