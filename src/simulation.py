"""
Simulation Engine - 多系统耦合仿真引擎
整合心脏、肺部、肾脏模块，实现器官间耦合
"""

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
from blood import BloodCompartment
from heart import HeartModule
from lung import LungModule
from kidney import KidneyModule
from toxicology import ToxicologyModule
from organ_health import OrganHealthTracker
from fluid import FluidCompartment, HendersonHasselbalch
from gut import GutModule
from liver import LiverModule
from endocrine import EndocrineModule
from neuro import NeuroModule
from immune import ImmuneModule
from coagulation import CoagulationModule
from lymphatic import LymphaticModule
from lifecycle import LifecycleEngine
from src.organs.coupling import CouplingEngine, OrganContext, PhysiologicalSignal
from parameters import (
    DT_SECONDS, SIMULATION_STEP_MS, T_MAX_MINUTES,
    PLASMA_VOLUME_FRACTION,
    total_blood_volume_ml, stroke_volume_ml, stroke_volume_ml_feline, stroke_volume_ml_equine,
    base_cardiac_output_ml_min,
    tidal_volume_ml, tidal_volume_ml_feline, tidal_volume_ml_equine, base_minute_ventilation,
    renal_blood_flow_ml_min, gfr_ml_min, baseline_urine_output_ml_min,
    DEFAULT_AGE_DAYS,
    HEART_RATE_REST_BPM, HEART_RATE_REST_BPM_FELINE, HEART_RATE_REST_BPM_EQUINE,
    HEART_RATE_STRESS_BPM, HEART_RATE_STRESS_BPM_FELINE, HEART_RATE_STRESS_BPM_EQUINE,
    ARTERIAL_PCO2_NORMAL, ARTERIAL_PCO2_NORMAL_FELINE, ARTERIAL_PCO2_NORMAL_EQUINE,
    RESPIRATORY_RATE_REST, RESPIRATORY_RATE_REST_FELINE, RESPIRATORY_RATE_REST_EQUINE,
)

logger = logging.getLogger(__name__)


# ── FactorCommand 指令结构体 ─────────────────────────────────────────────────

@dataclass(frozen=True)
class FactorCommand:
    """
    单条因子指令：声明式地描述"对哪个参数执行什么操作"。

    Attributes:
        target: 参数路径，格式 "module.attr"（如 "heart.heart_rate"）
        op: 操作类型 — "multiply"（乘因子）/ "add"（加偏移）/ "set"（设绝对值）
        value: 操作数值
    """
    target: str
    op: Literal["multiply", "add", "set"]
    value: float


# ── 参数路径映射表 ───────────────────────────────────────────────────────────
# 所有可被子系统（疾病、药物、事件）修改的引擎参数，必须在此注册。
# 格式: "module.attr" → (engine_module_name, attribute_name)

_PARAM_PATHS: dict[str, tuple[str, str]] = {
    # 心脏
    "heart.heart_rate":           ("heart", "heart_rate"),
    "heart.contractility_factor": ("heart", "contractility_factor"),
    "heart.SVR":                  ("heart", "SVR"),
    "heart.MAP":                  ("heart", "mean_arterial_pressure"),
    "heart.CVP":                  ("heart", "central_venous_pressure"),
    "heart.blood_volume":         ("heart", "circulating_volume_ml"),
    "heart.stroke_volume":        ("heart", "stroke_volume"),
    # 肺
    "lung.diffusion_coefficient": ("lung", "diffusion_coefficient"),
    "lung.PaO2":                  ("lung", "alveolar_PO2"),
    "lung.PaCO2":                 ("lung", "alveolar_PCO2"),
    "lung.VQ_ratio":              ("lung", "VQ_ratio"),
    "lung.respiratory_rate":      ("lung", "respiratory_rate"),
    # 肾脏
    "kidney.GFR":                    ("kidney", "GFR"),
    "kidney.urine_output":           ("kidney", "urine_output"),
    "kidney.renal_blood_flow":       ("kidney", "renal_blood_flow"),
    "kidney._disease_gfr_multiplier": ("kidney", "_disease_gfr_multiplier"),
    # 血液
    "blood.sodium_mEq_L":         ("blood", "sodium_mEq_L"),
    "blood.potassium":            ("blood", "potassium_mEq_L"),
    "blood.pH":                   ("blood", "arterial_pH"),
    "blood.temperature":          ("blood", "core_temperature_C"),
    "blood.BUN":                  ("blood", "bun_mg_dL"),
    "blood.HCO3":                 ("fluid", "vascular_hco3_meq_l"),
    "blood.glucose":              ("blood", "glucose_mmol_L"),
    "blood.lactate":              ("blood", "lactate_mmol_L"),
    "blood.creatinine":           ("blood", "creatinine_mg_dL"),
    "blood.red_cell_volume_ml":   ("blood", "red_cell_volume_ml"),
    "blood.bilirubin_mg_dL":      ("blood", "bilirubin_mg_dL"),
    "blood.ketone_mmol_L":        ("blood", "ketone_mmol_L"),
    "blood.PLT":                  ("blood", "PLT"),
    # Liver/gut blood markers
    "blood.ALT":                  ("blood", "ALT_U_L"),
    "blood.AST":                  ("blood", "AST_U_L"),
    "blood.ALP":                  ("blood", "ALP_U_L"),
    "blood.GGT":                  ("blood", "GGT_U_L"),
    "blood.albumin":              ("blood", "albumin_g_dL"),
    "blood.ammonia":              ("blood", "ammonia_umol_L"),
    "blood.bile_acids":           ("blood", "bile_acids_umol_L"),
    "blood.amino_acids":         ("blood", "amino_acids_g_L"),
    "blood.fatty_acids":         ("blood", "fatty_acids_mmol_L"),
    # Gut
    "gut.motility":               ("gut", "gut_motility"),
    "gut.barrier_integrity":      ("gut", "barrier_integrity"),
    "gut.microbiome_activity":    ("gut", "microbiome_activity"),
    # Liver
    "liver.metabolic_activity":   ("liver", "metabolic_activity"),
    "liver.detox_capacity":       ("liver", "detox_capacity"),
    "liver.cyp450_activity":      ("liver", "cyp450_activity"),
    "liver.glycogen_fraction":   ("liver", "glycogen_fraction"),
    "liver.bilirubin_conjugation": ("liver", "bilirubin_conjugation"),
    # Endocrine
    "endocrine.T3_factor":          ("endocrine", "T3_factor"),
    "endocrine.T4_factor":          ("endocrine", "T4_ug_dL"),
    "endocrine.metabolic_rate":     ("endocrine", "metabolic_rate"),
    "endocrine.T3_ng_dL":           ("endocrine", "T3_ng_dL"),
    "endocrine.T4_ug_dL":           ("endocrine", "T4_ug_dL"),
    "endocrine.insulin_factor":      ("endocrine", "insulin_factor"),
    "endocrine.glucagon_factor":    ("endocrine", "glucagon_factor"),
    "endocrine.insulin_uU_mL":       ("endocrine", "insulin_uU_mL"),
    "endocrine.glucagon_pg_mL":     ("endocrine", "glucagon_pg_mL"),
    "endocrine.cortisol_factor":     ("endocrine", "cortisol_factor"),
    "endocrine.cortisol_ug_dL":     ("endocrine", "cortisol_ug_dL"),
    "endocrine.HPA_axis":           ("endocrine", "HPA_axis"),
    "endocrine.epinephrine_pg_mL":  ("endocrine", "epinephrine_pg_mL"),
    "endocrine.norepinephrine_pg_mL": ("endocrine", "norepinephrine_pg_mL"),
    "endocrine.PTH_pg_mL":          ("endocrine", "PTH_pg_mL"),
    "endocrine.calcium_mg_dL":       ("endocrine", "calcium_mg_dL"),
    "endocrine.phosphate_mg_dL":    ("endocrine", "phosphate_mg_dL"),
    "endocrine.calcium_factor":     ("endocrine", "calcium_factor"),
    "endocrine.GH_ng_mL":           ("endocrine", "GH_ng_mL"),
    "endocrine.IGF1_nmol_L":        ("endocrine", "IGF1_nmol_L"),
    "endocrine.growth_factor":      ("endocrine", "growth_factor"),
    # Neuro
    "neuro.sympathetic_tone":        ("neuro", "sympathetic_tone"),
    "neuro.parasympathetic_tone":     ("neuro", "parasympathetic_tone"),
    "neuro.consciousness":           ("neuro", "consciousness"),
    "neuro.seizure":                 ("neuro", "seizure"),
    "neuro.pain_level":              ("neuro", "pain_level"),
    "neuro.chemoreceptor_drive":     ("neuro", "chemoreceptor_drive"),
    # Immune
    "immune.cytokine_level":         ("immune", "cytokine_level"),
    "immune.wbc_count":              ("immune", "wbc_count"),
    "immune.crp_level":             ("immune", "crp_level"),
    "immune.acute_phase_response":   ("immune", "acute_phase_response"),
    "immune.immune_suppression":     ("immune", "immune_suppression"),
    "immune.coagulation_state":      ("immune", "coagulation_state"),
    # Coagulation
    "coag.PT_sec":               ("blood", "PT_sec"),
    "blood.PT_sec":             ("blood", "PT_sec"),
    "coag.aPTT_sec":             ("blood", "aPTT_sec"),
    "coag.fibrinogen_mg_dL":     ("blood", "fibrinogen_mg_dL"),
    "coag.factor_VII":           ("coagulation", "factor_VII"),
    "coag.coagulation_state":    ("coagulation", "coagulation_state"),
    # Lymphatic
    "lymph.splenic_reserve_mL":  ("blood", "splenic_reserve_mL"),
    "blood.splenic_reserve_mL":  ("blood", "splenic_reserve_mL"),  # disease outputs use blood.*
    "lymph.lymph_flow":          ("lymphatic", "lymph_flow_rate"),
    "lymph.interstitial_fluid":  ("blood", "interstitial_fluid_mL"),
    # Coupling engine targets (multi-organ signals)
    "blood.arterial_PO2_mmHg":  ("blood", "arterial_PO2_mmHg"),
    "blood.BUN":                ("blood", "bun_mg_dL"),
    "blood.arterial_PCO2_mmHg": ("blood", "arterial_PCO2_mmHg"),
    "lung.diffusion_coefficient": ("lung", "diffusion_coefficient"),
    "lung.respiratory_rate":    ("lung", "respiratory_rate"),
}


# ── CONNECTIONS 表 — 统一 ODE 系统的模块间数据路由 ──────────────────────────
# 格式: { (from_module, from_var): [(to_module, to_var), ...], ... }
# 用于 _unified_rhs 中，将上一时间步的 outputs 路由为当前时间步的 inputs
# 采用半隐式耦合：模块在 rhs(t,y) 调用时使用上一 rhs 调用的 outputs 作为输入

