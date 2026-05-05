"""
Phosphorus Poisoning Module — 磷化锌/磷化铝灭鼠药中毒 ODE 动力学模型

状态变量（4 个 ODE）:
  1. cellular_toxicity   (0→1)   细胞毒性 — logistic 增长（磷化氢直接损伤细胞）
  2. myocardial_depression (0→1)  心肌抑制 — 非线性映射自 toxicity^1.3
  3. metabolic_acidosis  (0→1)   代谢性酸中毒 — 一阶滞后（乳酸堆积 + 排酸障碍）
  4. renal_injury        (0→1)   肾损伤 — 一阶滞后（肾小管坏死）

临床表现（涌现结果）:
  - 细胞毒性↑ → 心肌收缩力↓↓ → CO↓ → MAP↓
  - 酸中毒 → pH↓ → 呼吸代偿（深大呼吸）
  - 肾损伤 → GFR↓ → BUN↑ → 高钾血症
  - 晚期：低体温（代谢衰竭）
  - 特征性"大蒜味"（病史线索，非 ODE 变量）

治疗：无特效解毒剂，主要支持治疗（补液、纠正酸中毒）
"""

import logging

from . import DiseaseModule, register_disease
from ..logger_config import get_logger

logger = get_logger(__name__)


class PhosphorusPoisoningModule(DiseaseModule):
    """
    磷化锌/磷化铝灭鼠药中毒 ODE 模型。

    动力学参数基于兽医毒理学文献校准：
    - 细胞毒性 logistic K: 0.85（最大损伤 85%，保留部分代偿）
    - 心肌抑制：toxicity^1.3 非线性关系（早期影响小，超过阈值后加速）
    - 酸中毒 τ: ~20 min（乳酸快速堆积）
    - 肾损伤 τ: ~30 min（肾小管坏死进展相对慢）

    Usage:
        poisoning = PhosphorusPoisoningModule(severity="moderate")
        poisoning.activate(current_time_s=0.0)
        factors = poisoning.compute(dt=0.1, engine_state=state)
    """

    SEVERITY_PRESETS = {
        "mild": {
            "toxicity_rate": 0.004,
            "toxicity_K": 0.4,
        },
        "moderate": {
            "toxicity_rate": 0.008,
            "toxicity_K": 0.7,
        },
        "severe": {
            "toxicity_rate": 0.015,
            "toxicity_K": 0.9,
        },
    }

    def __init__(self, severity: str = "moderate"):
        super().__init__(name="phosphorus_poisoning")

        preset = self.SEVERITY_PRESETS.get(severity, self.SEVERITY_PRESETS["moderate"])

        # --- ODE 状态变量 ---
        self.cellular_toxicity = 0.05       # 细胞毒性程度 (0-1)
        self.myocardial_depression = 0.0     # 心肌抑制程度 (0-1)
        self.metabolic_acidosis = 0.0        # 代谢性酸中毒程度 (0-1)
        self.renal_injury = 0.0              # 肾损伤程度 (0-1)

        # --- 动力学参数 ---
        self._toxicity_rate = preset["toxicity_rate"]    # 毒性增长速率 (1/s)
        self._toxicity_K = preset["toxicity_K"]          # 毒性 logistic 上限
        self._acidosis_tau = 1200.0                       # 酸中毒时间常数 (s) ~20min
        self._renal_tau = 1800.0                          # 肾损伤时间常数 (s) ~30min

        logger.info(
            "PhosphorusPoisoningModule created: severity=%s, rate=%.4f, K=%.2f",
            severity, preset["toxicity_rate"], preset["toxicity_K"],
        )

    def compute(self, dt: float, engine_state: dict) -> list:
        """
        推进磷中毒 ODE 一个时间步，返回 FactorCommand 指令列表。

        ODE 系统（4 个耦合方程）:
          d(toxicity)/dt = rate * toxicity * (1 - toxicity/K)    # logistic
          myocardial_depression = toxicity ^ 1.3                    # 非线性代数
          d(acidosis)/dt = (acid_target - acidosis) / tau_a       # 一阶滞后
          d(renal)/dt = (renal_target - renal) / tau_r            # 一阶滞后

        Args:
            dt: 时间步长（秒）
            engine_state: 引擎当前状态（只读）

        Returns:
            list[FactorCommand] 指令列表
        """
        if not self.active:
            return []

        # ---- Step 1: 更新 ODE 状态变量 ----

        # 1a. 细胞毒性 — logistic 增长
        toxicity_growth = (
            self._toxicity_rate
            * self.cellular_toxicity
            * (1.0 - self.cellular_toxicity / self._toxicity_K)
        )
        # 即使毒性很小时也允许缓慢进展
        if self.cellular_toxicity < 0.01:
            toxicity_growth += 0.0003
        self.cellular_toxicity = self._clamp(
            self.cellular_toxicity + toxicity_growth * dt, 0.0, 1.0
        )

        # 1b. 心肌抑制 — 非线性映射（toxicity^1.3）
        # 早期毒性对心肌影响小，超过阈值后加速恶化
        self.myocardial_depression = self._clamp(
            self.cellular_toxicity ** 1.3, 0.0, 1.0
        )

        # 1c. 代谢性酸中毒 — 一阶滞后
        # toxicity 越高，酸中毒目标越严重
        # toxicity=0 → acid_target=0; toxicity=1 → acid_target=0.85
        acid_target = self.cellular_toxicity * 0.85
        acidosis_rate = (acid_target - self.metabolic_acidosis) / self._acidosis_tau
        self.metabolic_acidosis = self._clamp(
            self.metabolic_acidosis + acidosis_rate * dt, 0.0, 1.0
        )

        # 1d. 肾损伤 — 一阶滞后
        # 肾损伤目标与 toxicity 正相关，但进展更慢
        renal_target = self.cellular_toxicity * 0.7  # 最大损伤 70%
        renal_rate = (renal_target - self.renal_injury) / self._renal_tau
        self.renal_injury = self._clamp(
            self.renal_injury + renal_rate * dt, 0.0, 1.0
        )

        # ---- Step 2: 计算引擎扰动因子 ----

        # 2a. 心肌收缩力乘子
        # myocardial_depression=0 → multiplier=1.0（正常）
        # myocardial_depression=1 → multiplier=0.25（仅剩 25% 收缩力）
        contractility_multiplier = 1.0 - self.myocardial_depression * 0.75
        contractility_multiplier = self._clamp(contractility_multiplier, 0.25, 1.0)

        # 2b. 心率偏移 — 早期代偿性心动过速
        # toxicity < 0.4: 交感代偿 → HR↑
        # toxicity >= 0.4: 心肌严重抑制 → HR↓（失代偿）
        if self.cellular_toxicity < 0.4:
            hr_offset = 10.0 * self.cellular_toxicity  # 最多 +10 bpm
        else:
            hr_offset = 4.0 - 20.0 * (self.cellular_toxicity - 0.4)  # 转为负值
        hr_offset = self._clamp(hr_offset, -15.0, 10.0)

        # 2c. GFR 乘子 — 肾损伤降低 GFR
        # renal_injury=0 → gfr_mul=1.0; renal_injury=0.7 → gfr_mul=0.3
        gfr_multiplier = 1.0 - self.renal_injury
        gfr_multiplier = self._clamp(gfr_multiplier, 0.2, 1.0)

        # 2d. HCO₃⁻ 降低 — 代谢性酸中毒的核心表现
        # 通过降低血管 HCO₃⁻ 让 Henderson-Hasselbalch 方程自然算出低 pH
        # acidosis=0 → hco3_target=24（正常）; acidosis=1 → hco3_target=8（严重酸中毒）
        hco3_target = 24.0 - self.metabolic_acidosis * 16.0  # 24 → 8 mEq/L
        hco3_target = self._clamp(hco3_target, 6.0, 24.0)

        # 2e. 体温 — 初期轻度升高（代谢亢进），晚期降低（循环衰竭）
        if self.cellular_toxicity < 0.5:
            temp_offset = self.cellular_toxicity * 1.5  # 最多 +1.5°C
        else:
            temp_offset = 0.75 - 2.0 * (self.cellular_toxicity - 0.5)  # 转为负值
        temp_target = 38.5 + temp_offset  # 基线 38.5°C

        # ---- Step 3: 组装 FactorCommand 指令列表 ----

        commands = [
            self._cmd("heart.contractility_factor", "multiply",
                      round(contractility_multiplier, 4)),
            self._cmd("heart.heart_rate", "add",
                      round(hr_offset, 2)),
            self._cmd("kidney._disease_gfr_multiplier", "set",
                      round(gfr_multiplier, 4)),
            self._cmd("blood.HCO3", "set", round(hco3_target, 2)),
            self._cmd("blood.temperature", "set", round(temp_target, 2)),
        ]

        logger.debug(
            "phosphorus_poisoning t=%.0fs: toxicity=%.3f myocard=%.3f "
            "acid=%.3f renal=%.3f ctr_mul=%.3f hr_off=%.1f gfr_mul=%.3f",
            self.elapsed_since_activation_s,
            self.cellular_toxicity, self.myocardial_depression,
            self.metabolic_acidosis, self.renal_injury,
            contractility_multiplier, hr_offset, gfr_multiplier,
        )

        return commands

    def summary(self) -> dict:
        """返回当前疾病状态摘要"""
        return {
            "name": self.name,
            "active": self.active,
            "cellular_toxicity": round(self.cellular_toxicity, 4),
            "myocardial_depression": round(self.myocardial_depression, 4),
            "metabolic_acidosis": round(self.metabolic_acidosis, 4),
            "renal_injury": round(self.renal_injury, 4),
        }


# ---------- 自动注册 ----------
register_disease("phosphorus_poisoning", PhosphorusPoisoningModule)
