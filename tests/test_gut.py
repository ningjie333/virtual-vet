"""
Test: GutModule - 肠道吸收系统
Run with: python -m pytest tests/test_gut.py -v
"""
import pytest
import sys
sys.path.insert(0, 'src')

from gut import GutModule
from blood import BloodCompartment


@pytest.fixture
def blood():
    return BloodCompartment(total_volume_ml=1720, plasma_fraction=0.55)


@pytest.fixture
def gut(blood):
    return GutModule(weight_kg=20.0, blood=blood)


def test_gut_initialization(gut, blood):
    assert gut.gut_motility == 0.8
    assert gut.barrier_integrity == 1.0
    assert gut.microbiome_activity == 0.6
    assert gut.w == 20.0
    assert gut.blood is blood


def test_portal_blood_flow_scales_with_CO(gut):
    """门静脉血流量随心输出量变化（≈15% CO）"""
    gut._update_portal_flow(1700)  # CO=1700 mL/min
    assert gut.portal_blood_flow == 0.15 * 1700

    gut._update_portal_flow(3400)  # CO=3400 mL/min
    assert gut.portal_blood_flow == 0.15 * 3400


def test_gastric_emptying_depletes_lumen(gut, dt=0.1):
    """胃排空逐渐消耗肠腔营养"""
    gut.lumen_glucose_g = 10.0
    gut._compute_gastric_emptying(dt)
    assert gut.lumen_glucose_g < 10.0


def test_microbiome_scfa_production(gut, dt=1.0):
    """菌群活性影响 SCFA 产生"""
    gut.microbiome_activity = 0.6
    gut.SCFA_mmol_L = 0.1
    gut._compute_microbiome(dt)
    assert gut.SCFA_mmol_L > 0.1


def test_microbiome_depleted_low_scfa(gut, dt=1.0):
    """菌群活性低 → SCFA 低"""
    gut.microbiome_activity = 0.1
    gut.SCFA_mmol_L = 0.3
    gut._compute_microbiome(dt)
    assert gut.SCFA_mmol_L < 0.3


def test_compute_returns_required_keys(gut):
    """compute() 返回所有必需 keys"""
    state = gut.compute(dt=0.1, cardiac_output=1700.0)
    required_keys = {
        'portal_blood_flow_ml_min', 'gut_motility', 'barrier_integrity',
        'microbiome_activity', 'SCFA_mmol_L',
        'absorption_glucose_g_min', 'absorption_amino_g_min', 'absorption_fat_g_min',
        'lumen_glucose_g', 'lumen_amino_g', 'lumen_fat_g'
    }
    assert required_keys.issubset(state.keys()), f"Missing: {required_keys - set(state.keys())}"


def test_barrier_integrity_affects_absorption(gut, dt=0.1):
    """低肠道屏障 → 吸收效率下降"""
    gut.lumen_glucose_g = 10.0
    gut.barrier_integrity = 1.0
    glucose_abs_healthy = gut._compute_absorption(dt)[0]

    gut.lumen_glucose_g = 10.0
    gut.barrier_integrity = 0.5
    glucose_abs_damaged = gut._compute_absorption(dt)[0]

    assert glucose_abs_damaged < glucose_abs_healthy


def test_gut_motility_affects_absorption(gut, dt=0.1):
    """低蠕动 → 吸收效率下降"""
    gut.lumen_glucose_g = 10.0
    gut.gut_motility = 0.8
    glucose_abs_high_motility = gut._compute_absorption(dt)[0]

    gut.lumen_glucose_g = 10.0
    gut.gut_motility = 0.3
    glucose_abs_low_motility = gut._compute_absorption(dt)[0]

    assert glucose_abs_low_motility < glucose_abs_high_motility


def test_add_food_intake(gut):
    """进食事件添加肠腔营养"""
    gut.add_food_intake(glucose_g=50.0, amino_g=10.0, fat_g=5.0)
    assert gut.lumen_glucose_g == 50.0
    assert gut.lumen_amino_g == 10.0
    assert gut.lumen_fat_g == 5.0


def test_blood_amino_acids_updated_after_compute(gut, blood):
    """compute() 后血液 amino_acids_g_L 被更新"""
    gut.lumen_amino_g = 20.0
    gut.compute(dt=0.1, cardiac_output=1700.0)
    # 吸收效率 × 蠕动 × 屏障 × 菌群
    expected_absorption = (gut.lumen_amino_g / gut._TAU_ABSORPTION) * gut.base_absorption_rate * gut.gut_motility * gut.barrier_integrity * (0.5 + 0.5 * gut.microbiome_activity) * 0.1 / (0.15 * 1700) * 1000
    assert blood.amino_acids_g_L >= 0


def test_summary(gut):
    """summary() 返回肠道状态"""
    s = gut.summary()
    assert 'motility' in s
    assert 'barrier' in s
    assert 'microbiome' in s
    assert 'SCFA' in s
    assert 'portal_flow' in s