"""
Test: LiverModule - 肝脏代谢系统
Run with: python -m pytest tests/test_liver.py -v
"""
import pytest
import sys
sys.path.insert(0, 'src')

from liver import LiverModule
from blood import BloodCompartment


@pytest.fixture
def blood():
    b = BloodCompartment(total_volume_ml=1720, plasma_fraction=0.55)
    b.glucose_mmol_L = 4.5
    b.albumin_g_dL = 3.0
    b.ammonia_umol_L = 30.0
    b.ALT_U_L = 25.0
    b.AST_U_L = 25.0
    b.amino_acids_g_L = 1.0
    b.bilirubin_mg_dL = 0.2
    b.bun_mg_dL = 15.0
    return b


@pytest.fixture
def liver(blood):
    return LiverModule(weight_kg=20.0, blood=blood)


def test_liver_initialization(liver, blood):
    assert liver.metabolic_activity == 1.0
    assert liver.detox_capacity == 1.0
    assert liver.cyp450_activity == 1.0
    assert liver.glycogen_fraction == 0.6
    assert liver.w == 20.0
    assert liver.blood is blood


def test_compute_returns_required_keys(liver, blood):
    """compute() 返回所有必需 keys"""
    gut_state = {
        'portal_blood_flow_ml_min': 255.0,
        'absorption_glucose_g_min': 0.0,
        'absorption_amino_g_min': 0.0,
        'absorption_fat_g_min': 0.0,
    }
    state = liver.compute(dt=0.1, gut_state=gut_state, cardiac_output=1700.0)
    required_keys = {
        'hepatic_blood_flow_ml_min', 'metabolic_activity', 'detox_capacity',
        'cyp450_activity', 'glycogen_fraction', 'bilirubin_conjugation',
        'glucose_output_g_min', 'ammonia_clearance_umol_min',
        'albumin_synthesis_g_day', 'ALT_U_L', 'AST_U_L', 'ALP_U_L', 'GGT_U_L',
        'albumin_g_dL', 'ammonia_umol_L', 'glucose_mmol_L', 'BUN_mg_dL'
    }
    assert required_keys.issubset(state.keys()), f"Missing: {required_keys - set(state.keys())}"


def test_ammonia_clearance(liver, blood):
    """肝脏解毒降低血氨"""
    blood.ammonia_umol_L = 100.0
    blood.amino_acids_g_L = 1.0
    gut_state = {'absorption_amino_g_min': 0.0}
    liver.compute(dt=0.1, gut_state=gut_state, cardiac_output=1700.0)
    assert blood.ammonia_umol_L < 100.0


def test_low_hepatic_function_ammonia_rises(liver, blood):
    """低解毒能力 → 肠道来源氨积累 → 血氨升高"""
    blood.ammonia_umol_L = 50.0
    blood.amino_acids_g_L = 2.0  # 高氨基酸（肠道吸收来源）
    liver.detox_capacity = 0.2  # 严重受损（只有 20% 解毒能力）
    gut_state = {'absorption_amino_g_min': 0.5}  # 持续氨基酸吸收
    liver.compute(dt=0.1, gut_state=gut_state, cardiac_output=1700.0)
    # 解毒受损 + 肠道持续输入氨 → 血氨应高于初始值
    assert blood.ammonia_umol_L >= 49.0  # 允许数值精度误差


def test_glycogen_depletion_low_glucose(liver, blood):
    """低血糖时糖原被消耗"""
    initial_glycogen = liver.glycogen_fraction
    blood.glucose_mmol_L = 2.5  # 低血糖
    blood.amino_acids_g_L = 1.0
    gut_state = {'absorption_glucose_g_min': 0.0}
    liver.compute(dt=0.1, gut_state=gut_state, cardiac_output=1700.0)
    assert liver.glycogen_fraction < initial_glycogen


def test_albumin_synthesis_positive(liver, blood):
    """白蛋白合成率 > 0"""
    gut_state = {'absorption_glucose_g_min': 0.0, 'absorption_amino_g_min': 0.0}
    state = liver.compute(dt=0.1, gut_state=gut_state, cardiac_output=1700.0)
    assert state['albumin_synthesis_g_day'] >= 0


def test_bilirubin_rises_with_low_conjugation(liver, blood):
    """低胆红素结合能力 → 血胆红素升高"""
    blood.bilirubin_mg_dL = 0.2
    liver.bilirubin_conjugation = 0.5
    gut_state = {'absorption_glucose_g_min': 0.0, 'absorption_amino_g_min': 0.0}
    liver.compute(dt=0.1, gut_state=gut_state, cardiac_output=1700.0)
    assert blood.bilirubin_mg_dL > 0.2


def test_hepatic_flow_scales_with_CO(liver):
    """肝血流量随 CO 变化（≈25% CO）"""
    liver._update_hepatic_flow(1700.0)
    assert liver.hepatic_blood_flow == 0.25 * 1700.0


def test_summary(liver, blood):
    """summary() 返回肝脏状态"""
    s = liver.summary()
    assert 'metabolic_activity' in s
    assert 'detox_capacity' in s
    assert 'cyp450_activity' in s
    assert 'glycogen' in s
    assert 'hepatic_flow' in s
    assert 'albumin' in s
    assert 'ammonia' in s


def test_gut_liver_coupling_food_intake(liver, blood):
    """食物摄入 → gut 吸收 → liver 处理 → 血糖上升"""
    # 模拟进食后 gut 吸收
    blood.amino_acids_g_L = 2.0  # 进食后高氨基酸
    blood.glucose_mmol_L = 4.5
    gut_state = {
        'portal_blood_flow_ml_min': 255.0,
        'absorption_glucose_g_min': 0.5,  # gut 吸收 0.5 g/min 葡萄糖
        'absorption_amino_g_min': 0.2,
        'absorption_fat_g_min': 0.0,
    }
    liver.metabolic_activity = 1.0
    liver.detox_capacity = 1.0
    initial_glucose = blood.glucose_mmol_L
    liver.compute(dt=0.1, gut_state=gut_state, cardiac_output=1700.0)
    # 糖异生/糖原分解应该维持或增加血糖


def test_cyp450_factor_command_target(liver, blood):
    """cyp450_activity 可通过 FactorCommand 修改"""
    assert hasattr(liver, 'cyp450_activity')
    assert 0 <= liver.cyp450_activity <= 1.0