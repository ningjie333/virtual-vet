"""
Time Manager — 动态时间管理系统（v2：分钟级推进）

职责：
  - 游戏内时钟：跟踪游戏内时间（08:00 开始）
  - 夜间检测：22:00-06:00 为夜间
  - 夜间生理修正：HR 降低、代谢率降低
  - 兼容性场景策略辅助：保留夜间 pacing 因子查询接口
"""

from __future__ import annotations

# ── 时间常量 ────────────────────────────────────────────────────────────────

GAME_START_HOUR = 8          # 游戏内 08:00 开始
NIGHT_START_HOUR = 22        # 夜间开始 22:00
NIGHT_END_HOUR = 6           # 夜间结束 06:00
SECONDS_PER_HOUR = 3600
MINUTES_PER_HOUR = 60

# ── 夜间修正因子 ────────────────────────────────────────────────────────────

NIGHT_HR_FACTOR = 0.85       # 夜间 HR 降低 15%（生理性心动过缓）
NIGHT_PROGRESSION_FACTOR = 0.8  # Legacy scenario-policy helper; not a kernel disease-rate control.


def game_time_to_hour(game_time_min: float) -> float:
    """
    将游戏内分钟数转换为 24 小时制的小时数

    Args:
        game_time_min: 游戏内经过的分钟数（从 0 开始 = 08:00）

    Returns:
        当前游戏内小时数 [0, 24)
    """
    start_minutes = GAME_START_HOUR * MINUTES_PER_HOUR
    current_minutes = start_minutes + game_time_min
    return (current_minutes / MINUTES_PER_HOUR) % 24.0


def is_night_time(game_time_min: float) -> bool:
    """
    判断当前是否为夜间（22:00 - 06:00）

    Args:
        game_time_min: 游戏内经过的分钟数

    Returns:
        True 如果是夜间
    """
    hour = game_time_to_hour(game_time_min)
    return hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR


def get_night_hr_factor(game_time_min: float) -> float:
    """
    获取夜间 HR 修正因子

    夜间：0.85（HR 降低 15%）
    白天：1.0（无修正）

    Args:
        game_time_min: 游戏内经过的分钟数

    Returns:
        HR 乘数因子
    """
    if is_night_time(game_time_min):
        return NIGHT_HR_FACTOR
    return 1.0


def get_night_progression_factor(game_time_min: float) -> float:
    """
    Legacy compatibility helper for scenario-layer pacing policy.

    Important:
    - this is not a kernel biological time multiplier
    - it must not be interpreted as permission to rescale disease equations
    - current kernel progression remains defined in physical time

    Args:
        game_time_min: 游戏内经过的分钟数

    Returns:
        外层策略因子
    """
    if is_night_time(game_time_min):
        return NIGHT_PROGRESSION_FACTOR
    return 1.0


def apply_night_hr_modifier(base_hr: float, game_time_min: float) -> float:
    """
    应用夜间 HR 修正

    Args:
        base_hr: 基础心率
        game_time_min: 游戏内经过的分钟数

    Returns:
        修正后的心率
    """
    return base_hr * get_night_hr_factor(game_time_min)


def get_time_of_day_label(game_time_min: float) -> str:
    """
    返回当前时段标签（用于 UI 显示）

    Returns:
        "morning" | "afternoon" | "evening" | "night"
    """
    hour = game_time_to_hour(game_time_min)
    if 6 <= hour < 12:
        return "morning"
    elif 12 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 22:
        return "evening"
    else:
        return "night"


def format_game_time(game_time_min: float) -> str:
    """
    格式化游戏内时间为 HH:MM 字符串

    Args:
        game_time_min: 游戏内经过的分钟数

    Returns:
        格式化的时间字符串，如 "08:30"
    """
    total_minutes = int((GAME_START_HOUR * MINUTES_PER_HOUR + game_time_min) % (24 * MINUTES_PER_HOUR))
    hours = total_minutes // MINUTES_PER_HOUR
    minutes = total_minutes % MINUTES_PER_HOUR
    return f"{hours:02d}:{minutes:02d}"
