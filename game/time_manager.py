"""
Time Manager — 动态时间管理系统

职责：
  - 游戏内时钟：跟踪游戏内时间（08:00 开始）
  - 夜间检测：22:00-06:00 为夜间
  - 夜间生理修正：HR 降低、代谢率降低
  - 疾病进展速度修正：夜间略慢
"""

from __future__ import annotations

# ── 时间常量 ────────────────────────────────────────────────────────────────

GAME_START_HOUR = 8          # 游戏内 08:00 开始
NIGHT_START_HOUR = 22        # 夜间开始 22:00
NIGHT_END_HOUR = 6           # 夜间结束 06:00
SECONDS_PER_HOUR = 3600

# ── 夜间修正因子 ────────────────────────────────────────────────────────────

NIGHT_HR_FACTOR = 0.85       # 夜间 HR 降低 15%（生理性心动过缓）
NIGHT_PROGRESSION_FACTOR = 0.8  # 夜间疾病进展减慢 20%（代谢率降低）


def game_time_to_hour(game_time_s: float) -> float:
    """
    将游戏内秒数转换为 24 小时制的小时数

    Args:
        game_time_s: 游戏内经过的秒数（从 0 开始 = 08:00）

    Returns:
        当前游戏内小时数 [0, 24)
    """
    start_seconds = GAME_START_HOUR * SECONDS_PER_HOUR
    current_seconds = start_seconds + game_time_s
    return (current_seconds / SECONDS_PER_HOUR) % 24.0


def is_night_time(game_time_s: float) -> bool:
    """
    判断当前是否为夜间（22:00 - 06:00）

    Args:
        game_time_s: 游戏内经过的秒数

    Returns:
        True 如果是夜间
    """
    hour = game_time_to_hour(game_time_s)
    return hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR


def get_night_hr_factor(game_time_s: float) -> float:
    """
    获取夜间 HR 修正因子

    夜间：0.85（HR 降低 15%）
    白天：1.0（无修正）

    Args:
        game_time_s: 游戏内经过的秒数

    Returns:
        HR 乘数因子
    """
    if is_night_time(game_time_s):
        return NIGHT_HR_FACTOR
    return 1.0


def get_night_progression_factor(game_time_s: float) -> float:
    """
    获取夜间疾病进展速度修正因子

    夜间：0.8（进展减慢 20%）
    白天：1.0（正常速度）

    Args:
        game_time_s: 游戏内经过的秒数

    Returns:
        疾病进展速度乘数因子
    """
    if is_night_time(game_time_s):
        return NIGHT_PROGRESSION_FACTOR
    return 1.0


def apply_night_hr_modifier(base_hr: float, game_time_s: float) -> float:
    """
    应用夜间 HR 修正

    Args:
        base_hr: 基础心率
        game_time_s: 游戏内经过的秒数

    Returns:
        修正后的心率
    """
    return base_hr * get_night_hr_factor(game_time_s)


def get_time_of_day_label(game_time_s: float) -> str:
    """
    返回当前时段标签（用于 UI 显示）

    Returns:
        "morning" | "afternoon" | "evening" | "night"
    """
    hour = game_time_to_hour(game_time_s)
    if 6 <= hour < 12:
        return "morning"
    elif 12 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 22:
        return "evening"
    else:
        return "night"


def format_game_time(game_time_s: float) -> str:
    """
    格式化游戏内时间为 HH:MM 字符串

    Args:
        game_time_s: 游戏内经过的秒数

    Returns:
        格式化的时间字符串，如 "08:30"
    """
    total_seconds = (GAME_START_HOUR * SECONDS_PER_HOUR + game_time_s) % (24 * SECONDS_PER_HOUR)
    hours = int(total_seconds // SECONDS_PER_HOUR)
    minutes = int((total_seconds % SECONDS_PER_HOUR) // 60)
    return f"{hours:02d}:{minutes:02d}"
