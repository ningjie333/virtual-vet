"""
Test: LymphaticModule - 淋巴/脾脏系统
Run with: python -m pytest tests/test_lymphatic.py -v
"""
import pytest
import sys
sys.path.insert(0, 'src')

from blood import BloodCompartment
from lymphatic import LymphaticModule


@pytest.fixture
def blood():
    b = BloodCompartment(total_volume_ml=1720, plasma_fraction=0.55)
    b.splenic_reserve_mL = 75.0
    b.lymph_flow_mL_min = 3.0
    b.interstitial_fluid_mL = 2500.0
    b.cytokine_level = 0.0
    return b


@pytest.fixture
def lymph(blood):
    return LymphaticModule(weight_kg=20.0, blood=blood)


def test_initialization(lymph, blood):
    assert lymph.splenic_reserve_mL == 100.0  # 20kg * 5 mL/kg
    assert lymph.lymph_flow_rate == 3.0
    assert lymph.interstitial_fluid_mL == 800.0  # 20kg * 40
    assert lymph.immune_cell_reserve == 5.0
    assert lymph.blood is blood


def test_compute_returns_required_keys(lymph, blood):
    """compute() 返回所有必需 keys"""
    gut_state = {"fat_absorption_active": False}
    state = lymph.compute(dt=1.0, gut_state=gut_state, immune_state={})
    required_keys = {
        "splenic_reserve_mL", "lymph_flow_rate",
        "interstitial_fluid_mL", "immune_cell_reserve", "factor_commands",
    }
    assert required_keys.issubset(state.keys()), f"Missing keys: {required_keys - set(state.keys())}"


def test_lymph_flow_baseline(lymph, blood):
    """正常状态下淋巴流 ≈ 3 mL/min"""
    gut_state = {"fat_absorption_active": False}
    lymph.compute(dt=1.0, gut_state=gut_state, immune_state={})
    assert 2.0 <= blood.lymph_flow_mL_min <= 4.0


def test_inflammation_increases_lymph_flow(lymph, blood):
    """cytokine > 0.4 → 淋巴回流代偿性增加"""
    gut_state = {"fat_absorption_active": False}
    blood.cytokine_level = 0.7
    lymph.compute(dt=1.0, gut_state=gut_state, immune_state={})
    assert blood.lymph_flow_mL_min > 4.0, f"lymph_flow {blood.lymph_flow_mL_min} should increase with inflammation"


def test_splenic_reserve_normal_no_mobilization(lymph, blood):
    """正常 MAP > 60 → 脾脏储血不动员"""
    gut_state = {"fat_absorption_active": False}
    heart_state = {"MAP_mmHg": 90.0, "heart_rate_bpm": 80.0}
    gut_state["_heart_state"] = heart_state
    # After first compute, blood.splenic_reserve_mL syncs to lymph.splenic_reserve_mL (100.0)
    lymph.compute(dt=1.0, gut_state=gut_state, immune_state={})
    initial = blood.splenic_reserve_mL
    for _ in range(600):
        lymph.compute(dt=1.0, gut_state=gut_state, immune_state={})
    # 正常情况储血量应保持稳定 (within 10 mL drift)
    assert abs(blood.splenic_reserve_mL - initial) < 10.0


def test_splenic_reserve_mobilizes_in_shock(lymph, blood):
    """MAP < 60 mmHg → 脾脏储血动员"""
    heart_state = {"MAP_mmHg": 50.0, "heart_rate_bpm": 100.0}
    gut_state = {"fat_absorption_active": False, "_heart_state": heart_state}
    for _ in range(600):  # ~10分钟休克
        lymph.compute(dt=1.0, gut_state=gut_state, immune_state={})
    # 脾脏应该释放储血（减少超过5 mL）
    assert blood.splenic_reserve_mL < 95.0, f"splenic reserve {blood.splenic_reserve_mL} should decrease in shock"


def test_splenic_reserve_mobilizes_with_tachycardia(lymph, blood):
    """HR > 120 bpm → 脾脏储血动员（独立于MAP）"""
    # 使用新的 lymph 实例避免前一个测试的状态影响
    heart_state = {"MAP_mmHg": 80.0, "heart_rate_bpm": 140.0}
    gut_state = {"fat_absorption_active": False, "_heart_state": heart_state}
    lymph.compute(dt=1.0, gut_state=gut_state, immune_state={})  # sync blood value
    initial = lymph.splenic_reserve_mL  # use module's own value
    for _ in range(600):
        lymph.compute(dt=1.0, gut_state=gut_state, immune_state={})
    # 心动过速时交感激活 → 脾脏收缩
    assert lymph.splenic_reserve_mL < initial, "splenic reserve should decrease with tachycardia"


def test_fat_absorption_increases_lymph_flow(lymph, blood):
    """肠道脂质吸收 → 乳糜流增加"""
    gut_state = {"fat_absorption_active": True}
    blood.cytokine_level = 0.0
    lymph.compute(dt=1.0, gut_state=gut_state, immune_state={})
    assert blood.lymph_flow_mL_min > 4.0, f"lymph_flow {blood.lymph_flow_mL_min} should increase with fat absorption"


def test_summary_keys(lymph):
    """summary() 返回正确的 keys"""
    s = lymph.summary()
    expected_keys = {
        "splenic_reserve_mL", "lymph_flow_rate",
        "interstitial_fluid_mL", "immune_cell_reserve",
    }
    assert set(s.keys()) == expected_keys