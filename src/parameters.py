# Virtual Creature - Physiological Parameters
# 基于犬科动物正常生理值（Canine Physiology）
#
# 参数分两类:
#   A类 (函数): 随体重变化的参数，调用时传入 weight_kg
#   B类 (常量): 通用生理常数，与体重无关

# ============================================================
# A类: 随体重变化的参数 (函数)
# ============================================================

# ── Species-aware blood volume (mL/kg) ──────────────────────────────────
# Q3 (2026-06-14): 犬 86 / 猫 55 / 马 76 来自 severity_design_proposal.md §方向二
# 原总血容量函数固定 86.0 mL/kg（犬），猫/马需物种感知
BLOOD_VOLUME_ML_KG_CANINE = 86.0    # 犬 80-90, 取 86 (Guyton 14e Ch20)
BLOOD_VOLUME_ML_KG_FELINE = 55.0    # 猫 40-70, 取 55 (Nelson & Couto 5e Ch22)
BLOOD_VOLUME_ML_KG_EQUINE = 76.0    # 马 70-100, 取 76 (Merck Vet Manual)

# ── Species fever threshold (°C) ────────────────────────────────────────
# Q3 (2026-06-14): 犬 39.2 / 猫 39.5 / 马 38.5
# REF: Merck Vet Manual | Canine fever > 39.2°C (102.5°F)
# REF: Merck Vet Manual | Feline fever > 39.5°C (103.1°F)
# REF: Merck Vet Manual | Equine fever > 38.5°C (101.3°F)
FEVER_THRESHOLD_C_CANINE = 39.2     # 犬发热阈值 °C
FEVER_THRESHOLD_C_FELINE = 39.5     # 猫发热阈值 °C
FEVER_THRESHOLD_C_EQUINE = 38.5     # 马发热阈值 °C


# ── 3-way species lookup helpers ────────────────────────────────────────
# Q3 (2026-06-14): 统一 canine/feline/equine 的 3-way lookup 函数。
# 照 base_DO2_normal_ml_min 的 Hb if-else 范本，但用 canine/feline/equine
# 字符串（与 engine species 一致），不用 dog/cat（那是历史遗留）。
#
# 使用方式:
#   from src.parameters import species_hr, species_rr, species_paco2, fever_threshold_c
#   hr = species_hr("canine")  # 85
#   rr = species_rr("feline", stress=True)  # 50


def species_hr(species: str = "canine", stress: bool = False) -> float:
    """按物种返回静息或应激心率 (bpm)。"""
    if stress:
        if species == "feline":
            return HEART_RATE_STRESS_BPM_FELINE
        if species == "equine":
            return HEART_RATE_STRESS_BPM_EQUINE
        return HEART_RATE_STRESS_BPM_CANINE
    if species == "feline":
        return HEART_RATE_REST_BPM_FELINE
    if species == "equine":
        return HEART_RATE_REST_BPM_EQUINE
    return HEART_RATE_REST_BPM_CANINE


def species_rr(species: str = "canine", stress: bool = False) -> float:
    """按物种返回静息或应激呼吸频率 (/min)。"""
    if stress:
        if species == "feline":
            return RESPIRATORY_RATE_STRESS_FELINE
        if species == "equine":
            return RESPIRATORY_RATE_STRESS_EQUINE
        return RESPIRATORY_RATE_STRESS_CANINE
    if species == "feline":
        return RESPIRATORY_RATE_REST_FELINE
    if species == "equine":
        return RESPIRATORY_RATE_REST_EQUINE
    return RESPIRATORY_RATE_REST_CANINE


def species_paco2(species: str = "canine") -> float:
    """按物种返回正常 PaCO2 (mmHg)。"""
    if species == "feline":
        return ARTERIAL_PCO2_NORMAL_FELINE
    if species == "equine":
        return ARTERIAL_PCO2_NORMAL_EQUINE
    return ARTERIAL_PCO2_NORMAL_CANINE


