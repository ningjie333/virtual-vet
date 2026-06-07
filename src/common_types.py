"""
Common Types — 跨模块共享类型定义

设计原则：
  - FactorCommand 单一来源，消除 5+ 重复定义
  - _PARAM_PATHS 合并自 simulation.py + physiology_engine.py（已去重）
  - 所有器官模块从此模块导入，不再各自定义
"""

from dataclasses import dataclass
from typing import Literal


# ── FactorCommand 指令结构体 ─────────────────────────────────────────────────
# 原定义位置：simulation.py:47, physiology_engine.py:50（死代码）, immune.py:25,
#             neuro.py:19, coagulation.py:21, lymphatic.py:20
# 统一后：从此模块导入

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
#
# 合并自 simulation.py（95 条目）+ physiology_engine.py（87 条目），已去重。
# physiology_engine.py 独有的条目已并入；重复条目以 simulation.py 为准。

_PARAM_PATHS: dict[str, tuple[str, str]] = {
    # ── Heart ──────────────────────────────────────────────────────────────
    "heart.heart_rate":              ("heart", "heart_rate"),
    "heart.contractility_factor":    ("heart", "contractility_factor"),
    "heart.SVR":                     ("heart", "SVR"),
    "heart.MAP":                     ("heart", "mean_arterial_pressure"),
    "heart.CVP":                     ("heart", "central_venous_pressure"),
    "heart.blood_volume":            ("heart", "circulating_volume_ml"),
    "heart.stroke_volume":           ("heart", "stroke_volume"),
    # ── Lung ──────────────────────────────────────────────────────────────
    "lung.diffusion_coefficient":    ("lung", "diffusion_coefficient"),
    "lung.PaO2":                     ("lung", "alveolar_PO2"),
    "lung.PaCO2":                    ("lung", "alveolar_PCO2"),
    "lung.VQ_ratio":                 ("lung", "VQ_ratio"),
    "lung.respiratory_rate":         ("lung", "respiratory_rate"),
    # ── Kidney ────────────────────────────────────────────────────────────
    "kidney.GFR":                        ("kidney", "GFR"),
    "kidney.urine_output":               ("kidney", "urine_output"),
    "kidney.renal_blood_flow":           ("kidney", "renal_blood_flow"),
    "kidney._disease_gfr_multiplier":    ("kidney", "_disease_gfr_multiplier"),
    # ── Blood ─────────────────────────────────────────────────────────────
    "blood.sodium_mEq_L":          ("blood", "sodium_mEq_L"),
    "blood.potassium":             ("blood", "potassium_mEq_L"),
    "blood.pH":                    ("blood", "arterial_pH"),
    "blood.temperature":           ("blood", "core_temperature_C"),
    "blood.BUN":                   ("blood", "bun_mg_dL"),
    "blood.HCO3":                  ("fluid", "vascular_hco3_meq_l"),
    "blood.glucose":               ("blood", "glucose_mmol_L"),
    "blood.lactate":               ("blood", "lactate_mmol_L"),
    "blood.creatinine":            ("blood", "creatinine_mg_dL"),
    "blood.red_cell_volume_ml":    ("blood", "red_cell_volume_ml"),
    "blood.bilirubin_mg_dL":       ("blood", "bilirubin_mg_dL"),
    "blood.ketone_mmol_L":         ("blood", "ketone_mmol_L"),
    "blood.PLT":                   ("blood", "PLT"),
    # Blood — liver/gut markers
    "blood.ALT":                   ("blood", "ALT_U_L"),
    "blood.AST":                   ("blood", "AST_U_L"),
    "blood.ALP":                   ("blood", "ALP_U_L"),
    "blood.GGT":                   ("blood", "GGT_U_L"),
    "blood.albumin":               ("blood", "albumin_g_dL"),
    "blood.ammonia":               ("blood", "ammonia_umol_L"),
    "blood.bile_acids":            ("blood", "bile_acids_umol_L"),
    "blood.amino_acids":           ("blood", "amino_acids_g_L"),
    "blood.fatty_acids":           ("blood", "fatty_acids_mmol_L"),
    # Blood — coupling engine targets
    "blood.arterial_PO2_mmHg":     ("blood", "arterial_PO2_mmHg"),
    "blood.arterial_PCO2_mmHg":    ("blood", "arterial_PCO2_mmHg"),
    # Blood — coagulation aliases (coag.* 和 blood.* 指向同一属性)
    "blood.PT_sec":                ("blood", "PT_sec"),
    "blood.aPTT_sec":              ("blood", "aPTT_sec"),
    "blood.fibrinogen_mg_dL":      ("blood", "fibrinogen_mg_dL"),
    # Blood — lymphatic aliases
    "blood.splenic_reserve_mL":    ("blood", "splenic_reserve_mL"),
    "blood.interstitial_fluid_mL": ("blood", "interstitial_fluid_mL"),
    # ── Gut ────────────────────────────────────────────────────────────────
    "gut.motility":                ("gut", "gut_motility"),
    "gut.barrier_integrity":       ("gut", "barrier_integrity"),
    "gut.microbiome_activity":     ("gut", "microbiome_activity"),
    # ── Liver ─────────────────────────────────────────────────────────────
    "liver.metabolic_activity":    ("liver", "metabolic_activity"),
    "liver.detox_capacity":        ("liver", "detox_capacity"),
    "liver.cyp450_activity":       ("liver", "cyp450_activity"),
    "liver.glycogen_fraction":     ("liver", "glycogen_fraction"),
    "liver.bilirubin_conjugation": ("liver", "bilirubin_conjugation"),
    # ── Endocrine ──────────────────────────────────────────────────────────
    "endocrine.T3_factor":         ("endocrine", "T3_factor"),
    "endocrine.T4_factor":         ("endocrine", "T4_ug_dL"),
    "endocrine.metabolic_rate":    ("endocrine", "metabolic_rate"),
    "endocrine.T3_ng_dL":          ("endocrine", "T3_ng_dL"),
    "endocrine.T4_ug_dL":          ("endocrine", "T4_ug_dL"),
    "endocrine.insulin_factor":    ("endocrine", "insulin_factor"),
    "endocrine.glucagon_factor":   ("endocrine", "glucagon_factor"),
    "endocrine.insulin_uU_mL":     ("endocrine", "insulin_uU_mL"),
    "endocrine.glucagon_pg_mL":   ("endocrine", "glucagon_pg_mL"),
    "endocrine.cortisol_factor":   ("endocrine", "cortisol_factor"),
    "endocrine.cortisol_ug_dL":    ("endocrine", "cortisol_ug_dL"),
    "endocrine.HPA_axis":          ("endocrine", "HPA_axis"),
    "endocrine.epinephrine_pg_mL": ("endocrine", "epinephrine_pg_mL"),
    "endocrine.norepinephrine_pg_mL": ("endocrine", "norepinephrine_pg_mL"),
    "endocrine.PTH_pg_mL":         ("endocrine", "PTH_pg_mL"),
    "endocrine.calcium_mg_dL":      ("endocrine", "calcium_mg_dL"),
    "endocrine.phosphate_mg_dL":   ("endocrine", "phosphate_mg_dL"),
    "endocrine.calcium_factor":    ("endocrine", "calcium_factor"),
    "endocrine.GH_ng_mL":          ("endocrine", "GH_ng_mL"),
    "endocrine.IGF1_nmol_L":       ("endocrine", "IGF1_nmol_L"),
    "endocrine.growth_factor":     ("endocrine", "growth_factor"),
    # ── Neuro ──────────────────────────────────────────────────────────────
    "neuro.sympathetic_tone":     ("neuro", "sympathetic_tone"),
    "neuro.parasympathetic_tone":  ("neuro", "parasympathetic_tone"),
    "neuro.consciousness":         ("neuro", "consciousness"),
    "neuro.seizure":               ("neuro", "seizure"),
    "neuro.pain_level":            ("neuro", "pain_level"),
    "neuro.chemoreceptor_drive":   ("neuro", "chemoreceptor_drive"),
    # ── Immune ─────────────────────────────────────────────────────────────
    "immune.cytokine_level":       ("immune", "cytokine_level"),
    "immune.wbc_count":            ("immune", "wbc_count"),
    "immune.crp_level":            ("immune", "crp_level"),
    "immune.acute_phase_response": ("immune", "acute_phase_response"),
    "immune.immune_suppression":   ("immune", "immune_suppression"),
    "immune.coagulation_state":    ("immune", "coagulation_state"),
    "immune._infection_signal":     ("immune", "_infection_signal"),
    # ── Coagulation ────────────────────────────────────────────────────────
    "coag.PT_sec":                 ("blood", "PT_sec"),
    "coag.aPTT_sec":               ("blood", "aPTT_sec"),
    "coag.fibrinogen_mg_dL":       ("blood", "fibrinogen_mg_dL"),
    "coag.factor_VII":             ("coagulation", "factor_VII"),
    "coag.coagulation_state":      ("coagulation", "coagulation_state"),
    # ── Lymphatic ──────────────────────────────────────────────────────────
    "lymph.splenic_reserve_mL":    ("blood", "splenic_reserve_mL"),
    "lymph.lymph_flow":            ("lymphatic", "lymph_flow_rate"),
    "lymph.interstitial_fluid":    ("blood", "interstitial_fluid_mL"),
}


def resolve_param_path(target: str) -> tuple[str, str] | None:
    """
    解析 FactorCommand target → (module_name, attr_name)。

    Returns:
        (module_name, attr_name) 或 None（未注册的 target）
    """
    return _PARAM_PATHS.get(target)


def validate_target(target: str) -> bool:
    """检查 target 是否在注册表中。"""
    return target in _PARAM_PATHS