CONNECTIONS: dict[tuple[str, str], list[tuple[str, str]]] = {
    # Heart → kidney, fluid, neuro
    ("heart", "cardiac_output"):    [("kidney", "co_input"), ("lung", "co_input"), ("gut", "co_input")],
    ("heart", "MAP"):                [("kidney", "map_input"), ("fluid", "map_input"), ("neuro", "map_input")],
    ("heart", "CVP"):               [("kidney", "cvp_input")],
    ("heart", "blood_volume_ratio"): [("fluid", "blood_volume_ratio")],

    # Lung → blood, neuro
    ("lung", "arterial_PO2_mmHg"):  [("blood", "arterial_PO2"), ("neuro", "PO2")],
    ("lung", "arterial_PCO2_mmHg"): [("blood", "arterial_PCO2"), ("neuro", "PCO2")],
    ("lung", "arterial_saturation"): [("blood", "arterial_saturation")],
    ("lung", "arterial_pH"):         [("blood", "arterial_pH")],
    ("lung", "respiratory_rate"):   [("neuro", "lung_rr")],

    # Blood → kidney, neuro, endocrine, immune
    ("blood", "potassium_mEq_L"):    [("kidney", "blood_K"), ("endocrine", "K"), ("heart", "potassium_mEq_L")],
    ("blood", "sodium_mEq_L"):      [("kidney", "blood_Na")],
    ("blood", "glucose_mmol_L"):    [("kidney", "blood_glucose"), ("endocrine", "glucose")],
    ("blood", "arterial_pH"):        [("kidney", "blood_pH"), ("heart", "arterial_pH")],
    ("blood", "arterial_PO2_mmHg"): [("neuro", "PO2")],
    ("blood", "arterial_PCO2_mmHg"): [("neuro", "PCO2")],

    # Kidney → fluid, blood
    ("kidney", "ADH_level"):         [("fluid", "ADH")],
    ("kidney", "urine_output_mL_min"): [("fluid", "urine_output")],
    ("kidney", "angiotensin_II"):    [("fluid", "RAAS_activity")],
    ("kidney", "blood_volume_loss_rate_mL_min"): [("blood", "urine_loss")],

    # Fluid → heart, blood, lymphatic
    ("fluid", "V_vascular_mL"):      [("heart", "preload_volume")],
    ("fluid", "V_isf_mL"):           [("lymphatic", "isf_input")],

    # Endocrine → immune, liver, heart, kidney
    ("endocrine", "cortisol_ug_dL"): [("immune", "endocrine_cortisol")],
    ("endocrine", "T3_factor"):     [("heart", "T3")],
    ("endocrine", "insulin_uU_mL"):  [("liver", "insulin")],
    ("endocrine", "glucagon_pg_mL"): [("liver", "glucagon")],
    ("endocrine", "PTH_pg_mL"):      [("kidney", "PTH")],
    ("endocrine", "calcium_mg_dL"): [("kidney", "calcium")],

    # Neuro → kidney, endocrine, lymphatic
    ("neuro", "pain_level"):         [("endocrine", "pain_stress")],
    ("neuro", "heart_rate_bpm"):     [("lymphatic", "hr_input")],

    # Immune → neuro, liver, coagulation, lymphatic
    ("immune", "cytokine_level"):    [("neuro", "cytokine"), ("coagulation", "immune_cytokine"), ("lymphatic", "cytokine_input"), ("liver", "inflammation")],
    ("immune", "coagulation_state"): [("coagulation", "immune_coagulation_state")],
    ("immune", "wbc_count"):         [("blood", "WBC")],
    ("immune", "capillary_leak_factor"): [("blood", "capillary_leak")],

    # Coagulation → blood, immune
    ("coagulation", "PT_sec"):        [("blood", "PT_sec")],
    ("coagulation", "aPTT_sec"):     [("blood", "aPTT_sec")],
    ("coagulation", "fibrinogen_mg_dL"): [("blood", "fibrinogen_mg_dL")],
    ("coagulation", "coagulation_state"): [("blood", "coagulation_state")],

    # Liver → blood
    ("liver", "metabolic_activity"):  [("coagulation", "liver_health_factor")],
    ("liver", "glucose_output"):      [("blood", "liver_glucose")],
    ("liver", "ammonia_umol_L"):      [("blood", "ammonia_umol_L")],
    ("liver", "albumin_g_dL"):       [("blood", "albumin_g_dL")],
    ("liver", "bilirubin_mg_dL"):    [("blood", "bilirubin_mg_dL")],

    # Gut → liver
    ("gut", "amino_absorption_g_min"): [("liver", "amino_absorption_g_min")],
    ("gut", "portal_flow"):           [("liver", "portal_flow")],
    ("gut", "fat_absorption_active"):  [("lymphatic", "gut_fat_absorption")],

    # Lymphatic → blood
    ("lymphatic", "splenic_reserve_mL"): [("blood", "splenic_reserve_mL")],
    ("lymphatic", "lymph_flow_rate"): [("blood", "lymph_flow_mL_min")],
    ("lymphatic", "interstitial_fluid_mL"): [("blood", "interstitial_fluid_mL")],

    # Disease outputs (from disease.derivatives) → target modules
    # disease.compute_derivatives returns FactorCommand-style outputs
    # routed via CONNECTIONS as a special "disease" module
}