def fever_threshold_c(species: str = "canine") -> float:
    """按物种返回发热阈值 (°C)。"""
    if species == "feline":
        return FEVER_THRESHOLD_C_FELINE
    if species == "equine":
        return FEVER_THRESHOLD_C_EQUINE
    return FEVER_THRESHOLD_C_CANINE


def total_blood_volume_ml(weight_kg: float, species: str = "canine") -> float:
    """总血容量 (mL), 按物种校准。

    Q3 (2026-06-14): 从固定 86 mL/kg (犬 only) 升级为 3-species lookup。
    向后兼容: 不传 species 时默认 canine。
    """
    if species == "feline":
        return BLOOD_VOLUME_ML_KG_FELINE * weight_kg
    if species == "equine":
        return BLOOD_VOLUME_ML_KG_EQUINE * weight_kg
    return BLOOD_VOLUME_ML_KG_CANINE * weight_kg

def stroke_volume_ml(weight_kg: float) -> float:
    """犬每搏输出量: 1.0-1.5 mL/kg, 取 1.0 (危重基准线)"""
    return 1.0 * weight_kg

def stroke_volume_ml_feline(weight_kg: float) -> float:
    """猫每搏输出量: 0.5-0.6 mL/kg（猫是"高心率+低每搏量"模式）"""
    return 0.55 * weight_kg

def stroke_volume_ml_equine(weight_kg: float) -> float:
    """马每搏输出量: 1.7-2.4 mL/kg（马是"低心率+高每搏量"模式）"""
    return 2.0 * weight_kg

def base_cardiac_output_ml_min(weight_kg: float) -> float:
    """犬基础心输出量: HR × SV"""
    return HEART_RATE_REST_BPM * stroke_volume_ml(weight_kg)

def tidal_volume_ml(weight_kg: float) -> float:
    """犬潮气量: 临床标准 10-12 mL/kg, 取 12"""
    return 12.0 * weight_kg

def tidal_volume_ml_feline(weight_kg: float) -> float:
    """猫潮气量: 7-8 mL/kg（猫比犬略低）"""
    return 7.5 * weight_kg

def tidal_volume_ml_equine(weight_kg: float) -> float:
    """马潮气量: 10-12 mL/kg（马是深慢呼吸模式）"""
    return 10.0 * weight_kg

def base_minute_ventilation(weight_kg: float) -> float:
    """犬基础分钟通气量: TV × RR"""
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
HEART_RATE_REST_BPM = 85                          # 犬静息心率 bpm
HEART_RATE_REST_BPM_CANINE = 85                   # 犬显式别名 (Q3 对齐 3-way lookup)
# REF: Ninomiya 1988 PMID:3236570 | Cat resting HR 164±10 bpm; UC Davis CVET 100-140
HEART_RATE_REST_BPM_FELINE = 150                  # 猫静息心率 bpm (120-180 范围内)
# REF: textbook:nelson | Nelson & Couto 5e Ch22 | Estimated maximum ~180 bpm
HEART_RATE_STRESS_BPM = 180                       # 犬应激心率上限 bpm
HEART_RATE_STRESS_BPM_CANINE = 180                # 犬显式别名 (Q3)
HEART_RATE_STRESS_BPM_FELINE = 250                # 猫应激心率上限 bpm
# REF: Merck Vet Manual; Reed & Bayly Equine Internal Medicine | Horse resting HR 28-44 bpm
HEART_RATE_REST_BPM_EQUINE = 35                   # 马静息心率 bpm (28-44 范围内)
# REF: Thomas & Fregin 1990 PMID:9259809 | Horse max exercise HR 220-240 bpm
HEART_RATE_STRESS_BPM_EQUINE = 70                 # 马应激心率上限 bpm (轻度应激)

# H7: 心率硬限制（统一两处 clamp）
HEART_RATE_HARD_MIN = 5.0
HEART_RATE_HARD_MAX = 250.0

