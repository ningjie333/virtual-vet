"""
Acute Renal Failure Module — 急性肾衰竭 ODE 动力学模型

状态变量（5 个 ODE）:
  1. nephron_damage  (0→1)   肾单位损伤 — logistic 增长
  2. gfr_decline     (0→1)    GFR 下降比例 — 非线性映射自 nephron_damage^1.5
  3. bun_accumulation (0→∞)  尿素氮累积 — 指数累积，清除率与残余肾功能正相关
  4. potassium_shift (0→1)   血钾偏移 — 一阶滞后于 gfr_decline
  5. metabolic_acidosis (0→1) 代谢性酸中毒 — 排酸能力下降 + 乳酸堆积

临床表现（涌现结果）:
  - GFR↓ → 氮质血症（BUN↑）→ 尿量减少
  - K+↑ → 高钾血症 → 心动过缓
  - 酸中毒 → pH↓ → 呼吸代偿（深大呼吸）
  - 晚期：水钠潴留 → 高血压
"""

import math
import logging

from . import DiseaseModule, register_disease
from ..logger_config import get_logger

logger = get_logger(__name__)


class AcuteRenalFailureModule(DiseaseModule):
    """
    急性肾衰竭 ODE 模型。

    动力学参数基于犬类急性肾损伤文献值校准：
    - 肾单位损伤 doubling time: ~15-30 min（重度）
    - GFR 非线性下降：damage^1.5 关系
    - BUN 累积：半衰期与残余肾功能成反比
    - 高钾血症：GFR < 25% 时显著
    - 酸中毒：晚期表现，与 GFR 下降正相关
    """

    SEVERITY_PRESETS = {
        "mild": {
            "damage_rate": 0.005,
            "damage_K": 0.4,
        },
        "moderate": {
            "damage_rate": 0.008,
            "damage_K": 1.0,
        },
        "severe": {
            "damage_rate": 0.02,
            "damage_K": 0.95,
        },
    }

    def __init__(self, severity: str = "moderate"):
        super().__init__(name="acute_renal_failure")

        preset = self.SEVERITY_PRESETS.get(severity, self.SEVERITY_PRESETS["moderate"])

        # --- ODE 状态变量 ---
        self.nephron_damage = 0.05         # 肾单位损伤程度 (0-1)
        self.gfr_decline = 0.0             # GFR 下降比例 (0-1)
        self.potassium_shift = 0.0         # 血钾偏移 (mEq/L)
        self.metabolic_acidosis = 0.0      # 代谢性酸中毒程度 (0-1)

        # --- 动力学参数 ---
        self._damage_rate = preset["damage_rate"]       # 损伤增长速率 (1/s)
        self._damage_K = preset["damage_K"]             # 损伤 logistic 上限
        self._potassium_tau = 600.0                     # 血钾变化时间常数 (s) ~10min
        self._acidosis_tau = 900.0                      # 酸中毒时间常数 (s) ~15min
        self._gfr_exponent = 1.5                        # GFR 非线性指数

        logger.info(
            "AcuteRenalFailureModule created: severity=%s, rate=%.4f, K=%.2f",
            severity, preset["damage_rate"], preset["damage_K"],
        )

    def compute(self, dt: float, engine_state: dict) -> list[FactorCommand]:
        """
        推进急性肾衰竭 ODE 一个时间步，返回 FactorCommand 指令列表。

        ODE 系统（4 个耦合方程）:
          d(nephron_damage)/dt = rate * damage * (1 - damage/K)    # logistic
          gfr_decline = nephron_damage ^ 1.5                          # 非线性代数
          d(potassium)/dt = (k_target - potassium) / tau_k           # 一阶滞后
          d(acidosis)/dt = (acidosis_target - acidosis) / tau_a      # 一阶滞后
          注意: BUN 由 kidney.py 自己的 ODE 处理（GFR↓→BUN↑），此处不重复

        Args:
            dt: 时间步长（秒）
            engine_state: 引擎当前状态（只读）

        Returns:
            list[FactorCommand] 指令列表
        """
        if not self.active:
            return []

        # ---- Step 1: 更新 ODE 状态变量 ----

        # 1a. 肾单位损伤 — logistic 增长
        damage_growth = (
            self._damage_rate
            * self.nephron_damage
            * (1.0 - self.nephron_damage / self._damage_K)
        )
        # 即使损伤很小时也允许缓慢进展
        if self.nephron_damage < 0.01:
            damage_growth += 0.0005
        self.nephron_damage = self._clamp(damage_growth * dt + self.nephron_damage, 0.0, 1.0)

        # 1b. GFR 下降 — 非线性映射（damage^1.5）
        self.gfr_decline = self._clamp(self.nephron_damage ** self._gfr_exponent, 0.0, 1.0)

        # 1c. 血钾偏移 — 一阶滞后于 gfr_decline
        # GFR 越低，血钾目标越高（高钾血症）
        # gfr_decline=0 → k_target=0; gfr_decline=1 → k_target=3.0 mEq/L
        k_target = self.gfr_decline * 3.0
        k_rate = (k_target - self.potassium_shift) / self._potassium_tau
        self.potassium_shift = self._clamp(
            self.potassium_shift + k_rate * dt, 0.0, 3.5
        )

        # 1e. 代谢性酸中毒 — 一阶滞后
        # gfr_decline 越高，酸中毒越严重
        acidosis_target = self.gfr_decline * 0.8  # 最大酸中毒程度
        acidosis_rate = (acidosis_target - self.metabolic_acidosis) / self._acidosis_tau
        self.metabolic_acidosis = self._clamp(
            self.metabolic_acidosis + acidosis_rate * dt, 0.0, 1.0
        )

        # ---- Step 2: 计算引擎扰动因子 ----

        # 2a. GFR 乘子
        gfr_multiplier = 1.0 - self.gfr_decline
        gfr_multiplier = self._clamp(gfr_multiplier, 0.05, 1.0)

        # 2b. 血钾 — 直接设置目标值（引擎侧每步覆盖，不累积）
        # 返回绝对偏移量，引擎侧直接赋值而非累加
        potassium_add = self.potassium_shift

        # 2d. 心率偏移 — 高钾血症 → 心动过缓（负偏移）
        # 高钾时 HR 减慢，轻度肾衰可能反射性 HR 增快
        if self.potassium_shift > 1.5:
            hr_offset = -15.0 * (self.potassium_shift / 3.0)  # 最多减慢 15 bpm
        elif self.gfr_decline > 0.5:
            hr_offset = 5.0  # 早期代偿性心率增快
        else:
            hr_offset = 0.0

        # 2e. pH 影响 — 酸中毒降低血液 pH
        # pH_effect 最大约 -0.3（重度酸中毒）
        ph_effect = -self.metabolic_acidosis * 0.3

        # ---- Step 3: 组装 FactorCommand 指令列表 ----

        # 血钾：设绝对值（基线 4.2 + 偏移）
        potassium_target = 4.2 + self.potassium_shift

        # GFR 乘子：写入 kidney._disease_gfr_multiplier，由 kidney.compute() 每步应用
        commands = [
            self._cmd("kidney._disease_gfr_multiplier", "set", round(gfr_multiplier, 4)),
            self._cmd("blood.potassium", "set", round(potassium_target, 3)),
            self._cmd("blood.pH", "set", round(7.40 + ph_effect, 4)),
            self._cmd("heart.heart_rate", "add", round(hr_offset, 2)),
        ]

        logger.debug(
            "ARF t=%.0fs: damage=%.3f gfr_dec=%.3f k+=%.3f acid=%.3f"
            " gfr_mul=%.3f hr_off=%.1f",
            self.elapsed_since_activation_s,
            self.nephron_damage, self.gfr_decline,
            self.potassium_shift, self.metabolic_acidosis,
            gfr_multiplier, hr_offset,
        )

        return commands

    def summary(self) -> dict:
        """返回当前疾病状态摘要"""
        return {
            "name": self.name,
            "active": self.active,
            "nephron_damage": round(self.nephron_damage, 4),
            "gfr_decline": round(self.gfr_decline, 4),
            # BUN 由 kidney.py ODE 处理，此处不再追踪
            "potassium_shift": round(self.potassium_shift, 3),
            "metabolic_acidosis": round(self.metabolic_acidosis, 4),
        }


# ---------- 自动注册 ----------
register_disease("acute_renal_failure", AcuteRenalFailureModule)
