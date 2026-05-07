"""
Blood Compartment - 血液隔室
所有器官共享的血液状态（物质浓度、气体分压等）
"""


class BloodCompartment:
    """
    血液隔室：存储动脉血和静脉血的关键参数
    作为所有器官模块之间的物质交换载体
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
        }
