"""
Endocrine Module - 内分泌系统
建模5个内分泌轴对整体生理的调控:
  1. 甲状腺轴 (T3/T4 → 代谢率、心率、体温)
  2. 胰腺轴 (胰岛素/胰高血糖素 → 血糖控制)
  3. 肾上腺轴 (HPA → 皮质醇/应激/肠道屏障)
  4. 甲状旁腺轴 (PTH → 钙磷代谢)
  5. 生长轴 (GH/IGF-1 → 白蛋白合成)

所有激素浓度以血液浓度形式存在(blood.*)。
代谢率驱动体温被动变化(无主动产热)。
"""

import math
from parameters import *
from src.organ_guard import organ_setattr, _blood_escape


class EndocrineModule:

    __setattr__ = organ_setattr

    # ── Phase 5: I/O contract (declarative, no behavior change) ────────
    INPUTS: tuple[str, ...] = ('blood_pH',)
    OUTPUTS: tuple[str, ...] = ('T3_ng_dL', 'T4_ug_dL', 'insulin_uU_mL', 'glucagon_pg_mL', 'cortisol_ug_dL', 'epinephrine_pg_mL', 'norepinephrine_pg_mL', 'PTH_pg_mL', 'calcium_mg_dL', 'phosphate_mg_dL', 'GH_ng_mL', 'IGF1_nmol_L', 'metabolic_rate', 'core_temperature_C')
    READS_BLOOD: tuple[str, ...] = ('glucose_mmol_L', 'albumin_g_dL', 'calcium_mg_dL', 'phosphate_mg_dL', 'cortisol_ug_dL', 'core_temperature_C')
    WRITES_BLOOD: tuple[str, ...] = ('core_temperature_C', 'glucose_mmol_L', 'PTH_pg_mL', 'calcium_mg_dL', 'phosphate_mg_dL', 'albumin_g_dL', 'cortisol_ug_dL')
    """
    内分泌模块：整合5个激素轴对生理功能的影响

    设计原则:
      - 各轴状态独立，激素浓度存储于 self.blood.*
      - 代谢率驱动核心体温被动漂移
      - FactorCommand 目标注册于 simulation._PARAM_PATHS
      - Step 4.7 (liver之后, organ_health之前)
    """

    def __init__(self, weight_kg: float, blood):
        self.w = weight_kg
        with _blood_escape(EndocrineModule):
            self.blood = blood  # 血液隔室引用(共享读写)

        # ══════════════════════════════════════════════════════
        # 1. 甲状腺轴
        # ══════════════════════════════════════════════════════
        self.T3_ng_dL = BASELINE_T3_NG_DL        # 三碘甲状腺原氨酸
        self.T4_ug_dL = BASELINE_T4_UG_DL        # 甲状腺素(T4是前体)
        self.metabolic_rate = METABOLIC_RATE_NORMAL  # 代谢率乘子(0.5-2.0)
        self.T3_factor = 1.0                     # T3归一化因子(对外输出)
        self._T3_target = BASELINE_T3_NG_DL     # T3目标值(由疾病写入)

        # ══════════════════════════════════════════════════════
        # 2. 胰腺轴
        # ══════════════════════════════════════════════════════
        self.insulin_uU_mL = BASELINE_INSULIN_UU_ML      # 胰岛素
        self.glucagon_pg_mL = BASELINE_GLUCAGON_PG_ML   # 胰高血糖素
        self.insulin_factor = 1.0                 # 胰岛素归一化因子
        self.glucagon_factor = 1.0               # 胰高血糖素归一化因子
        self._insulin_target = BASELINE_INSULIN_UU_ML
        self._glucagon_target = BASELINE_GLUCAGON_PG_ML

        # ══════════════════════════════════════════════════════
        # 3. 肾上腺轴
        # ══════════════════════════════════════════════════════
        self.HPA_axis = 0.0                      # 下丘脑-垂体-肾上腺轴活性(0-1应激)
        self.cortisol_ug_dL = BASELINE_CORTISOL_UG_DL  # 皮质醇
        self.epinephrine_pg_mL = BASELINE_EPINEPHRINE_PG_ML
        self.norepinephrine_pg_mL = BASELINE_NOREPINEPHRINE_PG_ML
        self.cortisol_factor = 1.0              # 皮质醇归一化因子
        self._cortisol_target = BASELINE_CORTISOL_UG_DL
        self._elapsed_s = 0.0                    # 用于皮质醇昼夜节律

        # ══════════════════════════════════════════════════════
        # 4. 甲状旁腺轴
        # ══════════════════════════════════════════════════════
        self.PTH_pg_mL = BASELINE_PTH_PG_ML     # 甲状旁腺激素
        self.calcium_mg_dL = BASELINE_CALCIUM_MG_DL  # 血钙
        self.phosphate_mg_dL = BASELINE_PHOSPHATE_MG_DL  # 血磷
        self.calcium_factor = 1.0               # 钙归一化因子
        self._PTH_target = BASELINE_PTH_PG_ML

        # ══════════════════════════════════════════════════════
        # 5. 生长轴
        # ══════════════════════════════════════════════════════
        self.GH_ng_mL = BASELINE_GH_NG_ML       # 生长激素
        self.IGF1_nmol_L = BASELINE_IGF1_NMOL_L  # IGF-1
        self.growth_factor = 1.0                # 生长因子

        # 内部累计量
        self._stress_input = 0.0                # 累积应激输入(用于HPA)

    # ── derivatives() — 供 solve_ivp Radau 调用 ──────────────────────────────
    # 状态变量（进入统一 y 向量）: T3, insulin, glucagon, cortisol, PTH, IGF1, HPA, Ca, phosphate
    # 输出端口（供其他模块）: metabolic_rate, insulin_factor, glucagon_factor, cortisol_factor, calcium_factor, growth_factor

    def derivatives(self, dt: float) -> tuple[dict, dict]:
        """
        返回本模块所有状态变量的导数 + 输出端口（供统一 ODE 求解器）。

        Returns:
            (dydt, outputs):
              dydt: dict[str, float] — 状态变量导数
              outputs: dict[str, float] — 供其他模块使用的输出端口
        """
        self._elapsed_s += dt
        glucose = self.blood.glucose_mmol_L

        # ── 甲状腺轴 ───────────────────────────────────────────────────────
        circadian_T3 = 5.0 * math.sin(2.0 * math.pi * self._elapsed_s / 86400.0)
        T3_target = BASELINE_T3_NG_DL + circadian_T3
        tau = THYROID_TAU_SEC
        dT3 = (T3_target - self.T3_ng_dL) / tau if tau > 0 else 0.0
        self.T3_ng_dL = max(0.0, self.T3_ng_dL + dT3 * dt)
        self.T4_ug_dL = self.T3_ng_dL * 0.015
        baseline_ratio = self.T3_ng_dL / BASELINE_T3_NG_DL
        metabolic_rate = max(METABOLIC_RATE_MIN, min(METABOLIC_RATE_MAX, METABOLIC_RATE_NORMAL * baseline_ratio))
        T3_factor = self.T3_ng_dL / BASELINE_T3_NG_DL

        # 体温
        dt_min = dt / 60.0
        heat_drift = (metabolic_rate - METABOLIC_RATE_NORMAL) * 0.05 * dt_min
        # NOTE(C5): 纯函数化 — 改为本地变量，由 caller 写回
        new_core_temp = max(37.0, min(42.0, self.blood.core_temperature_C + heat_drift))
        baseline_pull = (38.5 - new_core_temp) * 0.001
        new_core_temp = max(37.0, min(42.0, new_core_temp + baseline_pull))

        # ── 胰腺轴 ────────────────────────────────────────────────────────
        if glucose > INSULIN_HYPERGLYCEMIA_THRESHOLD:
            excess_ratio = (glucose - INSULIN_HYPERGLYCEMIA_THRESHOLD) / INSULIN_HYPERGLYCEMIA_THRESHOLD
            insulin_target = BASELINE_INSULIN_UU_ML * (1.0 + 2.0 * excess_ratio)
        else:
            insulin_target = BASELINE_INSULIN_UU_ML

        if glucose < GLUCAGON_HYPOGLYCEMIA_THRESHOLD:
            deficit_ratio = (GLUCAGON_HYPOGLYCEMIA_THRESHOLD - glucose) / GLUCAGON_HYPOGLYCEMIA_THRESHOLD
            glucagon_target = BASELINE_GLUCAGON_PG_ML * (1.0 + 3.0 * deficit_ratio)
        else:
            glucagon_target = BASELINE_GLUCAGON_PG_ML

        tau = PANCREATIC_RESPONSE_TAU_SEC
        dInsulin = (insulin_target - self.insulin_uU_mL) / tau if tau > 0 else 0.0
        dGlucagon = (glucagon_target - self.glucagon_pg_mL) / tau if tau > 0 else 0.0
        self.insulin_uU_mL = max(0.0, self.insulin_uU_mL + dInsulin * dt)
        self.glucagon_pg_mL = max(0.0, self.glucagon_pg_mL + dGlucagon * dt)
        insulin_factor = self.insulin_uU_mL / BASELINE_INSULIN_UU_ML
        glucagon_factor = self.glucagon_pg_mL / BASELINE_GLUCAGON_PG_ML

        # 被动血糖调节
        insulin_effect = (insulin_factor - 1.0) * 0.01 * dt
        glucagon_effect = (1.0 - glucagon_factor) * 0.005 * dt
        net_glucose_shift = insulin_effect - glucagon_effect
        # NOTE(C5): 纯函数化 — 改为本地变量
        new_glucose_mmol_L = self.blood.glucose_mmol_L
        if self.insulin_uU_mL > BASELINE_INSULIN_UU_ML * 1.5:
            new_glucose_mmol_L = max(2.0, self.blood.glucose_mmol_L + net_glucose_shift)
        elif self.glucagon_pg_mL > BASELINE_GLUCAGON_PG_ML * 1.5:
            new_glucose_mmol_L = min(12.0, self.blood.glucose_mmol_L - net_glucose_shift)

        # ── 肾上腺轴 ───────────────────────────────────────────────────────
        baseline_activity = 0.05
        self.HPA_axis = max(self.HPA_axis, baseline_activity)
        if self._stress_input > 0.1:
            growth_rate = 0.01 * self._stress_input
            self.HPA_axis += growth_rate * self.HPA_axis * (1.0 - self.HPA_axis) * dt
            self.HPA_axis = max(0.0, min(1.0, self.HPA_axis))

        cortisol_range = CORTISOL_STRESS_MAX - BASELINE_CORTISOL_UG_DL
        cortisol_target = BASELINE_CORTISOL_UG_DL + cortisol_range * self.HPA_axis
        tau = CORTISOL_TAU_SEC
        dCortisol = (cortisol_target - self.cortisol_ug_dL) / tau if tau > 0 else 0.0
        self.cortisol_ug_dL = max(0.0, self.cortisol_ug_dL + dCortisol * dt)
        cortisol_factor = self.cortisol_ug_dL / BASELINE_CORTISOL_UG_DL
        self.epinephrine_pg_mL = BASELINE_EPINEPHRINE_PG_ML * (1.0 + 5.0 * self.HPA_axis)
        self.norepinephrine_pg_mL = BASELINE_NOREPINEPHRINE_PG_ML * (1.0 + 3.0 * self.HPA_axis)
        self._stress_input = max(0.0, self._stress_input - 0.01 * dt)

        # ── 甲状旁腺轴 ────────────────────────────────────────────────────
        calcium_deviation = CALCIUM_NORMAL_LOW - self.calcium_mg_dL
        if calcium_deviation > 0:
            pth_stimulus = calcium_deviation * PTH_CALCIUM_SENSITIVITY
            pth_target = BASELINE_PTH_PG_ML * (1.0 + pth_stimulus)
        else:
            pth_target = BASELINE_PTH_PG_ML

        tau = PTH_TAU_SEC
        dPTH = (pth_target - self.PTH_pg_mL) / tau if tau > 0 else 0.0
        self.PTH_pg_mL = max(0.0, self.PTH_pg_mL + dPTH * dt)

        if abs(calcium_deviation) > 0.5:
            self.calcium_mg_dL += calcium_deviation * 0.002 * dt

        phosphate_error = self.blood.phosphate_mg_dL - BASELINE_PHOSPHATE_MG_DL
        if self.PTH_pg_mL > BASELINE_PTH_PG_ML:
            self.phosphate_mg_dL = max(1.5, self.phosphate_mg_dL - 0.001 * (self.PTH_pg_mL / BASELINE_PTH_PG_ML - 1.0) * dt)

        calcium_factor = self.calcium_mg_dL / BASELINE_CALCIUM_MG_DL
        # NOTE(C5): 纯函数化 — 改为本地变量，caller 写回
        new_PTH_pg_mL = self.PTH_pg_mL
        new_calcium_mg_dL = self.calcium_mg_dL
        new_phosphate_mg_dL = self.phosphate_mg_dL

        # ── 生长轴 ─────────────────────────────────────────────────────────
        nutrition_factor = 1.0
        if glucose < 3.5:
            nutrition_factor = 0.5
        if self.blood.albumin_g_dL < 2.5:
            nutrition_factor = 0.7

        igf1_target = BASELINE_IGF1_NMOL_L * nutrition_factor
        tau = GROWTH_TAU_SEC
        dIGF1 = (igf1_target - self.IGF1_nmol_L) / tau if tau > 0 else 0.0
        self.IGF1_nmol_L = max(0.0, self.IGF1_nmol_L + dIGF1 * dt)
        growth_factor = self.IGF1_nmol_L / BASELINE_IGF1_NMOL_L
        self.GH_ng_mL = BASELINE_GH_NG_ML * (0.8 + 0.2 * growth_factor)
        # NOTE(C5): 纯函数化
        albumin_delta = 0.0
        if growth_factor > 1.05:
            albumin_delta = min(4.5, self.blood.albumin_g_dL + (growth_factor - 1.0) * 0.001 * dt) - self.blood.albumin_g_dL
        new_albumin_g_dL = self.blood.albumin_g_dL + albumin_delta

        dydt = {
            "T3": dT3,
            "insulin": dInsulin,
            "glucagon": dGlucagon,
            "cortisol": dCortisol,
            "PTH": dPTH,
            "IGF1": dIGF1,
            "HPA_axis": 0.0,
            "calcium": 0.0,
            "phosphate": 0.0,
        }

        outputs = {
            "metabolic_rate": metabolic_rate,
            "T3_factor": T3_factor,
            "insulin_factor": insulin_factor,
            "glucagon_factor": glucagon_factor,
            "cortisol_factor": cortisol_factor,
            "calcium_factor": calcium_factor,
            "growth_factor": growth_factor,
            "core_temperature_C": new_core_temp,  # NOTE(C5): 本地变量
            "epinephrine_pg_mL": self.epinephrine_pg_mL,
            "norepinephrine_pg_mL": self.norepinephrine_pg_mL,
            "GH_ng_mL": self.GH_ng_mL,
            # NOTE(C5): blood 字段 (Newton 迭代 caller 一次性写回)
            "blood_core_temperature_C": new_core_temp,
            "blood_glucose_mmol_L": new_glucose_mmol_L,
            "blood_PTH_pg_mL": new_PTH_pg_mL,
            "blood_calcium_mg_dL": new_calcium_mg_dL,
            "blood_phosphate_mg_dL": new_phosphate_mg_dL,
            "blood_albumin_g_dL": new_albumin_g_dL,
        }

        return dydt, outputs

    # ══════════════════════════════════════════════════════════
    # 甲状腺轴
    # ══════════════════════════════════════════════════════════

    def _compute_thyroid(self, dt: float) -> dict:
        """
        甲状腺轴: T3/T4调控代谢率和心率

        方程:
          - T4 → T3 转化率随代谢需求变化
          - metabolic_rate = clamp(0.5 + T3/T3_baseline * 0.5, 0.5, 2.0)
          - T3_factor = T3 / BASELINE_T3  (对外输出)

        体温被动计算:
          - dT/dt = (metabolic_rate - 1.0) * 0.05 C/min
          - 无主动产热机制
        """
        # 基线昼夜节律: 24h周期，±5 ng/dL 波动
        circadian_T3 = 5.0 * math.sin(2.0 * math.pi * self._elapsed_s / 86400.0)
        self._T3_target = BASELINE_T3_NG_DL + circadian_T3

        # first_order_lag: T3向目标值平滑移动
        tau = THYROID_TAU_SEC
        alpha = dt / tau if tau > 0 else 1.0
        alpha = min(1.0, alpha)  # 防止步长过大导致数值不稳定
        self.T3_ng_dL += (self._T3_target - self.T3_ng_dL) * alpha

        # T4稳定在T3的10倍(犬正常比值)
        self.T4_ug_dL = self.T3_ng_dL * 0.015

        # 代谢率: T3越高代谢越快
        baseline_ratio = self.T3_ng_dL / BASELINE_T3_NG_DL
        self.metabolic_rate = max(METABOLIC_RATE_MIN,
                                  min(METABOLIC_RATE_MAX,
                                      METABOLIC_RATE_NORMAL * baseline_ratio))
        self.metabolic_rate = max(METABOLIC_RATE_MIN, min(METABOLIC_RATE_MAX, self.metabolic_rate))

        # T3归一化因子
        self.T3_factor = self.T3_ng_dL / BASELINE_T3_NG_DL

        # 体温被动漂移(C/min per unit deviation)
        dt_min = dt / 60.0
        heat_drift = (self.metabolic_rate - METABOLIC_RATE_NORMAL) * 0.05 * dt_min
        self.blood.core_temperature_C = max(37.0, min(42.0,
            self.blood.core_temperature_C + heat_drift))

        # 体温弱的自稳态(每步微弱恢复向38.5)
        baseline_pull = (38.5 - self.blood.core_temperature_C) * 0.001
        self.blood.core_temperature_C = max(37.0, min(42.0,
            self.blood.core_temperature_C + baseline_pull))

        return {
            "T3_ng_dL": self.T3_ng_dL,
            "T4_ug_dL": self.T4_ug_dL,
            "metabolic_rate": self.metabolic_rate,
            "T3_factor": self.T3_factor,
        }

    # ══════════════════════════════════════════════════════════
    # 胰腺轴
    # ══════════════════════════════════════════════════════════

    def _compute_pancreatic(self, dt: float) -> dict:
        """
        胰腺轴: 胰岛素/胰高血糖素调控血糖

        方程:
          - 高血糖(>6.0 mmol/L) → 胰岛素分泌↑
          - 低血糖(<3.5 mmol/L) → 胰高血糖素分泌↑
          - 中性血糖(3.5-6.0) → 两者趋近基线

        血糖控制(被动维持):
          - 胰岛素促进组织摄取葡萄糖
          - 胰高血糖素促进肝糖原分解/糖异生
          - 稳态血糖约 5 mmol/L
        """
        glucose = self.blood.glucose_mmol_L

        # 胰岛素分泌响应
        if glucose > INSULIN_HYPERGLYCEMIA_THRESHOLD:
            # 高血糖刺激胰岛素: 超出阈值的比例决定分泌强度
            excess_ratio = (glucose - INSULIN_HYPERGLYCEMIA_THRESHOLD) / INSULIN_HYPERGLYCEMIA_THRESHOLD
            self._insulin_target = BASELINE_INSULIN_UU_ML * (1.0 + 2.0 * excess_ratio)
        else:
            # 正常/低血糖: 胰岛素回基线
            self._insulin_target = BASELINE_INSULIN_UU_ML

        # 胰高血糖素分泌响应
        if glucose < GLUCAGON_HYPOGLYCEMIA_THRESHOLD:
            deficit_ratio = (GLUCAGON_HYPOGLYCEMIA_THRESHOLD - glucose) / GLUCAGON_HYPOGLYCEMIA_THRESHOLD
            self._glucagon_target = BASELINE_GLUCAGON_PG_ML * (1.0 + 3.0 * deficit_ratio)
        else:
            self._glucagon_target = BASELINE_GLUCAGON_PG_ML

        # first_order_lag平滑
        tau = PANCREATIC_RESPONSE_TAU_SEC
        alpha_insulin = dt / tau
        alpha_glucagon = dt / tau
        self.insulin_uU_mL += (self._insulin_target - self.insulin_uU_mL) * alpha_insulin
        self.glucagon_pg_mL += (self._glucagon_target - self.glucagon_pg_mL) * alpha_glucagon

        # 归一化因子
        self.insulin_factor = self.insulin_uU_mL / BASELINE_INSULIN_UU_ML
        self.glucagon_factor = self.glucagon_pg_mL / BASELINE_GLUCAGON_PG_ML

        # 被动血糖调节(自身无疾病时维持稳态)
        # 胰岛素 ↑ → 血糖趋于下降(代谢消耗)
        # 胰高血糖素 ↑ → 血糖趋于上升(肝脏输出)
        # 稳态机制: 高血糖时胰岛素高/胰高血糖素低 → 血糖下降
        #          低血糖时胰高血糖素高/胰岛素低 → 血糖上升
        insulin_effect = (self.insulin_factor - 1.0) * 0.01 * dt  # 每步修正幅度
        glucagon_effect = (1.0 - self.glucagon_factor) * 0.005 * dt

        net_glucose_shift = insulin_effect - glucagon_effect
        if self.insulin_uU_mL > BASELINE_INSULIN_UU_ML * 1.5:
            # 高胰岛素状态: 微弱降低血糖(代谢消耗)
            self.blood.glucose_mmol_L = max(2.0,
                self.blood.glucose_mmol_L + net_glucose_shift)
        elif self.glucagon_pg_mL > BASELINE_GLUCAGON_PG_ML * 1.5:
            # 高胰高血糖素状态: 微弱升高血糖(肝脏糖输出)
            self.blood.glucose_mmol_L = min(12.0,
                self.blood.glucose_mmol_L - net_glucose_shift)

        return {
            "insulin_uU_mL": self.insulin_uU_mL,
            "glucagon_pg_mL": self.glucagon_pg_mL,
            "insulin_factor": self.insulin_factor,
            "glucagon_factor": self.glucagon_factor,
        }

    # ══════════════════════════════════════════════════════════
    # 肾上腺轴
    # ══════════════════════════════════════════════════════════

    def _compute_adrenal(self, dt: float) -> dict:
        """
        肾上腺轴: HPA激活 → 皮质醇/儿茶酚胺分泌

        方程:
          - HPA_axis: 应激输入驱动logistic增长(0→1)
          - cortisol: first_order_lag向目标(0.5-25 ug/dL)
          - epinephrine: HPA直接驱动

        效应:
          - 皮质醇↑ → 肠道屏障↓, 代谢调节, 免疫抑制
          - 儿茶酚胺↑ → SVR↑, 心率↑(已在heart和pharmacology建模)
        """
        # HPA轴: 应激输入驱动logistic增长
        # 基线昼夜节律: 维持最低激活水平，防止完全冻结
        baseline_activity = 0.05
        self.HPA_axis = max(self.HPA_axis, baseline_activity)

        if self._stress_input > 0.1:
            # 应力输入 → logistic增长
            growth_rate = 0.01 * self._stress_input
            self.HPA_axis += growth_rate * self.HPA_axis * (1.0 - self.HPA_axis) * dt
            self.HPA_axis = max(0.0, min(1.0, self.HPA_axis))

        # 皮质醇: first_order_lag向目标值
        # 目标: HPA_axis从0→1时, 皮质醇从基线→应激最大值
        cortisol_range = CORTISOL_STRESS_MAX - BASELINE_CORTISOL_UG_DL
        self._cortisol_target = BASELINE_CORTISOL_UG_DL + cortisol_range * self.HPA_axis

        tau = CORTISOL_TAU_SEC
        alpha = dt / tau if tau > 0 else 1.0
        alpha = min(1.0, alpha)
        self.cortisol_ug_dL += (self._cortisol_target - self.cortisol_ug_dL) * alpha

        # 皮质醇归一化因子(应激时>1, 肾上腺功能减退时<1)
        self.cortisol_factor = self.cortisol_ug_dL / BASELINE_CORTISOL_UG_DL

        # 儿茶酚胺: HPA轴驱动
        self.epinephrine_pg_mL = BASELINE_EPINEPHRINE_PG_ML * (1.0 + 5.0 * self.HPA_axis)
        self.norepinephrine_pg_mL = BASELINE_NOREPINEPHRINE_PG_ML * (1.0 + 3.0 * self.HPA_axis)

        # 皮质醇对肠道屏障的效应(写入blood共享供gut模块读取)
        # 高皮质醇 → 肠道屏障完整性下降(应激溃疡机制)
        cortisol_barrier_effect = 1.0 - (self.cortisol_ug_dL - BASELINE_CORTISOL_UG_DL) / CORTISOL_STRESS_MAX * 0.4
        self.blood.cortisol_ug_dL = self.cortisol_ug_dL  # 更新血液浓度

        # 消耗应激输入(每步消退)
        self._stress_input = max(0.0, self._stress_input - 0.01 * dt)

        return {
            "HPA_axis": self.HPA_axis,
            "cortisol_ug_dL": self.cortisol_ug_dL,
            "epinephrine_pg_mL": self.epinephrine_pg_mL,
            "norepinephrine_pg_mL": self.norepinephrine_pg_mL,
            "cortisol_factor": self.cortisol_factor,
        }

    # ══════════════════════════════════════════════════════════
    # 甲状旁腺轴
    # ══════════════════════════════════════════════════════════

    def _compute_parathyroid(self, dt: float) -> dict:
        """
        甲状旁腺轴: PTH调控钙磷平衡

        方程:
          - 血钙<9.0 mg/dL → PTH分泌↑
          - 血磷↑ → PTH进一步升高
          - PTH → 骨吸收释放钙, 肾脏排磷

        效应:
          - 钙直接影响心脏收缩力
          - 低钙 → 心脏收缩力下降
          - 高钙 → 心脏收缩力增强(但需防过度)
        """
        # 钙偏差驱动PTH分泌
        calcium_deviation = CALCIUM_NORMAL_LOW - self.blood.calcium_mg_dL
        if calcium_deviation > 0:
            # 低钙 → PTH分泌增加
            pth_stimulus = calcium_deviation * PTH_CALCIUM_SENSITIVITY
            self._PTH_target = BASELINE_PTH_PG_ML * (1.0 + pth_stimulus)
        else:
            # 正常/高钙 → PTH受抑
            self._PTH_target = BASELINE_PTH_PG_ML

        # PTH first_order_lag
        tau = PTH_TAU_SEC
        alpha = dt / tau if tau > 0 else 1.0
        alpha = min(1.0, alpha)
        self.PTH_pg_mL += (self._PTH_target - self.PTH_pg_mL) * alpha

        # 钙磷平衡(简化模型)
        # PTH升高 → 血钙趋于正常, 血磷趋于下降(肾脏排磷)
        calcium_error = CALCIUM_NORMAL_LOW - self.calcium_mg_dL
        if abs(calcium_error) > 0.5:
            # 钙缓慢回归正常范围
            self.calcium_mg_dL += calcium_error * 0.002 * dt

        phosphate_error = self.blood.phosphate_mg_dL - BASELINE_PHOSPHATE_MG_DL
        if self.PTH_pg_mL > BASELINE_PTH_PG_ML:
            # PTH升高 → 肾脏排磷增强
            self.phosphate_mg_dL = max(1.5,
                self.phosphate_mg_dL - 0.001 * (self.PTH_pg_mL / BASELINE_PTH_PG_ML - 1.0) * dt)

        # 归一化钙因子
        self.calcium_factor = self.calcium_mg_dL / BASELINE_CALCIUM_MG_DL

        # 同步到血液
        self.blood.PTH_pg_mL = self.PTH_pg_mL
        self.blood.calcium_mg_dL = self.calcium_mg_dL
        self.blood.phosphate_mg_dL = self.phosphate_mg_dL

        return {
            "PTH_pg_mL": self.PTH_pg_mL,
            "calcium_mg_dL": self.calcium_mg_dL,
            "phosphate_mg_dL": self.phosphate_mg_dL,
            "calcium_factor": self.calcium_factor,
        }

    # ══════════════════════════════════════════════════════════
    # 生长轴
    # ══════════════════════════════════════════════════════════

    def _compute_growth(self, dt: float) -> dict:
        """
        生长轴: GH/IGF-1调控组织合成

        方程:
          - GH基础分泌 → IGF-1合成
          - IGF-1 → 肝脏白蛋白合成增强

        效应:
          - growth_factor → liver.albumin_g_dL 微弱提升
        """
        # IGF-1: 缓慢响应(时间常数2h)
        tau = GROWTH_TAU_SEC
        alpha = dt / tau if tau > 0 else 1.0
        alpha = min(1.0, alpha)

        # IGF-1目标: 营养状态和GH驱动
        nutrition_factor = 1.0
        if self.blood.glucose_mmol_L < 3.5:
            nutrition_factor = 0.5  # 低血糖抑制IGF-1
        if self.blood.albumin_g_dL < 2.5:
            nutrition_factor = 0.7  # 低白蛋白提示营养不足

        igf1_target = BASELINE_IGF1_NMOL_L * nutrition_factor
        self.IGF1_nmol_L += (igf1_target - self.IGF1_nmol_L) * alpha

        # 生长因子归一化
        self.growth_factor = self.IGF1_nmol_L / BASELINE_IGF1_NMOL_L

        # GH基础分泌(简化)
        self.GH_ng_mL = BASELINE_GH_NG_ML * (0.8 + 0.2 * self.growth_factor)

        # 生长因子微弱促进白蛋白合成
        if self.growth_factor > 1.05:
            albumin_boost = (self.growth_factor - 1.0) * 0.001 * dt
            self.blood.albumin_g_dL = min(4.5, self.blood.albumin_g_dL + albumin_boost)

        return {
            "GH_ng_mL": self.GH_ng_mL,
            "IGF1_nmol_L": self.IGF1_nmol_L,
            "growth_factor": self.growth_factor,
        }

    # ══════════════════════════════════════════════════════════
    # 主计算函数
    # ══════════════════════════════════════════════════════════

    def compute(self, dt: float) -> dict:
        """
        主计算: 推进所有内分泌轴一个时间步

        Args:
            dt: 时间步长(秒)

        Returns:
            所有轴状态dict
        """
        self._elapsed_s += dt
        thyroid = self._compute_thyroid(dt)
        pancreatic = self._compute_pancreatic(dt)
        adrenal = self._compute_adrenal(dt)
        parathyroid = self._compute_parathyroid(dt)
        growth = self._compute_growth(dt)

        return {
            **thyroid,
            **pancreatic,
            **adrenal,
            **parathyroid,
            **growth,
        }

    # ══════════════════════════════════════════════════════════
    # 疾病/外部调用接口
    # ══════════════════════════════════════════════════════════

    def add_stress(self, amount: float):
        """外部调用: 添加应激输入(事件/处置触发)"""
        self._stress_input = max(0.0, self._stress_input + amount)

    def set_thyroid_T3_target(self, value: float):
        """外部调用: 设置T3目标值(疾病驱动)"""
        self._T3_target = max(0.0, value)

    def set_cortisol_target(self, value: float):
        """外部调用: 设置皮质醇目标值(疾病驱动)"""
        self._cortisol_target = max(0.0, value)

    def set_insulin_target(self, value: float):
        """外部调用: 设置胰岛素目标值(疾病驱动)"""
        self._insulin_target = max(0.0, value)

    def set_glucagon_target(self, value: float):
        """外部调用: 设置胰高血糖素目标值(疾病驱动)"""
        self._glucagon_target = max(0.0, value)

    # ══════════════════════════════════════════════════════════
    # 调试/状态查询
    # ══════════════════════════════════════════════════════════

    def summary(self) -> dict:
        return {
            # 甲状腺
            "T3_ng_dL": round(self.T3_ng_dL, 1),
            "T4_ug_dL": round(self.T4_ug_dL, 3),
            "metabolic_rate": round(self.metabolic_rate, 3),
            "T3_factor": round(self.T3_factor, 3),
            "core_temperature_C": round(self.blood.core_temperature_C, 1),
            # 胰腺
            "insulin_uU_mL": round(self.insulin_uU_mL, 1),
            "glucagon_pg_mL": round(self.glucagon_pg_mL, 1),
            "insulin_factor": round(self.insulin_factor, 3),
            "glucagon_factor": round(self.glucagon_factor, 3),
            # 肾上腺
            "HPA_axis": round(self.HPA_axis, 3),
            "cortisol_ug_dL": round(self.cortisol_ug_dL, 1),
            "epinephrine_pg_mL": round(self.epinephrine_pg_mL, 1),
            "cortisol_factor": round(self.cortisol_factor, 3),
            # 甲状旁腺
            "PTH_pg_mL": round(self.PTH_pg_mL, 1),
            "calcium_mg_dL": round(self.calcium_mg_dL, 1),
            "phosphate_mg_dL": round(self.phosphate_mg_dL, 2),
            "calcium_factor": round(self.calcium_factor, 3),
            # 生长
            "GH_ng_mL": round(self.GH_ng_mL, 2),
            "IGF1_nmol_L": round(self.IGF1_nmol_L, 2),
            "growth_factor": round(self.growth_factor, 3),
        }