class VirtualCreature:
    """
    虚拟生物体：整合所有器官模块的耦合仿真

    模块耦合关系：
    ┌──────────────────────────────────────────────┐
    │  Heart → CO → 分配到各器官                    │
    │           ↓                                  │
    │  Lung ← CO（肺循环）← 心输出量                  │
    │   ↓↑                                       │
    │  Blood ←→ Gas exchange ←→ Alveolar gas       │
    │   ↓                                         │
    │  Kidney ← CO（RBF = 20% CO）← 心输出量        │
    │   ↓                                         │
    │  Urine output ←→ Fluid balance              │
    │   ↓                                         │
    │  Blood volume ←→ RAAS feedback              │
    └──────────────────────────────────────────────┘
    """

    def __init__(
        self,
        body_weight_kg: float = 20.0,
        species: str = "canine",
        age_days: float = DEFAULT_AGE_DAYS,
        dt: float = None,
        solver: str = "euler",
    ):
        self.w = body_weight_kg
        self.species = species
        self._solver = solver  # "euler" | "radau"

        # 根据物种选择特异性参数
        if species == "feline":
            _hr_rest = HEART_RATE_REST_BPM_FELINE      # 150 bpm
            _hr_stress = HEART_RATE_STRESS_BPM_FELINE  # 250 bpm
            _pco2_normal = ARTERIAL_PCO2_NORMAL_FELINE # 35 mmHg
        elif species == "equine":
            _hr_rest = HEART_RATE_REST_BPM_EQUINE      # 35 bpm
            _hr_stress = HEART_RATE_STRESS_BPM_EQUINE  # 70 bpm
            _pco2_normal = ARTERIAL_PCO2_NORMAL_EQUINE # 42 mmHg
        else:
            _hr_rest = HEART_RATE_REST_BPM              # 85 bpm
            _hr_stress = HEART_RATE_STRESS_BPM          # 180 bpm
            _pco2_normal = ARTERIAL_PCO2_NORMAL         # 40 mmHg

        # 根据实际体重计算 A 类参数（根据物种选择不同函数）
        _tbv = total_blood_volume_ml(body_weight_kg)
        if species == "feline":
            _sv  = stroke_volume_ml_feline(body_weight_kg)   # 猫：0.55 mL/kg
            _tv  = tidal_volume_ml_feline(body_weight_kg)    # 猫：7.5 mL/kg
            _rr  = RESPIRATORY_RATE_REST_FELINE              # 猫：25 /min
        elif species == "equine":
            _sv  = stroke_volume_ml_equine(body_weight_kg)   # 马：2.0 mL/kg
            _tv  = tidal_volume_ml_equine(body_weight_kg)    # 马：10 mL/kg
            _rr  = RESPIRATORY_RATE_REST_EQUINE              # 马：12 /min
        else:
            _sv  = stroke_volume_ml(body_weight_kg)          # 犬：1.0 mL/kg
            _tv  = tidal_volume_ml(body_weight_kg)           # 犬：12 mL/kg
            _rr  = RESPIRATORY_RATE_REST                     # 犬：18 /min
        _co  = _hr_rest * _sv                                # 心输出量 = HR × SV
        _mv  = _tv * _rr                                     # 分钟通气量 = TV × RR
        _rbf = 0.20 * _co                                    # 肾血流量 = 20% CO
        _gfr = gfr_ml_min(body_weight_kg)
        _urine = baseline_urine_output_ml_min(body_weight_kg)

        # 初始化血液隔室（最先创建，所有器官共享）
        self.blood = BloodCompartment(
            total_volume_ml=_tbv,
            plasma_fraction=PLASMA_VOLUME_FRACTION
        )

        # 初始化器官模块（传入体重缩放后的参数）
        self.heart = HeartModule(
            weight_kg=body_weight_kg, blood=self.blood,
            sv_ml=_sv, base_co_ml_min=_co,
            HR_rest=_hr_rest, HR_max=_hr_stress,
        )
        self.lung = LungModule(
            weight_kg=body_weight_kg, blood=self.blood,
            base_RR=_rr, tidal_vol_ml=_tv, base_minute_vent=_mv,
        )
        self.kidney = KidneyModule(
            weight_kg=body_weight_kg, blood=self.blood,
            base_gfr_ml_min=_gfr, base_rbf_ml_min=_rbf,
            base_urine_ml_min=_urine,
        )
        self.toxicology = ToxicologyModule(weight_kg=body_weight_kg)
        self.organ_health = OrganHealthTracker()
        self.disease = None  # 疾病模块（由外部 attach_disease() 注入）

        # 三室体液模型
        self.fluid = FluidCompartment(weight_kg=body_weight_kg)
        self._hh = HendersonHasselbalch(
            hco3_meq_l=self.fluid.vascular_hco3_meq_l,
            pco2_mmHg=self.blood.arterial_PCO2_mmHg,
        )
        self.gut = GutModule(weight_kg=body_weight_kg, blood=self.blood)
        self.liver = LiverModule(weight_kg=body_weight_kg, blood=self.blood)
        self.endocrine = EndocrineModule(weight_kg=body_weight_kg, blood=self.blood)
        self.neuro = NeuroModule(weight_kg=body_weight_kg, blood=self.blood)
        self.immune = ImmuneModule(weight_kg=body_weight_kg, blood=self.blood, endocrine=self.endocrine)
        self.coagulation = CoagulationModule(weight_kg=body_weight_kg, blood=self.blood)
        self.lymphatic = LymphaticModule(weight_kg=body_weight_kg, blood=self.blood)

        # ── 多器官耦合引擎 ─────────────────────────────────────────────
        # OrganContext: 每个器官模块的信号总线
        self._organ_contexts: dict[str, OrganContext] = {}
        for mod_name in ("heart", "lung", "kidney", "blood", "fluid", "liver"):
            self._organ_contexts[mod_name] = OrganContext(mod_name)
        self.coupling_engine = CouplingEngine()

        # ── 统一 ODE 求解器缓存（半隐式耦合）────────────────────────────
        # _cached_inputs[module_name][input_name] = value
        # 在 rhs(t,y) 调用时，用上一 rhs 调用的 outputs 填充 inputs
        self._cached_inputs: dict[str, dict[str, float]] = {}
        self._current_outputs: dict[str, dict[str, float]] = {}

        # ── 连续失血模型（A3：替代 schedule_event 用于 Radau）──────────
        # sigmoid 失血：dV/dt = -k * sigmoid((t-t_onset)/width)
        # k = blood_loss_total / duration  (mL/s)
        # 累积失血量通过 Radau 积分（每次 rhs 调用应用微小损失）
        self._blood_loss_config: dict[str, float] | None = None
        self._cumulative_blood_loss_ml: float = 0.0  # 累积失血量（每次 rhs 调用累加）

        # ── 生命周期引擎（驱动生长/衰老/死亡）──────────────────────────
        self.lifecycle = LifecycleEngine(species=species, initial_age_days=age_days)

        # 仿真时间
        self.current_time_s = 0.0
        self.dt = DT_SECONDS if dt is None else dt  # dt=None → 0.1s (production); dt=float → override (testing)
        self._solver = "euler"  # "euler" | "radau" — set via solver= kwarg

        # 事件系统
        self.events = []                            # 待处理事件列表
        self.event_log = []                         # 事件历史

        # 历史记录
        self.history = {
            "time_s": [],
            # 心血管
            "HR_bpm": [],
            "CO_ml_min": [],
            "MAP_mmHg": [],
            "CVP_mmHg": [],
            # 呼吸
            "RR": [],
            "art_PO2": [],
            "art_PCO2": [],
            "saturation": [],
            "pH": [],
            # 肾脏
            "GFR": [],
            "urine_ml_min": [],
            "BUN": [],
            "plasma_Na": [],
            # 代谢
            "glucose": [],
            "blood_volume_ml": [],
            # 毒理
            "contractility_factor": [],
            "svr_factor": [],
            # 衰竭
            "heart_health": [],
            "lung_health": [],
            "kidney_health": [],
            "liver_health": [],
            # 体液三室
            "fluid_vascular_ml": [],
            "fluid_isf_ml": [],
            "fluid_icf_ml": [],
            "fluid_nfp_mmHg": [],
            # 肝脏/肠道
            "liver_metabolic_activity": [],
            "liver_detox_capacity": [],
            "liver_glycogen": [],
            "gut_motility": [],
            "gut_barrier": [],
            "gut_microbiome": [],
            # 内分泌
            "T3_ng_dL": [],
            "insulin_uU_mL": [],
            "cortisol_ug_dL": [],
            "metabolic_rate": [],
            "core_temperature_C": [],
            # 神经
            "neuro_sympathetic": [],
            "neuro_consciousness": [],
            "neuro_seizure": [],
            "neuro_pain": [],
            "neuro_chemodrive": [],
            # 免疫
            "immune_cytokine": [],
            "immune_wbc": [],
            "immune_crp": [],
            "immune_coagulation": [],
            # 凝血
            "coag_PT": [],
            "coag_aPTT": [],
            "coag_fibrinogen": [],
            # 淋巴/脾脏
            "lymph_splenic_reserve": [],
            "lymph_lymph_flow": [],
        }

        # 场景事件
        self._scheduled_events = []  # [(time_s, event_type, params)]

    def schedule_event(self, time_s: float, event_type: str, params: dict):
        """
        注册一个场景事件

        event_type:
        - 'blood_loss': params = {'volume_ml': 200.0}
        - 'fluid_infusion': params = {'volume_ml': 500.0, 'type': 'saline'}
        - 'exercise': params = {'intensity': 0.8, 'duration_s': 300}
        - 'food_intake': params = {'glucose_grams': 50}
        """
        self._scheduled_events.append((time_s, event_type, params))

    def set_blood_loss_scenario(self, t_onset: float, total_ml: float, duration: float = 300.0, width: float = 5.0):
        """
        设置连续 ODE 失血场景（替代 schedule_event，用于 Radau/Euler 仿真）。

        失血模型：dV/dt = -k * sigmoid_on(t) * (1 - sigmoid_off(t))
                  bell curve 面积 = k * 3 * width
                  → k = total_ml / (3 * width)

        Args:
            t_onset:   失血开始时间（s）
            total_ml:  总失血量（mL）
            duration:  失血持续时间窗口（参考值，默认 300s）
            width:     sigmoid 上升沿/下降沿宽度（s），默认 5s
        """
        k = total_ml / (3.0 * width)
        self._blood_loss_config = {
            "t_onset": t_onset,
            "total_ml": total_ml,
            "duration": duration,
            "width": width,
            "k": k,
        }

    def attach_disease(self, disease_module):
        """
        注入疾病模块。

        Args:
            disease_module: DiseaseModule 实例（如 PneumoniaModule）
        """
        self.disease = disease_module
        self.disease.activate(self.current_time_s)

    def apply_factor(self, cmd: FactorCommand) -> None:
        """
        统一因子写入接口 — 所有外部扰动（疾病、药物、事件）的唯一参数修改入口。

        根据 FactorCommand 中的 target 查找 _PARAM_PATHS，对对应模块的属性执行
        multiply / add / set 操作。未知 target 或 op 记录警告并静默返回。

        Args:
            cmd: FactorCommand 指令
        """
        path = _PARAM_PATHS.get(cmd.target)
        if path is None:
            logger.warning("apply_factor: unknown target '%s'", cmd.target)
            return

        module_name, attr_name = path
        module = getattr(self, module_name, None)
        if module is None:
            logger.warning("apply_factor: module '%s' not found", module_name)
            return

        current = getattr(module, attr_name, None)
        if current is None:
            logger.warning("apply_factor: attr '%s' not found on %s", attr_name, module_name)
            return

        if cmd.op == "multiply":
            new_value = current * cmd.value
        elif cmd.op == "add":
            new_value = current + cmd.value
        elif cmd.op == "set":
            new_value = cmd.value
        else:
            logger.warning("apply_factor: unknown op '%s'", cmd.op)
            return

        setattr(module, attr_name, new_value)
        logger.debug(
            "apply_factor: %s %s %.4f → %.4f",
            cmd.target, cmd.op, current, new_value,
        )

    def _process_events(self, t: float):
        """处理到达当前时间的事件"""
        triggered = []
        for i, (event_t, event_type, params) in enumerate(self._scheduled_events):
            if event_t <= t + 1e-6:
                triggered.append((event_type, params))

        for event_type, params in triggered:
            if event_type == "blood_loss":
                vol = params["volume_ml"]
                self.heart.blood_volume_change(-vol)
                self.event_log.append(f"[{t:.1f}s] 失血 {vol:.0f} mL")
            elif event_type == "fluid_infusion":
                vol = params["volume_ml"]
                self.heart.blood_volume_change(vol)
                self.event_log.append(f"[{t:.1f}s] 输液 {vol:.0f} mL")
            elif event_type == "food_intake":
                glucose = params.get("glucose_grams", 0)
                amino_g = params.get("amino_grams", 0)
                fat_g = params.get("fat_grams", 0)
                self.gut.add_food_intake(glucose, amino_g, fat_g)
                self.event_log.append(f"[{t:.1f}s] 进食 葡萄糖{glucose:.0f}g 氨基酸{amino_g:.0f}g 脂肪{fat_g:.0f}g")
            elif event_type == "cocaine":
                dose = params.get("dose_mg_kg", 3.0)
                self.toxicology.administer_cocaine(dose_mg_kg=dose)
                self.event_log.append(f"[{t:.1f}s] 注射可卡因 {dose:.1f} mg/kg")

        # 移除已处理的事件（只保留 event_t > t 的未来事件）
        # 容差 1e-6 处理浮点精度边界（如 300×0.1=29.99999≠30.0）
        self._scheduled_events = [
            (et, evt, p) for (et, evt, p) in self._scheduled_events if et > t + 1e-6
        ]

    def _handle_death(self, cause: str) -> None:
        """生命周期死亡处理：记录原因，终止仿真。"""
        self.death_reason = cause
        logger.info(
            "Creature died: %s at age %.1f days (phase=%s)",
            cause,
            self.lifecycle.state.age_days,
            self.lifecycle.state.phase.value,
        )

    def _update_venous_gas(self):
        """
        更新静脉血气（由组织代谢决定）
        简化：组织从动脉血提取 O2，释放 CO2
        """
        O2_extracted = self.heart.cardiac_output * (
            self.blood.get_arterial_O2_content() -
            self.blood.get_venous_O2_content()) / 100.0

        # CO2 产生量 = O2 消耗量 × 呼吸商（引用肺模块权威值）
        RQ = self.lung.respiratory_quotient
        CO2_released = O2_extracted * RQ

        # 更新静脉血气分压（简化）
        self.blood.venous_PO2_mmHg = max(20.0, 40.0 - 0.1 * O2_extracted)
        self.blood.venous_PCO2_mmHg = min(60.0, 46.0 + 0.2 * CO2_released)
        self.blood.venous_saturation = self.lung._oxygen_saturation_curve(
            self.blood.venous_PO2_mmHg)

    def _update_blood_metabolites(self, dt: float):
        """
        更新血液代谢物（由各器官共同影响）

        血糖：摄入 - 利用 + 糖异生
        乳酸：产生 - 清除
        """
        # 基础代谢消耗
        basal_glucose_utilization = 0.01 * self.w  # mg/kg/min → mmol/L/min
        basal_lactate_production = 0.002 * self.w    # mmol/L/min

        # 心输出量对代谢的影响
        CO_factor = self.heart.cardiac_output / base_cardiac_output_ml_min(self.w)
        if CO_factor < 0.8:
            # 低灌注 → 组织缺氧 → 乳酸产生增加
            self.blood.lactate_mmol_L += 0.001 * dt * (1.0 / CO_factor - 1.0)
            self.blood.lactate_mmol_L = min(10.0, self.blood.lactate_mmol_L)

        # 乳酸清除（肝脏 Cori cycle + 肾脏）
        hepatic_lactate_consumed = self.liver.consume_lactate(dt)  # Cori cycle
        renal_lactate_clearance = 0.002 * self.blood.lactate_mmol_L  # ~30% renal
        lactate_net = hepatic_lactate_consumed + renal_lactate_clearance
        self.blood.lactate_mmol_L = max(
            0.5, self.blood.lactate_mmol_L - lactate_net * dt
        )

    def step(self):
        """
        推进仿真一个时间步。

        根据 self._solver 分流：
        - "euler": 顺序调用各模块 compute(dt)，精度 O(dt)
        - "radau": solve_ivp(method='Radau') 统一积分，精度 O(dt^5)
        """
        if self._solver == "radau":
            return self._step_radau()
        else:
            return self._step_euler()

    def _step_euler(self):
        """
        Euler 求解器路径 — 推进仿真一个时间步

        执行顺序（保证因果关系正确）：
        0. 处理事件（失血、输液、药物注射等）
        1. 毒理学（可卡因等药物效应 → contractility/SVR 因子）
        1.5. 药理学（治疗药物 PK/PD → 修改 contractility/SVR/尿量/血容量）
        2. 心脏循环（血容量 → CO、MAP）
        3. 肺部气体交换（CO → 血气）
        4. 肾脏泌尿（MAP/CO → GFR、尿量）
        5. 器官衰竭追踪 + 器官健康损伤应用
        5.5. 疾病模块（修改器官输出因子）
        6. 更新静脉血气（组织代谢）
        7. 血液代谢物
        7.5. 尿量导致的循环血量损失
        8. 记录历史
        """
        t = self.current_time_s
        dt = self.dt

        # Step 0: 事件处理（必须先于 tox.compute，确保药物注射立即生效）
        self._process_events(t)

        # Step 0.1: 连续失血模型（sigmoid + 累积截止，用于 Euler step 路径）
        # 两条路径独立：Euler→step() 用这里，Radau→_unified_rhs() 用下面的逻辑
        if self._blood_loss_config is not None:
            cfg = self._blood_loss_config
            t_rel = t - cfg["t_onset"]
            if t_rel >= 0:
                # bell curve: rise sigmoid × (1 - fall sigmoid)
                sigmoid_on = 1.0 / (1.0 + np.exp(-t_rel / cfg["width"]))
                t_fall = t_rel - 3 * cfg["width"]
                sigmoid_off = 1.0 / (1.0 + np.exp(-t_fall / cfg["width"]))
                rate = cfg["k"] * sigmoid_on * (1.0 - sigmoid_off)
                self.heart.circulating_volume_ml -= rate * dt
                if self.heart.circulating_volume_ml < 0:
                    self.heart.circulating_volume_ml = 0

        # Step 0.5: 生命周期因子应用（年龄调整后的基线参数）
        if not self.lifecycle.is_dead():
            self.lifecycle.apply_age_factors(self)
            death_cause = self.lifecycle.death_check()
            if death_cause:
                self._handle_death(death_cause)
                return

        # Step 1: 毒理学（可卡因等药物效应）
        tox_state = self.toxicology.compute(dt)
        self.heart.contractility_factor = tox_state["contractility_factor"]
        svr_factor = tox_state["svr_factor"]

        # Step 1.5: 药理学（治疗药物 PK/PD 效应）
        # 药物通过 FactorCommand → apply_factor() 统一写入（与疾病模块同路径）
        pharma_effects: dict = {}
        if hasattr(self, "pharmacology") and self.pharmacology is not None:
            # 记录 tox 写入后的 SVR 基准值（pharma 的 multiply 基于此）
            svr_before_pharma = self.heart.SVR
            pharma_commands = self.pharmacology.compute(dt, self)
            for cmd in pharma_commands:
                self.apply_factor(cmd)
            # 同步 pharma 对 SVR 的修改到局部变量：
            # heart.compute() 会覆盖 self.SVR（baroreflex），所以 pharma 的 SVR 效果
            # 必须通过 svr_factor 局部变量传递（与 tox 相同的路径）
            svr_after_pharma = self.heart.SVR
            if svr_after_pharma != svr_before_pharma:
                # pharma 修改了 self.SVR，将变化比例应用到 svr_factor
                svr_factor *= (svr_after_pharma / svr_before_pharma)

        # Step 2: 心脏循环（输入：血容量 → 输出：CO、MAP）
        # chemoreceptor_drive 来自上一时间步的 neuro 状态（Gauss-Seidel 一阶滞后，
        # 产生 O(dt) 误差，随 dt 细化收敛，不产生 O(1) 偏差）
        neuro_chemo = self.neuro.chemoreceptor_drive if hasattr(self, "neuro") else 0.0
        heart_state = self.heart.compute(dt, svr_factor=svr_factor,
                                         chemoreceptor_drive=neuro_chemo)
        CVP = heart_state["CVP_mmHg"]
        CO = heart_state["cardiac_output_ml_min"]

        # Step 3: 肺部气体交换（输入：CO → 输出：血气）
        lung_state = self.lung.compute(dt, CO)

        # Step 4: 肾脏泌尿（输入：MAP、CO → 输出：GFR、尿量）
        kidney_state = self.kidney.compute(dt, heart_state["MAP_mmHg"], CVP, CO)

        # Step 4.5: 肠道吸收
        gut_state = self.gut.compute(dt, CO)

        # Step 4.6: 肝脏代谢
        liver_state = self.liver.compute(dt, gut_state, CO)

        # Step 4.7: 内分泌轴
        endocrine_state = self.endocrine.compute(dt)

        # Step 4.65: 凝血系统
        coagulation_state = self.coagulation.compute(dt, liver_state, {})
        for cmd in coagulation_state.get("factor_commands", []):
            self.apply_factor(cmd)

        # Step 4.75: 淋巴/脾脏系统
        lymphatic_state = self.lymphatic.compute(dt, gut_state, {})
        for cmd in lymphatic_state.get("factor_commands", []):
            self.apply_factor(cmd)

        # Step 4.8: 神经系统
        neuro_state = self.neuro.compute(dt, heart_state, lung_state)
        for cmd in neuro_state.get("factor_commands", []):
            self.apply_factor(cmd)

        # Step 4.9: 免疫/炎症系统
        immune_state = self.immune.compute(dt, endocrine_state)
        for cmd in immune_state.get("factor_commands", []):
            self.apply_factor(cmd)

        # ── Step 4.95: 多器官耦合 ─────────────────────────────────────────────
        # 所有器官 compute() 完成后，发布信号到各自的 OrganContext
        ctx = self._organ_contexts
        t = self.current_time_s
        # Heart signals
        ctx["heart"].publish(PhysiologicalSignal("cardiac_output", CO, "mL/min", "heart", t))
        ctx["heart"].publish(PhysiologicalSignal("MAP", heart_state["MAP_mmHg"], "mmHg", "heart", t))
        ctx["heart"].publish(PhysiologicalSignal("central_venous_pressure", CVP, "mmHg", "heart", t))
        ctx["heart"].publish(PhysiologicalSignal("heart_rate", self.heart.heart_rate, "bpm", "heart", t))
        ctx["heart"].publish(PhysiologicalSignal("stroke_volume", self.heart.stroke_volume, "mL", "heart", t))
        ctx["heart"].publish(PhysiologicalSignal("SVR", self.heart.SVR, "mmHg·s/mL", "heart", t))
        # Lung signals
        ctx["lung"].publish(PhysiologicalSignal("arterial_PO2", self.blood.arterial_PO2_mmHg, "mmHg", "lung", t))
        ctx["lung"].publish(PhysiologicalSignal("arterial_PCO2", self.blood.arterial_PCO2_mmHg, "mmHg", "lung", t))
        ctx["lung"].publish(PhysiologicalSignal("arterial_saturation", self.blood.arterial_saturation, "", "lung", t))
        ctx["lung"].publish(PhysiologicalSignal("respiratory_rate", lung_state["respiratory_rate"], "/min", "lung", t))
        ctx["lung"].publish(PhysiologicalSignal("minute_ventilation", lung_state["minute_ventilation"], "mL/min", "lung", t))
        ctx["lung"].publish(PhysiologicalSignal("diffusion_coefficient", self.lung.diffusion_coefficient, "", "lung", t))
        # Kidney signals
        ctx["kidney"].publish(PhysiologicalSignal("GFR", kidney_state["GFR_ml_min"], "mL/min", "kidney", t))
        ctx["kidney"].publish(PhysiologicalSignal("renin_activity", kidney_state["renin_activity"], "", "kidney", t))
        ctx["kidney"].publish(PhysiologicalSignal("angiotensin_II", kidney_state.get("angiotensin_II", self.kidney.angiotensin_II), "", "kidney", t))
        ctx["kidney"].publish(PhysiologicalSignal("aldosterone", kidney_state["aldosterone"], "", "kidney", t))
        ctx["kidney"].publish(PhysiologicalSignal("urine_output", kidney_state["urine_output_ml_min"], "mL/min", "kidney", t))
        # Blood signals
        ctx["blood"].publish(PhysiologicalSignal("arterial_pH", self.blood.arterial_pH, "", "blood", t))
        ctx["blood"].publish(PhysiologicalSignal("arterial_PCO2", self.blood.arterial_PCO2_mmHg, "mmHg", "blood", t))
        ctx["blood"].publish(PhysiologicalSignal("lactate", self.blood.lactate_mmol_L, "mmol/L", "blood", t))
        ctx["blood"].publish(PhysiologicalSignal("potassium", self.blood.potassium_mEq_L, "mEq/L", "blood", t))
        ctx["blood"].publish(PhysiologicalSignal("albumin", self.blood.albumin_g_dL, "g/dL", "blood", t))
        ctx["blood"].publish(PhysiologicalSignal("ALT", self.blood.ALT_U_L, "U/L", "blood", t))
        ctx["blood"].publish(PhysiologicalSignal("PT_sec", self.blood.PT_sec, "sec", "blood", t))
        ctx["blood"].publish(PhysiologicalSignal("fibrinogen_mg_dL", self.blood.fibrinogen_mg_dL, "mg/dL", "blood", t))
        ctx["blood"].publish(PhysiologicalSignal("HCO3", self.fluid.vascular_hco3_meq_l, "mEq/L", "blood", t))
        # Fluid signals
        ctx["fluid"].publish(PhysiologicalSignal("vascular_volume_ml", self.fluid.vascular_volume_ml, "mL", "fluid", t))
        # Liver signals
        ctx["liver"].publish(PhysiologicalSignal("metabolic_activity", liver_state["metabolic_activity"], "", "liver", t))

        # 解析耦合规则 → 生成 FactorCommands → apply_factor()
        coupling_cmds = self.coupling_engine.resolve(ctx, dt)
        for cmd in coupling_cmds:
            self.apply_factor(cmd)

        # Step 5: 器官衰竭追踪
        # 根据当前危险条件更新各器官健康状态
        self.organ_health.track(dt, heart_state, lung_state, kidney_state, liver_state)

        # 健康因子永久降低器官输出（不可逆）
        # 同时修改返回 dict 和模块内部状态，确保损伤有累积效应
        if self.organ_health.heart_factor < 1.0:
            heart_state["cardiac_output_ml_min"] *= self.organ_health.heart_factor
            heart_state["MAP_mmHg"] *= self.organ_health.heart_factor
            self.heart.mean_arterial_pressure *= self.organ_health.heart_factor
            self.heart.cardiac_output *= self.organ_health.heart_factor
        if self.organ_health.lung_factor < 1.0:
            lung_state["arterial_PO2"] *= self.organ_health.lung_factor
            self.lung.diffusion_coefficient *= self.organ_health.lung_factor
        if self.organ_health.kidney_factor < 1.0:
            kidney_state["GFR_ml_min"] *= self.organ_health.kidney_factor
            self.kidney.GFR *= self.organ_health.kidney_factor

        # Step 5.5: 疾病模块 — 通过 apply_factor() 统一写入
        if self.disease and self.disease.active:
            self.disease._current_time_s = t
            engine_state = {
                "heart": {
                    "heart_rate_bpm": heart_state["heart_rate_bpm"],
                    "MAP_mmHg": heart_state["MAP_mmHg"],
                    "cardiac_output_ml_min": heart_state["cardiac_output_ml_min"],
                },
                "lung": {"arterial_PO2": lung_state["arterial_PO2"]},
                "kidney": {"GFR_ml_min": kidney_state["GFR_ml_min"]},
            }
            commands = self.disease.compute(dt, engine_state)
            for cmd in commands:
                self.apply_factor(cmd)

            # 生理 clamp：防止疾病累积效应把参数推到非生理范围
            # 心率：犬 40-250，猫 140-300
            self.heart.heart_rate = max(40.0, min(250.0, self.heart.heart_rate))
            # MAP：30-200 mmHg
            self.heart.mean_arterial_pressure = max(30.0, min(200.0, self.heart.mean_arterial_pressure))

            # 重新读取被疾病修改后的器官状态（用于后续器官健康追踪和历史记录）
            heart_state["heart_rate_bpm"] = self.heart.heart_rate
            heart_state["MAP_mmHg"] = self.heart.mean_arterial_pressure
            heart_state["CVP_mmHg"] = self.heart.central_venous_pressure
            heart_state["cardiac_output_ml_min"] = self.heart.cardiac_output
            lung_state["arterial_PO2"] = self.blood.arterial_PO2_mmHg
            kidney_state["GFR_ml_min"] = self.kidney.GFR
            kidney_state["urine_output_ml_min"] = self.kidney.urine_output

        # 从修改后的 dict 读取最终值（而非旧快照）
        final_MAP = heart_state["MAP_mmHg"]
        final_CO  = heart_state["cardiac_output_ml_min"]

        # Step 6: 更新静脉血气（组织代谢）
        self._update_venous_gas()

        # Step 7: 血液代谢物
        self._update_blood_metabolites(dt)

        # Step 7.5: 尿量导致的循环血量损失
        # 肾脏计算 blood_volume_loss_rate，此处应用到心脏血容量
        bv_loss = self.kidney.blood_volume_loss_rate * dt / 60.0  # mL/min × dt(s) / 60
        if bv_loss > 0:
            self.heart.circulating_volume_ml = max(0.0, self.heart.circulating_volume_ml - bv_loss)

        # Step 7.6: 三室体液交换 + Henderson-Hasselbalch pH
        fluid_state = self.fluid.compute(dt)
        # 用 HH 方程更新动脉血 pH（基于当前 HCO₃⁻ 和 PCO₂）
        self._hh.hco3 = self.fluid.vascular_hco3_meq_l
        self._hh.pco2 = self.blood.arterial_PCO2_mmHg
        self.blood.arterial_pH = self._hh._compute_ph()

        # Step 7.7: 保守血容量同步
        # HeartModule.circulating_volume_ml 是循环血量的权威来源。
        # blood.total_volume_ml 会在每步结束时与之一致，
        # 确保血液隔室的血容量始终反映真实的循环血量。
        self.blood.total_volume_ml = self.heart.circulating_volume_ml

        # Step 8: 记录（使用修改后的最终值）
        self.history["time_s"].append(t)
        self.history["HR_bpm"].append(heart_state["heart_rate_bpm"])
        self.history["CO_ml_min"].append(final_CO)
        self.history["MAP_mmHg"].append(final_MAP)
        self.history["CVP_mmHg"].append(CVP)
        self.history["RR"].append(lung_state["respiratory_rate"])
        self.history["art_PO2"].append(lung_state["arterial_PO2"])
        self.history["art_PCO2"].append(lung_state["arterial_PCO2"])
        self.history["saturation"].append(lung_state["arterial_saturation"])
        self.history["pH"].append(self.blood.arterial_pH)
        self.history["GFR"].append(kidney_state["GFR_ml_min"])
        self.history["urine_ml_min"].append(kidney_state["urine_output_ml_min"])
        self.history["BUN"].append(kidney_state["BUN_mg_dL"])
        self.history["plasma_Na"].append(self.blood.sodium_mEq_L)
        self.history["glucose"].append(self.blood.glucose_mmol_L)
        self.history["blood_volume_ml"].append(heart_state["blood_volume_ml"])
        self.history["contractility_factor"].append(heart_state["contractility_factor"])
        self.history["svr_factor"].append(svr_factor)
        self.history["heart_health"].append(self.organ_health.heart_health)
        self.history["lung_health"].append(self.organ_health.lung_health)
        self.history["kidney_health"].append(self.organ_health.kidney_health)
        self.history["liver_health"].append(self.organ_health.liver_health)
        # 体液三室
        self.history["fluid_vascular_ml"].append(fluid_state["vascular_ml"])
        self.history["fluid_isf_ml"].append(fluid_state["isf_ml"])
        self.history["fluid_icf_ml"].append(fluid_state["icf_ml"])
        self.history["fluid_nfp_mmHg"].append(fluid_state["nfp_mmHg"])
        # 肝脏/肠道
        self.history["liver_metabolic_activity"].append(liver_state["metabolic_activity"])
        self.history["liver_detox_capacity"].append(liver_state["detox_capacity"])
        self.history["liver_glycogen"].append(liver_state["glycogen_fraction"])
        self.history["gut_motility"].append(gut_state["gut_motility"])
        self.history["gut_barrier"].append(gut_state["barrier_integrity"])
        self.history["gut_microbiome"].append(gut_state["microbiome_activity"])
        # 内分泌
        self.history["T3_ng_dL"].append(endocrine_state["T3_ng_dL"])
        self.history["insulin_uU_mL"].append(endocrine_state["insulin_uU_mL"])
        self.history["cortisol_ug_dL"].append(endocrine_state["cortisol_ug_dL"])
        self.history["metabolic_rate"].append(endocrine_state["metabolic_rate"])
        self.history["core_temperature_C"].append(self.blood.core_temperature_C)
        # 神经
        self.history["neuro_sympathetic"].append(neuro_state["sympathetic_tone"])
        self.history["neuro_consciousness"].append(neuro_state["consciousness"])
        self.history["neuro_seizure"].append(neuro_state["seizure"])
        self.history["neuro_pain"].append(neuro_state["pain_level"])
        self.history["neuro_chemodrive"].append(neuro_state["chemoreceptor_drive"])
        # 免疫
        self.history["immune_cytokine"].append(immune_state["cytokine_level"])
        self.history["immune_wbc"].append(immune_state["wbc_count"])
        self.history["immune_crp"].append(immune_state["crp_level"])
        self.history["immune_coagulation"].append(immune_state["coagulation_state"])

        # 凝血
        self.history["coag_PT"].append(self.blood.PT_sec)
        self.history["coag_aPTT"].append(self.blood.aPTT_sec)
        self.history["coag_fibrinogen"].append(self.blood.fibrinogen_mg_dL)

        # 淋巴/脾脏
        self.history["lymph_splenic_reserve"].append(self.blood.splenic_reserve_mL)
        self.history["lymph_lymph_flow"].append(self.lymphatic.lymph_flow_rate)

        # 更新时间
        self.current_time_s += dt

        return {
            "heart": heart_state,
            "lung": lung_state,
            "kidney": kidney_state,
            "gut": gut_state,
            "liver": liver_state,
            "endocrine": self.endocrine.summary(),
            "neuro": self.neuro.summary(),
            "immune": self.immune.summary(),
            "coagulation": self.coagulation.summary(),
            "lymphatic": self.lymphatic.summary(),
            "blood": self.blood.summary(),
            "toxicology": tox_state,
            "pharmacology": pharma_effects if (hasattr(self, "pharmacology") and self.pharmacology is not None) else {},
        }

    def _step_radau(self):
        """
        Radau 隐式求解器路径 — 单步推进。

        1. 调用 solve_ivp(method='Radau') 在 [t, t+dt] 上积分
        2. 解包结果到模块属性
        3. 执行耦合规则（同 Euler 路径）
        4. 执行疾病模块
        5. 记录 history
        """
        from scipy.integrate import solve_ivp

        t = self.current_time_s
        dt = self.dt

        # 1. 事件处理
        self._process_events(t)

        # 2. 打包状态
        y0 = self._pack_unified_state()
        if len(y0) == 0:
            # 无疾病状态，退化为 Euler
            self._step_euler()
            return

        # 3. 预热：初始化 _cached_inputs
        _ = self._unified_rhs(t, y0)

        # 4. solve_ivp 单步
        sol = solve_ivp(
            self._unified_rhs,
            [t, t + dt],
            y0,
            method='Radau',
            rtol=1e-5,
            atol=1e-8,
            dense_output=False,
            vectorized=False,
        )

        if not sol.success:
            # 求解失败，退化为 Euler
            logger.warning("Radau failed at t=%.2fs: %s, falling back to Euler", t, sol.message)
            self._step_euler()
            return

        # 5. 解包结果到模块属性
        self._unpack_unified_state(sol.y[:, -1])

        # 6. 耦合规则（同 Euler 路径）
        ctx = self._organ_contexts
        t_now = self.current_time_s + dt
        # 重新发布信号（用解包后的状态）
        ctx["heart"].publish(PhysiologicalSignal("cardiac_output", self.heart.cardiac_output, "mL/min", "heart", t_now))
        ctx["heart"].publish(PhysiologicalSignal("MAP", self.heart.mean_arterial_pressure, "mmHg", "heart", t_now))
        ctx["heart"].publish(PhysiologicalSignal("central_venous_pressure", self.heart.central_venous_pressure, "mmHg", "heart", t_now))
        ctx["kidney"].publish(PhysiologicalSignal("GFR", self.kidney.GFR, "mL/min", "kidney", t_now))
        ctx["kidney"].publish(PhysiologicalSignal("renin_activity", self.kidney.renin_activity, "", "kidney", t_now))
        ctx["kidney"].publish(PhysiologicalSignal("angiotensin_II", self.kidney.angiotensin_II, "", "kidney", t_now))
        ctx["kidney"].publish(PhysiologicalSignal("aldosterone", self.kidney.aldosterone, "", "kidney", t_now))
        ctx["blood"].publish(PhysiologicalSignal("arterial_pH", self.blood.arterial_pH, "", "blood", t_now))
        ctx["blood"].publish(PhysiologicalSignal("arterial_PCO2", self.blood.arterial_PCO2_mmHg, "mmHg", "blood", t_now))
        ctx["fluid"].publish(PhysiologicalSignal("vascular_volume_ml", self.fluid.vascular_volume_ml, "mL", "fluid", t_now))
        ctx["liver"].publish(PhysiologicalSignal("metabolic_activity", self.liver.metabolic_activity, "", "liver", t_now))

        coupling_cmds = self.coupling_engine.resolve(ctx, dt)
        for cmd in coupling_cmds:
            self.apply_factor(cmd)

        # 7. 疾病模块
        if self.disease is not None:
            engine_state = {
                "heart": {"HR": self.heart.heart_rate, "MAP": self.heart.mean_arterial_pressure,
                          "CO": self.heart.cardiac_output, "contractility": self.heart.contractility_factor,
                          "SVR": self.heart.SVR, "CVP": self.heart.central_venous_pressure},
                "lung": {"arterial_PO2": self.blood.arterial_PO2_mmHg,
                         "arterial_PCO2": self.blood.arterial_PCO2_mmHg,
                         "diffusion_coefficient": self.lung.diffusion_coefficient,
                         "respiratory_rate": self.lung.respiratory_rate},
                "kidney": {"GFR": self.kidney.GFR, "urine_output": self.kidney.urine_output,
                           "renin_activity": self.kidney.renin_activity,
                           "angiotensin_II": self.kidney.angiotensin_II,
                           "aldosterone": self.kidney.aldosterone},
                "blood": {"pH": self.blood.arterial_pH, "lactate": self.blood.lactate_mmol_L,
                          "BUN": self.blood.bun_mg_dL, "creatinine": self.blood.creatinine_mg_dL,
                          "glucose": self.blood.glucose_mmol_L, "sodium": self.blood.sodium_mEq_L,
                          "potassium": self.blood.potassium_mEq_L},
                "fluid": {"vascular_volume_ml": self.fluid.vascular_volume_ml},
                "temperature": self.blood.core_temperature_C,
            }
            cmds = self.disease.compute(dt, engine_state)
            for cmd in cmds:
                self.apply_factor(cmd)

        # 8. 记录历史（同 Euler 路径最后部分）
        self._record_history(dt)
        return {}

    def _record_history(self, dt: float):
        """记录当前状态到 history dict（Euler 和 Radau 共用）。"""
        self.history["time_s"].append(self.current_time_s)
        self.history["HR_bpm"].append(self.heart.heart_rate)
        self.history["CO_ml_min"].append(self.heart.cardiac_output)
        self.history["MAP_mmHg"].append(self.heart.mean_arterial_pressure)
        self.history["CVP_mmHg"].append(self.heart.central_venous_pressure)
        self.history["RR"].append(self.lung.respiratory_rate)
        self.history["art_PO2"].append(self.blood.arterial_PO2_mmHg)
        self.history["art_PCO2"].append(self.blood.arterial_PCO2_mmHg)
        self.history["saturation"].append(self.blood.arterial_saturation)
        self.history["pH"].append(self.blood.arterial_pH)
        self.history["GFR"].append(self.kidney.GFR)
        self.history["urine_ml_min"].append(self.kidney.urine_output)
        self.history["BUN"].append(self.blood.bun_mg_dL)
        self.history["creatinine"].append(self.blood.creatinine_mg_dL)
        self.history["lactate"].append(self.blood.lactate_mmol_L)
        self.history["glucose"].append(self.blood.glucose_mmol_L)
        self.history["temperature"].append(self.blood.core_temperature_C)
        self.history["blood_volume_ml"].append(self.heart.circulating_volume_ml)
        self.history["sympathetic"].append(self.neuro.sympathetic_tone)
        self.history["contractility_factor"].append(self.heart.contractility_factor)
        self.history["SVR"].append(self.heart.SVR)
        self.history["endocrine"].append(self.endocrine.summary())
        self.history["immune"].append(self.immune.summary())
        self.history["toxicology"].append(self.toxicology.summary() if hasattr(self.toxicology, 'summary') else {})
        self.history["liver"].append(self.liver.summary() if hasattr(self.liver, 'summary') else {})
        self.history["neuro"].append(self.neuro.summary())
        self.history["coagulation"].append(self.coagulation.summary())
        self.history["lymphatic"].append(self.lymphatic.summary())
        self.history["lymph_splenic_reserve"].append(self.blood.splenic_reserve_mL)
        self.history["lymph_lymph_flow"].append(self.lymphatic.lymph_flow_rate)

        self.current_time_s += dt

    def simulate(self, duration_minutes: float, verbose: bool = False):
        """
        运行仿真直到指定时长

        Args:
            duration_minutes: 仿真时长（分钟）
            verbose: 是否打印进度
        """
        total_steps = int(duration_minutes * 60.0 / self.dt)

        if verbose:
            print(f"开始仿真：{duration_minutes} min, {total_steps} steps")

        for i in range(total_steps):
            self.step()
            if verbose and i % 1000 == 0:
                t = self.current_time_s
                print(f"  t={t:.1f}s, HR={self.history['HR_bpm'][-1]:.0f}, "
                      f"MAP={self.history['MAP_mmHg'][-1]:.1f}, "
                      f"GFR={self.history['GFR'][-1]:.1f}")

    # ── solve_ivp Radau 引擎（Phase 2: 替换 Euler 求解器）────────────────────────

    # ── 统一 ODE 状态映射（器官 + 疾病）────────────────────────────────────
    # 每个模块的名称、状态变量名列表、模块实例
    # 状态变量 = 进入统一 y 向量的变量（而非仅代数输出的变量）
    _UNIFIED_MODULES = [
        # name, state_var_names, module_attr
        ("heart",       ["HR", "SV", "SVR", "blood_volume", "sympathetic", "parasympathetic"], "heart"),
        ("lung",        ["RR", "TV", "VQ"],                    "lung"),
        ("kidney",      ["GFR", "RBF", "urine_output", "ADH"], "kidney"),
        ("fluid",       ["V_vascular", "V_isf", "V_icf"],      "fluid"),
        ("gut",         ["motility", "barrier", "microbiome"],  "gut"),
        ("liver",       ["glycogen_fraction", "bilirubin_accumulation"], "liver"),
        ("endocrine",   ["T3", "insulin", "glucagon", "cortisol", "PTH", "IGF1", "HPA_axis"], "endocrine"),
        ("neuro",       ["sympathetic_tone", "parasympathetic_tone", "consciousness", "seizure", "pain"], "neuro"),
        ("immune",      ["cytokine", "acute_phase", "wbc", "coagulation_state"], "immune"),
        ("coagulation", ["factor_VII", "factor_V", "factor_II", "factor_IX", "factor_X", "factor_XI", "fibrinogen", "coagulation_state"], "coagulation"),
        ("lymphatic",   ["splenic_reserve_mL", "interstitial_fluid_mL"], "lymphatic"),
    ]

    def _build_unified_state_map(self) -> dict[tuple[str, str], int]:
        """建立 (module_name, var_name) → y-array index 映射表（器官 + 疾病）。"""
        state_map: dict[tuple[str, str], int] = {}
        idx = 0

        # 器官状态变量
        for mname, var_names, _ in self._UNIFIED_MODULES:
            for vname in var_names:
                state_map[(mname, vname)] = idx
                idx += 1

        # 疾病状态变量
        if self.disease is not None and hasattr(self.disease, '_state_vars'):
            for vname in self.disease._state_vars:
                state_map[("disease", vname)] = idx
                idx += 1

        return state_map

    def _pack_unified_state(self) -> np.ndarray:
        """将所有器官 + 疾病状态打包成 numpy 向量 y0。"""
        state_map = self._build_unified_state_map()
        n = len(state_map)
        y0 = np.zeros(n)

        # 器官状态
        for mname, var_names, attr_name in self._UNIFIED_MODULES:
            module = getattr(self, attr_name)
            for vname in var_names:
                idx = state_map[(mname, vname)]
                # 从模块实例属性读取状态
                if mname == "heart":
                    if vname == "HR": y0[idx] = module.heart_rate
                    elif vname == "SV": y0[idx] = module.stroke_volume
                    elif vname == "SVR": y0[idx] = module.SVR
                    elif vname == "blood_volume": y0[idx] = module.circulating_volume_ml
                    elif vname == "sympathetic": y0[idx] = module.sympathetic
                    elif vname == "parasympathetic": y0[idx] = module.parasympathetic
                elif mname == "lung":
                    if vname == "RR": y0[idx] = module.respiratory_rate
                    elif vname == "TV": y0[idx] = module.tidal_volume
                    elif vname == "VQ": y0[idx] = module.VQ_ratio
                elif mname == "kidney":
                    if vname == "GFR": y0[idx] = module.GFR
                    elif vname == "RBF": y0[idx] = module.renin_activity  # RBF 用 renin_activity 代
                    elif vname == "ADH": y0[idx] = module.ADH_level
                    elif vname == "urine_output": y0[idx] = module.urine_output
                elif mname == "fluid":
                    if vname == "V_vascular": y0[idx] = module.vascular_volume_ml
                    elif vname == "V_isf": y0[idx] = module.isf_volume_ml
                    elif vname == "V_icf": y0[idx] = module.icf_volume_ml
                elif mname == "gut":
                    if vname == "motility": y0[idx] = module.gut_motility
                    elif vname == "barrier": y0[idx] = module.barrier_integrity
                    elif vname == "microbiome": y0[idx] = module.microbiome_activity
                elif mname == "liver":
                    if vname == "glycogen_fraction": y0[idx] = module.glycogen_fraction
                    elif vname == "bilirubin_accumulation": y0[idx] = module._bilirubin_accumulation
                elif mname == "endocrine":
                    if vname == "T3": y0[idx] = module.T3_ng_dL
                    elif vname == "insulin": y0[idx] = module.insulin_uU_mL
                    elif vname == "glucagon": y0[idx] = module.glucagon_pg_mL
                    elif vname == "cortisol": y0[idx] = module.cortisol_ug_dL
                    elif vname == "PTH": y0[idx] = module.PTH_pg_mL
                    elif vname == "IGF1": y0[idx] = module.IGF1_nmol_L
                    elif vname == "HPA_axis": y0[idx] = module.HPA_axis
                elif mname == "neuro":
                    if vname == "sympathetic_tone": y0[idx] = module.sympathetic_tone
                    elif vname == "parasympathetic_tone": y0[idx] = module.parasympathetic_tone
                    elif vname == "consciousness": y0[idx] = module.consciousness
                    elif vname == "seizure": y0[idx] = module.seizure
                    elif vname == "pain": y0[idx] = module.pain_level
                elif mname == "immune":
                    if vname == "cytokine": y0[idx] = module.cytokine_level
                    elif vname == "acute_phase": y0[idx] = module.acute_phase_response
                    elif vname == "wbc": y0[idx] = module.wbc_count
                    elif vname == "coagulation_state": y0[idx] = module.coagulation_state
                elif mname == "coagulation":
                    attr_map = {
                        "factor_VII": "factor_VII", "factor_V": "factor_V",
                        "factor_II": "factor_II", "factor_IX": "factor_IX",
                        "factor_X": "factor_X", "factor_XI": "factor_XI",
                        "fibrinogen": "fibrinogen", "coagulation_state": "coagulation_state",
                    }
                    if vname in attr_map:
                        y0[idx] = getattr(module, attr_map[vname])
                elif mname == "lymphatic":
                    if vname == "splenic_reserve_mL": y0[idx] = module.splenic_reserve_mL
                    elif vname == "interstitial_fluid_mL": y0[idx] = module.interstitial_fluid_mL

        # 疾病状态
        if self.disease is not None and hasattr(self.disease, '_state_vars'):
            for vname in self.disease._state_vars:
                idx = state_map[("disease", vname)]
                y0[idx] = self.disease._state_vars[vname]

        return y0

    def _unpack_unified_state(self, y: np.ndarray) -> None:
        """将 numpy 向量 y 分解到各模块的实例属性。"""
        state_map = self._build_unified_state_map()

        for mname, var_names, attr_name in self._UNIFIED_MODULES:
            module = getattr(self, attr_name)
            for vname in var_names:
                idx = state_map[(mname, vname)]
                val = y[idx]

                if mname == "heart":
                    if vname == "HR": module.heart_rate = val
                    elif vname == "SV": module.stroke_volume = val
                    elif vname == "SVR": module.SVR = val
                    elif vname == "blood_volume": module.circulating_volume_ml = val
                    elif vname == "sympathetic": module.sympathetic = val
                    elif vname == "parasympathetic": module.parasympathetic = val
                    # 同步 filtered MAP（低通滤波），与 heart.compute() 的 α=0.3 一致
                    # 在 blood_volume unpack 后计算（确保 vol_ratio 正确）
                    # mean_arterial_pressure 不在 y 向量里，需要主动同步
                    if vname == "blood_volume":
                        CO = module.heart_rate * module.stroke_volume
                        vol_ratio = module.circulating_volume_ml / module.total_BV
                        MAP_base = module.MAP_baseline
                        raw_MAP = MAP_base + (CO / 60.0) * module.SVR
                        if vol_ratio < 0.7:
                            raw_MAP = raw_MAP * (0.5 + 0.5 * vol_ratio / 0.7)
                        raw_MAP = max(30.0, min(180.0, raw_MAP))
                        module.mean_arterial_pressure = raw_MAP  # 直接赋值，无状态记忆
                elif mname == "lung":
                    if vname == "RR": module.respiratory_rate = val
                    elif vname == "TV": module.tidal_volume = val
                    elif vname == "VQ": module.VQ_ratio = val
                elif mname == "kidney":
                    if vname == "GFR": module.GFR = val
                    elif vname == "ADH": module.ADH_level = val
                elif mname == "fluid":
                    if vname == "V_vascular": module.vascular_volume_ml = val
                    elif vname == "V_isf": module.isf_volume_ml = val
                    elif vname == "V_icf": module.icf_volume_ml = val
                elif mname == "gut":
                    if vname == "motility": module.gut_motility = val
                    elif vname == "barrier": module.barrier_integrity = val
                    elif vname == "microbiome": module.microbiome_activity = val
                elif mname == "liver":
                    if vname == "glycogen_fraction": module.glycogen_fraction = val
                    elif vname == "bilirubin_accumulation": module._bilirubin_accumulation = val
                elif mname == "endocrine":
                    if vname == "T3": module.T3_ng_dL = val
                    elif vname == "insulin": module.insulin_uU_mL = val
                    elif vname == "glucagon": module.glucagon_pg_mL = val
                    elif vname == "cortisol": module.cortisol_ug_dL = val
                    elif vname == "PTH": module.PTH_pg_mL = val
                    elif vname == "IGF1": module.IGF1_nmol_L = val
                    elif vname == "HPA_axis": module.HPA_axis = val
                elif mname == "neuro":
                    if vname == "sympathetic_tone": module.sympathetic_tone = val
                    elif vname == "parasympathetic_tone": module.parasympathetic_tone = val
                    elif vname == "consciousness": module.consciousness = val
                    elif vname == "seizure": module.seizure = val
                    elif vname == "pain": module.pain_level = val
                elif mname == "immune":
                    if vname == "cytokine": module.cytokine_level = val
                    elif vname == "acute_phase": module.acute_phase_response = val
                    elif vname == "wbc": module.wbc_count = val
                    elif vname == "coagulation_state": module.coagulation_state = val
                elif mname == "coagulation":
                    attr_map = {
                        "factor_VII": "factor_VII", "factor_V": "factor_V",
                        "factor_II": "factor_II", "factor_IX": "factor_IX",
                        "factor_X": "factor_X", "factor_XI": "factor_XI",
                        "fibrinogen": "fibrinogen", "coagulation_state": "coagulation_state",
                    }
                    if vname in attr_map:
                        setattr(module, attr_map[vname], val)
                elif mname == "lymphatic":
                    if vname == "splenic_reserve_mL": module.splenic_reserve_mL = val
                    elif vname == "interstitial_fluid_mL": module.interstitial_fluid_mL = val

        # 疾病状态
        if self.disease is not None and hasattr(self.disease, '_state_vars'):
            for vname in self.disease._state_vars:
                idx = state_map[("disease", vname)]
                self.disease._state_vars[vname] = y[idx]

    def _unified_rhs(self, t: float, y: np.ndarray) -> np.ndarray:
        """
        统一 ODE 右端函数（供 solve_ivp Radau 调用）。

        半隐式耦合策略：
        - 在 rhs(t,y) 调用时，用上一 rhs 调用的 outputs 路由为当前 inputs
        - 每个模块的 derivatives() 只读 inputs（不读其他模块的当前状态）
        - Radau 的 Newton 迭代会自动收敛到耦合解

        数据流：
        1. 解包 y → 模块实例属性
        2. 用 _cached_inputs 填充每个模块的 inputs
        3. 调用各模块 derivatives() → dydt + outputs
        4. 将 outputs 存入 _current_outputs
        5. 在连接表上路由：_current_outputs → _cached_inputs（下次调用用）
        6. 打包 dydt → numpy 向量
        """
        # 1. 连续失血模型（sigmoid，用于 Radau 积分路径）
        # 与 step() 里的公式保持一致：bell curve = sigmoid_on × (1 - sigmoid_off)
        blood_loss_rate_ml_s = 0.0
        if self._blood_loss_config is not None:
            cfg = self._blood_loss_config
            t_rel = t - cfg["t_onset"]
            if t_rel >= 0:
                sigmoid_on = 1.0 / (1.0 + np.exp(-t_rel / cfg["width"]))
                t_fall = t_rel - 3 * cfg["width"]
                sigmoid_off = 1.0 / (1.0 + np.exp(-t_fall / cfg["width"]))
                blood_loss_rate_ml_s = cfg["k"] * sigmoid_on * (1.0 - sigmoid_off)

        # 2. 解包状态
        self._unpack_unified_state(y)

        # 3. 准备各模块的 inputs（用 cached 值 + 当前输出填充）
        all_outputs: dict[str, dict[str, float]] = {}
        module_inputs: dict[str, dict] = {}

        # 初始化 inputs 为 cached_inputs（上一调用输出的值）
        for mname, _, _ in self._UNIFIED_MODULES:
            module_inputs[mname] = dict(self._cached_inputs.get(mname, {}))
            all_outputs[mname] = {}

        # 3a. 第一批：不需要其他模块输出作为输入的模块
        # 所有模块的 derivatives（用 time-constant 参数 dt，别用 _USE_DT）
        # dydt 收集到 module_dydt（用于打包 return dydt_vec）
        # outputs 收集到 all_outputs（用于 CONNECTIONS 路由和供其他模块调用）
        # 注：这里 dt 只用于低通滤波时间常数的计算（如 dHR/dt 中的 alpha/dt），
        # 不影响 dydt 的物理量纲。Radau 积分器自己管理步长，不受这里 dt 值影响。
        _USE_DT = 0.01  # 代表性时间步长，保证 alpha/dt 不会溢出
        module_dydt: dict[str, dict] = {}

        # 心脏 — 传入当前失血率（用于 blood_volume dydt）
        module = getattr(self, "heart")
        dydt, outputs = module.derivatives(dt=_USE_DT, svr_factor=1.0,
                                            blood_loss_rate_ml_s=blood_loss_rate_ml_s)
        module_dydt["heart"] = dydt
        all_outputs["heart"] = outputs

        # 肺部 — co_input 从缓存
        module = getattr(self, "lung")
        co_input = module_inputs.get("lung", {}).get("co_input")
        dydt, outputs = module.derivatives(dt=_USE_DT, co_input=co_input)
        module_dydt["lung"] = dydt
        all_outputs["lung"] = outputs

        # 肾脏 — 三个必需位置参数都从缓存
        module = getattr(self, "kidney")
        kidney_in = module_inputs.get("kidney", {})
        dydt, outputs = module.derivatives(
            dt=_USE_DT,
            map_input=kidney_in.get("map_input", 90.0),
            cvp_input=kidney_in.get("cvp_input", 5.0),
            co_input=kidney_in.get("co_input", 1500.0),
        )
        module_dydt["kidney"] = dydt
        all_outputs["kidney"] = outputs

        # 肠道 — co_input 从缓存；输出是 gut_state dict，存入 all_outputs["gut"]
        module = getattr(self, "gut")
        gut_in = module_inputs.get("gut", {})
        dydt, gut_gut_outputs = module.derivatives(dt=_USE_DT, co_input=gut_in.get("co_input", 1500.0))
        module_dydt["gut"] = dydt
        all_outputs["gut"] = gut_gut_outputs

        # 肝脏 — co_input 从缓存，gut_state 取自肠道输出
        module = getattr(self, "liver")
        liver_in = module_inputs.get("liver", {})
        dydt, outputs = module.derivatives(
            dt=_USE_DT,
            co_input=liver_in.get("co_input", 1500.0),
            gut_state=gut_gut_outputs,  # 肠道输出作为 liver 的输入
        )
        module_dydt["liver"] = dydt
        all_outputs["liver"] = outputs

        # 内分泌 — 无外部输入
        module = getattr(self, "endocrine")
        dydt, outputs = module.derivatives(dt=0.0)
        module_dydt["endocrine"] = dydt
        all_outputs["endocrine"] = outputs

        # 神经 — map_input, lung_rr 从缓存
        module = getattr(self, "neuro")
        neuro_in = module_inputs.get("neuro", {})
        dydt, outputs = module.derivatives(
            dt=_USE_DT,
            map_input=neuro_in.get("map_input", 90.0),
            heart_hr=neuro_in.get("heart_rate_bpm", 80.0),
            lung_rr=neuro_in.get("lung_rr", 15.0),
        )
        module_dydt["neuro"] = dydt
        all_outputs["neuro"] = outputs

        # 免疫 — endocrine_cortisol 从缓存
        module = getattr(self, "immune")
        immune_in = module_inputs.get("immune", {})
        dydt, outputs = module.derivatives(
            dt=_USE_DT,
            endocrine_cortisol=immune_in.get("endocrine_cortisol"),
        )
        module_dydt["immune"] = dydt
        all_outputs["immune"] = outputs

        # 凝血 — liver_health_factor, immune_cytokine 从缓存
        module = getattr(self, "coagulation")
        coag_in = module_inputs.get("coagulation", {})
        dydt, outputs = module.derivatives(
            dt=_USE_DT,
            liver_health_factor=coag_in.get("liver_health_factor", 1.0),
            immune_cytokine=coag_in.get("immune_cytokine", 0.0),
        )
        module_dydt["coagulation"] = dydt
        all_outputs["coagulation"] = outputs

        # 淋巴 — map_input, hr_input, cytokine_input, gut_fat_absorption
        module = getattr(self, "lymphatic")
        lymph_in = module_inputs.get("lymphatic", {})
        dydt, outputs = module.derivatives(
            dt=_USE_DT,
            map_input=lymph_in.get("map_input", 80.0),
            hr_input=lymph_in.get("hr_input", 80.0),
            cytokine_input=lymph_in.get("cytokine_input", 0.0),
            gut_fat_absorption=lymph_in.get("gut_fat_absorption", False),
        )
        module_dydt["lymphatic"] = dydt
        all_outputs["lymphatic"] = outputs

        # 体液 — map_input 从缓存
        module = getattr(self, "fluid")
        fluid_in = module_inputs.get("fluid", {})
        dydt, outputs = module.derivatives(dt=0.0, map_input=fluid_in.get("map_input"))
        module_dydt["fluid"] = dydt
        all_outputs["fluid"] = outputs

        # 疾病
        if self.disease is not None and hasattr(self.disease, 'compute_derivatives'):
            engine_state = self._get_engine_state()
            disease_dydt = self.disease.compute_derivatives(engine_state)
            all_outputs["disease"] = disease_dydt

        # 4. 按 CONNECTIONS 表路由 outputs → cached inputs（供下次 rhs 调用用）
        for (src_mod, src_var), targets in CONNECTIONS.items():
            val = all_outputs.get(src_mod, {}).get(src_var)
            if val is not None:
                for (tgt_mod, tgt_var) in targets:
                    if tgt_mod not in self._cached_inputs:
                        self._cached_inputs[tgt_mod] = {}
                    self._cached_inputs[tgt_mod][tgt_var] = val

        # ── 5. 打包 dydt — 使用各模块 derivatives() 返回的 dydt（而非 outputs）
        # blood_volume 的 dydt 现在由 heart.derivatives() 直接提供（blood_loss_rate_ml_s）
        # Radau 通过 y 向量积分 blood_volume 状态变量，不再需要外部应用
        state_map = self._build_unified_state_map()
        n = len(state_map)
        dydt_vec = np.zeros(n)

        for (mname, vname), idx in state_map.items():
            if mname == "disease":
                dydt_vec[idx] = module_dydt.get("disease", {}).get(vname, 0.0)
            else:
                dydt_vec[idx] = module_dydt.get(mname, {}).get(vname, 0.0)

        return dydt_vec

    def _build_ivp_state_map(self) -> dict[tuple[str, str], int]:
        """建立 (module_name, var_name) → y-array index 映射表。"""
        ivp_state_map: dict[tuple[str, str], int] = {}
        idx = 0
        for module_name in self._get_ivp_disease_modules():
            module = getattr(self, module_name)
            for var_name in module._state_vars:
                ivp_state_map[(module_name, var_name)] = idx
                idx += 1
        return ivp_state_map

    def _get_ivp_disease_modules(self) -> list[str]:
        """返回带有疾病 ODE 状态变量的模块名列表。"""
        # 疾病状态存在 disease 模块里
        modules = []
        if self.disease is not None and hasattr(self.disease, 'compute_derivatives'):
            modules.append('disease')
        return modules

    def _pack_disease_state(self) -> np.ndarray:
        """将当前疾病状态打包成 numpy 向量 y0。"""
        state_map = self._build_ivp_state_map()
        n = len(state_map)
        y0 = np.zeros(n)
        for (mname, vname), idx in state_map.items():
            if mname == 'disease':
                y0[idx] = self.disease._state_vars[vname]
        return y0

    def _unpack_disease_state(self, y: np.ndarray) -> None:
        """将 numpy 向量 y 分解到各疾病模块的 _state_vars。"""
        state_map = self._build_ivp_state_map()
        for (mname, vname), idx in state_map.items():
            if mname == 'disease':
                self.disease._state_vars[vname] = y[idx]

    def _get_engine_state(self) -> dict:
        """收集当前血液/器官状态（供导数计算用）。"""
        return {
            "heart": {
                "heart_rate_bpm": self.heart.heart_rate,
                "MAP_mmHg": self.heart.mean_arterial_pressure,
                "cardiac_output_ml_min": self.heart.cardiac_output,
            },
            "lung": {"arterial_PO2": self.blood.arterial_PO2_mmHg},
            "kidney": {"GFR_ml_min": self.kidney.GFR},
        }

    def _ivp_rhs(self, t: float, y: np.ndarray) -> np.ndarray:
        """ODE 右端函数（供 solve_ivp 调用）。"""
        self._unpack_disease_state(y)
        engine_state = self._get_engine_state()
        state_map = self._build_ivp_state_map()
        n = len(state_map)
        dydt = np.zeros(n)

        for (mname, vname), idx in state_map.items():
            if mname == 'disease':
                derivs = self.disease.compute_derivatives(engine_state)
                dydt[idx] = derivs.get(vname, 0.0)

        return dydt

    def run_ivp(self, t_end: float, dt_save: float = 1.0):
        """使用 Radau 隐式求解器跑 ODE 疾病子系统。

        Args:
            t_end: 仿真结束时间（秒）
            dt_save: 采样间隔（秒）

        Returns:
            solve_ivp result object with sol.t, sol.y
        """
        from scipy.integrate import solve_ivp

        y0 = self._pack_disease_state()
        t_eval = np.arange(0.0, t_end + dt_save, dt_save)

        sol = solve_ivp(
            self._ivp_rhs,
            [0.0, t_end],
            y0,
            method='Radau',
            rtol=1e-6,
            atol=1e-9,
            t_eval=t_eval,
            dense_output=True,
            vectorized=False,
        )
        return sol

    def run_unified_ivp(self, t_end: float, dt_save: float = 1.0):
        """使用 Radau 隐式求解器跑统一 ODE 系统（所有器官 + 疾病）。

        半隐式耦合：_cached_inputs 在每次 rhs 调用时从上一输出的 outputs 填充。
        Radau 的 Newton 迭代会收敛耦合解。

        Args:
            t_end: 仿真结束时间（秒）
            dt_save: 采样间隔（秒）

        Returns:
            solve_ivp result object with sol.t, sol.y
        """
        from scipy.integrate import solve_ivp

        # 初始化缓存（启动时为空，使用模块默认值）
        self._cached_inputs.clear()

        y0 = self._pack_unified_state()
        state_map = self._build_unified_state_map()

        # 预热：调用一次 rhs 以初始化 _cached_inputs
        if len(y0) > 0:
            _ = self._unified_rhs(0.0, y0)

        t_eval = np.arange(0.0, t_end + dt_save, dt_save)
        t_eval = t_eval[t_eval <= t_end]  # clip to t_span

        sol = solve_ivp(
            self._unified_rhs,
            [0.0, t_end],
            y0,
            method='Radau',
            rtol=1e-5,
            atol=1e-8,
            t_eval=t_eval,
            dense_output=True,
            vectorized=False,
        )
        return sol

    def run_scenario(self, scenario_name: str):
        """
        运行预设场景
        """
        scenarios = {
            "normal": self._scenario_normal,
            "blood_loss": self._scenario_blood_loss,
            "fluid_resuscitation": self._scenario_fluid_resuscitation,
            "exercise": self._scenario_exercise,
            "dehydration": self._scenario_dehydration,
            "cocaine": self._scenario_cocaine,
            "cocaine_high": self._scenario_cocaine_high,
        }

        if scenario_name not in scenarios:
            print(f"未知场景：{scenario_name}")
            print(f"可用场景：{list(scenarios.keys())}")
            return

        print(f"\n{'='*60}")
        print(f"  场景：{scenario_name}")
        print(f"{'='*60}")

        # 重置
        self.__init__(body_weight_kg=self.w)
        scenarios[scenario_name]()
        self.simulate(T_MAX_MINUTES, verbose=True)

        print(f"\n事件记录：")
        for event in self.event_log[-5:]:
            print(f"  {event}")

        self.print_summary()

    def _scenario_normal(self):
        """正常稳态"""
        pass

    def _scenario_blood_loss(self):
        """失血 200 mL"""
        self.schedule_event(60.0, "blood_loss", {"volume_ml": 200.0})

    def _scenario_fluid_resuscitation(self):
        """失血后输液复苏"""
        self.schedule_event(60.0, "blood_loss", {"volume_ml": 200.0})
        self.schedule_event(180.0, "fluid_infusion", {"volume_ml": 300.0, "type": "saline"})

    def _scenario_exercise(self):
        """运动应激"""
        self.schedule_event(30.0, "exercise", {"intensity": 0.8, "duration_s": 180})

    def _scenario_dehydration(self):
        """脱水（无饮水 12h）"""
        # 简化：相当于血容量下降 8%
        self.schedule_event(10.0, "blood_loss", {"volume_ml": total_blood_volume_ml(self.w) * 0.05})

    def _scenario_cocaine(self):
        """可卡因中毒（3 mg/kg IV）— 基于 Liu et al. 1993
        直接心脏抑制（短暂）+ 交感外周血管收缩（持续 ≥30 min）
        """
        self.schedule_event(30.0, "cocaine", {"dose_mg_kg": 3.0})

    def _scenario_cocaine_high(self):
        """可卡因高剂量（6 mg/kg IV）— 心脏抑制更明显"""
        self.schedule_event(30.0, "cocaine", {"dose_mg_kg": 6.0})

    def to_minimal_snapshot(self) -> dict:
        """
        Serialize the essential readable engine state for session persistence.

        Omits full history to save space.  Stores only the last value of each
        vital so that an instructor can review a completed session without
        replaying the full simulation.
        """
        h = self.history

        def _last(key: str, fallback):
            vals = h.get(key, [])
            return vals[-1] if vals else fallback

        return {
            # ── Simulation time ──────────────────────────────────────────
            "time_s": self.current_time_s,

            # ── Cardiovascular ───────────────────────────────────────────
            "HR_bpm": round(_last("HR_bpm", self.heart.heart_rate), 1),
            "MAP_mmHg": round(_last("MAP_mmHg", self.heart.mean_arterial_pressure), 1),
            "CO_ml_min": round(_last("CO_ml_min", self.heart.cardiac_output), 1),
            "CVP_mmHg": round(_last("CVP_mmHg", self.heart.central_venous_pressure), 1),
            "blood_volume_ml": round(
                _last("blood_volume_ml", self.heart.circulating_volume_ml), 1
            ),
            "contractility_factor": round(
                _last("contractility_factor", self.heart.contractility_factor), 3
            ),

            # ── Respiratory ─────────────────────────────────────────────
            "RR": round(_last("RR", self.lung.respiratory_rate), 1),
            "art_PO2": round(_last("art_PO2", self.blood.arterial_PO2_mmHg), 1),
            "art_PCO2": round(_last("art_PCO2", self.blood.arterial_PCO2_mmHg), 1),
            "saturation": round(_last("saturation", self.blood.arterial_saturation) * 100, 1),

            # ── Renal ───────────────────────────────────────────────────
            "GFR": round(_last("GFR", self.kidney.GFR), 1),
            "urine_ml_min": round(_last("urine_ml_min", self.kidney.urine_output), 3),
            "BUN": round(_last("BUN", self.blood.bun_mg_dL), 1),

            # ── Metabolic / Blood ──────────────────────────────────────
            "pH": round(_last("pH", self.blood.arterial_pH), 3),
            "glucose_mmol_L": round(_last("glucose", self.blood.glucose_mmol_L), 2),
            "lactate_mmol_L": round(self.blood.lactate_mmol_L, 2),
            "core_temperature_C": round(self.blood.core_temperature_C, 1),

            # ── Fluid compartments ───────────────────────────────────────
            "fluid_vascular_ml": round(
                _last("fluid_vascular_ml", self.fluid.vascular_volume_ml), 1
            ),
            "fluid_isf_ml": round(_last("fluid_isf_ml", self.fluid.isf_volume_ml), 1),
            "fluid_icf_ml": round(_last("fluid_icf_ml", self.fluid.icf_volume_ml), 1),

            # ── Organ health ────────────────────────────────────────────
            "heart_health": round(self.organ_health.heart_health, 3),
            "lung_health": round(self.organ_health.lung_health, 3),
            "kidney_health": round(self.organ_health.kidney_health, 3),

            # ── Lifecycle ───────────────────────────────────────────────
            "lifecycle": self.lifecycle.serialize(),

            # ── Disease state (readable summary) ────────────────────────
            "disease_state": self.disease.summary() if self.disease else None,
        }

    def print_summary(self):
        """打印当前状态摘要"""
        print(f"\n--- 当前状态 (t={self.current_time_s:.1f}s) ---")
        print(f"心血管: HR={self.heart.heart_rate:.0f} bpm, "
              f"CO={self.heart.cardiac_output:.0f} mL/min, "
              f"MAP={self.heart.mean_arterial_pressure:.1f} mmHg")
        print(f"  收缩力={self.heart.contractility_factor:.3f}, "
              f"SVR={self.heart.SVR:.2f} (factor={self.toxicology.svr_factor:.2f})")
        print(f"呼吸: RR={self.lung.respiratory_rate:.0f} /min, "
              f"PaO2={self.blood.arterial_PO2_mmHg:.0f} mmHg, "
              f"PaCO2={self.blood.arterial_PCO2_mmHg:.0f} mmHg")
        print(f"肾脏: GFR={self.kidney.GFR:.1f} mL/min, "
              f"尿量={self.kidney.urine_output:.3f} mL/min, "
              f"BUN={self.blood.bun_mg_dL:.1f} mg/dL")
        print(f"血液: 血糖={self.blood.glucose_mmol_L:.2f} mmol/L, "
              f"血容量={self.heart.circulating_volume_ml:.0f} mL, "
              f"pH={self.blood.arterial_pH:.3f}")
        hh = self.organ_health
        if hh.heart_health < 0.95 or hh.lung_health < 0.95 or hh.kidney_health < 0.95:
            print(f"器官健康: 心={hh.heart_health:.2f}  肺={hh.lung_health:.2f}  肾={hh.kidney_health:.2f}")
        print(f"肝脏: 代谢={self.liver.metabolic_activity:.2f}  解毒={self.liver.detox_capacity:.2f}  糖原={self.liver.glycogen_fraction:.2f}")
        print(f"肠道: 蠕动={self.gut.gut_motility:.2f}  屏障={self.gut.barrier_integrity:.2f}  菌群={self.gut.microbiome_activity:.2f}")


# 参数导入已移至文件顶部
