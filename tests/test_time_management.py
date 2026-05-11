"""
P3: Dynamic Time Management 测试（v2：时间预算版）
时间流速、夜间模式、疾病进展权衡
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from game.action_system import (
    GameState,
    process_action,
)
from src.simulation import VirtualCreature
from src.diseases import create_disease


def _make_state(disease_name="pneumonia"):
    """辅助：创建带疾病的游戏状态"""
    vc = VirtualCreature(body_weight_kg=20.0)
    disease = create_disease(disease_name)
    vc.attach_disease(disease)
    return GameState(engine=vc, disease_name=disease_name, time_budget_min=10000)


def _make_state_no_disease():
    """辅助：创建无疾病的游戏状态（用于夜间 HR 测试）"""
    vc = VirtualCreature(body_weight_kg=20.0)
    return GameState(engine=vc, disease_name="none", time_budget_min=10000)


# ── P3-A: 时间消耗 ──────────────────────────────────────────────────────

class TestTimeCost:
    """不同行动消耗不同时间"""

    def test_examine_physical_cost(self):
        """体格检查消耗 5 分钟"""
        state = _make_state()
        result = process_action(state, "examine", {"test_type": "physical"})
        assert result["time_cost_min"] == 5

    def test_examine_blood_gas_cost(self):
        """血气分析消耗 5 分钟（即时出结果）"""
        state = _make_state()
        result = process_action(state, "examine", {"test_type": "blood_gas"})
        assert result["time_cost_min"] == 5

    def test_examine_chest_xray_cost(self):
        """X光胸片消耗 20 分钟"""
        state = _make_state()
        result = process_action(state, "examine", {"test_type": "chest_xray"})
        assert result["time_cost_min"] == 20

    def test_examine_ct_cost(self):
        """CT 消耗 45 分钟"""
        state = _make_state()
        result = process_action(state, "examine", {"test_type": "ct"})
        assert result["time_cost_min"] == 45

    def test_wait_cost(self):
        """等待消耗 10 分钟"""
        state = _make_state()
        result = process_action(state, "wait", {})
        assert result["time_cost_min"] == 10

    def test_treat_cost(self):
        """治疗消耗 5 分钟"""
        state = _make_state()
        result = process_action(state, "treat", {"disease_guess": "pneumonia"})
        assert result["time_cost_min"] == 5


class TestTimeAccumulation:
    """时间预算正确累加"""

    def test_time_elapsed_increments(self):
        """每次行动后 time_elapsed_min 增加"""
        state = _make_state()
        process_action(state, "wait", {})
        assert state.time_elapsed_min == 10
        process_action(state, "examine", {"test_type": "physical"})
        assert state.time_elapsed_min == 15

    def test_time_remaining_decrements(self):
        """剩余时间随行动递减"""
        state = _make_state()
        initial_remaining = state.time_remaining_min
        process_action(state, "examine", {"test_type": "chest_xray"})
        assert state.time_remaining_min == initial_remaining - 20

    def test_simulation_advances_with_action(self):
        """行动推进仿真时间"""
        state = _make_state_no_disease()
        initial_t = state.engine.current_time_s
        process_action(state, "wait", {})
        # wait = 10 分钟 → 600 秒仿真
        assert state.engine.current_time_s == pytest.approx(initial_t + 600.0, abs=5.0)

    def test_longer_examine_advances_more_simulation(self):
        """耗时更长的检查推进更多仿真时间"""
        state = _make_state_no_disease()
        initial_t = state.engine.current_time_s
        process_action(state, "examine", {"test_type": "chest_xray"})
        # chest_xray = 20 分钟 → 1200 秒仿真
        assert state.engine.current_time_s == pytest.approx(initial_t + 1200.0, abs=10.0)


class TestNightMode:
    """夜间模式：游戏内夜间时段生理参数变化"""

    def test_night_time_detection(self):
        """能判断当前是否为夜间（22:00-06:00）"""
        from game.time_manager import is_night_time
        # 游戏内时间 0min = 08:00（早上 8 点开始）
        assert is_night_time(0) is False
        # 22:00 = 14 小时后 = 840 分钟
        assert is_night_time(840) is True
        # 02:00 = 18 小时后 = 1080 分钟
        assert is_night_time(1080) is True
        # 06:00 = 22 小时后 = 1320 分钟
        assert is_night_time(1320) is False

    def test_night_hr_modifier(self):
        """夜间 HR 降低（生理性心动过缓）"""
        from game.time_manager import get_night_hr_factor
        assert get_night_hr_factor(840) < 1.0
        assert get_night_hr_factor(0) == 1.0

    def test_night_disease_progression_slower(self):
        """夜间疾病进展略慢（代谢率降低）"""
        from game.time_manager import get_night_progression_factor
        assert get_night_progression_factor(840) < 1.0
        assert get_night_progression_factor(0) == 1.0


class TestDiseaseProgressionTradeoff:
    """疾病进展权衡：等待让病情恶化，但给玩家思考时间"""

    def test_wait_worsens_condition(self):
        """多次 wait 后病情恶化"""
        state = _make_state("pneumonia")
        initial_spo2 = state.engine.blood.arterial_saturation
        for _ in range(5):
            if state.phase == "lost":
                break
            process_action(state, "wait", {})
        final_spo2 = state.engine.blood.arterial_saturation
        assert final_spo2 <= initial_spo2

    def test_death_timer_decreases_in_moribund(self):
        """濒死状态下每次行动倒计时减 1"""
        state = _make_state("pneumonia")
        for _ in range(30):
            if state.phase == "lost":
                break
            if state.death_timer is not None:
                break
            process_action(state, "wait", {})
        if state.death_timer is not None:
            initial_timer = state.death_timer
            process_action(state, "wait", {})
            if state.phase != "lost":
                assert state.death_timer == initial_timer - 1


class TestNightHrReversibility:
    """HR 夜间修正可逆性：白天→夜间→白天，HR_rest 应恢复"""

    def test_hr_rest_decreases_at_night(self):
        """进入夜间后 HR_rest 降低"""
        state = _make_state()
        initial_hr_rest = state.engine.heart.HR_rest
        state.time_elapsed_min = 840  # 22:00
        process_action(state, "wait", {})
        assert state.engine.heart.HR_rest < initial_hr_rest

    def test_hr_rest_recovers_after_night(self):
        """夜间结束后 HR_rest 恢复"""
        state = _make_state()
        initial_hr_rest = state.engine.heart.HR_rest
        state.time_elapsed_min = 840  # 22:00
        process_action(state, "wait", {})
        assert state.engine.heart.HR_rest < initial_hr_rest
        # 推进到白天并多步让 HR_rest 恢复
        state.time_elapsed_min = 1320  # 06:00
        for _ in range(5):
            process_action(state, "wait", {})
        assert state.engine.heart.HR_rest == pytest.approx(initial_hr_rest, abs=1.0)

    def test_hr_rest_multiple_cycles(self):
        """多次昼夜循环后 HR_rest 不累积衰减"""
        state = _make_state()
        initial_hr_rest = state.engine.heart.HR_rest
        for cycle in range(3):
            state.time_elapsed_min = 840
            process_action(state, "wait", {})
            state.time_elapsed_min = 1320
            for _ in range(3):
                process_action(state, "wait", {})
        assert state.engine.heart.HR_rest == pytest.approx(initial_hr_rest, abs=2.0)

    def test_hr_current_follows_rest_down(self):
        """夜间 HR 跟随 HR_rest 下降（无疾病干扰）"""
        state = _make_state_no_disease()
        initial_hr = state.engine.heart.heart_rate
        state.time_elapsed_min = 840
        for _ in range(5):
            process_action(state, "wait", {})
        assert state.engine.heart.heart_rate < initial_hr

    def test_hr_current_recovers_after_night(self):
        """白天 HR 恢复（无疾病干扰）"""
        state = _make_state_no_disease()
        initial_hr = state.engine.heart.heart_rate
        state.time_elapsed_min = 840
        for _ in range(5):
            process_action(state, "wait", {})
        night_hr = state.engine.heart.heart_rate
        assert night_hr < initial_hr
        # 推进到白天并多步让 HR 恢复（引擎 HR 收敛需要时间）
        state.time_elapsed_min = 1320
        for _ in range(20):
            if state.engine.heart.heart_rate > night_hr:
                break
            process_action(state, "wait", {})
        assert state.engine.heart.heart_rate > night_hr
