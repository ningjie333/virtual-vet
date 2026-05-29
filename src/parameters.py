# Virtual Creature - Physiological Parameters
# 基于犬科动物正常生理值（Canine Physiology）
#
# 参数分两类:
#   A类 (函数): 随体重变化的参数，调用时传入 weight_kg
#   B类 (常量): 通用生理常数，与体重无关

# ============================================================
# A类: 随体重变化的参数 (函数)
# ============================================================

def total_blood_volume_ml(weight_kg: float) -> float:
    """总血容量: 80-90 mL/kg, 取 86"""
    return 86.0 * weight_kg

def stroke_volume_ml(weight_kg: float) -> float:
    """每搏输出量: 1.0-1.5 mL/kg, 取 1.0 (危重基准线)"""
    return 1.0 * weight_kg

def base_cardiac_output_ml_min(weight_kg: float) -> float:
    """基础心输出量: HR × SV"""
    return HEART_RATE_REST_BPM * stroke_volume_ml(weight_kg)

def tidal_volume_ml(weight_kg: float) -> float:
    """潮气量: 临床标准 10-12 mL/kg, 取 12"""
    return 12.0 * weight_kg

def base_minute_ventilation(weight_kg: float) -> float:
    """基础分钟通气量: TV × RR"""
    return tidal_volume_ml(weight_kg) * RESPIRATORY_RATE_REST

def renal_blood_flow_ml_min(weight_kg: float) -> float:
    """基础肾血流量: ≈ 20% CO"""
    return 0.20 * base_cardiac_output_ml_min(weight_kg)

def gfr_ml_min(weight_kg: float) -> float:
    """基础 GFR: 2.5-4.0 mL/min/kg, 取 3.0"""
    return 3.0 * weight_kg

def baseline_urine_output_ml_min(weight_kg: float) -> float:
    """基础尿量: 正常 1-2 mL/kg/hr ≈ 0.017-0.033 mL/min/kg, 取 0.02"""
    return 0.02 * weight_kg


# ============================================================
# B类: 通用生理常量 (与体重无关)
# ============================================================

# --- 心血管系统 ---
# REF: textbook:nelson | Nelson & Couto 5e Ch22 | Canine normal resting HR 60-140 bpm
HEART_RATE_REST_BPM = 85                          # 静息心率 bpm
# REF: textbook:nelson | Nelson & Couto 5e Ch22 | Estimated maximum ~180 bpm
HEART_RATE_STRESS_BPM = 180                       # 应激心率上限 bpm

# 血管阻力 (mmHg·s/mL = PRU)
# REF: textbook:guyton | Guyton 14e Ch26 | TPR ≈ 1.4 mmHg·s/mL in resting dog
# 推导: MAP = 60 + CO × R / 60
# 正常 MAP=100, CO=1700 mL/min → R = 1.41
SYSTEMIC_VASCULAR_RESISTANCE = 1.41               # 体循环血管阻力
# REF: textbook:guyton | Guyton 14e Ch26 | PVR ≈ 0.18 mmHg·s/mL
PULMONARY_VASCULAR_RESISTANCE = 0.18              # 肺循环血管阻力

# 顺应性 (mL/mmHg)
# REF: textbook:guyton | Guyton 14e Ch20 | Arterial compliance ≈ 1.5 mL/mmHg
ARTERIAL_COMPLIANCE = 1.5                         # 动脉顺应性
# REF: textbook:guyton | Guyton 14e Ch20 | Venous compliance ≈ 30 mL/mmHg
VENOUS_COMPLIANCE = 30.0                          # 静脉顺应性
PULMONARY_COMPLIANCE = 4.0                        # 肺顺应性

# 正常稳态值
# REF: textbook:nelson | Nelson & Couto 5e Ch22 | MAP normal 80-120 mmHg
MEAN_ARTERIAL_PRESSURE_MMHG = 100.0               # 平均动脉压 mmHg
CENTRAL_VENOUS_PRESSURE_MMHG = 4.0                # 中心静脉压 mmHg
PULMONARY_ARTERIAL_PRESSURE_MMHG = 15.0           # 肺动脉压 mmHg

