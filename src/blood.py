"""
Blood Compartment - 血液隔室
所有器官共享的血液状态（物质浓度、气体分压等）
"""


class BloodCompartment:
    """
    血液隔室：存储动脉血和静脉血的关键参数
    作为所有器官模块之间的物质交换载体

    Note:
        total_volume_ml is kept in sync with HeartModule.circulating_volume_ml
        by the simulation engine at the end of each step(). The blood compartment
        does not modify volume itself — all changes flow through heart's
        blood_volume_change() or urine loss in simulation.py Step 7.5.
    """

    def __init__(self, total_volume_ml: float, plasma_fraction: float = 0.55):
        """
        初始化血液隔室

        Args:
            total_volume_ml: 总血容量 mL
            plasma_fraction: 血浆占总血容量比例
        """
        self.total_volume_ml = total_volume_ml
        self.plasma_volume_ml = total_volume_ml * plasma_fraction
        self.red_cell_volume_ml = total_volume_ml * (1 - plasma_fraction)

        # 动脉血参数
        self.arterial_PO2_mmHg = 95.0          # 动脉血氧分压
        self.arterial_PCO2_mmHg = 40.0          # 动脉血CO2分压
        self.arterial_saturation = 0.97         # 血氧饱和度
        self.arterial_pH = 7.40                 # 动脉血pH

        # 静脉血参数
        self.venous_PO2_mmHg = 40.0            # 静脉血氧分压
        self.venous_PCO2_mmHg = 46.0            # 静脉血CO2分压
        self.venous_saturation = 0.70           # 静脉血氧饱和度

        # 代谢物浓度
        self.glucose_mmol_L = 4.5              # 血糖 mmol/L
        self.lactate_mmol_L = 1.0              # 血乳酸 mmol/L
        self.bun_mg_dL = 15.0                  # 血尿素氮 mg/dL
        self.sodium_mEq_L = 145.0              # 血钠 mEq/L
        self.potassium_mEq_L = 4.2            # 血钾 mEq/L
        self.creatinine_mg_dL = 1.0           # 血肌酐 mg/dL

        # 体温（核心体温 °C）
        self.core_temperature_C = 38.5         # 犬正常体温

        # 胆红素（mg/dL）— IMHA 等疾病可升高
        self.bilirubin_mg_dL = 0.2            # 正常 < 0.5

        # 酮体（mmol/L）— DKA 可升高
        self.ketone_mmol_L = 0.0              # 正常 < 0.5

        # 血小板（×10³/μL）— DIC 可消耗
        self.PLT = 300.0                      # 正常 150-400

        # ============================================================
        # Gut absorption products (portal vein cache, cleared by liver each step)
        # ============================================================
        self.amino_acids_g_L = 1.0            # 氨基酸 g/L (fasting ~1.0, postprandial ~2.0)
        self.fatty_acids_mmol_L = 0.5         # 游离脂肪酸 mmol/L

        # ============================================================
        # Liver synthesis products
        # ============================================================
        self.albumin_g_dL = 3.0               # 白蛋白 g/dL (正常 2.5-4.0)
        self.ammonia_umol_L = 30.0            # 血氨 μmol/L (正常 <50)
        self.bile_acids_umol_L = 10.0         # 胆汁酸 μmol/L

        # ============================================================
        # Liver injury markers
        # ============================================================
        self.ALT_U_L = 25.0                   # 丙氨酸氨基转移酶 U/L
        self.AST_U_L = 25.0                   # 天冬氨酸氨基转移酶 U/L
        self.ALP_U_L = 30.0                   # 碱性磷酸酶 U/L
        self.GGT_U_L = 5.0                    # 谷氨酰转肽酶 U/L

        # ============================================================
        # Pharmacology / Drug concentration (generic, mg/kg equivalent)
        # CYP450 hepatic first-pass metabolism via liver.compute_drug_clearance()
        # ============================================================
        self.drug_concentration_mg_kg = 0.0   # 通用药物浓度占位

        # ============================================================
        # Coagulation factors (liver synthesis)
        # ============================================================
        self.coagulation_factor_VII = 1.0     # 凝血因子 VII 活性 (0-1)
        self.PT_seconds = 12.0                # 凝血酶原时间（正常 ~12s）
        self.INR = 1.0                        # 国际标准化比值

        # ============================================================
        # Endocrine hormones (blood concentration)
        # ============================================================
        # 甲状腺轴
        self.T3_ng_dL = 100.0                # 三碘甲状腺原氨酸 ng/dL
        self.T4_ug_dL = 1.5                  # 甲状腺素 ug/dL

        # 胰腺轴
        self.insulin_uU_mL = 12.0            # 胰岛素 uU/mL
        self.glucagon_pg_mL = 80.0           # 胰高血糖素 pg/mL

        # 肾上腺轴
        self.cortisol_ug_dL = 5.0             # 皮质醇 ug/dL
        self.epinephrine_pg_mL = 30.0        # 肾上腺素 pg/mL
        self.norepinephrine_pg_mL = 100.0     # 去甲肾上腺素 pg/mL

        # 甲状旁腺轴
        self.PTH_pg_mL = 30.0                # 甲状旁腺激素 pg/mL
        self.calcium_mg_dL = 10.0            # 血钙 mg/dL
        self.phosphate_mg_dL = 4.0           # 血磷 mg/dL

        # 生长轴
        self.GH_ng_mL = 2.0                  # 生长激素 ng/mL
        self.IGF1_nmol_L = 10.0             # 胰岛素样生长因子-1 nmol/L

        # ============================================================
        # Neurological state (written by NeuroModule)
        # ============================================================
        self.consciousness_level = 1.0     # CNS function (0=coma, 1=fully alert)
        self.seizure_activity = 0.0        # 癫痫活动强度 (0=none, 1=severe)
        self.pain_level = 0.0              # 疼痛强度 (0-10)
        self.chemoreceptor_drive = 0.0     # 化学感受器驱动 (0-1)

        # ============================================================
        # Immune/Inflammation state (written by ImmuneModule)
        # ============================================================
        self.WBC_K_uL = 10.0              # 白细胞计数 x10³/μL (正常 ~10k)
        self.CRP_mg_L = 10.0              # C反应蛋白 mg/L (正常 <10)
        self.cytokine_level = 0.0          # 统一细胞因子水平 (0-1)
        self.acute_phase_response = 0.0     # 急性期反应 (0-1)
        self.immune_suppression = 0.0      # 免疫抑制水平 (0-1)
        self.coagulation_state = 0.0       # 高凝状态 (0=正常, 1=DIC)

    def calculate_O2_content(self, PO2_mmHg, saturation, is_arterial=True):
        """
        计算血液氧含量 (mL O2/100mL blood)
        氧含量 = 血红蛋白 × 1.34 × 饱和度 + 溶解氧(0.003 × PO2)
        """
        Hb_g_dL = 14.0 if is_arterial else 14.0  # 犬血红蛋白 g/dL
        O2_bound = Hb_g_dL * 1.34 * saturation
        O2_dissolved = 0.003 * PO2_mmHg
        return O2_bound + O2_dissolved

    def get_arterial_O2_content(self):
        return self.calculate_O2_content(
            self.arterial_PO2_mmHg, self.arterial_saturation, is_arterial=True)

    def get_venous_O2_content(self):
        return self.calculate_O2_content(
            self.venous_PO2_mmHg, self.venous_saturation, is_arterial=False)

    def summary(self) -> dict:
        """返回血液状态摘要"""
        return {
            "arterial_PO2": round(self.arterial_PO2_mmHg, 1),
            "arterial_PCO2": round(self.arterial_PCO2_mmHg, 1),
            "venous_PO2": round(self.venous_PO2_mmHg, 1),
            "venous_PCO2": round(self.venous_PCO2_mmHg, 1),
            "saturation_art": round(self.arterial_saturation, 3),
            "saturation_ven": round(self.venous_saturation, 3),
            "glucose": round(self.glucose_mmol_L, 2),
            "lactate": round(self.lactate_mmol_L, 2),
            "sodium": round(self.sodium_mEq_L, 1),
            "potassium": round(self.potassium_mEq_L, 2),
            "temperature_C": round(self.core_temperature_C, 1),
            # Liver/gut markers
            "albumin": round(self.albumin_g_dL, 2),
            "ammonia": round(self.ammonia_umol_L, 1),
            "ALT": round(self.ALT_U_L, 1),
            "AST": round(self.AST_U_L, 1),
            "ALP": round(self.ALP_U_L, 1),
            "GGT": round(self.GGT_U_L, 1),
            "bile_acids": round(self.bile_acids_umol_L, 1),
            # Endocrine
            "T3": round(self.T3_ng_dL, 1),
            "insulin": round(self.insulin_uU_mL, 1),
            "cortisol": round(self.cortisol_ug_dL, 1),
            "calcium": round(self.calcium_mg_dL, 1),
            # Neurological
            "consciousness": round(self.consciousness_level, 2),
            "seizure": round(self.seizure_activity, 2),
            "pain": round(self.pain_level, 1),
            "chemoreceptor_drive": round(self.chemoreceptor_drive, 2),
            # Immune
            "WBC": round(self.WBC_K_uL, 1),
            "CRP": round(self.CRP_mg_L, 0),
            "cytokine": round(self.cytokine_level, 3),
            "acute_phase": round(self.acute_phase_response, 3),
            "immune_suppression": round(self.immune_suppression, 3),
            "coagulation": round(self.coagulation_state, 3),
        }
