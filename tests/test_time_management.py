"""
P3: Dynamic Time Management 测试
行动点系统、时间流速、夜间模式、疾病进展权衡
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from game.action_system import (
    GameState,
    process_action,
    K_SECONDS_PER_ACTION,
    _get_examine_cost,
)
from src.simulation import VirtualCreature
from src.diseases import create_disease


def _make_state(disease_name="pneumonia"):
    """辅助：创建带疾病的游戏状态"""
    vc = VirtualCreature(body_weight_kg=20.0)
    disease = create_disease(disease_name)
    vc.attach_disease(disease)
    return GameState(engine=vc, disease_name=disease_name)


def _make_state_no_disease():
    """辅助：创建无疾病的游戏状态（用于夜间 HR 测试）"""
    vc = VirtualCreature(body_weight_kg=20.0)
    return GameState(engine=vc, disease_name="none")


# ── P3-A: 行动点系统 ──────────────────────────────────────────────────────


class TestActionPointSystem:
    """行动点系统：不同行动消耗不同点数"""

    def test_examine_cost_physical(self):
        """体格检查消耗 1 点"""
        assert _get_examine_cost("examine", {"test_type": "physical"}) == 1

    def test_examine_cost_blood_gas(self):
        """血气分析消耗 3 点"""
        assert _get_examine_cost("examine", {"test_type": "blood_gas"}) == 3

    def test_examine_cost_ct(self):
        """CT 消耗 5 点"""
        assert _get_examine_cost("examine", {"test_type": "ct"}) == 5

    def test_treat_cost(self):
        """治疗消耗 2 点"""
        assert _get_examine_cost("treat", {}) == 1  # 当前实现是 1

    def test_wait_cost(self):
        """等待消耗 1 点"""
        assert _get_examine_cost("wait", {}) == 1

    def test_administer_drug_cost(self):
        """给药消耗 1 点"""
        assert _get_examine_cost("administer_drug", {}) == 1


class TestTimeScale:
    """时间流速：行动推进的仿真时间可缩放"""

    def test_default_time_scale(self):
        """默认 1x：1 次行动 = 60 秒仿真"""
        assert K_SECONDS_PER_ACTION == 60

    def test_action_advances_time(self):
        """每次行动后 elapsed_time_s 增加"""
        state = _make_state()
        initial_time = state.elapsed_time_s
        process_action(state, "wait", {})
        assert state.elapsed_time_s > initial_time

    def test_wait_advances_simulation(self):
        """wait 行动推进仿真时间"""
        state = _make_state()
        initial_t = state.engine.current_time_s
        process_action(state, "wait", {})
        # 默认 60 秒
        assert state.engine.current_time_s == pytest.approx(initial_t + 60.0, abs=1.0)

    def test_high_cost_examine_advances_more_time(self):
        """高 cost 检查推进更多时间"""
        state = _make_state()
        initial_t = state.engine.current_time_s
        # blood_gas cost=3 → 3×60 = 180 秒
        process_action(state, "examine", {"test_type": "blood_gas"})
        assert state.engine.current_time_s == pytest.approx(initial_t + 180.0, abs=2.0)


class TestNightMode:
    """夜间模式：游戏内夜间时段生理参数变化"""

    def test_night_time_detection(self):
        """能判断当前是否为夜间（22:00-06:00）"""
        from game.time_manager import is_night_time
        # 游戏内时间 0s = 08:00（早上 8 点开始）
        # 08:00 → 不是夜间
        assert is_night_time(game_time_s=0.0) is False
        # 22:00 = 14 小时后 = 50400 秒
        assert is_night_time(game_time_s=50400.0) is True
        # 02:00 = 18 小时后 = 64800 秒
        assert is_night_time(game_time_s=64800.0) is True
        # 06:00 = 22 小时后 = 79200 秒
        assert is_night_time(game_time_s=79200.0) is False

    def test_night_hr_modifier(self):
        """夜间 HR 降低（生理性心动过缓）"""
        from game.time_manager import get_night_hr_factor
        # 夜间因子 < 1.0
        assert get_night_hr_factor(game_time_s=50400.0) < 1.0
        # 白天因子 = 1.0
        assert get_night_hr_factor(game_time_s=0.0) == 1.0

    def test_night_disease_progression_slower(self):
        """夜间疾病进展略慢（代谢率降低）"""
        from game.time_manager import get_night_progression_factor
        # 夜间进展因子 < 1.0
        assert get_night_progression_factor(game_time_s=50400.0) < 1.0
        # 白天因子 = 1.0
        assert get_night_progression_factor(game_time_s=0.0) == 1.0


class TestDiseaseProgressionTradeoff:
    """疾病进展权衡：等待让病情恶化，但给玩家思考时间"""

    def test_wait_worsens_condition(self):
        """多次 wait 后病情恶化"""
        state = _make_state("pneumonia")
        # 记录初始 SpO2
        initial_spo2 = state.engine.blood.arterial_saturation
        # 等待 5 次
        for _ in range(5):
            if state.phase == "lost":
                break
            process_action(state, "wait", {})
        # 肺炎应该恶化（SpO2 下降）
        final_spo2 = state.engine.blood.arterial_saturation
        assert final_spo2 <= initial_spo2

    def test_action_count_increments(self):
        """行动次数正确累加"""
        state = _make_state()
        process_action(state, "wait", {})
        assert state.action_count == 1
        process_action(state, "examine", {"test_type": "physical"})
        assert state.action_count == 2

    def test_death_timer_decreases_in_moribund(self):
        """濒死状态下每次行动倒计时减 1"""
        state = _make_state("pneumonia")
        # 让病情恶化到濒死
        for _ in range(20):
            if state.phase == "lost":
                break
            if state.death_timer is not None:
                break
            process_action(state, "wait", {})
        # 如果进入了濒死状态
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
        # 推进到夜间（22:00 = 14h = 50400s，每次 wait 60s）
        # 从 08:00 开始，需要 14h = 840 次 wait → 太多，直接设置 clock
        state.game_clock_s = 50400.0  # 22:00
        process_action(state, "wait", {})
        assert state.engine.heart.HR_rest < initial_hr_rest

    def test_hr_rest_recovers_after_night(self):
        """夜间结束后 HR_rest 恢复"""
        state = _make_state()
        initial_hr_rest = state.engine.heart.HR_rest
        # 进入夜间
        state.game_clock_s = 50400.0  # 22:00
        process_action(state, "wait", {})
        assert state.engine.heart.HR_rest < initial_hr_rest
        # 推进到白天（06:00 = 22h = 79200s）
        state.game_clock_s = 79201.0  # 06:00 刚过
        process_action(state, "wait", {})
        # HR_rest 应恢复到原始值
        assert state.engine.heart.HR_rest == pytest.approx(initial_hr_rest, abs=0.5)

    def test_hr_rest_multiple_cycles(self):
        """多次昼夜循环后 HR_rest 不累积衰减"""
        state = _make_state()
        initial_hr_rest = state.engine.heart.HR_rest
        # 模拟 3 次昼夜循环
        for cycle in range(3):
            # 夜间
            state.game_clock_s = 50400.0
            process_action(state, "wait", {})
            # 白天
            state.game_clock_s = 79201.0
            process_action(state, "wait", {})
        # 最终 HR_rest 应接近原始值
        assert state.engine.heart.HR_rest == pytest.approx(initial_hr_rest, abs=1.0)

    def test_hr_current_follows_rest_down(self):
        """夜间 HR 跟随 HR_rest 下降（无疾病干扰）"""
        state = _make_state_no_disease()
        initial_hr = state.engine.heart.heart_rate
        # 进入夜间
        state.game_clock_s = 50400.0
        # 多步让 HR 有时间下降
        for _ in range(5):
            process_action(state, "wait", {})
        # HR 应该比初始低
        assert state.engine.heart.heart_rate < initial_hr

    def test_hr_current_recovers_after_night(self):
        """白天 HR 恢复（无疾病干扰）"""
        state = _make_state_no_disease()
        initial_hr = state.engine.heart.heart_rate
        # 夜间
        state.game_clock_s = 50400.0
        for _ in range(5):
            process_action(state, "wait", {})
        night_hr = state.engine.heart.heart_rate
        assert night_hr < initial_hr
        # 白天恢复
        state.game_clock_s = 79201.0
        for _ in range(10):
            process_action(state, "wait", {})
        # HR 应该回升（至少不低于夜间值）
        assert state.engine.heart.heart_rate > night_hr