# 血管阻力 (mmHg·s/mL = PRU)
# REF: textbook:guyton | Guyton 14e Ch26 | TPR ≈ 1.4 mmHg·s/mL in resting dog
# 推导: MAP = 60 + CO × R / 60
# 正常 MAP=100, CO=1700 mL/min → R = 1.41
SYSTEMIC_VASCULAR_RESISTANCE = 1.41               # 体循环血管阻力
# REF: textbook:guyton | Guyton 14e Ch26 | PVR ≈ 0.18 mmHg·s/mL
PULMONARY_VASCULAR_RESISTANCE = 0.18              # 肺循环血管阻力

# SVR baroreflex 响应时间常数 — Fix-B Phase 1 (2026-06-14, RAAS 振荡 #4):
# Euler 路径 heart._baroreceptor_feedback 的 SVR 赋值此前是瞬时代数覆盖（无 τ），
# 与 Radau 路径 derivatives() 的 alpha_svr=0.1 (τ≈10s) 不对称，是 MAP 周期-2
# 极限环的核心驱动。此常量让 Euler 对齐 Radau 的 τ。生理上动脉压力反射的 SVR
# 分量响应在 ~10s 量级（比 HR 的交感分量 τ=5s 略慢，因 arteriole 平滑肌惯性）。
# REF: textbook:guyton | Guyton 14e Ch18 | Baroreflex SVR component ~10s
SVR_BAROREFLEX_TAU_SEC = 10.0                     # SVR 压力反射一阶滞后 τ (s)

# RAAS 响应时间常数 — Fix-B Phase 2 (2026-06-14, RAAS 振荡 #4):
# kidney._apply_RAAS 的 renin_activity 此前是瞬时代数赋值（无 τ），与 heart SVR 滞后
# 叠加形成第二条无阻尼环路。真实 RAAS 响应分钟级（renin 释放 → ACE → angiotensin 效应）。
# REF: textbook:hall | Hall 2016 | RAAS effector response ~minutes
TAU_RAAS = 120.0                                # RAAS 肾素活性一阶滞后 τ (s)

# ── GFR Starling 模型系数 ───────────────────────────────────────────────
# P2.2: 原在 kidney.py 模块级定义，集中到此处管理
GFR_PGC_MAP_RATIO = 0.6       # 肾小球毛细血管压 / MAP 比值
GFR_PBS_CVP_OFFSET = 10.0     # 鲍曼囊压 = CVP + 10 mmHg
GFR_KF = 3.0                  # 肾小球超滤系数 mL/min/mmHg

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
RESPIRATORY_RATE_REST = 18                        # 犬静息呼吸频率 /min
RESPIRATORY_RATE_REST_CANINE = 18                 # 犬显式别名 (Q3)
# REF: Dijkstra 2018 PMID:29680402 | Cat resting RR 20-30 /min; UC Davis CVET 20-30
RESPIRATORY_RATE_REST_FELINE = 25                 # 猫静息呼吸频率 /min
# REF: Merck Vet Manual; BMC Vet Res 2016 | Horse resting RR 8-16 /min, typical ~12
RESPIRATORY_RATE_REST_EQUINE = 12                 # 马静息呼吸频率 /min
RESPIRATORY_RATE_STRESS = 40                      # 犬应激呼吸频率 /min
RESPIRATORY_RATE_STRESS_CANINE = 40               # 犬显式别名 (Q3)
RESPIRATORY_RATE_STRESS_FELINE = 50               # 猫应激呼吸频率 /min
# REF: Fregin 1990 | Horse exercise RR 60-120 /min, 轻度应激取 60
RESPIRATORY_RATE_STRESS_EQUINE = 60               # 马应激呼吸频率 /min

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
ARTERIAL_PO2_NORMAL = 95.0                        # 犬正常动脉血氧分压 mmHg
# REF: textbook:nelson | Nelson & Couto 5e Ch6 | Normal PaCO2 35-45 mmHg
ARTERIAL_PCO2_NORMAL = 40.0                       # 犬正常动脉血CO2分压 mmHg
ARTERIAL_PCO2_NORMAL_CANINE = 40.0                # 犬显式别名 (Q3)
# REF: Merck Veterinary Manual | Cat PaCO2 29-42 mmHg
ARTERIAL_PCO2_NORMAL_FELINE = 35.0                # 猫正常动脉血CO2分压 mmHg
# REF: Sherlock et al. 2019 PMID:31471125 (n=139) | Horse PaCO2 36.3-54.0, median 45.2
ARTERIAL_PCO2_NORMAL_EQUINE = 42.0                # 马正常动脉血CO2分压 mmHg
ARTERIAL_SATURATION_NORMAL = 0.97                 # 正常血氧饱和度
# REF: textbook:guyton | Guyton 14e Ch31 | O2 capacity ≈ 20 mL O2/100mL blood
BLOOD_O2_CAPACITY_ML_O2_PER_100ML = 20.0          # 100mL血液携氧量 mL O2/100mL blood

