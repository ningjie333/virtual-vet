"""
Lifecycle Curves — 发育和衰退数学函数。

基于文献数据：
- CYP450: Tanaka 1998 PMID 9741958 (犬类三型发育模式)
- GFR: Laroute 2005 PMID 15924934, Hall 2016 PMID 27925141
- 免疫衰老: Holder 2017 PMID 27824893 (犬类胸腺TREC)
- 骨骼成熟: Geiger 2016 PMID 27555921 (137犬，15品种)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class CurveType(Enum):
    SIGMOID = "sigmoid"           # S形发育（典型）
    LINEAR_SATURATE = "linear_saturate"  # 线性→饱和
    GOMPERTZ = "gompertz"         # Gompertz 指数衰退
    CONSTANT = "constant"          # 无年龄变化


# ── 发育曲线 ────────────────────────────────────────────────────────────────


def sigmoid(
    age_days: float,
    k: float,
    midpoint_days: float,
    sign: float = 1.0,
) -> float:
    """
    标准 sigmoid 发育曲线（0→1）。

    f(t) = 1 / (1 + exp(-sign·k·(t - midpoint)))

    适用于：GFR、交感神经成熟、CYP450 Type 1
    sign=-1 用于三相曲线的下降段
    """
    return 1.0 / (1.0 + math.exp(-sign * k * (age_days - midpoint_days)))


def linear_saturate(
    age_days: float,
    max_days: float,
) -> float:
    """
    线性饱和发育（0→1，快速→减缓）。

    f(t) = min(1.0, t / max_days)

    适用于：心脏顺应性、肺泡面积（产后继续发育）
    """
    return min(1.0, age_days / max_days)


def sigmoid_three_phase(
    age_days: float,
    k_rise: float,
    k_fall: float,
    peak_days: float,
    peak_value: float = 1.0,
) -> float:
    """
    三相发育曲线：低→峰值→回落至成人水平。

    用于 CYP450 Type 1 (CYP1A2, CYP3A等)：
    - 新生犬：低活性
    - 4-8周：快速上升超过成人水平
    - 成年后：回落至成人=1.0

    f(t) = peak × sigmoid(rise, peak_days) × sigmoid(fall, peak_days, sign=-1)
    """
    rise = sigmoid(age_days, k_rise, peak_days)
    fall = sigmoid(age_days, k_fall, peak_days, sign=-1)
    return peak_value * rise * fall


def constant(_age_days: float) -> float:
    """无年龄变化（常数值 1.0）。"""
    return 1.0


# ── 衰退曲线 ────────────────────────────────────────────────────────────────


def gompertz_decline(
    age_days: float,
    onset_days: float,
    rate_per_day: float,
) -> float:
    """
    Gompertz 衰退因子（1→0）。

    成熟后按指数衰退：
    f(t) = exp(-rate × (t - onset))  当 t ≥ onset
             1.0                     当 t < onset

    参数标定（犬类）：
    - onset_days = 2555 (~7岁，大型犬) 或 4380 (~12岁，小型犬)
    - rate_per_day = ln(2) / (half_life_years × 365)
    - 例如：rate=2.5e-5 → half_life ≈ 10年

    适用于：GFR、免疫功能、心肌收缩力
    """
    if age_days <= onset_days:
        return 1.0
    return math.exp(-rate_per_day * (age_days - onset_days))


def linear_decline(
    age_days: float,
    onset_days: float,
    min_factor: float = 0.3,
) -> float:
    """
    线性衰退（1→min_factor）。

    适用于：基础代谢率（随肌肉量减少而下降）
    """
    if age_days <= onset_days:
        return 1.0
    decline_years = (age_days - onset_days) / 365.0
    return max(min_factor, 1.0 - 0.02 * decline_years)


# ── 工厂函数 ────────────────────────────────────────────────────────────────


def maturation_curve(
    curve_type: str,
    age_days: float,
    **kwargs,
) -> float:
    """
    统一入口：根据 curve_type 调用对应的发育曲线。

    Supported types:
      "sigmoid":         k, midpoint_days
      "linear_saturate":  max_days
      "sigmoid_three_phase": k_rise, k_fall, peak_days, peak_value
      "constant":        (无参数)
    """
    match curve_type:
        case "sigmoid":
            return sigmoid(age_days, kwargs["k"], kwargs["midpoint_days"])
        case "linear_saturate":
            return linear_saturate(age_days, kwargs["max_days"])
        case "sigmoid_three_phase":
            return sigmoid_three_phase(
                age_days,
                kwargs["k_rise"],
                kwargs["k_fall"],
                kwargs["peak_days"],
                kwargs.get("peak_value", 1.0),
            )
        case "constant":
            return constant(age_days)
        case _:
            raise ValueError(f"Unknown maturation curve type: {curve_type}")


def decline_curve(
    curve_type: str,
    age_days: float,
    **kwargs,
) -> float:
    """
    统一入口：根据 curve_type 调用对应的衰退曲线。

    Supported types:
      "gompertz":       onset_days, rate_per_day
      "linear":           onset_days, min_factor
      "constant":         (无参数)
    """
    match curve_type:
        case "gompertz":
            return gompertz_decline(age_days, kwargs["onset_days"], kwargs["rate_per_day"])
        case "linear":
            return linear_decline(age_days, kwargs["onset_days"], kwargs.get("min_factor", 0.3))
        case "constant":
            return constant(age_days)
        case _:
            raise ValueError(f"Unknown decline curve type: {curve_type}")