# --- 呼吸系统 ---
# REF: textbook:nelson | Nelson & Couto 5e Ch6 | Normal RR 10-30 /min (resting)
RESPIRATORY_RATE_REST = 18                        # 静息呼吸频率 /min
RESPIRATORY_RATE_STRESS = 40                      # 应激呼吸频率 /min

# 气体分压 (mmHg)
# REF: textbook:guyton | Guyton 14e Ch40 | Standard atmospheric 760 mmHg (sea level)
ATMOSPHERIC_PRESSURE_MMHG = 760.0                 # 标准大气压（海平面）
WATER_VAPOR_PRESSURE_MMHG = 47.0                  # 37°C 水蒸气分压
ATMOSPHERIC_PO2 = 150.0                           # 大气氧分压（海平面）
ATMOSPHERIC_PCO2 = 0.0                            # 大气CO2分压
ALVEOLAR_PO2_NORMAL = 100.0                       # 正常肺泡氧分压
ALVEOLAR_PCO2_NORMAL = 40.0                       # 正常肺泡CO2分压

# 动脉血气
# REF: textbook:nelson | Nelson & Couto 5e Ch6 | Normal PaO2 90-100 mmHg
ARTERIAL_PO2_NORMAL = 95.0                        # 正常动脉血氧分压 mmHg
# REF: textbook:nelson | Nelson & Couto 5e Ch6 | Normal PaCO2 35-45 mmHg
ARTERIAL_PCO2_NORMAL = 40.0                       # 正常动脉血CO2分压 mmHg
ARTERIAL_SATURATION_NORMAL = 0.97                 # 正常血氧饱和度
# REF: textbook:guyton | Guyton 14e Ch31 | O2 capacity ≈ 20 mL O2/100mL blood
BLOOD_O2_CAPACITY_ML_O2_PER_100ML = 20.0          # 100mL血液携氧量 mL O2/100mL blood

# 肺扩散系数 (mL O2/min/mmHg)
LUNG_DIFFUSION_COEFFICIENT = 25.0

# --- 血液化学 ---
HCO3_EXTRACELLULAR_MEQ_L = 24.0                    # 细胞外 HCO₃⁻ mEq/L
HCO3_INTRACELLULAR_MEQ_L = 12.0                    # 细胞内 HCO₃⁻ mEq/L
PLASMA_COLLOID_OSMOTIC_MMHG = 25.0                # 血浆胶体渗透压 πc

# --- 泌尿系统 ---
PLASMA_SODIUM_MEQ_L = 145.0                       # 血浆钠离子 mEq/L
TUBULAR_WATER_REABSORPTION = 0.99                 # 99% 的滤过水被重吸收

# --- 血液系统 ---
PLASMA_VOLUME_FRACTION = 0.55                     # 血浆占总血容量比例
BASELINE_LACTATE = 1.0                            # 基础血乳酸 mmol/L

# --- 调节系统 ---
SYMPATHETIC_BASELINE = 0.3                        # 交感神经基线活性 (0-1)

# --- 内分泌系统 (犬科正常基线) ---
# 甲状腺轴
# REF: textbook:nelson | Nelson & Couto 5e Ch44 | Canine total T3 normal 30-80 ng/dL
BASELINE_T3_NG_DL = 100.0                         # 正常犬 T3 ng/dL
# REF: textbook:nelson | Nelson & Couto 5e Ch44 | Canine total T4 normal 1-4 ug/dL
BASELINE_T4_UG_DL = 1.5                           # 正常犬 T4 ug/dL
THYROID_T3_T4_RATIO = 0.1                         # T4→T3 转换率
METABOLIC_RATE_MIN = 0.5                          # 甲减时代谢率下限
METABOLIC_RATE_MAX = 2.0                          # 甲亢时代谢率上限
METABOLIC_RATE_NORMAL = 1.0                       # 正常代谢率
THYROID_TAU_SEC = 3600.0                          # T3 转换时间常数 (1h)