# 肺扩散系数 (mL O2/min/mmHg)
LUNG_DIFFUSION_COEFFICIENT = 25.0

# --- 血液化学 ---
HCO3_EXTRACELLULAR_MEQ_L = 24.0                    # 细胞外 HCO₃⁻ mEq/L
HCO3_INTRACELLULAR_MEQ_L = 12.0                    # 细胞内 HCO₃⁻ mEq/L
PLASMA_COLLOID_OSMOTIC_MMHG = 25.0                # 血浆胶体渗透压 πc

# 血红蛋白浓度 (g/dL)
# REF: textbook:nelson | Nelson & Couto 5e Ch22 | Canine normal Hb 13-17 g/dL (取 14.0)
NORMAL_HB_CANINE = 14.0
# REF: textbook:nelson | Nelson & Couto 5e Ch22 | Feline normal Hb 9-15 g/dL (取 12.0)
NORMAL_HB_FELINE = 12.0
# REF: Merck Vet Manual | Equine normal Hb 11-15 g/dL (取 13.0)
NORMAL_HB_EQUINE = 13.0

# Hüfner 常数 (mL O₂/g Hb)
HUFNER_CONSTANT = 1.34

# DO2 基准（用于临床解释层 ratio 计算）
# DO2_normal = CO_normal × Hb × SaO2 × Hüfner
# REF: textbook:guyton | Guyton 14e Ch31 | O2 capacity ≈ 20 mL O2/100mL blood → 1.34 × Hb


def base_DO2_normal_ml_min(weight_kg: float, species: str = "dog") -> float:
    """正常 DO2（mL O₂/min），用于 ratio 计算。DO2 = CO × Hb × SaO2 × 1.34"""
    co_normal = base_cardiac_output_ml_min(weight_kg)
    hb = NORMAL_HB_CANINE if species == "dog" else NORMAL_HB_FELINE if species == "cat" else NORMAL_HB_EQUINE
    return (co_normal / 1000.0) * hb * ARTERIAL_SATURATION_NORMAL * HUFNER_CONSTANT

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
DT_SECONDS = 0.5                                  # 积分时间步长（秒）—— 阶段 1 已消除 heart.py 的 dt 敏感隐式假设（SV/MAP 低通滤波改用 first_order_lag 精确指数解），从 0.1 提升到 0.5 可获 5x 性能提升且连续轨迹等价。注：test_solver_drift 硬编码 dt=0.1 不受此参数影响，其 GFR Euler/Radau 5.71% 偏差为预先存在问题（git stash 验证）
SIMULATION_STEP_MS = 100                          # 仿真记录步长（毫秒）
T_MAX_MINUTES = 10                                # 默认仿真时长（分钟）
