"""
Liver Module - 肝脏代谢系统
建模肝脏糖代谢、氨解毒、白蛋白合成、胆红素代谢、药物代谢
"""

import math
from parameters import *

# ── 生理常数 ──
_MAX_GLYCOGEN_G = 300.0           # 满糖原储备 g（犬类约300g）
_AMINO_TO_AMMONIA_UMOL_PER_G = 10.0  # 每克氨基酸脱氨产生氨 μmol
_UREA_MMOL_TO_BUN_MG_DL = 2.8    # 尿素 mmol → BUN mg/dL 转换系数
_NORMAL_BILIRUBIN_MG_DL_PER_KG = 0.004  # 正常胆红素产生率 mg/day/kg
_BILIRUBIN_AXIS_INTERCEPT = 0.2   # 胆红素基准值 mg/dL（正常）
_BILIRUBIN_SEVERITY_SLOPE = 2.0   # 解毒能力下降时胆红素上升斜率


class LiverModule:
    """
    肝脏模块：核心代谢和解毒器官

    核心变量：
    - metabolic_activity: 代谢活性 (0-1, 1=正常)
    - detox_capacity: 氨解毒能力 (0-1, 1=正常)
    - cyp450_activity: CYP450 药物代谢活性 (0-1, 1=正常)
    - glycogen_fraction: 糖原储备比例 (0-1, 1=满)
    - bilirubin_conjugation: 胆红素结合能力 (0-1, 1=正常)

    数据流：
    compute(gut_state) → 读取 gut_state（肠道吸收速率）
                         → 读取 blood.portal_cache + gut_state
                         → 更新 blood.glucose, blood.albumin, blood.ammonia,
                           blood.ALT_U_L, blood.AST_U_L, blood.ALP_U_L
                         → 返回 liver_state
    """

    def __init__(self, weight_kg: float, blood):
        self.w = weight_kg
        self.blood = blood  # 血液隔室引用

        # 代谢功能 (0-1)
        self.metabolic_activity = 1.0

        # 氨解毒能力 (CPS/OTC 酶活性, 0-1)
        self.detox_capacity = 1.0

        # 内源性氨产生速率 (μmol/min)：组织蛋白分解 + 肾脏产氨基准
        self.endogenous_ammonia_rate = 20.0

        # CYP450 药物代谢活性 (0-1)
        self.cyp450_activity = 1.0

        # 糖原储备 (0-1)
        self.glycogen_fraction = 0.6

        # 胆红素结合能力 (0-1)
        self.bilirubin_conjugation = 1.0

        # 肝脏血流量 (≈25% CO)
        self.hepatic_blood_flow = 0.25 * base_cardiac_output_ml_min(weight_kg)

        # 胆红素状态变量（用于时序ODE）
        self._bilirubin_accumulation = 0.0

        # 累计输出（用于追踪）
        self.cumulative_glucose_production_g = 0.0
        self.cumulative_urea_production_mmol = 0.0
        self.cumulative_albumin_production_g = 0.0

    def _update_hepatic_flow(self, CO: float):
        """更新肝血流量（≈25% CO）"""
        if CO <= 0:
            raise ValueError("cardiac_output must be positive")
        self.hepatic_blood_flow = 0.25 * CO

    def _compute_glucose_homeostasis(self, dt: float, gut_state: dict) -> float:
        """
        葡萄糖稳态调节

        规则：
        - blood.glucose < 3.5 mmol/L → 糖原分解 + 糖异生
        - blood.glucose > 6.0 mmol/L → 糖原合成
        - 极低 (< 2.5) → 强烈糖异生
        - 极高 (> 8.0) → 强烈糖原合成

        dt: 秒（转换为分钟用于 per-minute 速率计算）
        gut_state: 包含 absorption_amino_g_min 等速率值
        """
        dt_min = dt / 60.0
        glucose = self.blood.glucose_mmol_L
        glucose_production_g_min = 0.0

        # 低血糖：糖原分解
        if glucose < 3.5:
            # 糖原分解速率 (g/min)，受 metabolic_activity 调节
            base_rate = 0.3 * self.glycogen_fraction  # 最大 0.3 g/min（满糖原时）
            rate = base_rate * self.metabolic_activity

            # 极低血糖时加速
            if glucose < 2.5:
                rate *= 3.0
            elif glucose < 3.0:
                rate *= 1.5

            # 消耗糖原（per-minute rate × dt_min）
            glycogen_consumed_g = rate * dt_min * _MAX_GLYCOGEN_G
            self.glycogen_fraction = max(0.0, self.glycogen_fraction - glycogen_consumed_g / _MAX_GLYCOGEN_G)
            glucose_production_g_min += rate

        # 高血糖：糖原合成
        if glucose > 6.0:
            # 糖原合成速率 (g/min)
            base_rate = 0.2 * self.metabolic_activity
            rate = base_rate

            # 极高血糖时加速
            if glucose > 8.0:
                rate *= 2.0
            elif glucose > 7.0:
                rate *= 1.5

            # 合成糖原（限制最大糖原量），per-minute rate × dt_min
            glycogen_synthesized_g = rate * dt_min * _MAX_GLYCOGEN_G
            max_glycogen_g = _MAX_GLYCOGEN_G
            self.glycogen_fraction = min(
                1.0,
                self.glycogen_fraction + glycogen_synthesized_g / max_glycogen_g
            )

        # 氨中毒时抑制糖异生（肝脏受损时）
        if self.blood.ammonia_umol_L > 100:
            glucose_production_g_min *= max(0.3, 1.0 - (self.blood.ammonia_umol_L - 100) / 400)

        # 糖异生：利用氨基酸（来自 gut_state 速率）合成葡萄糖
        if self.blood.glucose_mmol_L < 3.5 and self.metabolic_activity > 0.3:
            # 氨基酸糖异生（使用 gut_state 中的吸收速率 g/min）
            amino_g_min = gut_state.get("absorption_amino_g_min", 0.0)
            gluconeogenesis_rate = amino_g_min * 0.6  # 60% 转化为葡萄糖
            glucose_production_g_min += gluconeogenesis_rate * self.metabolic_activity

        return glucose_production_g_min

    def _compute_ammonia_detox(self, dt: float, gut_state: dict) -> float:
        """
        氨解毒（尿素循环）

        CPS → OTC → ARG 酶促反应
        氨 + CO2 → 精氨酸 → 尿素 + 鸟氨酸

        dt 的单位是秒，所有 rate 参数都是 per-minute。
        公式使用分钟制：dt_min = dt / 60.0

        稳态分析（detox_capacity=1.0, endogenous=20, gut_input≈2）：
          production_rate = 20 + 2 = 22 μmol/min
          clearance_rate = k * ammonia, where k = 1.0/min
          steady_state = production_rate / k = 22 μmol/L ≈ 正常范围 10-40 ✓

        detox_capacity=0.2 时：
          k_eff = 0.2 → SS = 22/0.2 = 110 μmol/L（严重高氨血症）
        """
        ammonia = self.blood.ammonia_umol_L
        dt_min = dt / 60.0

        # 清除：第一阶动力学，k 受 detox_capacity 调节
        k = 1.0 * self.detox_capacity  # 随解毒能力缩放
        detox_rate_umol_min = k * ammonia  # 随浓度变化的清除率

        # 肠道来源的氨（来自 gut_state 的氨基酸吸收速率，per-minute）
        gut_amino_rate = gut_state.get("absorption_amino_g_min", 0.0)
        gut_ammonia_rate = gut_amino_rate * _AMINO_TO_AMMONIA_UMOL_PER_G

        # 内源性氨产生率（组织蛋白分解 + 肾脏产氨，per-minute）
        endogenous_rate = self.endogenous_ammonia_rate

        # 总产氨速率 (μmol/min)
        total_production_rate = gut_ammonia_rate + endogenous_rate

        # 血氨更新：dA/dt = production - k*A
        # 解析解（每个 dt）：A(t+dt) = A(t)*exp(-k*dt_min) + (P/k)*(1-exp(-k*dt_min))
        new_ammonia = (
            ammonia * math.exp(-k * dt_min)
            + (total_production_rate / k) * (1.0 - math.exp(-k * dt_min))
        )
        new_ammonia = max(0.0, new_ammonia)
        self.blood.ammonia_umol_L = new_ammonia

        # 尿素产生（2 NH3 → 1 CO(NH2)2）
        ammonia_consumed = max(0.0, ammonia - new_ammonia)
        urea_produced_mmol = ammonia_consumed / 2.0

        # 更新血尿素氮
        if urea_produced_mmol > 0:
            self.blood.bun_mg_dL += urea_produced_mmol * _UREA_MMOL_TO_BUN_MG_DL * dt_min

        return total_production_rate

    def _compute_protein_synthesis(self, dt: float) -> float:
        """
        白蛋白合成

        正常合成速率：约 0.5 g/day/kg
        受代谢活性、氨基酸可用性调节
        """
        dt_min = dt / 60.0
        dt_hour = dt / 3600.0
        base_rate_g_day = 0.5 * self.w  # 0.5 g/day/kg
        activity_factor = self.metabolic_activity

        # 氨基酸可用性因子（门静脉氨基酸浓度）
        amino_factor = min(2.0, self.blood.amino_acids_g_L / 1.0)  # 正常 ~1.0 g/L

        # 合成速率 g/day
        synthesis_rate = base_rate_g_day * activity_factor * amino_factor

        # 更新白蛋白（正常 2.5-4.0 g/dL，半衰期 ~20 天，简化处理）
        albumin_change_g_dL = synthesis_rate * dt_hour / 24.0  # g/dL per step
        self.blood.albumin_g_dL = max(1.0, self.blood.albumin_g_dL + albumin_change_g_dL)
        self.blood.albumin_g_dL = min(5.0, self.blood.albumin_g_dL)  # 上限

        # 累计（g）
        self.cumulative_albumin_production_g += synthesis_rate * dt_min / 60.0

        return synthesis_rate

    def _compute_bilirubin_metabolism(self, dt: float):
        """
        胆红素代谢（时序 ODE）

        规则：
        - 正常衰老红细胞 → 非结合胆红素（间接胆红素）
        - 肝脏结合 → 胆红素葡萄糖醛酸（直接胆红素）
        - 胆汁排泄 → 肠肝循环

        时序模型：
        dBIL/dt = production_rate × (1 - conjugation_factor) - k_clear × BIL_accumulation
        """
        dt_day = dt / 86400.0  # 秒 → 天

        # 正常胆红素产生（来自红细胞分解，mg/day/kg）
        normal_production_rate = _NORMAL_BILIRUBIN_MG_DL_PER_KG * self.w  # mg/day

        # 结合能力下降 → 累积加速
        conjugation_factor = self.bilirubin_conjugation

        # 胆红素累积 ODE
        # production 输入（未结合部分），清除 = k × accumulation（肝脏排泄能力）
        k_clear = 0.5 * conjugation_factor  # 清除率常数，天^-1
        production_input = normal_production_rate * (1.0 - conjugation_factor)

        # 累积微分：dA/dt = production - k_clear × A
        # 解析解：A(t) = A(0)*exp(-k*t) + (P/k)*(1-exp(-k*t))
        if k_clear > 1e-6:
            new_accumulation = (
                self._bilirubin_accumulation * math.exp(-k_clear * dt_day)
                + (production_input / k_clear) * (1.0 - math.exp(-k_clear * dt_day))
            )
        else:
            # conjugation_factor=0 时，仅累积不清除
            new_accumulation = self._bilirubin_accumulation + production_input * dt_day
        new_accumulation = max(0.0, new_accumulation)
        self._bilirubin_accumulation = new_accumulation

        # 血胆红素 = 基准 + 累积贡献
        bilirubin_level = (
            _BILIRUBIN_AXIS_INTERCEPT
            + new_accumulation * _BILIRUBIN_SEVERITY_SLOPE
        )
        self.blood.bilirubin_mg_dL = max(0.1, min(15.0, bilirubin_level))

        # 肝酶升高模拟（ALT, AST 反映肝细胞损伤）
        # ALP 反映胆汁淤积
        if conjugation_factor < 0.8:
            self.blood.ALT_U_L = 25.0 + (1.0 - conjugation_factor) * 150.0
            self.blood.AST_U_L = 25.0 + (1.0 - conjugation_factor) * 200.0
            self.blood.ALP_U_L = 30.0 + (1.0 - conjugation_factor) * 300.0

    def _compute_cyp450_drug_metabolism(self, dt: float):
        """
        CYP450 药物代谢

        简化：代谢速率与 cyp450_activity 成正比
        实际应用中，药物浓度更新由 pharmacology.py 处理
        """
        pass  # 占位，pharmacology.py 会通过 FactorCommand 修改此参数

    def compute(self, dt: float, gut_state: dict, cardiac_output: float) -> dict:
        """
        肝脏计算主函数

        Args:
            dt: 时间步长 秒
            gut_state: GutModule.compute() 返回的状态 dict
            cardiac_output: 心输出量 mL/min

        Returns:
            liver_state dict
        """
        # Step 1: 更新肝血流量
        self._update_hepatic_flow(cardiac_output)

        # Step 2: 葡萄糖稳态（使用 gut_state 中的吸收速率）
        glucose_output_g_min = self._compute_glucose_homeostasis(dt, gut_state)

        # 将肠道吸收的葡萄糖加入血液（gut 已经写了 blood.glucose，这里补充糖异生）
        if glucose_output_g_min > 0.05:
            dt_min = dt / 60.0
            # 葡萄糖增加量 = 产生速率 × dt_min → 转换为 mmol/L
            plasma_ml = self.w * 86 * 0.55
            if plasma_ml > 0:
                glucose_mmol = (glucose_output_g_min * 1000 / 180)  # g → mmol
                glucose_increase = glucose_mmol / (plasma_ml / 1000)  # mmol/L per min
                # 移除地板：允许血糖跌至生理下限（约 1.5 mmol/L）
                self.blood.glucose_mmol_L = max(
                    1.0,  # 生理下限（不是地板，是糖异生极限）
                    min(25.0, self.blood.glucose_mmol_L + glucose_increase * dt_min)
                )

        # Step 3: 氨解毒（使用 gut_state 速率）
        ammonia_clearance = self._compute_ammonia_detox(dt, gut_state)

        # Step 4: 蛋白质合成
        albumin_synthesis = self._compute_protein_synthesis(dt)

        # Step 5: 胆红素代谢（时序 ODE）
        self._compute_bilirubin_metabolism(dt)

        # Step 6: CYP450（占位）
        self._compute_cyp450_drug_metabolism(dt)

        # 清除门户缓存（模拟肝脏对肠道吸收营养的摄取）
        # 肠道来的氨基酸被肝脏摄取用于糖异生/蛋白质合成
        gut_amino_rate = gut_state.get("absorption_amino_g_min", 0.0)
        dt_min = dt / 60.0
        amino_removed_g_L = gut_amino_rate * dt_min / (self.hepatic_blood_flow / 1000) if self.hepatic_blood_flow > 0 else 0.0
        self.blood.amino_acids_g_L = max(0.1, self.blood.amino_acids_g_L - amino_removed_g_L)

        # 累计输出追踪
        dt_min = dt / 60.0
        self.cumulative_glucose_production_g += glucose_output_g_min * dt_min
        self.cumulative_urea_production_mmol += ammonia_clearance * dt_min / 2.0

        return {
            "hepatic_blood_flow_ml_min": round(self.hepatic_blood_flow, 1),
            "metabolic_activity": round(self.metabolic_activity, 3),
            "detox_capacity": round(self.detox_capacity, 3),
            "cyp450_activity": round(self.cyp450_activity, 3),
            "glycogen_fraction": round(self.glycogen_fraction, 3),
            "bilirubin_conjugation": round(self.bilirubin_conjugation, 3),
            "glucose_output_g_min": round(glucose_output_g_min, 3),
            "ammonia_clearance_umol_min": round(ammonia_clearance, 1),
            "albumin_synthesis_g_day": round(albumin_synthesis, 2),
            "ALT_U_L": round(self.blood.ALT_U_L, 1),
            "AST_U_L": round(self.blood.AST_U_L, 1),
            "ALP_U_L": round(self.blood.ALP_U_L, 1),
            "GGT_U_L": round(self.blood.GGT_U_L, 1),
            "albumin_g_dL": round(self.blood.albumin_g_dL, 2),
            "ammonia_umol_L": round(self.blood.ammonia_umol_L, 1),
            "glucose_mmol_L": round(self.blood.glucose_mmol_L, 2),
            "BUN_mg_dL": round(self.blood.bun_mg_dL, 1),
        }

    def summary(self) -> dict:
        """返回肝脏状态摘要"""
        return {
            "metabolic_activity": round(self.metabolic_activity, 3),
            "detox_capacity": round(self.detox_capacity, 3),
            "cyp450_activity": round(self.cyp450_activity, 3),
            "glycogen": round(self.glycogen_fraction, 3),
            "hepatic_flow": round(self.hepatic_blood_flow, 1),
            "albumin": round(self.blood.albumin_g_dL, 2),
            "ammonia": round(self.blood.ammonia_umol_L, 1),
        }