# 胰腺轴
BASELINE_INSULIN_UU_ML = 12.0                     # 正常空腹胰岛素 uU/mL
BASELINE_GLUCAGON_PG_ML = 80.0                   # 正常空腹胰高血糖素 pg/mL
GLUCOSE_EUGLYCEMIA_LOW = 3.5                      # 血糖正常下限 mmol/L
GLUCOSE_EUGLYCEMIA_HIGH = 6.0                     # 血糖正常上限 mmol/L
GLUCAGON_HYPOGLYCEMIA_THRESHOLD = 3.5            # 低血糖刺激胰高血糖素分泌阈值
INSULIN_HYPERGLYCEMIA_THRESHOLD = 5.5             # 高血糖刺激胰岛素分泌阈值（从6.0降低以提高敏感性）
PANCREATIC_RESPONSE_TAU_SEC = 300.0               # 胰岛素分泌响应时间常数 (5min)

# 肾上腺轴
# REF: textbook:nelson | Nelson & Couto 5e Ch44 | Baseline cortisol 2-10 ug/dL (resting)
BASELINE_CORTISOL_UG_DL = 5.0                     # 正常犬皮质醇 ug/dL
CORTISOL_STRESS_MAX = 25.0                        # 最大应激皮质醇 ug/dL
# REF: textbook:guyton | Guyton 14e Ch24 | Basal plasma epinephrine ~30 pg/mL
BASELINE_EPINEPHRINE_PG_ML = 30.0                # 正常血浆肾上腺素 pg/mL
# REF: textbook:guyton | Guyton 14e Ch24 | Basal plasma norepinephrine ~100 pg/mL
BASELINE_NOREPINEPHRINE_PG_ML = 100.0             # 正常血浆去甲肾上腺素 pg/mL
HPA_TAU_SEC = 900.0                               # HPA轴响应时间常数 (15min)
CORTISOL_HALF_LIFE_SEC = 3600.0                   # 皮质醇半衰期 ≈ 60-90min
CORTISOL_TAU_SEC = 900.0                          # 皮质醇响应时间常数

# 甲状旁腺轴
BASELINE_PTH_PG_ML = 30.0                        # 正常犬 PTH pg/mL
BASELINE_CALCIUM_MG_DL = 10.0                    # 正常血钙 mg/dL
BASELINE_PHOSPHATE_MG_DL = 4.0                   # 正常血磷 mg/dL
CALCIUM_NORMAL_LOW = 9.0                          # 血钙临界下限 mg/dL
CALCIUM_NORMAL_HIGH = 11.5                       # 血钙临界上限 mg/dL
PTH_CALCIUM_SENSITIVITY = 2.0                    # PTH 对钙变化的响应系数
PTH_TAU_SEC = 120.0                              # PTH 分泌响应时间常数

# 生长轴
BASELINE_GH_NG_ML = 2.0                          # 正常生长激素 ng/mL
BASELINE_IGF1_NMOL_L = 10.0                      # 正常 IGF-1 nmol/L
GROWTH_TAU_SEC = 7200.0                          # IGF-1 响应时间常数 (2h)

# --- 毒理学参数 ---
# 基于 Liu et al. (1993) JACC 21:260-268
# 可卡因犬实验: 3 mg/kg IV, 心脏抑制短暂(5-10 min), 外周血管收缩持续(≥30 min)
COCAINE_DOSE_MG_KG = 3.0                          # 标准可卡因 IV 剂量 mg/kg
COCAINE_T_DECAY_MIN = 5.0                         # 心脏抑制时间常数 τ
COCAINE_MAX_CONTRACTILITY_DROP = 0.19             # ESPVR 最大下降幅度 ≈ 19%
COCAINE_SVR_PEAK_FACTOR = 2.0                     # SVR 最大升高倍数
COCAINE_SVR_T_DECAY_MIN = 30.0                    # 血管收缩时间常数 τ
COCAINE_LD50_DOG_MG_KG = 60.0                     # 犬 LD50 ≈ 60 mg/kg

# --- 生命周期默认年龄 ---
# 成年犬默认年龄 1095 天（~3 年）→ LifecyclePhase.MATURE，growth_factor≈1.0
# 幼犬（age_days=0）的 organ_multiplier=0.1，会将所有参数缩放到 10%
DEFAULT_AGE_DAYS = 1095.0                         # 成年犬默认年龄（天）

# --- ODE 求解器参数 ---
DT_SECONDS = 0.1                                  # 积分时间步长（秒）
SIMULATION_STEP_MS = 100                          # 仿真记录步长（毫秒）
T_MAX_MINUTES = 10                                # 默认仿真时长（分钟）
