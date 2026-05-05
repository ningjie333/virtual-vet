"""
Pneumonia Module — 大叶性肺炎 ODE 动力学模型

状态变量（4 个 ODE）：
  1. alveolar_exudate  (0→1)   肺泡渗出物 — logistic 增长
  2. bacterial_load   (0→∞)   细菌载量 — 指数增长 + 免疫清除
  3. fever_state      (0→1)   体温偏移 — 延迟于细菌增长（一阶滞后）
  4. tissue_hypoxia   (0→1)   组织缺氧 — 非线性 (exudate² 驱动)

临床表现（涌现结果，非硬编码阶段表）：
  - 渗出物↑ → diffusion_multiplier↓ → 低氧血症
  - 细菌↑ → fever↑ → 心率↑（代谢需求↑）
  - 缺氧² → tissue_hypoxia↑ → 晚期脓毒性血管扩张 → SVR↓
  - 低氧 + 酸中毒 → 呼吸代偿（由引擎 RR 模块自然响应）

所有扰动以乘法因子形式返回，与 SimulationInterface.apply_params 兼容。
"""

import math
import logging

from . import DiseaseModule, register_disease
from ..logger_config import get_logger

logger = get_logger(__name__)


class PneumoniaModule(DiseaseModule):
    """
    大叶性肺炎 ODE 模型。

    动力学参数基于犬类肺炎文献值校准：
    - 细菌 doubling time: ~20 min（无免疫清除时）
    - 渗出物 logistic K: 0.8（最大填充 80% 肺泡腔）
    - 发热延迟 τ: ~30 min（内源性致热原产生滞后）
    - 脓毒性血管扩张阈值: tissue_hypoxia > 0.6

    Usage:
        pneumonia = PneumoniaModule(severity="moderate")
        pneumonia.activate(current_time_s=0.0)
        # 每步调用:
        factors = pneumonia.compute(dt=0.1, engine_state=state)
        # factors → {"lung": {"diffusion_multiplier": 0.7, ...}, ...}
    """

    # ---------- 严重程度预设 ----------
    SEVERITY_PRESETS = {
        "mild": {
            "bacterial_seed": 0.1,
            "growth_rate": 0.02,
            "exudate_K": 0.4,
            "immune_clearance": 0.015,
        },
        "moderate": {
            "bacterial_seed": 0.3,
            "growth_rate": 0.035,
            "exudate_K": 0.7,
            "immune_clearance": 0.01,
        },
        "severe": {
            "bacterial_seed": 0.6,
            "growth_rate": 0.05,
            "exudate_K": 0.95,
            "immune_clearance": 0.005,
        },
    }

    def __init__(self, severity: str = "moderate"):
        super().__init__(name="pneumonia")

        preset = self.SEVERITY_PRESETS.get(severity, self.SEVERITY_PRESETS["moderate"])

        # --- ODE 状态变量 ---
        self.alveolar_exudate = 0.0    # 肺泡渗出物填充比例 (0-1)
        self.bacterial_load = preset["bacterial_seed"]  # 细菌载量 (arbitrary, 0-∞)
        self.fever_state = 0.0         # 发热程度 (0-1, 0=正常体温)
        self.tissue_hypoxia = 0.0      # 组织缺氧 (0-1)

        # --- 动力学参数 ---
        self._growth_rate = preset["growth_rate"]          # 细菌净增长率 (1/s)
        self._exudate_K = preset["exudate_K"]              # 渗出物 logistic 上限
        self._exudate_r = 0.005                            # 渗出物增长速率 (1/s)
        self._immune_clearance = preset["immune_clearance"]  # 免疫清除率 (1/s)
        self._fever_tau = 1800.0                           # 发热延迟时间常数 (s) ~30min
        self._hypoxia_exponent = 2.0                       # 缺氧非线性指数

        # --- 脓毒症阈值 ---
        self._sepsis_hypoxia_threshold = 0.6   # tissue_hypoxia 超过此值触发血管扩张
        self._svr_sepsis_min = 0.5             # SVR 最低降至正常的 50%

        logger.info(
            "PneumoniaModule created: severity=%s, seed=%.2f, growth=%.4f",
            severity, preset["bacterial_seed"], preset["growth_rate"],
        )

    def compute(self, dt: float, engine_state: dict) -> list[FactorCommand]:
        """
        推进肺炎 ODE 一个时间步，返回 FactorCommand 指令列表。

        ODE 系统（4 个耦合方程）：
          d(exudate)/dt = r * exudate * (1 - exudate/K)          # logistic
          d(bacteria)/dt = growth * bacteria - immune * bacteria   # 净增长
          d(fever)/dt = (fever_target - fever) / tau              # 一阶滞后
          d(hypoxia)/dt = f(exudate², bacteria)                    # 非线性驱动

        Args:
            dt: 时间步长（秒）
            engine_state: 引擎当前状态（只读）

        Returns:
            list[FactorCommand] 指令列表
        """
        if not self.active:
            return []

        # ---- Step 1: 更新 ODE 状态变量 ----

        # 1a. 肺泡渗出物 — logistic 增长
        # 渗出速率与细菌载量正相关（细菌越多 → 炎症越强 → 渗出越多）
        bacterial_factor = self._clamp(self.bacterial_load / (self.bacterial_load + 1.0), 0.0, 1.0)
        exudate_growth = (
            self._exudate_r
            * self.alveolar_exudate
            * (1.0 - self.alveolar_exudate / self._exudate_K)
            * bacterial_factor
        )
        # 即使 exudate=0，也允许从细菌直接触发初始渗出
        if self.alveolar_exudate < 0.01 and bacterial_factor > 0.1:
            exudate_growth += 0.001 * bacterial_factor
        self.alveolar_exudate = self._clamp(self.alveolar_exudate + exudate_growth * dt, 0.0, 1.0)

        # 1b. 细菌载量 — 指数增长 - 免疫清除
        # 免疫清除与 fever_state 正相关（发热增强免疫功能）
        immune_effect = self._immune_clearance * (1.0 + 0.5 * self.fever_state)
        net_growth = (self._growth_rate - immune_effect) * self.bacterial_load
        self.bacterial_load = max(0.0, self.bacterial_load + net_growth * dt)

        # 1c. 发热 — 一阶滞后于细菌载量
        # fever_target 与 bacterial_load 成正比（S 型映射）
        fever_target = self._clamp(self.bacterial_load / (self.bacterial_load + 2.0), 0.0, 1.0)
        fever_rate = (fever_target - self.fever_state) / self._fever_tau
        self.fever_state = self._clamp(self.fever_state + fever_rate * dt, 0.0, 1.0)

        # 1d. 组织缺氧 — 由渗出物² 驱动（非线性）
        # exudate 低时缺氧轻微，超过阈值后急剧恶化
        exudate_hypoxia = self.alveolar_exudate ** self._hypoxia_exponent
        # 缺氧还受细菌毒素影响（细菌载量高 → 线粒体功能障碍）
        toxin_hypoxia = self._clamp(self.bacterial_load / (self.bacterial_load + 5.0), 0.0, 0.3)
        hypoxia_target = self._clamp(exudate_hypoxia + toxin_hypoxia, 0.0, 1.0)
        # 缺氧变化比渗出物慢（组织氧储备缓冲）
        hypoxia_tau = 600.0  # 10 min 缓冲
        hypoxia_rate = (hypoxia_target - self.tissue_hypoxia) / hypoxia_tau
        self.tissue_hypoxia = self._clamp(self.tissue_hypoxia + hypoxia_rate * dt, 0.0, 1.0)

        # ---- Step 2: 计算引擎扰动因子 ----

        # 2a. 肺扩散能力 — 渗出物填充肺泡 → 有效扩散面积↓
        # exudate=0 → multiplier=1.0 (正常)
        # exudate=1 → multiplier=0.1 (仅剩 10% 扩散能力)
        diffusion_multiplier = 1.0 - self.alveolar_exudate * 0.9
        diffusion_multiplier = self._clamp(diffusion_multiplier, 0.1, 1.0)

        # 2b. 心率偏移 — 发热增加代谢需求
        # fever=0 → offset=0; fever=1 → offset=+20 bpm
        heart_rate_offset = self.fever_state * 20.0

        # 2c. SVR 乘子 — 晚期脓毒性血管扩张
        # tissue_hypoxia > 阈值时触发，进行性血管扩张（NO 释放）
        if self.tissue_hypoxia > self._sepsis_hypoxia_threshold:
            sepsis_severity = (
                (self.tissue_hypoxia - self._sepsis_hypoxia_threshold)
                / (1.0 - self._sepsis_hypoxia_threshold)
            )
            svr_multiplier = 1.0 - (1.0 - self._svr_sepsis_min) * sepsis_severity
        else:
            svr_multiplier = 1.0
        svr_multiplier = self._clamp(svr_multiplier, self._svr_sepsis_min, 1.0)

        # ---- Step 3: 组装 FactorCommand 指令列表 ----

        commands = [
            self._cmd("lung.diffusion_coefficient", "multiply",
                      round(diffusion_multiplier, 4)),
            self._cmd("heart.heart_rate", "add",
                      round(heart_rate_offset, 2)),
        ]
        if svr_multiplier < 1.0:
            commands.append(
                self._cmd("heart.SVR", "multiply",
                          round(svr_multiplier, 4)),
            )

        logger.debug(
            "pneumonia t=%.0fs: exudate=%.3f bacteria=%.3f fever=%.3f hypoxia=%.3f"
            " diff=%.3f hr_offset=%.1f svr=%.3f",
            self.elapsed_since_activation_s,
            self.alveolar_exudate, self.bacterial_load,
            self.fever_state, self.tissue_hypoxia,
            diffusion_multiplier, heart_rate_offset, svr_multiplier,
        )

        return commands

    def summary(self) -> dict:
        """返回当前疾病状态摘要（调试用）"""
        return {
            "name": self.name,
            "active": self.active,
            "alveolar_exudate": round(self.alveolar_exudate, 4),
            "bacterial_load": round(self.bacterial_load, 4),
            "fever_state": round(self.fever_state, 4),
            "tissue_hypoxia": round(self.tissue_hypoxia, 4),
        }


# ---------- 自动注册 ----------
register_disease("pneumonia", PneumoniaModule)
