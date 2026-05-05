"""
Kidney Module - 肾脏泌尿系统
建模肾小球滤过、肾小管重吸收、水电解质平衡
"""

from parameters import *


class KidneyModule:
    """
    肾脏泌尿模块：模拟肾脏滤过、重吸收和排泄功能

    核心变量：
    - GFR: 肾小球滤过率 mL/min
    - renal_blood_flow: 肾血流量 mL/min
    - urine_output: 尿量 mL/min
    - plasma_osmolality: 血浆渗透压 mOsm/kg

    核心方程：
    - GFR = Kf × (PGC - PBS - πGC + πBS)
    - 滤过钠 = GFR × [Na]_plasma
    - 尿量 = 滤过量 - 重吸收量
    """

    def __init__(
        self,
        weight_kg: float,
        blood,
        base_gfr_ml_min: float = None,   # 若为 None 则按 3.0 mL/kg 计算
        base_rbf_ml_min: float = None,   # 若为 None 则按 20% CO 计算
        base_urine_ml_min: float = None, # 若为 None 则按 0.02 mL/min/kg 计算
        water_reabsorp_rate: float = TUBULAR_WATER_REABSORPTION,
    ):
        self.w = weight_kg
        self.blood = blood  # 血液隔室引用

        # 基础GFR（外部传入或按 3.0 mL/kg 计算）
        _gfr = base_gfr_ml_min if base_gfr_ml_min is not None else 3.0 * weight_kg
        self.base_GFR = _gfr
        self.GFR = _gfr                    # 当前GFR
        self._disease_gfr_multiplier = 1.0  # 疾病导致的 GFR 乘子（持久化）

        # 肾血流量（外部传入或按 20% CO 计算）
        _co = base_rbf_ml_min if base_rbf_ml_min is not None else 0.20 * (85 * 1.0 * weight_kg)
        self.base_renal_blood_flow = _co
        self.renal_blood_flow = _co

        # 尿量（外部传入或按 0.02 mL/min/kg 计算）
        _urine = base_urine_ml_min if base_urine_ml_min is not None else 0.02 * weight_kg
        self.base_urine_output = _urine
        self.urine_output = _urine

        # 滤过分数
        self.filtration_fraction = self.base_GFR / self.base_renal_blood_flow  # ≈ 0.2

        # 水重吸收率（正常约 99%）
        self.water_reabsorption_rate = water_reabsorp_rate  # 0.99

        # 电解质平衡
        self.plasma_sodium = PLASMA_SODIUM_MEQ_L       # 145 mEq/L
        self.filtered_sodium_load = 0.0                  # 每分钟滤过钠量 mEq/min
        self.reabsorbed_sodium = 0.0                    # 每分钟重吸收钠量 mEq/min
        self.excreted_sodium = 0.0                      # 每分钟排出的钠量 mEq/min

        # 体液状态
        self.total_body_water_ml = 600 * weight_kg     # 总体液 kg × mL/kg（60%体重）
        self.plasma_volume_ml = PLASMA_VOLUME_FRACTION * total_blood_volume_ml(weight_kg)

        # 渗透压
        self.plasma_osmolality = 295.0                  # mOsm/kg（正常 290-300）

        # 抗利尿激素水平（0-1，影响水通道）
        # 正常动物基础 ADH 较低，允许适度尿量（约 1% 滤过液被排出）
        self.ADH_level = 0.2                             # 正常基线

        # RAAS 系统
        self.renin_activity = 0.0                       # 肾素活性（arbitrary units）
        self.angiotensin_II = 0.0                      # 血管紧张素 II（相对水平）
        self.aldosterone = 0.0                          # 醛固酮（相对水平）

        # 累计输出
        self.cumulative_urine_ml = 0.0
        # 尿量导致的循环血量损失
        self.blood_volume_loss_rate = 0.0  # mL/min

    def _apply_RAAS(self, MAP: float, CVP: float, Na_conc: float):
        """
        肾素-血管紧张素-醛固酮系统（RAAS）

        激活条件：
        - 血压下降（肾动脉灌注压 ↓）
        - 钠浓度降低
        - 交感神经激活

        效应：
        - 血管收缩（升高血压）
        - 保钠保水（减少尿量）
        - 醛固酮促进钠重吸收
        """
        # 肾素激活（血压低 + 钠低）
        MAP_deficit = (MEAN_ARTERIAL_PRESSURE_MMHG - MAP) / MEAN_ARTERIAL_PRESSURE_MMHG
        Na_deficit = max(0.0, (145.0 - Na_conc) / 145.0)

        self.renin_activity = max(0.0, 0.5 * MAP_deficit + 0.5 * Na_deficit)

        # 血管紧张素 II（简化：与肾素成正比）
        self.angiotensin_II = self.renin_activity * 2.0

        # 醛固酮（由 AngII 激活）
        self.aldosterone = self.angiotensin_II * 0.5

        # 醛固酮效应：增强近端小管钠重吸收
        if self.aldosterone > 0.1:
            # 醛固酮每升高 1 单位，钠排泄减少约 10%
            reabsorp_boost = 1.0 + 0.1 * self.aldosterone
            self.water_reabsorption_rate = min(0.999, TUBULAR_WATER_REABSORPTION * reabsorp_boost)

    def _update_GFR(self, MAP: float, CVP: float):
        """
        GFR 更新：受血压和肾灌注压调节

        简化 Starling 方程：
        GFR = Kf × (PGC - PBS - πGC + πBS)

        其中：
        PGC ≈ MAP（肾小球毛细血管压）
        PBS ≈ CVP（鲍曼囊压）
        πGC ≈ 血浆胶体渗透压（≈ 25 mmHg）
        πBS ≈ 0（鲍曼囊胶渗压可忽略）
        """
        PGC = MAP * 0.6  # 肾小球毛细血管压 ≈ MAP 的 60%
        PBS = CVP + 10   # 鲍曼囊压 ≈ CVP + 10 mmHg
        plasma_colloid = 25.0  # 血浆胶体渗透压 mmHg

        filtration_pressure = PGC - PBS - plasma_colloid
        # 目标 GFR = base_GFR = 60 mL/min（20kg 犬）
        # net_pressure ≈ 21 mmHg → Kf = GFR/net_pressure ≈ 60/21 ≈ 2.86
        Kf = 3.0

        self.GFR = max(0.0, Kf * filtration_pressure)
        # 应用疾病导致的 GFR 乘子（持久化，每步生效）
        self.GFR *= self._disease_gfr_multiplier
        # GFR 最低为 0（允许完全无尿，由 MAP 无尿阈值和疾病乘子控制）
        self.GFR = max(0.0, self.GFR)

    def _compute_sodium_balance(self, GFR: float, plasma_Na: float):
        """
        钠平衡计算

        每分钟滤过钠 = GFR × [Na]_plasma
        重吸收钠 ≈ 99%（正常情况下）
        """
        self.filtered_sodium_load = GFR * plasma_Na  # mEq/min

        # 醛固酮调节重吸收（醛固酮升高 → 重吸收增加 → 排泄减少）
        aldosterone_effect = 1.0 + 0.01 * self.aldosterone
        reabsorp_rate = min(0.999, 0.99 * aldosterone_effect)

        self.reabsorbed_sodium = self.filtered_sodium_load * reabsorp_rate
        self.excreted_sodium = self.filtered_sodium_load - self.reabsorbed_sodium

    def _compute_urine_output(self, GFR: float):
        """
        尿量计算

        正常动物：GFR ≈ 20 mL/min，约 98% 滤过水被重吸收 → 尿量 ≈ 0.4 mL/min

        公式结构（分段）：
        - 大部分水在近端小管被强制重吸收（67%）
        - ADH 控制远曲小管/集合管对剩余水的重吸收比例
        - 最终尿量 = 滤过量 - 总重吸收量
        """
        filtered_water = GFR  # mL/min（水自由滤过）

        # 近端小管强制重吸收（不受 ADH 控制）
        proximal_reabsorption = 0.67 * filtered_water

        # 远端 ADH 调节重吸收
        # ADH=0 时：约 97% 的远端水被重吸收
        # ADH=0.2 时：约 97.3% 被重吸收 → 正常尿量（0.4 mL/min）
        # ADH=1.0 时：约 98.6% 被重吸收 → 极度浓缩尿
        distal_reabsorption_fraction = 0.97 + 0.013 * self.ADH_level
        distal_reabsorption = (filtered_water - proximal_reabsorption) * distal_reabsorption_fraction

        total_reabsorption = proximal_reabsorption + distal_reabsorption
        self.urine_output = max(0.0, filtered_water - total_reabsorption)

    def compute(self, dt: float, MAP: float, CVP: float, cardiac_output: float):
        """
        主计算函数：推进肾脏功能一个时间步

        Args:
            dt: 时间步长（秒）
            MAP: 平均动脉压 mmHg
            CVP: 中心静脉压 mmHg
            cardiac_output: 心输出量 mL/min

        Returns:
            肾脏状态 dict
        """
        # Step 1: 更新肾血流量（与心输出量成正比）
        CO_fraction = cardiac_output / base_cardiac_output_ml_min(self.w)
        self.renal_blood_flow = self.base_renal_blood_flow * CO_fraction

        # Step 2: RAAS 系统激活（MAP 低时触发）
        self._apply_RAAS(MAP, CVP, self.blood.sodium_mEq_L)

        # Step 3: 更新 GFR
        self._update_GFR(MAP, CVP)

        # Step 4: 钠平衡
        self._compute_sodium_balance(self.GFR, self.blood.sodium_mEq_L)

        # Step 5: 尿量
        self._compute_urine_output(self.GFR)

        # Step 5.5: MAP 无尿阈值 — MAP < 60 时肾灌注不足，尿量骤降
        if MAP < 60.0:
            # MAP 30 → 因子 0（无尿），MAP 60 → 因子 1（正常），线性插值
            map_factor = max(0.0, (MAP - 30.0) / 30.0)
            self.urine_output *= map_factor

        # Step 6: 血浆渗透压（简化：与钠浓度成正比）
        self.plasma_osmolality = 2 * self.blood.sodium_mEq_L + 5 + 10
        # 简化：2×[Na] + [BUN]/2.8 + [GLUCOSE]/18 ≈ 290-300 mOsm/kg

        # Step 7: 更新血液代谢物（肾脏排泄）
        # 尿素氮（BUN）：GFR ↓ → BUN ↑
        # 目标 BUN = base_clearance / current_clearance × 15
        # 正常 GFR 时目标=15，GFR 减半时目标=30，GFR→0 时目标→150（上限）
        if self.GFR > 0.5:
            bun_target = (self.base_GFR / self.GFR) * 15.0
        else:
            bun_target = 150.0  # 无尿时 BUN 上限
        bun_target = min(150.0, bun_target)
        # 低通滤波：每步向目标移动 5%（时间常数约 20s，避免振荡）
        self.blood.bun_mg_dL = max(5.0, self.blood.bun_mg_dL + (bun_target - self.blood.bun_mg_dL) * 0.05)

        # 肌酐：与 GFR 成反比（GFR↓→Cr↑），正常 GFR 时目标≈1.0 mg/dL
        # 公式：crea_target = base_GFR / current_GFR * 1.0
        if self.GFR > 0.01:
            crea_target = (self.base_GFR / self.GFR) * 1.0
        else:
            crea_target = 5.0  # 无尿时肌酐上限
        crea_target = min(5.0, crea_target)
        self.blood.creatinine_mg_dL = max(0.5, self.blood.creatinine_mg_dL + (crea_target - self.blood.creatinine_mg_dL) * 0.1)

        # Step 8: 累计尿量
        self.cumulative_urine_ml += self.urine_output * dt

        # Step 9: 尿量从血液隔室排出
        # 70% 由体内水分补充（胃肠道、细胞内液），30% 直接减少循环血量
        # simulation.py Step 7.5 读取此值并应用到心脏血容量
        self.blood_volume_loss_rate = self.urine_output * 0.30  # mL/min

        # Step 10: 模拟 ADH 响应（血渗压高或血容量低时释放 ADH）
        osmotic_pressure = self.plasma_osmolality - 295.0
        if osmotic_pressure > 10:
            self.ADH_level = min(1.0, self.ADH_level + 0.1 * osmotic_pressure / 10)
        else:
            self.ADH_level = max(0.1, self.ADH_level - 0.01)

        return {
            "GFR_ml_min": self.GFR,
            "renal_blood_flow_ml_min": self.renal_blood_flow,
            "urine_output_ml_min": self.urine_output,
            "cumulative_urine_ml": self.cumulative_urine_ml,
            "plasma_osmolality": self.plasma_osmolality,
            "filtered_sodium_mEq_min": self.filtered_sodium_load,
            "excreted_sodium_mEq_min": self.excreted_sodium,
            "renin_activity": self.renin_activity,
            "aldosterone": self.aldosterone,
            "ADH_level": self.ADH_level,
            "BUN_mg_dL": round(self.blood.bun_mg_dL, 1),
            "creatinine_mg_dL": round(self.blood.creatinine_mg_dL, 2),
        }

    def summary(self) -> dict:
        return {
            "GFR": round(self.GFR, 1),
            "RBF": round(self.renal_blood_flow, 1),
            "urine": round(self.urine_output, 3),
            "cumulative_urine": round(self.cumulative_urine_ml, 1),
            "BUN": round(self.blood.bun_mg_dL, 1),
            "Na_excretion": round(self.excreted_sodium, 4),
            "renin": round(self.renin_activity, 3),
            "aldosterone": round(self.aldosterone, 3),
        }