"""
Toxicology Module - 毒理学效应仿真
基于 Liu et al. (1993) JACC 21:260-268

可卡因的两条独立通路：
  1. 直接心脏抑制（Na+ 通道阻断）：短暂，τ = 5 min，恢复后不影响后效
  2. 交感介导外周血管收缩：2 min 达峰，持续 ≥ 30 min

神经节阻断实验证明：两条通路相互独立，机制不同。
"""

import math
from parameters import (
    COCAINE_DOSE_MG_KG,
    COCAINE_T_DECAY_MIN,
    COCAINE_MAX_CONTRACTILITY_DROP,
    COCAINE_SVR_PEAK_FACTOR,
    COCAINE_SVR_T_DECAY_MIN,
)


class ToxicologyModule:
    """
    毒理学模块：处理药物（可卡因）的两路独立效应

    状态变量：
      contractility_depression : float  # 心脏抑制因子 (0 = 无抑制, -0.19 = 最大)
      svr_factor               : float  # SVR 倍数 (1.0 = 正常, 2.0 = 最大收缩)
    """

    def __init__(self, weight_kg: float):
        self.w = weight_kg

        # 心脏抑制（直接毒性，短暂）
        self.contractility_depression = 0.0   # 0 = 无效，最大 = COCAINE_MAX_CONTRACTILITY_DROP

        # 交感血管收缩（持续）
        self.svr_factor = 1.0                 # 1.0 = 正常，max = COCAINE_SVR_PEAK_FACTOR

        # 注射后时间
        self._t_since_injection_min = None   # None = 未注射

    def administer_cocaine(self, dose_mg_kg: float = COCAINE_DOSE_MG_KG):
        """
        注射可卡因（IV）

        Args:
            dose_mg_kg: 剂量 mg/kg（默认 3 mg/kg，文献标准剂量）
        """
        self._t_since_injection_min = 0.0

        # 效应强度与剂量成正比（线性假设，简化）
        dose_ratio = dose_mg_kg / COCAINE_DOSE_MG_KG

        # 心脏抑制：剂量依赖性最大抑制（存负值，公式 contractility_factor = 1.0 + depression）
        self._max_depression = -COCAINE_MAX_CONTRACTILITY_DROP * dose_ratio
        # 限制最大抑制不超过 60%（避免不可逆心脏停搏）
        self._max_depression = -min(0.60, abs(self._max_depression))

        # SVR：交感激活程度（剂量依赖）
        self._max_svr_factor = 1.0 + (COCAINE_SVR_PEAK_FACTOR - 1.0) * dose_ratio
        self._max_svr_factor = min(3.5, self._max_svr_factor)  # 上限 3.5 倍

    def compute(self, dt: float):
        """
        推进毒理学状态一个时间步

        心脏抑制：一阶指数衰减
          d(depression)/dt = -depression / τ
          → depression(t) = max_depression * exp(-t / τ)

        交感血管收缩：一阶指数衰减（更慢）
          d(svr_factor-1)/dt = -(svr_factor-1) / τ_svr
        """
        if self._t_since_injection_min is None:
            # 未注射药物，无效应
            return {
                "contractility_factor": 1.0,
                "svr_factor": 1.0,
                "cocaine_active": False,
            }

        t_min = self._t_since_injection_min

        # 心脏直接抑制：快衰减（τ = 5 min）
        # 5 min 后剩余 ≈ exp(-5/5) = 36.8%
        # 10 min 后剩余 ≈ exp(-10/5) = 13.5%
        self.contractility_depression = self._max_depression * math.exp(-t_min / COCAINE_T_DECAY_MIN)

        # 交感血管收缩：慢衰减（τ = 30 min）
        # 30 min 后剩余 ≈ 36.8%（与实验观测一致：持续 ≥ 30 min）
        self.svr_factor = 1.0 + (self._max_svr_factor - 1.0) * math.exp(-t_min / COCAINE_SVR_T_DECAY_MIN)

        # 更新时间（dt 是秒，转分钟）
        self._t_since_injection_min += dt / 60.0

        # 心脏收缩力因子 = 1 + depression（depression 是负值）
        contractility_factor = 1.0 + self.contractility_depression  # e.g. 0.81

        return {
            "contractility_factor": contractility_factor,
            "svr_factor": self.svr_factor,
            "cocaine_active": True,
            "t_since_injection_min": t_min,
            "depression_ratio": abs(self.contractility_depression) / max(0.001, abs(self._max_depression)),
            "svr_ratio": (self.svr_factor - 1.0) / max(0.001, (self._max_svr_factor - 1.0)),
        }

    def summary(self) -> dict:
        """返回当前毒理状态摘要"""
        if self._t_since_injection_min is None:
            return {
                "cocaine_dosed": False,
                "contractility_factor": 1.0,
                "svr_factor": 1.0,
            }
        return {
            "cocaine_dosed": True,
            "t_since_injection_min": round(self._t_since_injection_min, 2),
            "contractility_factor": round(1.0 + self.contractility_depression, 3),
            "svr_factor": round(self.svr_factor, 3),
        }
