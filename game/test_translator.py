"""
Test Translator — 把 ODE 引擎的原始数值翻译成玩家可见的检查报告。

输入: VirtualCreature 实例（通过属性访问当前引擎状态）
输出: 结构化检查报告 dict（含参数值、正常范围、异常标记、中文描述）

Legacy compatibility wrapper.

新代码应优先通过 `GameRuntime.interpreter.report(...)` 获取检查报告。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from game.runtime import default_runtime

if TYPE_CHECKING:
    from src.simulation import VirtualCreature

logger = logging.getLogger(__name__)


def translate(test_type: str, creature: VirtualCreature) -> dict:
    """
    Legacy compatibility API.

    根据检查类型返回对应的检查报告。

    新代码应优先使用 `GameRuntime.interpreter.report(...)`。

    Args:
        test_type: 检查类型字符串
        creature: VirtualCreature 实例

    Returns:
        结构化检查报告 dict
    """
    return default_runtime().interpreter.report(test_type, creature)
