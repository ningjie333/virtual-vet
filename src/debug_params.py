"""
Debug Params — 生理参数调试器后端逻辑。

独立于游戏逻辑，用于：
- 查看不同年龄/体重/品种的生理参数
- 验证生命周期系统效果
- 调试器官耦合问题

不创建 GameState，不涉及 AP、疾病、时间管理。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── 品种数据加载 ─────────────────────────────────────────────────────────────

_breed_data: dict[str, Any] | None = None


def _load_breed_data() -> dict[str, Any]:
    """加载品种→体重映射数据。"""
    global _breed_data
    if _breed_data is not None:
        return _breed_data

    data_dir = Path(__file__).parent.parent / "data"
    path = data_dir / "breed_standards.json"
    if not path.exists():
        logger.warning("breed_standards.json not found at %s", path)
        return {}

    with open(path, encoding="utf-8") as f:
        _breed_data = json.load(f)
    return _breed_data


def get_available_species() -> dict[str, Any]:
    """
    返回可用的物种、品种和体重范围。

    Returns:
        {
            "canine": {
                "labrador": {"display": "拉布拉多", "weight_kg": {"min": 25, "max": 36, "default": 30}, "size_category": "large"},
                ...
            },
            ...
        }
    """
    data = _load_breed_data()
    # 移除 _schema 和 _comment
    return {k: v for k, v in data.items() if not k.startswith("_")}


def get_breed_weight(species: str, breed: str) -> float | None:
    """
    获取品种的默认体重。

    Args:
        species: 物种（如 "canine"）
        breed: 品种（如 "labrador"）

    Returns:
        默认体重（kg），未找到返回 None
    """
    data = _load_breed_data()
    species_data = data.get(species, {})
    breed_data = species_data.get(breed, {})
    return breed_data.get("weight_kg", {}).get("default")


# ── 生理参数计算 ─────────────────────────────────────────────────────────────

def compute_debug_params(
    species: str,
    breed: str,
    age_days: float,
    weight_kg: float | None = None,
) -> dict[str, Any]:
    """
    计算指定物种/品种/年龄的生理参数。

    流程：
    1. 如果 weight_kg 为 None，从品种数据查找默认值
    2. 创建 VirtualCreature（应用体重缩放）
    3. 应用生命周期（应用年龄修正）
    4. 读取所有器官参数

    Args:
        species: 物种（如 "canine"）
        breed: 品种（如 "labrador"）
        age_days: 年龄（天）
        weight_kg: 体重（kg），可选

    Returns:
        {
            "input": {...},
            "lifecycle": {...},
            "organs": {...},
            "summary": {...}
        }
    """
    # 1. 解析体重
    if weight_kg is None:
        weight_kg = get_breed_weight(species, breed)
        if weight_kg is None:
            weight_kg = 20.0  # 默认值

    # 2. 创建引擎（不创建 GameState，不涉及游戏逻辑）
    from simulation import VirtualCreature

    creature = VirtualCreature(
        body_weight_kg=weight_kg,
        species=species,
        age_days=age_days,
    )

    # 3. 应用生命周期
    lifecycle_info = {}
    if creature.lifecycle is not None and creature.lifecycle.mode.value != "bypass":
        creature.lifecycle.capture_baselines(creature)
        creature.lifecycle.apply(creature)
        lifecycle_info = {
            "phase": creature.lifecycle._state.phase.value,
            "age_days": age_days,
            "organ_function": creature.lifecycle.organ_function,
        }

    # 4. 运行一步仿真，让所有系统达到稳态
    #    这样 RAAS、内分泌等系统会从初始值（0）计算到正常生理值
    creature.step()

    # 5. 读取所有器官参数
    organs = _extract_organ_params(creature)

    # 5. 计算统计
    summary = _compute_summary(organs)

    return {
        "input": {
            "species": species,
            "breed": breed,
            "age_days": age_days,
            "weight_kg": weight_kg,
        },
        "lifecycle": lifecycle_info,
        "organs": organs,
        "summary": summary,
    }


def _extract_organ_params(creature) -> dict[str, dict[str, Any]]:
    """从 VirtualCreature 提取所有器官参数。"""
    organs: dict[str, dict[str, Any]] = {}

    # 心脏
    organs["heart"] = {
        "heart_rate": {"value": creature.heart.heart_rate, "unit": "bpm", "label_zh": "心率"},
        "stroke_volume": {"value": creature.heart.stroke_volume, "unit": "mL", "label_zh": "每搏输出量"},
        "cardiac_output": {"value": creature.heart.cardiac_output, "unit": "mL/min", "label_zh": "心输出量"},
        "mean_arterial_pressure": {"value": creature.heart.mean_arterial_pressure, "unit": "mmHg", "label_zh": "平均动脉压"},
        "SVR": {"value": creature.heart.SVR, "unit": "mmHg·s/mL", "label_zh": "体循环血管阻力"},
        "central_venous_pressure": {"value": creature.heart.central_venous_pressure, "unit": "mmHg", "label_zh": "中心静脉压"},
        "contractility_factor": {"value": creature.heart.contractility_factor, "unit": "--", "label_zh": "收缩力因子"},
        "circulating_volume_ml": {"value": creature.heart.circulating_volume_ml, "unit": "mL", "label_zh": "循环血量"},
    }

    # 肺
    organs["lung"] = {
        "respiratory_rate": {"value": creature.lung.respiratory_rate, "unit": "/min", "label_zh": "呼吸频率"},
        "tidal_volume": {"value": creature.lung.tidal_volume, "unit": "mL", "label_zh": "潮气量"},
        "diffusion_coefficient": {"value": creature.lung.diffusion_coefficient, "unit": "--", "label_zh": "肺扩散系数"},
        "VQ_ratio": {"value": creature.lung.VQ_ratio, "unit": "--", "label_zh": "通气/灌注比"},
    }

    # 肾脏
    organs["kidney"] = {
        "GFR": {"value": creature.kidney.GFR, "unit": "mL/min", "label_zh": "肾小球滤过率"},
        "urine_output": {"value": creature.kidney.urine_output, "unit": "mL/min", "label_zh": "尿量"},
        "renal_blood_flow": {"value": creature.kidney.renal_blood_flow, "unit": "mL/min", "label_zh": "肾血流量"},
        "renin_activity": {"value": creature.kidney.renin_activity, "unit": "--", "label_zh": "肾素活性"},
        "angiotensin_II": {"value": creature.kidney.angiotensin_II, "unit": "--", "label_zh": "血管紧张素II"},
        "aldosterone": {"value": creature.kidney.aldosterone, "unit": "--", "label_zh": "醛固酮"},
    }

    # 血液
    organs["blood"] = {
        "arterial_pH": {"value": creature.blood.arterial_pH, "unit": "--", "label_zh": "动脉血pH"},
        "arterial_PO2_mmHg": {"value": creature.blood.arterial_PO2_mmHg, "unit": "mmHg", "label_zh": "动脉氧分压"},
        "arterial_PCO2_mmHg": {"value": creature.blood.arterial_PCO2_mmHg, "unit": "mmHg", "label_zh": "动脉CO2分压"},
        "arterial_saturation": {"value": creature.blood.arterial_saturation, "unit": "%", "label_zh": "血氧饱和度"},
        "sodium_mEq_L": {"value": creature.blood.sodium_mEq_L, "unit": "mEq/L", "label_zh": "血钠"},
        "potassium_mEq_L": {"value": creature.blood.potassium_mEq_L, "unit": "mEq/L", "label_zh": "血钾"},
        "glucose_mmol_L": {"value": creature.blood.glucose_mmol_L, "unit": "mmol/L", "label_zh": "血糖"},
        "lactate_mmol_L": {"value": creature.blood.lactate_mmol_L, "unit": "mmol/L", "label_zh": "血乳酸"},
        "bun_mg_dL": {"value": creature.blood.bun_mg_dL, "unit": "mg/dL", "label_zh": "血尿素氮"},
        "creatinine_mg_dL": {"value": creature.blood.creatinine_mg_dL, "unit": "mg/dL", "label_zh": "血肌酐"},
        "core_temperature_C": {"value": creature.blood.core_temperature_C, "unit": "°C", "label_zh": "核心体温"},
    }

    # 体液
    organs["fluid"] = {
        "vascular_volume_ml": {"value": creature.fluid.vascular_volume_ml, "unit": "mL", "label_zh": "血管内容量"},
        "isf_volume_ml": {"value": creature.fluid.isf_volume_ml, "unit": "mL", "label_zh": "间质液容量"},
        "icf_volume_ml": {"value": creature.fluid.icf_volume_ml, "unit": "mL", "label_zh": "细胞内液容量"},
        "vascular_hco3_meq_l": {"value": creature.fluid.vascular_hco3_meq_l, "unit": "mEq/L", "label_zh": "碳酸氢根"},
    }

    # 肝脏
    organs["liver"] = {
        "metabolic_activity": {"value": creature.liver.metabolic_activity, "unit": "--", "label_zh": "代谢活性"},
        "detox_capacity": {"value": creature.liver.detox_capacity, "unit": "--", "label_zh": "解毒能力"},
        "cyp450_activity": {"value": creature.liver.cyp450_activity, "unit": "--", "label_zh": "CYP450活性"},
        "glycogen_fraction": {"value": creature.liver.glycogen_fraction, "unit": "--", "label_zh": "糖原储备"},
    }

    # 肠道
    organs["gut"] = {
        "gut_motility": {"value": creature.gut.gut_motility, "unit": "--", "label_zh": "肠道动力"},
        "barrier_integrity": {"value": creature.gut.barrier_integrity, "unit": "--", "label_zh": "肠屏障完整性"},
        "microbiome_activity": {"value": creature.gut.microbiome_activity, "unit": "--", "label_zh": "微生物活性"},
    }

    # 内分泌
    organs["endocrine"] = {
        "T3_ng_dL": {"value": creature.endocrine.T3_ng_dL, "unit": "ng/dL", "label_zh": "T3"},
        "insulin_uU_mL": {"value": creature.endocrine.insulin_uU_mL, "unit": "uU/mL", "label_zh": "胰岛素"},
        "cortisol_ug_dL": {"value": creature.endocrine.cortisol_ug_dL, "unit": "ug/dL", "label_zh": "皮质醇"},
        "metabolic_rate": {"value": creature.endocrine.metabolic_rate, "unit": "--", "label_zh": "代谢率"},
    }

    # 神经
    organs["neuro"] = {
        "sympathetic_tone": {"value": creature.neuro.sympathetic_tone, "unit": "--", "label_zh": "交感神经张力"},
        "parasympathetic_tone": {"value": creature.neuro.parasympathetic_tone, "unit": "--", "label_zh": "副交感神经张力"},
        "consciousness": {"value": creature.neuro.consciousness, "unit": "--", "label_zh": "意识水平"},
        "pain_level": {"value": creature.neuro.pain_level, "unit": "--", "label_zh": "疼痛等级"},
    }

    # 免疫
    organs["immune"] = {
        "cytokine_level": {"value": creature.immune.cytokine_level, "unit": "--", "label_zh": "细胞因子水平"},
        "wbc_count": {"value": creature.immune.wbc_count, "unit": "x10^9/L", "label_zh": "白细胞计数"},
        "crp_level": {"value": creature.immune.crp_level, "unit": "mg/L", "label_zh": "C反应蛋白"},
    }

    # 凝血（PT/aPTT 写入 blood 模块）
    organs["coagulation"] = {
        "factor_VII": {"value": creature.coagulation.factor_VII, "unit": "--", "label_zh": "凝血因子VII"},
        "factor_V": {"value": creature.coagulation.factor_V, "unit": "--", "label_zh": "凝血因子V"},
        "factor_II": {"value": creature.coagulation.factor_II, "unit": "--", "label_zh": "凝血因子II"},
        "coagulation_state": {"value": creature.coagulation.coagulation_state, "unit": "--", "label_zh": "凝血状态"},
        "fibrinogen": {"value": creature.coagulation.fibrinogen, "unit": "mg/dL", "label_zh": "纤维蛋白原"},
    }

    # 淋巴
    organs["lymphatic"] = {
        "splenic_reserve_mL": {"value": creature.lymphatic.splenic_reserve_mL, "unit": "mL", "label_zh": "脾脏储血量"},
        "lymph_flow_rate": {"value": creature.lymphatic.lymph_flow_rate, "unit": "mL/min", "label_zh": "淋巴回流速率"},
    }

    # 四舍五入所有值
    for organ_name, params in organs.items():
        for param_name, param_info in params.items():
            if isinstance(param_info["value"], float):
                param_info["value"] = round(param_info["value"], 4)

    return organs


def _compute_summary(organs: dict[str, dict[str, Any]]) -> dict[str, int]:
    """计算参数统计。"""
    total = 0
    for params in organs.values():
        total += len(params)
    return {
        "total": total,
        "organs": len(organs),
    }
