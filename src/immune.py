"""
Immune/Inflammation Module - 免疫/炎症系统
建模固有免疫应答对整体生理的影响:

  1. 细胞因子动力学: 感染信号 → cytokine_level 上升 → 皮质醇抑制
  2. 发热: cytokine>0.3 → 体温升高 (FactorCommand set)
  3. 毛细血管漏: cytokine>0.4 → 血浆外渗 → 血钠升高(血液浓缩)
  4. 血管扩张: cytokine>0.5 → SVR下降 → 感染性休克
  5. WBC响应: cytokine>0.2 → WBC升高 (一阶滞后 τ=600s)
  6. 急性期反应: cytokine → CRP升高 (一阶滞后 τ=1800s)
  7. 高凝状态: cytokine>0.6 → 凝血状态上升

FactorCommand 目标: blood.temperature, blood.sodium_mEq_L, heart.SVR,
                    blood.WBC, blood.CRP, gut.barrier_integrity
Step: 4.9 (neuro之后, organ_health之前)

直接调用 endocrine.add_stress() 进行细胞因子→HPA耦合。
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FactorCommand:
    """统一因子写入接口"""
    target: str
    op: Literal["multiply", "add", "set"]
    value: float


class ImmuneModule:
    """
    免疫/炎症模块: 整合固有免疫应答对生理的影响

    设计原则:
      - 状态存储于 self.blood.* (共享读写)
      - FactorCommand 用于写入其他模块(立即apply)
      - Step 4.9 (neuro之后, organ_health之前)
      - 皮质醇>15ug/dL 时才显著抑制细胞因子产生(基准5不抑制)
      - cytokine<0.3 时不写体温, 内分泌被动漂移正常
    """

    # 皮质醇免疫抑制阈值 (ug/dL)
    _CORTISOL_SUPPRESSION_THRESHOLD = 15.0

    def __init__(self, weight_kg: float, blood, endocrine=None):
        self.w = weight_kg
        self.blood = blood  # BloodCompartment 引用
        self.endocrine = endocrine  # EndocrineModule 引用(可选)

        # 细胞因子状态
        self.cytokine_level = 0.0           # 统一细胞因子水平 (0-1)
        self._cytokine_target = 0.0        # 细胞因子目标值(由疾病设置)
        self._infection_signal = 0.0       # 感染信号(外部驱动)

        # 急性期反应
        self.acute_phase_response = 0.0     # 急性期反应 (0-1)
        self._CRP_target = 10.0            # CRP目标值 mg/L

        # WBC
        self.wbc_count = 10.0              # WBC x10³/μL
        self._WBC_target = 10.0            # WBC目标值
        self.crp_level = 10.0              # CRP mg/L (mirrors blood.CRP_mg_L)

        # 免疫抑制
        self.immune_suppression = 0.0      # 免疫抑制水平 (0-1)

        # 凝血状态
        self.coagulation_state = 0.0       # 高凝状态 (0=正常, 1=DIC)

    # ── derivatives() — 供 solve_ivp Radau 调用 ──────────────────────────────
    # 状态变量（进入统一 y 向量）: cytokine, acute_phase, wbc, coagulation_state
    # 输出端口（供其他模块）: cytokine_level, wbc_count, crp_level, fever_C, etc.

    def derivatives(self, dt: float, endocrine_cortisol: float = None) -> tuple[dict, dict]:
        """
        返回本模块所有状态变量的导数 + 输出端口（供统一 ODE 求解器）。

        Returns:
            (dydt, outputs):
              dydt: dict[str, float] — 状态变量导数
              outputs: dict[str, float] — 供其他模块使用的输出端口
        """
        dt_min = dt / 60.0

        # ── 免疫抑制（皮质醇） ─────────────────────────────────────────────
        cortisol = self.blood.cortisol_ug_dL if endocrine_cortisol is None else endocrine_cortisol
        if cortisol > self._CORTISOL_SUPPRESSION_THRESHOLD:
            suppression_excess = cortisol - self._CORTISOL_SUPPRESSION_THRESHOLD
            immune_suppression = min(0.9, suppression_excess / 20.0)
        else:
            immune_suppression = 0.0
        self.immune_suppression = immune_suppression

        # ── 细胞因子动力学 ─────────────────────────────────────────────────
        infection_drive = self._infection_signal * (1.0 - immune_suppression * 0.8)
        self._cytokine_target = infection_drive

        tau_cytokine = 600.0
        dCytokine = (self._cytokine_target - self.cytokine_level) / tau_cytokine if tau_cytokine > 0 else 0.0
        self.cytokine_level = max(0.0, min(1.0, self.cytokine_level + dCytokine * dt))

        # ── 发热（写入 blood.temperature） ───────────────────────────────
        fever_target_C = 38.5
        if self.cytokine_level > 0.3:
            fever_magnitude = (self.cytokine_level - 0.3) / 0.7
            fever_delta = fever_magnitude * 3.0
            fever_target_C = min(41.5, 38.5 + fever_delta)
            self.blood.core_temperature_C = max(37.0, min(41.5, fever_target_C))

        # ── WBC 响应 ───────────────────────────────────────────────────────
        if self.cytokine_level > 0.2:
            wbc_drive = (self.cytokine_level - 0.2) / 0.8
            self._WBC_target = 10.0 + wbc_drive * 30.0
        else:
            self._WBC_target = 10.0

        tau_wbc = 600.0
        dWBC = (self._WBC_target - self.wbc_count) / tau_wbc if tau_wbc > 0 else 0.0
        self.wbc_count = max(3.0, min(50.0, self.wbc_count + dWBC * dt))

        # ── CRP 急性期反应 ────────────────────────────────────────────────
        if self.cytokine_level > 0.1:
            crp_drive = (self.cytokine_level - 0.1) / 0.9
            self._CRP_target = 10.0 + crp_drive * 200.0
        else:
            self._CRP_target = 10.0

        tau_crp = 1800.0
        dCRP = (self._CRP_target - self.blood.CRP_mg_L) / tau_crp if tau_crp > 0 else 0.0
        self.blood.CRP_mg_L = max(0.0, self.blood.CRP_mg_L + dCRP * dt)
        self.crp_level = self.blood.CRP_mg_L

        # ── 高凝状态 ───────────────────────────────────────────────────────
        if self.cytokine_level > 0.6:
            coag_drive = (self.cytokine_level - 0.6) / 0.4
            tau_coag = 900.0
            dCoag = (min(1.0, coag_drive) - self.coagulation_state) / tau_coag if tau_coag > 0 else 0.0
            self.coagulation_state = max(0.0, min(1.0, self.coagulation_state + dCoag * dt))
        else:
            dCoag = -self.coagulation_state / 900.0 if self.coagulation_state > 0 else 0.0
            self.coagulation_state = max(0.0, min(1.0, self.coagulation_state + dCoag * dt))

        # ── 急性期反应 ────────────────────────────────────────────────────
        dAcutePhase = (self.cytokine_level - self.acute_phase_response) / 600.0
        self.acute_phase_response = max(0.0, min(1.0, self.acute_phase_response + dAcutePhase * dt))

        # ── 毛细血管漏（钠浓度变化） ──────────────────────────────────────
        capillary_leak_factor = 0.0
        if self.cytokine_level > 0.4:
            leak_intensity = (self.cytokine_level - 0.4) / 0.6
            capillary_leak_factor = leak_intensity
            sodium_shift = leak_intensity * 8.0 * dt_min
            self.blood.sodium_mEq_L += sodium_shift

        # ── 肠道屏障损伤因子（输出，供 gut 读取） ──────────────────────
        gut_barrier_mult = 1.0
        if self.cytokine_level > 0.3:
            barrier_effect = (self.cytokine_level - 0.3) / 0.7
            gut_barrier_mult = max(0.3, 1.0 - barrier_effect * 0.7)

        # ── 肝脏代谢负担因子（输出，供 liver 读取） ─────────────────────
        liver_factor = 1.0
        if self.cytokine_level > 0.4:
            liver_inflammation_cost = max(0.5, 1.0 - self.cytokine_level * 0.4)
            liver_factor = liver_inflammation_cost

        # ── SVR 因子（输出，供 heart 读取） ─────────────────────────────
        svr_factor = 1.0
        if self.cytokine_level > 0.5:
            vasodilation_intensity = (self.cytokine_level - 0.5) / 0.5
            svr_factor = max(0.25, 1.0 - vasodilation_intensity * 0.75)

        dydt = {
            "cytokine": dCytokine,
            "acute_phase": dAcutePhase,
            "wbc": dWBC,
            "coagulation_state": dCoag if self.cytokine_level <= 0.6 else 0.0,
        }

        outputs = {
            "cytokine_level": self.cytokine_level,
            "wbc_count": self.wbc_count,
            "crp_level": self.blood.CRP_mg_L,
            "fever_C": fever_target_C,
            "immune_suppression": immune_suppression,
            "coagulation_state": self.coagulation_state,
            "acute_phase_response": self.acute_phase_response,
            "gut_barrier_mult": gut_barrier_mult,
            "liver_metabolic_factor": liver_factor,
            "svr_factor": svr_factor,
            "capillary_leak_factor": capillary_leak_factor,
        }

        return dydt, outputs

    def set_infection_signal(self, value: float) -> None:
        """外部调用: 设置感染信号(由疾病通过FactorCommand或直接调用)"""
        self._infection_signal = max(0.0, min(1.0, value))

    def compute(self, dt: float, endocrine_state: dict) -> dict:
        """
        计算免疫/炎症状态和FactorCommand

        Args:
            dt: 时间步长 (秒)
            endocrine_state: endocrine.compute() 返回的 dict

        Returns:
            dict包含所有状态变量 + factor_commands列表
        """
        dt_min = dt / 60.0

        # ── 1. 免疫抑制 (来自皮质醇) ──────────────────────────────
        cortisol = self.blood.cortisol_ug_dL
        if cortisol > self._CORTISOL_SUPPRESSION_THRESHOLD:
            suppression_excess = cortisol - self._CORTISOL_SUPPRESSION_THRESHOLD
            self.immune_suppression = min(0.9, suppression_excess / 20.0)  # 最多90%抑制
        else:
            self.immune_suppression = 0.0

        # ── 2. 细胞因子动力学 ─────────────────────────────────────
        # 感染信号 → 细胞因子上升；高皮质醇抑制
        infection_drive = self._infection_signal * (1.0 - self.immune_suppression * 0.8)
        cytokine_target = infection_drive  # 目标=感染驱动
        self._cytokine_target = cytokine_target

        # 一阶滞后 τ=600s (10分钟)
        tau_cytokine = 600.0
        alpha_cytokine = dt / tau_cytokine
        self.cytokine_level += alpha_cytokine * (self._cytokine_target - self.cytokine_level)

        # ── 3. 发热 ───────────────────────────────────────────────
        fever_target_C = 38.5  # 默认正常体温
        fever_commands = []
        if self.cytokine_level > 0.3:
            fever_magnitude = (self.cytokine_level - 0.3) / 0.7  # 0.3-1.0 → 0-1
            fever_delta = fever_magnitude * 3.0  # 最大+3.0°C → 最高41.5°C
            fever_target_C = min(41.5, 38.5 + fever_delta)
            fever_commands.append(FactorCommand("blood.temperature", "set", fever_target_C))

        # ── 4. 毛细血管漏 ─────────────────────────────────────────
        capillary_leak_commands = []
        if self.cytokine_level > 0.4:
            leak_intensity = (self.cytokine_level - 0.4) / 0.6
            # 血浆容量外渗 → 血钠升高(血液浓缩)
            sodium_shift = leak_intensity * 8.0  # 最大+8 mEq/L
            capillary_leak_commands.append(FactorCommand("blood.sodium_mEq_L", "add", sodium_shift))

        # ── 5. 血管扩张 (感染性休克) ──────────────────────────────
        vasodilation_commands = []
        if self.cytokine_level > 0.5:
            vasodilation_intensity = (self.cytokine_level - 0.5) / 0.5
            # TNF-α/NO → SVR下降, 最低×0.25
            svr_factor = max(0.25, 1.0 - vasodilation_intensity * 0.75)
            vasodilation_commands.append(FactorCommand("heart.SVR", "multiply", svr_factor))

        # ── 6. WBC响应 (白细胞增多) ───────────────────────────────
        if self.cytokine_level > 0.2:
            wbc_drive = (self.cytokine_level - 0.2) / 0.8
            self._WBC_target = 10.0 + wbc_drive * 30.0  # 最高40k
        else:
            self._WBC_target = 10.0

        # 一阶滞后 τ=600s
        tau_wbc = 600.0
        alpha_wbc = dt / tau_wbc
        self.wbc_count += alpha_wbc * (self._WBC_target - self.wbc_count)

        # ── 7. 急性期反应 (CRP) ─────────────────────────────────
        if self.cytokine_level > 0.1:
            crp_drive = (self.cytokine_level - 0.1) / 0.9
            self._CRP_target = 10.0 + crp_drive * 200.0  # 最高210 mg/L
        else:
            self._CRP_target = 10.0

        # 一阶滞后 τ=1800s (30分钟)
        tau_crp = 1800.0
        alpha_crp = dt / tau_crp
        current_crp = self.blood.CRP_mg_L
        self.blood.CRP_mg_L += alpha_crp * (self._CRP_target - current_crp)
        self.crp_level = self.blood.CRP_mg_L  # mirror for _PARAM_PATHS access

        # ── 8. 高凝状态 ──────────────────────────────────────────
        if self.cytokine_level > 0.6:
            coag_drive = (self.cytokine_level - 0.6) / 0.4
            # 一阶滞后 τ=900s
            tau_coag = 900.0
            alpha_coag = dt / tau_coag
            self.coagulation_state += alpha_coag * (min(1.0, coag_drive) - self.coagulation_state)

        # ── 9. 细胞因子→HPA激活 ────────────────────────────────
        stress_commands = []
        if self.cytokine_level > 0.2 and self.endocrine is not None:
            stress_from_cytokine = (self.cytokine_level - 0.2) * 0.3
            self.endocrine.add_stress(stress_from_cytokine * dt_min)

        # ── 10. 肠道屏障损伤 ─────────────────────────────────────
        gut_barrier_commands = []
        if self.cytokine_level > 0.3:
            barrier_effect = (self.cytokine_level - 0.3) / 0.7
            barrier_mult = max(0.3, 1.0 - barrier_effect * 0.7)
            gut_barrier_commands.append(FactorCommand("gut.barrier_integrity", "multiply", barrier_mult))

        # ── 11. 肝脏代谢负担 ─────────────────────────────────────
        liver_commands = []
        if self.cytokine_level > 0.4:
            liver_inflammation_cost = max(0.5, 1.0 - self.cytokine_level * 0.4)
            liver_commands.append(FactorCommand("liver.metabolic_activity", "multiply", liver_inflammation_cost))
            liver_commands.append(FactorCommand("liver.detox_capacity", "multiply", liver_inflammation_cost))

        # ── 12. 汇总所有FactorCommands ──────────────────────────
        factor_commands = (
            fever_commands
            + capillary_leak_commands
            + vasodilation_commands
            + gut_barrier_commands
            + liver_commands
        )

        return {
            "cytokine_level": round(self.cytokine_level, 3),
            "wbc_count": round(self.wbc_count, 1),
            "crp_level": round(self.blood.CRP_mg_L, 0),
            "acute_phase_response": round(self.acute_phase_response, 3),
            "immune_suppression": round(self.immune_suppression, 3),
            "coagulation_state": round(self.coagulation_state, 3),
            "fever_C": round(fever_target_C, 1),
            "factor_commands": factor_commands,
        }

    def summary(self) -> dict:
        """返回免疫状态摘要(用于历史记录)"""
        return {
            "cytokine_level": round(self.cytokine_level, 3),
            "wbc_count": round(self.wbc_count, 1),
            "crp_level": round(self.blood.CRP_mg_L, 0),
            "acute_phase_response": round(self.acute_phase_response, 3),
            "immune_suppression": round(self.immune_suppression, 3),
            "coagulation_state": round(self.coagulation_state, 3),
            "fever_C": round(self.blood.core_temperature_C, 1),
        }
