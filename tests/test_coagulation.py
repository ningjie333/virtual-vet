"""
Test: CoagulationModule - 凝血系统
Run with: python -m pytest tests/test_coagulation.py -v
"""
import pytest
import sys
sys.path.insert(0, 'src')

from blood import BloodCompartment
from coagulation import CoagulationModule


@pytest.fixture
def blood():
    b = BloodCompartment(total_volume_ml=1720, plasma_fraction=0.55)
    b.cytokine_level = 0.0
    b.PLT = 300.0
    b.PT_sec = 12.0
    b.aPTT_sec = 30.0
    b.fibrinogen_mg_dL = 300.0
    b.coagulation_state = 0.0
    return b


@pytest.fixture
def coag(blood):
    return CoagulationModule(weight_kg=20.0, blood=blood)


def test_initialization(coag, blood):
    assert coag.factor_VII == 1.0
    assert coag.factor_V == 1.0
    assert coag.factor_II == 1.0
    assert coag.factor_IX == 1.0
    assert coag.factor_X == 1.0
    assert coag.factor_XI == 1.0
    assert coag.coagulation_state == 0.0
    assert coag.fibrinogen == 300.0
    assert coag.blood is blood


def test_compute_returns_required_keys(coag, blood):
    """compute() 返回所有必需 keys"""
    liver_state = {"health_factor": 1.0, "metabolic_activity": 1.0}
    state = coag.compute(dt=1.0, liver_state=liver_state, immune_state={})
    required_keys = {
        "factor_VII", "factor_V", "factor_II", "factor_IX",
        "factor_X", "factor_XI", "coagulation_state", "fibrinogen",
        "PT_sec", "aPTT_sec", "factor_commands",
    }
    assert required_keys.issubset(state.keys()), f"Missing keys: {required_keys - set(state.keys())}"


def test_PT_normal_range(coag, blood):
    """正常状态下 PT ≈ 12s"""
    liver_state = {"health_factor": 1.0, "metabolic_activity": 1.0}
    coag.compute(dt=1.0, liver_state=liver_state, immune_state={})
    assert 10.0 <= blood.PT_sec <= 14.0, f"PT {blood.PT_sec} outside normal range"


def test_aPTT_normal_range(coag, blood):
    """正常状态下 aPTT ≈ 30s"""
    liver_state = {"health_factor": 1.0, "metabolic_activity": 1.0}
    coag.compute(dt=1.0, liver_state=liver_state, immune_state={})
    assert 25.0 <= blood.aPTT_sec <= 35.0, f"aPTT {blood.aPTT_sec} outside normal range"


def test_liver_failure_prolongs_PT(coag, blood):
    """严重肝衰竭 → Factor VII ↓ → PT 延长"""
    liver_state = {"health_factor": 0.1, "metabolic_activity": 0.1}
    # 多次调用让因子充分下降
    for _ in range(6000):  # ~100分钟
        coag.compute(dt=1.0, liver_state=liver_state, immune_state={})
    assert blood.PT_sec > 14.0, f"PT {blood.PT_sec} should be prolonged with liver failure"


def test_inflammation_suppresses_factors(coag, blood):
    """高细胞因子水平 → 因子合成受抑制"""
    liver_state = {"health_factor": 1.0, "metabolic_activity": 1.0}
    blood.cytokine_level = 0.7
    for _ in range(6000):  # ~100分钟
        coag.compute(dt=1.0, liver_state=liver_state, immune_state={})
    # 因子 VII 应该被炎症抑制（低于正常1.0）
    assert coag.factor_VII < 0.99, f"factor_VII {coag.factor_VII} should be suppressed by inflammation"


def test_high_cytokine_drives_coagulation_state(coag, blood):
    """cytokine > 0.6 → 凝血状态上升"""
    liver_state = {"health_factor": 1.0, "metabolic_activity": 1.0}
    blood.cytokine_level = 0.8
    blood.PLT = 300.0
    blood.fibrinogen_mg_dL = 300.0
    for _ in range(1800):  # ~30分钟让凝血状态充分建立
        coag.compute(dt=1.0, liver_state=liver_state, immune_state={})
    assert blood.coagulation_state > 0.3, f"coagulation_state {blood.coagulation_state} should be elevated"


def test_fibrinogen_rises_with_inflammation(coag, blood):
    """轻度炎症 → 纤维蛋白原代偿性升高"""
    liver_state = {"health_factor": 1.0, "metabolic_activity": 1.0}
    blood.cytokine_level = 0.5
    blood.coagulation_state = 0.0
    for _ in range(1800):
        coag.compute(dt=1.0, liver_state=liver_state, immune_state={})
    assert blood.fibrinogen_mg_dL >= 300.0, f"fibrinogen {blood.fibrinogen_mg_dL} should not drop without consumption"


def test_summary_keys(coag):
    """summary() 返回正确的 keys"""
    s = coag.summary()
    expected_keys = {
        "factor_VII", "factor_V", "factor_II", "factor_IX",
        "factor_X", "factor_XI", "coagulation_state", "fibrinogen",
    }
    assert set(s.keys()) == expected_keys