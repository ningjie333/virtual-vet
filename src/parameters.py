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
HEART_RATE_REST_BPM = 85                          # 静息心率 bpm
HEART_RATE_STRESS_BPM = 180                       # 应激心率上限 bpm

# 血管阻力 (mmHg·s/mL = PRU)
# 推导: MAP = 60 + CO × R / 60
# 正常 MAP=100, CO=1700 mL/min → R = 1.41
SYSTEMIC_VASCULAR_RESISTANCE = 1.41               # 体循环血管阻力
PULMONARY_VASCULAR_RESISTANCE = 0.18              # 肺循环血管阻力

# 顺应性 (mL/mmHg)
ARTERIAL_COMPLIANCE = 1.5                         # 动脉顺应性
VENOUS_COMPLIANCE = 30.0                          # 静脉顺应性
PULMONARY_COMPLIANCE = 4.0                        # 肺顺应性

# 正常稳态值
MEAN_ARTERIAL_PRESSURE_MMHG = 100.0               # 平均动脉压 mmHg
CENTRAL_VENOUS_PRESSURE_MMHG = 4.0                # 中心静脉压 mmHg
PULMONARY_ARTERIAL_PRESSURE_MMHG = 15.0           # 肺动脉压 mmHg

# --- 呼吸系统 ---
RESPIRATORY_RATE_REST = 18                        # 静息呼吸频率 /min
RESPIRATORY_RATE_STRESS = 40                      # 应激呼吸频率 /min

# 气体分压 (mmHg)
ATMOSPHERIC_PO2 = 150.0                           # 大气氧分压（海平面）
ATMOSPHERIC_PCO2 = 0.0                            # 大气CO2分压
ALVEOLAR_PO2_NORMAL = 100.0                       # 正常肺泡氧分压
ALVEOLAR_PCO2_NORMAL = 40.0                       # 正常肺泡CO2分压

# 动脉血气
ARTERIAL_PO2_NORMAL = 95.0                        # 正常动脉血氧分压 mmHg
ARTERIAL_PCO2_NORMAL = 40.0                       # 正常动脉血CO2分压 mmHg
ARTERIAL_SATURATION_NORMAL = 0.97                 # 正常血氧饱和度
BLOOD_O2_CAPACITY_ML_O2_PER_100ML = 20.0          # 100mL血液携氧量 mL O2/100mL blood

# 肺扩散系数 (mL O2/min/mmHg)
LUNG_DIFFUSION_COEFFICIENT = 25.0

# --- 泌尿系统 ---
PLASMA_SODIUM_MEQ_L = 145.0                       # 血浆钠离子 mEq/L
TUBULAR_WATER_REABSORPTION = 0.99                 # 99% 的滤过水被重吸收

# --- 血液系统 ---
PLASMA_VOLUME_FRACTION = 0.55                     # 血浆占总血容量比例
BASELINE_LACTATE = 1.0                            # 基础血乳酸 mmol/L

# --- 调节系统 ---
SYMPATHETIC_BASELINE = 0.3                        # 交感神经基线活性 (0-1)

# --- 毒理学参数 ---
# 基于 Liu et al. (1993) JACC 21:260-268
# 可卡因犬实验: 3 mg/kg IV, 心脏抑制短暂(5-10 min), 外周血管收缩持续(≥30 min)
COCAINE_DOSE_MG_KG = 3.0                          # 标准可卡因 IV 剂量 mg/kg
COCAINE_T_DECAY_MIN = 5.0                         # 心脏抑制时间常数 τ
COCAINE_MAX_CONTRACTILITY_DROP = 0.19             # ESPVR 最大下降幅度 ≈ 19%
COCAINE_SVR_PEAK_FACTOR = 2.0                     # SVR 最大升高倍数
COCAINE_SVR_T_DECAY_MIN = 30.0                    # 血管收缩时间常数 τ
COCAINE_LD50_DOG_MG_KG = 60.0                     # 犬 LD50 ≈ 60 mg/kg

# --- ODE 求解器参数 ---
DT_SECONDS = 0.1                                  # 积分时间步长（秒）
SIMULATION_STEP_MS = 100                          # 仿真记录步长（毫秒）
T_MAX_MINUTES = 10                                # 默认仿真时长（分钟）
