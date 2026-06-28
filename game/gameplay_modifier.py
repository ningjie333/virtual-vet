"""
Gameplay Modifier — 玩法状态写协议（灰区 #1 收纳器）。

职责:
  - 收纳游戏层对内核状态的"玩法修正"写操作（如夜间 HR 修正）
  - 与 `EngineAdvancerProtocol`（时间推进）和 `ClinicalInterpreterProtocol`
    （只读解释）并列，作为 `GameRuntime` 的第四个协作者

设计原则:
  - interpreter 是只读契约，不承担 mutation
  - advancer 主管时间推进，不混淆玩法修正
  - modifier 是"游戏玩法 → 内核状态写"的唯一合规通道
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from game.time_manager import (
    is_night_time,
    get_night_hr_factor,
    format_game_time,
)

if TYPE_CHECKING:
    from game.action_system import GameState

logger = logging.getLogger(__name__)


@runtime_checkable
class GameplayModifierProtocol(Protocol):
    """游戏玩法修正协议：把玩法状态写入内核。"""

    def apply_night_modifiers(self, state: "GameState") -> None:
        """根据 state.time_elapsed_min 应用夜间生理修正到引擎。"""
        ...


class DefaultGameplayModifier:
    """默认实现：夜间 HR 修正。

    逻辑迁自 game/action_system.py::_apply_night_modifiers（阶段 2 重构）。
    直接读写 engine.heart.HR_rest / engine.heart.heart_rate —— 这是预期行为：
    Protocol 实现内部是"灰区收纳器"，把散落在游戏层的直写集中到一处可控实现。
    """

    def apply_night_modifiers(self, state: "GameState") -> None:
        clock_min = state.time_elapsed_min
        engine = state.engine
        hr_factor = get_night_hr_factor(clock_min)

        if state._original_hr_rest is None:
            state._original_hr_rest = engine.heart.HR_rest

        if is_night_time(clock_min):
            night_hr_rest = max(50.0, state._original_hr_rest * hr_factor)
            engine.heart.HR_rest = night_hr_rest
            if engine.heart.heart_rate > night_hr_rest:
                engine.heart.heart_rate = max(
                    night_hr_rest,
                    engine.heart.heart_rate * 0.95,
                )
        else:
            engine.heart.HR_rest = state._original_hr_rest
            if engine.heart.heart_rate < state._original_hr_rest:
                engine.heart.heart_rate = min(
                    state._original_hr_rest,
                    engine.heart.heart_rate * 1.05,
                )

        logger.debug(
            "夜间修正: is_night=%s, HR_factor=%.2f, HR_rest=%.1f, clock=%s",
            is_night_time(clock_min),
            hr_factor,
            engine.heart.HR_rest,
            format_game_time(clock_min),
        )
