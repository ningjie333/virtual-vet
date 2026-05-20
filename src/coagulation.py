"""
Coagulation Module - 凝血系统
建模凝血因子动力学 + 临床可测指标（PT/aPTT/纤维蛋白原）:

  1. 肝脏合成因子 (II, V, VII, IX, X, XI) — 肝脏损伤 → 因子↓
  2. 炎症抑制因子合成 (cytokine > 0.4 → 合成↓)
  3. 凝血状态 = f(cytokine_level, factor levels)
  4. PT (Factor VII, 外源性途径), aPTT (Factors VIII, IX, XI, XII, 内源性途径)
  5. 纤维蛋白原 → 凝血酶生成 → DIC

FactorCommand 目标: blood.PT_sec, blood.aPTT_sec, blood.fibrinogen_mg_dL,
                    blood.coagulation_state
Step: 4.65 (liver之后, endocrine之前)
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FactorCommand:
    """统一因子写入接口"""
    target: str
    op: Literal["multiply", "add", "set"]
    value: float


class CoagulationModule:
    """
    凝血模块: 凝血因子动力学 + 临床凝血指标

    设计原则:
      - 状态存储于 self.blood.* (共享读写)
      - FactorCommand 用于写入其他模块(立即apply)
      - Step 4.65 (liver之后, endocrine之前)
      - 不建模完整 cascade（20+ 因子），聚焦临床可测指标
      - 简化：只建模主要因子（VII, V, II, IX, X, XI），PT/aPTT 从因子活性推导
    """

    # 正常因子活性基线
    _FACTOR_NORMAL = 1.0  # 100%

    def __init__(self, weight_kg: float, blood):
        self.w = weight_kg
        self.blood = blood  # BloodCompartment 引用

        # 凝血因子活性 (0-1, 1=100%)
        self.factor_VII = 1.0   # 外源性途径（肝脏合成）
        self.factor_V = 1.0    # 辅因子
        self.factor_II = 1.0   # 凝血酶原
        self.factor_IX = 1.0   # 内源性途径
        self.factor_X = 1.0    # 共同途径
        self.factor_XI = 1.0   # 内源性途径

        # 凝血状态 (0=正常, 1=DIC)
        self.coagulation_state = 0.0

        # 纤维蛋白原 (mg/dL)
        self.fibrinogen = 300.0

        # 肝脏健康（用于因子合成计算）
        self._liver_health = 1.0

    def _compute_liver_synthesis(self, liver_state: dict) -> float:
        """
        计算肝脏合成因子能力。

        Args:
            liver_state: liver.compute() 返回的 dict

        Returns:
            肝脏合成因子活性因子 (0-1)
        """
        liver_health = liver_state.get("health_factor", 1.0)
        liver_metabolic = liver_state.get("metabolic_activity", 1.0)
        # 肝脏合成能力 = health × metabolic_activity
        synthesis_factor = liver_health * liver_metabolic
        return max(0.05, synthesis_factor)  # 最低 5%（严重肝衰竭时）

    def _compute_inflammation_suppression(self) -> float:
        """
        计算炎症对因子合成的抑制。

        Returns:
            抑制因子 (0-1, 1=无抑制)
        """
        cytokine = self.blood.cytokine_level
        if cytokine > 0.4:
            # cytokine 0.4-1.0 → 抑制 0-60%
            suppression = (cytokine - 0.4) / 0.6 * 0.6
            return max(0.4, 1.0 - suppression)
        return 1.0

    def _compute_PT_sec(self) -> float:
        """
        计算凝血酶原时间 (PT)。

        PT 主要反映外源性途径（Factor VII）和共同途径（Factor X, V, II）。
        正常 PT ≈ 12s，因子活性下降导致 PT 延长。
        """
        # PT 公式（简化）：PT = 12 × (1 / effective_factor)
        # effective_factor = factor_VII × factor_X × factor_V × factor_II
        effective = self.factor_VII * self.factor_X * self.factor_V * self.factor_II
        effective = max(0.1, effective)
        pt = 12.0 / effective
        # 正常范围 10-18s，严重 DIC 可达 40s+
        return max(10.0, min(60.0, pt))

    def _compute_aPTT_sec(self) -> float:
        """
        计算活化部分凝血活酶时间 (aPTT)。

        aPTT 主要反映内源性途径（Factors VIII, IX, XI, XII）和共同途径。
        正常 aPTT ≈ 30s。
        """
        # aPTT 公式（简化）
        # 内源性有效因子 = factor_VIII × factor_IX × factor_XI × factor_X
        effective = self.factor_VII * 0.5 + self.factor_IX * self.factor_XI * self.factor_X
        effective = max(0.1, effective)
        aptt = 30.0 / effective
        return max(20.0, min(120.0, aptt))

    def _compute_coagulation_state(self) -> float:
        """
        计算凝血状态（0=正常, 1=DIC）。

        DIC 驱动因素：
        1. 细胞因子 > 0.6 → 高凝
        2. 纤维蛋白原显著降低 → 消耗性凝血障碍
        3. 血小板显著降低 → 消耗性凝血障碍
        """
        cytokine = self.blood.cytokine_level

        # 1. 细胞因子驱动的高凝
        # 基线预备态: 防止完全冻结，系统随时可响应
        baseline_coag = 0.02
        if cytokine > 0.6:
            cytokine_coag = (cytokine - 0.6) / 0.4  # 0-1
        else:
            cytokine_coag = 0.0
        cytokine_component = max(baseline_coag, cytokine_coag)

        # 2. 纤维蛋白原消耗
        fibrin_ratio = self.fibrinogen / 300.0  # 相对于正常
        if fibrin_ratio < 0.5:
            fibrin_coag = (0.5 - fibrin_ratio) / 0.5  # 0-1
        else:
            fibrin_coag = 0.0

        # 3. 血小板消耗
        plt_ratio = self.blood.PLT / 300.0
        if plt_ratio < 0.5:
            plt_coag = (0.5 - plt_ratio) / 0.5
        else:
            plt_coag = 0.0

        # 综合凝血状态：使用 cytokine_component（包含 baseline）作为主成分
        raw_state = max(cytokine_component, fibrin_coag * 0.5, plt_coag * 0.3)
        # 一阶滞后，避免突变
        tau = 900.0  # τ=900s (15分钟)
        return raw_state

    def compute(self, dt: float, liver_state: dict, immune_state: dict) -> dict:
        """
        计算凝血状态和FactorCommand

        Args:
            dt: 时间步长 (秒)
            liver_state: liver.compute() 返回的 dict
            immune_state: immune.compute() 返回的 dict (当前未使用，保留接口)

        Returns:
            dict包含所有状态变量 + factor_commands列表
        """
        dt_min = dt / 60.0

        # ── 1. 肝脏合成能力 ───────────────────────────────────────────
        liver_synthesis = self._compute_liver_synthesis(liver_state)
        self._liver_health = liver_synthesis

        # ── 2. 炎症抑制 ────────────────────────────────────────────────
        inflammation_factor = self._compute_inflammation_suppression()

        # ── 3. 因子动力学 ──────────────────────────────────────────────
        # 肝脏合成因子（所有因子由肝脏合成，除了 vWF 携带的 factor VIII）
        # 加速衰减：在肝衰竭/炎症时因子快速下降（半衰期约 30-60 分钟）
        synthesis_rate = 0.005 * dt_min * liver_synthesis * inflammation_factor
        decay_rate = 0.001 * dt_min  # 加速衰减

        targets = {
            "factor_VII": self.factor_VII,
            "factor_V": self.factor_V,
            "factor_II": self.factor_II,
            "factor_IX": self.factor_IX,
            "factor_X": self.factor_X,
            "factor_XI": self.factor_XI,
        }
        for name, current in targets.items():
            # 基线合成率: 极微弱，防止因子在1.0处完全冻结（但 liver failure 时仍能显著下降）
            baseline_synthesis = 0.0000001
            if current < 1.0:
                synthesis = synthesis_rate * (1.0 - current) + baseline_synthesis
            else:
                synthesis = baseline_synthesis
            decay = decay_rate * (current - 0.3) if current > 0.3 else 0.0
            new_val = current + synthesis - decay
            setattr(self, name, max(0.05, min(1.5, new_val)))

        # ── 4. PT / aPTT ──────────────────────────────────────────────
        pt_sec = self._compute_PT_sec()
        aptt_sec = self._compute_aPTT_sec()

        # 一阶滞后更新 blood.PT_sec / aPTT_sec
        tau_pt = 300.0  # τ=5min
        alpha_pt = dt / tau_pt
        self.blood.PT_sec += alpha_pt * (pt_sec - self.blood.PT_sec)
        self.blood.aPTT_sec += alpha_pt * (aptt_sec - self.blood.aPTT_sec)

        # ── 5. 纤维蛋白原 ──────────────────────────────────────────────
        # 炎症时急性期反应 → 纤维蛋白原升高（代偿）
        # 但严重 DIC 时消耗 > 合成 → 纤维蛋白原降低
        cytokine = self.blood.cytokine_level
        if cytokine > 0.3:
            fibrin_synthesis = (cytokine - 0.3) / 0.7 * 0.5 * dt_min
        else:
            fibrin_synthesis = 0.0

        # DIC 消耗
        if self.coagulation_state > 0.5:
            fibrin_consumption = self.coagulation_state * 0.005 * dt_min
        else:
            fibrin_consumption = 0.0

        fibrin_net = fibrin_synthesis - fibrin_consumption
        self.fibrinogen += fibrin_net
        self.fibrinogen = max(50.0, min(800.0, self.fibrinogen))
        self.blood.fibrinogen_mg_dL = self.fibrinogen

        # ── 6. 凝血状态 ────────────────────────────────────────────────
        target_coag_state = self._compute_coagulation_state()
        # 一阶滞后 τ=900s
        tau_coag = 900.0
        alpha_coag = dt / tau_coag
        self.coagulation_state += alpha_coag * (target_coag_state - self.coagulation_state)
        self.blood.coagulation_state = self.coagulation_state

        # ── 7. FactorCommands ─────────────────────────────────────────
        factor_commands = []

        return {
            "factor_VII": round(self.factor_VII, 3),
            "factor_V": round(self.factor_V, 3),
            "factor_II": round(self.factor_II, 3),
            "factor_IX": round(self.factor_IX, 3),
            "factor_X": round(self.factor_X, 3),
            "factor_XI": round(self.factor_XI, 3),
            "coagulation_state": round(self.coagulation_state, 3),
            "fibrinogen": round(self.fibrinogen, 0),
            "PT_sec": round(self.blood.PT_sec, 1),
            "aPTT_sec": round(self.blood.aPTT_sec, 1),
            "factor_commands": factor_commands,
        }

    def summary(self) -> dict:
        """返回凝血状态摘要(用于历史记录)"""
        return {
            "factor_VII": round(self.factor_VII, 3),
            "factor_V": round(self.factor_V, 3),
            "factor_II": round(self.factor_II, 3),
            "factor_IX": round(self.factor_IX, 3),
            "factor_X": round(self.factor_X, 3),
            "factor_XI": round(self.factor_XI, 3),
            "coagulation_state": round(self.coagulation_state, 3),
            "fibrinogen": round(self.fibrinogen, 0),
        }