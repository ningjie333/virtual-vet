"""
Dilated Cardiomyopathy Module — 扩张型心肌病 ODE 动力学模型

状态变量（4 个 ODE）:
  1. myocardial_fibrosis  (0→1)   心肌纤维化 — logistic 增长（不可逆）
  2. contractility_loss   (0→1)   收缩力丧失比例 — 非线性映射自 fibrosis^1.2
  3. ventricular_dilation (0→1)   心室扩张 — 一阶滞后于 contractility_loss
  4. fluid_retention     (0→1)   水钠潴留 — RAAS 激活（低 CO 驱动）

临床表现（涌现结果）:
  - 收缩力↓ → CO↓ → MAP↓ → 代偿性 HR↑（早期）
  - CO↓↓ → Frank-Starling 代偿 → 心室扩张 → 恶性循环
  - RAAS 激活 → 水钠潴留 → 前负荷↑ → CVP↑ → 肺淤血
  - 晚期：MAP↓↓ + HR↓↓（失代偿） → 心源性休克
  - 肾灌注↓ → GFR↓ → 肾前性氮质血症（继发肾损伤）
"""

import logging

from . import DiseaseModule, register_disease
from ..logger_config import get_logger

logger = get_logger(__name__)


class DilatedCardiomyopathyModule(DiseaseModule):
    """
    扩张型心肌病 ODE 模型。

    动力学参数基于犬类 DCM 文献值校准：
    - 心肌纤维化进展：数周到数月（游戏时间压缩为 10-20 分钟）
    - 收缩力丧失：fibrosis^1.2 非线性关系
    - 心室扩张：τ ~15 min（代偿性重构）
    - 水钠潴留：RAAS 激活，τ ~20 min

    Usage:
        dcm = DilatedCardiomyopathyModule(severity="moderate")
        dcm.activate(current_time_s=0.0)
        factors = dcm.compute(dt=0.1, engine_state=state)
    """

    SEVERITY_PRESETS = {
        "mild": {
            "fibrosis_rate": 0.003,
            "fibrosis_K": 0.4,
        },
        "moderate": {
            "fibrosis_rate": 0.006,
            "fibrosis_K": 0.75,
        },
        "severe": {
            "fibrosis_rate": 0.012,
            "fibrosis_K": 0.95,
        },
    }

    def __init__(self, severity: str = "moderate"):
        super().__init__(name="dilated_cardiomyopathy")

        preset = self.SEVERITY_PRESETS.get(severity, self.SEVERITY_PRESETS["moderate"])

        # --- ODE 状态变量 ---
        self.myocardial_fibrosis = 0.05      # 心肌纤维化程度 (0-1)
        self.contractility_loss = 0.0         # 收缩力丧失比例 (0-1)
        self.ventricular_dilation = 0.0       # 心室扩张程度 (0-1)
        self.fluid_retention = 0.0            # 水钠潴留程度 (0-1)

        # --- 动力学参数 ---
        self._fibrosis_rate = preset["fibrosis_rate"]    # 纤维化增长速率 (1/s)
        self._fibrosis_K = preset["fibrosis_K"]          # 纤维化 logistic 上限
        self._dilation_tau = 900.0                        # 心室扩张时间常数 (s) ~15min
        self._raas_tau = 1200.0                           # RAAS 激活时间常数 (s) ~20min

        logger.info(
            "DilatedCardiomyopathyModule created: severity=%s, rate=%.4f, K=%.2f",
            severity, preset["fibrosis_rate"], preset["fibrosis_K"],
        )

    def compute(self, dt: float, engine_state: dict) -> list[FactorCommand]:
        """
        推进 DCM ODE 一个时间步，返回 FactorCommand 指令列表。

        ODE 系统（4 个耦合方程）:
          d(fibrosis)/dt = rate * fibrosis * (1 - fibrosis/K)     # logistic
          contractility_loss = fibrosis ^ 1.2                       # 非线性代数
          d(dilation)/dt = (dilation_target - dilation) / tau_d   # 一阶滞后
          d(fluid)/dt = (fluid_target - fluid) / tau_raas         # RAAS 驱动

        Args:
            dt: 时间步长（秒）
            engine_state: 引擎当前状态（只读）

        Returns:
            list[FactorCommand] 指令列表
        """
        if not self.active:
            return []

        # ---- Step 1: 更新 ODE 状态变量 ----

        # 1a. 心肌纤维化 — logistic 增长（不可逆进程）
        fibrosis_growth = (
            self._fibrosis_rate
            * self.myocardial_fibrosis
            * (1.0 - self.myocardial_fibrosis / self._fibrosis_K)
        )
        # 即使纤维化很小时也允许缓慢进展
        if self.myocardial_fibrosis < 0.01:
            fibrosis_growth += 0.0003
        self.myocardial_fibrosis = self._clamp(
            self.myocardial_fibrosis + fibrosis_growth * dt, 0.0, 1.0
        )

        # 1b. 收缩力丧失 — 非线性映射（fibrosis^1.2）
        # 纤维化早期收缩力下降缓慢，超过阈值后加速恶化
        self.contractility_loss = self._clamp(
            self.myocardial_fibrosis ** 1.2, 0.0, 1.0
        )

        # 1c. 心室扩张 — 一阶滞后于 contractility_loss
        # 收缩力越低，心室扩张越严重（Frank-Starling 代偿 → 病理性重构）
        dilation_target = self.contractility_loss * 0.8  # 最大扩张 80%
        dilation_rate = (dilation_target - self.ventricular_dilation) / self._dilation_tau
        self.ventricular_dilation = self._clamp(
            self.ventricular_dilation + dilation_rate * dt, 0.0, 1.0
        )

        # 1d. 水钠潴留 — RAAS 激活（低 CO 驱动）
        # 读取当前 CO 判断 RAAS 激活程度
        co = engine_state.get("heart", {}).get("cardiac_output_ml_min", 1700.0)
        co_ratio = co / 1700.0  # 归一化到健康犬基础 CO
        # CO 越低 → RAAS 激活越强 → 水钠潴留越多
        if co_ratio < 0.7:
            fluid_target = self._clamp(1.0 - co_ratio, 0.0, 0.8)
        else:
            fluid_target = 0.0
        fluid_rate = (fluid_target - self.fluid_retention) / self._raas_tau
        self.fluid_retention = self._clamp(
            self.fluid_retention + fluid_rate * dt, 0.0, 1.0
        )

        # ---- Step 2: 计算引擎扰动因子 ----

        # 2a. 收缩力乘子 — 直接降低心脏泵血能力
        # contractility_loss=0 → multiplier=1.0（正常）
        # contractility_loss=1 → multiplier=0.2（仅剩 20% 收缩力）
        contractility_multiplier = 1.0 - self.contractility_loss * 0.8
        contractility_multiplier = self._clamp(contractility_multiplier, 0.2, 1.0)

        # 2b. 心率偏移 — 早期代偿性心动过速，晚期失代偿心动过缓
        # 早期（contractility_loss < 0.5）：交感代偿 → HR↑
        # 晚期（contractility_loss >= 0.5）：心脏传导受损 → HR↓
        if self.contractility_loss < 0.5:
            hr_offset = 15.0 * self.contractility_loss  # 最多 +15 bpm（代偿）
        else:
            hr_offset = 7.5 - 30.0 * (self.contractility_loss - 0.5)  # 转为负值（失代偿）
        hr_offset = self._clamp(hr_offset, -20.0, 15.0)

        # 2c. CVP 升高 — 水钠潴留 + 心室扩张 → 前负荷↑ → 静脉淤血
        # fluid_retention=0 → cvp_add=0; fluid_retention=0.8 → cvp_add=8 mmHg
        cvp_add = self.fluid_retention * 10.0

        # 2d. 肾脏灌注 — 低 CO → 肾血流↓ → GFR↓（肾前性损伤）
        # CO 下降越多，GFR 乘子越低
        gfr_multiplier = self._clamp(co_ratio + 0.2, 0.3, 1.0)

        # 2e. 血容量增加 — 水钠潴留
        # fluid_retention=0 → 0; fluid_retention=0.8 → +15% 血容量
        bv_add_pct = self.fluid_retention * 0.15

        # ---- Step 3: 组装 FactorCommand 指令列表 ----

        commands = [
            self._cmd("heart.contractility_factor", "multiply",
                      round(contractility_multiplier, 4)),
            self._cmd("heart.heart_rate", "add",
                      round(hr_offset, 2)),
            self._cmd("heart.CVP", "add",
                      round(cvp_add, 2)),
            self._cmd("heart.blood_volume", "multiply",
                      round(1.0 + bv_add_pct, 4)),
            self._cmd("kidney.GFR", "multiply",
                      round(gfr_multiplier, 4)),
        ]

        logger.debug(
            "DCM t=%.0fs: fibrosis=%.3f contr_loss=%.3f dilation=%.3f fluid=%.3f"
            " contr_mul=%.3f hr_off=%.1f gfr_mul=%.3f",
            self.elapsed_since_activation_s,
            self.myocardial_fibrosis, self.contractility_loss,
            self.ventricular_dilation, self.fluid_retention,
            contractility_multiplier, hr_offset, gfr_multiplier,
        )

        return commands

    def summary(self) -> dict:
        return {
            "name": self.name,
            "active": self.active,
            "myocardial_fibrosis": round(self.myocardial_fibrosis, 4),
            "contractility_loss": round(self.contractility_loss, 4),
            "ventricular_dilation": round(self.ventricular_dilation, 4),
            "fluid_retention": round(self.fluid_retention, 4),
        }


# ---------- 自动注册 ----------
register_disease("dilated_cardiomyopathy", DilatedCardiomyopathyModule)
