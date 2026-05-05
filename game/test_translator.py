"""
Test Translator — 把 ODE 引擎的原始数值翻译成玩家可见的检查报告。

输入: VirtualCreature 实例（通过属性访问当前引擎状态）
输出: 结构化检查报告 dict（含参数值、正常范围、异常标记、中文描述）

支持的检查类型:
  physical / auscultation / inspection / blood_routine / blood_biochem /
  blood_gas / chest_xray / ultrasound / ct / ecg
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.simulation import VirtualCreature

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 生理参考范围（犬类 20kg）
# ──────────────────────────────────────────────
NORMAL_RANGES: dict[str, tuple[float, float, str]] = {
    # 心血管
    "HR":       (60, 120, "bpm"),
    "MAP":      (80, 120, "mmHg"),
    "CVP":      (0, 5, "mmHg"),
    # 呼吸
    "RR":       (10, 30, "/min"),
    "SpO2":     (95, 100, "%"),
    "PaO2":     (80, 110, "mmHg"),
    "PaCO2":    (35, 45, "mmHg"),
    "pH":       (7.35, 7.45, ""),
    # 肾脏
    "GFR":      (60, 120, "mL/min"),
    "BUN":      (10, 30, "mg/dL"),
    "Na":       (140, 155, "mEq/L"),
    "K":        (3.5, 5.5, "mEq/L"),
    # 代谢
    "Glu":      (3.3, 6.1, "mmol/L"),
    "Lactate":  (0.5, 2.5, "mmol/L"),
    # 血常规
    "HCT":     (37, 55, "%"),
    "WBC":     (6.0, 17.0, "×10⁹/L"),
    "PLT":     (150, 500, "×10⁹/L"),
    # 体温
    "Temp":    (38.0, 39.2, "°C"),
}

# 危急值阈值（超出即为 critical）
CRITICAL_THRESHOLDS: dict[str, tuple[float, float]] = {
    "HR":      (40, 180),
    "MAP":     (50, 160),
    "SpO2":    (85, 100),   # 低于 85% 为危急
    "PaO2":    (50, 150),
    "PaCO2":   (25, 65),
    "pH":      (7.1, 7.6),
    "Temp":    (37.0, 41.0),
    "Glu":     (2.0, 15.0),
    "Lactate": (0.0, 5.0),
}


def _flag(value: float, param: str) -> str:
    """根据正常范围和危急值返回 low / normal / high / critical"""
    lo, hi = NORMAL_RANGES[param][:2]
    if value < lo:
        direction = "low"
    elif value > hi:
        direction = "high"
    else:
        return "normal"

    # 检查是否达到危急值
    if param in CRITICAL_THRESHOLDS:
        crit_lo, crit_hi = CRITICAL_THRESHOLDS[param]
        if value < crit_lo or value > crit_hi:
            return "critical"
    return direction


def _result_entry(param: str, value: float, flag: str) -> dict:
    """生成单个检查结果的标准化条目"""
    lo, hi, unit = NORMAL_RANGES[param]
    return {
        "param": param,
        "value": round(value, 2),
        "unit": unit,
        "normal_range": f"{lo}-{hi}",
        "flag": flag,
    }


def _get_state(creature: VirtualCreature) -> dict:
    """
    从 VirtualCreature 实例提取当前状态快照。

    优先从 history 读取最新值（包含疾病模块修改后的结果），
    history 为空时回退到直接读取器官属性。
    """
    hist = creature.history

    def _last(key: str, fallback):
        vals = hist.get(key, [])
        return vals[-1] if vals else fallback

    h = creature.heart
    b = creature.blood

    hr = _last("HR_bpm", h.heart_rate)
    pa_o2 = _last("art_PO2", b.arterial_PO2_mmHg)
    pa_co2 = _last("art_PCO2", b.arterial_PCO2_mmHg)
    sat = _last("saturation", b.arterial_saturation)
    ph = _last("pH", b.arterial_pH)
    gfr = _last("GFR", creature.kidney.GFR)
    bun = _last("BUN", b.bun_mg_dL)
    rr = _last("RR", creature.lung.respiratory_rate)
    co = _last("CO_ml_min", h.cardiac_output)
    map_val = _last("MAP_mmHg", h.mean_arterial_pressure)
    cvp = _last("CVP_mmHg", h.central_venous_pressure)
    bv = _last("blood_volume_ml", h.circulating_volume_ml)
    ctr = _last("contractility_factor", h.contractility_factor)
    urine = _last("urine_ml_min", creature.kidney.urine_output)

    return {
        "HR":           hr,
        "MAP":          map_val,
        "CVP":          cvp,
        "CO":           co,
        "RR":           rr,
        "SpO2":         sat * 100,    # 引擎存 0-1，转为百分比
        "PaO2":         pa_o2,
        "PaCO2":        pa_co2,
        "pH":           ph,
        "GFR":          gfr,
        "BUN":          bun,
        "Na":           b.sodium_mEq_L,
        "K":            b.potassium_mEq_L,
        "Glu":          b.glucose_mmol_L,
        "Lactate":      b.lactate_mmol_L,
        "HCT":          (b.red_cell_volume_ml / b.total_volume_ml) * 100,
        "Temp":         b.core_temperature_C,
        "BV":           bv,
        "contractility": ctr,
        "Urine":        urine,
    }


# ──────────────────────────────────────────────
# 各检查类型的生成函数
# ──────────────────────────────────────────────

def _physical(state: dict, creature: VirtualCreature) -> dict:
    """体格检查 — HR, RR, 体温, 精神状态"""
    results = []
    results.append(_result_entry("HR", state["HR"], _flag(state["HR"], "HR")))
    results.append(_result_entry("RR", state["RR"], _flag(state["RR"], "RR")))
    results.append(_result_entry("Temp", state["Temp"], _flag(state["Temp"], "Temp")))
    results.append(_result_entry("MAP", state["MAP"], _flag(state["MAP"], "MAP")))

    # 精神状态基于 MAP 和 SpO2 综合判断
    if state["MAP"] < 50 or state["SpO2"] < 85:
        mental = "昏迷"
    elif state["MAP"] < 65 or state["SpO2"] < 90:
        mental = "嗜睡/沉郁"
    elif state["HR"] > 140:
        mental = "烦躁不安"
    else:
        mental = "警觉/正常"

    abnormal = [r for r in results if r["flag"] != "normal"]
    if mental not in ("警觉/正常",):
        mental_note = f"精神状态：{mental}"
    else:
        mental_note = None

    if not abnormal and not mental_note:
        summary = "体格检查未见明显异常。"
    else:
        parts = []
        for r in abnormal:
            flag_cn = {"low": "偏低", "high": "偏高", "critical": "危急"}[r["flag"]]
            parts.append(f"{r['param']}{flag_cn}（{r['value']}{r['unit']}）")
        if mental_note:
            parts.append(mental_note)
        summary = "，".join(parts) + "。"

    return {
        "name": "体格检查",
        "test_type": "physical",
        "results": results,
        "mental_status": mental,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _auscultation(state: dict, creature: VirtualCreature) -> dict:
    """听诊 — 心音/肺音描述"""
    findings = []

    # 心音
    if state["HR"] > 140:
        findings.append("心动过速，心音增强")
    elif state["HR"] < 50:
        findings.append("心动过缓，心音减弱")
    else:
        findings.append("心率正常，心音清晰")

    if state["contractility"] > 1.3:
        findings.append("心音增强（高动力状态）")
    elif state["contractility"] < 0.7:
        findings.append("心音低沉（收缩力减弱）")

    # 肺音
    if state["PaO2"] < 60:
        findings.append("双肺湿啰音（肺泡渗出）")
    elif state["PaO2"] < 80:
        findings.append("肺底细湿啰音")
    elif state["RR"] > 35:
        findings.append("呼吸音粗粝（呼吸急促）")
    else:
        findings.append("肺音清晰，呼吸音正常")

    # 心律
    if state["HR"] > 160:
        findings.append("节律不齐待排（建议心电图）")

    summary = "；".join(findings) + "。"

    return {
        "name": "听诊",
        "test_type": "auscultation",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _inspection(state: dict, creature: VirtualCreature) -> dict:
    """视诊 — 黏膜颜色/脱水程度"""
    findings = []

    # 黏膜颜色（基于 SpO2）
    if state["SpO2"] < 85:
        findings.append("黏膜发绀（严重低氧）")
    elif state["SpO2"] < 92:
        findings.append("黏膜轻度发绀")
    elif state["MAP"] < 60:
        findings.append("黏膜苍白（低灌注）")
    else:
        findings.append("黏膜颜色正常，粉红色")

    # 脱水程度（基于血容量）
    total_bv = creature.blood.total_volume_ml  # 该动物的真实总血容量
    bv_ratio = state["BV"] / total_bv if total_bv > 0 else 1.0
    if bv_ratio < 0.85:
        findings.append("重度脱水（皮肤弹性差，眼球凹陷）")
    elif bv_ratio < 0.92:
        findings.append("中度脱水（皮肤弹性下降）")
    elif bv_ratio < 0.97:
        findings.append("轻度脱水")
    else:
        findings.append("水合状态正常")

    # 体温相关
    if state["Temp"] > 40.0:
        findings.append("高热（体温 {:.1f}°C）".format(state["Temp"]))
    elif state["Temp"] > 39.5:
        findings.append("发热（体温 {:.1f}°C）".format(state["Temp"]))
    elif state["Temp"] < 37.5:
        findings.append("低体温（体温 {:.1f}°C）".format(state["Temp"]))

    summary = "；".join(findings) + "。"

    return {
        "name": "视诊",
        "test_type": "inspection",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _blood_routine(state: dict, creature: VirtualCreature) -> dict:
    """血常规 — WBC, RBC(HCT), HB, PLT"""
    results = []

    # HCT（引擎直接计算）
    hct = state["HCT"]
    results.append(_result_entry("HCT", hct, _flag(hct, "HCT")))

    # WBC — 引擎没有直接建模，基于疾病状态估算
    # 健康犬 ~12 ×10⁹/L，感染时升高，免疫抑制时降低
    disease = creature.disease
    if disease and disease.active:
        if hasattr(disease, 'bacterial_load'):
            # 肺炎：细菌感染 → WBC 升高
            wbc = 12.0 + disease.bacterial_load * 8.0
        else:
            wbc = 12.0
    else:
        wbc = 12.0
    results.append(_result_entry("WBC", wbc, _flag(wbc, "WBC")))

    # PLT — 引擎未建模，正常范围
    plt = 300.0
    results.append(_result_entry("PLT", plt, _flag(plt, "PLT")))

    abnormal = [r for r in results if r["flag"] != "normal"]
    if not abnormal:
        summary = "血常规各项指标均在正常范围内。"
    else:
        parts = []
        for r in abnormal:
            flag_cn = {"low": "偏低", "high": "偏高", "critical": "危急"}[r["flag"]]
            parts.append(f"{r['param']}{flag_cn}")
        summary = "，".join(parts) + "。"

    return {
        "name": "血常规",
        "test_type": "blood_routine",
        "results": results,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _blood_biochem(state: dict, creature: VirtualCreature) -> dict:
    """生化全项 — BUN, Cr, GLU, ALT, Na, K, Cl"""
    results = []
    results.append(_result_entry("BUN", state["BUN"], _flag(state["BUN"], "BUN")))
    results.append(_result_entry("Glu", state["Glu"], _flag(state["Glu"], "Glu")))
    results.append(_result_entry("Na", state["Na"], _flag(state["Na"], "Na")))
    results.append(_result_entry("K", state["K"], _flag(state["K"], "K")))

    # Cr — 从引擎获取
    cr = creature.blood.creatinine_mg_dL
    results.append({
        "param": "Cr",
        "value": round(cr, 2),
        "unit": "mg/dL",
        "normal_range": "0.5-1.5",
        "flag": "normal" if 0.5 <= cr <= 1.5 else ("low" if cr < 0.5 else "high"),
    })

    # ALT — 引擎未建模，正常值
    alt = 45.0
    results.append({
        "param": "ALT",
        "value": alt,
        "unit": "U/L",
        "normal_range": "10-100",
        "flag": "normal",
    })

    abnormal = [r for r in results if r["flag"] != "normal"]
    if not abnormal:
        summary = "生化指标未见明显异常。"
    else:
        parts = []
        for r in abnormal:
            flag_cn = {"low": "偏低", "high": "偏高", "critical": "危急"}[r["flag"]]
            parts.append(f"{r['param']}{flag_cn}")
        summary = "，".join(parts) + "。"

    return {
        "name": "生化全项",
        "test_type": "blood_biochem",
        "results": results,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _blood_gas(state: dict, creature: VirtualCreature) -> dict:
    """血气分析 — PaO2, PaCO2, pH, Lactate, SpO2"""
    results = []
    results.append(_result_entry("PaO2", state["PaO2"], _flag(state["PaO2"], "PaO2")))
    results.append(_result_entry("PaCO2", state["PaCO2"], _flag(state["PaCO2"], "PaCO2")))
    results.append(_result_entry("pH", state["pH"], _flag(state["pH"], "pH")))
    results.append(_result_entry("Lactate", state["Lactate"], _flag(state["Lactate"], "Lactate")))
    results.append(_result_entry("SpO2", state["SpO2"], _flag(state["SpO2"], "SpO2")))

    # 分析酸碱状态
    if state["pH"] < 7.35:
        if state["PaCO2"] > 45:
            acidosis_type = "呼吸性酸中毒"
        elif state["Lactate"] > 2.5:
            acidosis_type = "代谢性酸中毒（乳酸酸中毒）"
        else:
            acidosis_type = "酸中毒"
    elif state["pH"] > 7.45:
        if state["PaCO2"] < 35:
            alkalosis_type = "呼吸性碱中毒"
        else:
            alkalosis_type = "碱中毒"
        acidosis_type = None
    else:
        acidosis_type = None
        alkalosis_type = None

    abnormal = [r for r in results if r["flag"] != "normal"]
    if not abnormal:
        summary = "血气分析结果正常。"
    else:
        parts = []
        for r in abnormal:
            flag_cn = {"low": "偏低", "high": "偏高", "critical": "危急"}[r["flag"]]
            parts.append(f"{r['param']}{flag_cn}（{r['value']}{r['unit']}）")
        summary = "，".join(parts) + "。"
        if acidosis_type:
            summary += f"提示{acidosis_type}。"
        elif alkalosis_type:
            summary += f"提示{alkalosis_type}。"

    return {
        "name": "血气分析",
        "test_type": "blood_gas",
        "results": results,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _chest_xray(state: dict, creature: VirtualCreature) -> dict:
    """X光胸片 — 肺野/渗出描述"""
    findings = []

    # 基于 PaO2 和疾病状态推断
    disease = creature.disease
    has_pneumonia = (
        disease is not None
        and disease.active
        and hasattr(disease, 'alveolar_exudate')
    )

    if has_pneumonia:
        exudate = disease.alveolar_exudate
        if exudate > 0.7:
            findings.append("双肺大面积实变影，空气支气管征可见")
            findings.append("肺泡渗出严重，呈大叶性肺炎表现")
        elif exudate > 0.3:
            findings.append("肺野斑片状渗出影，以下叶为主")
            findings.append("提示支气管肺炎")
        elif exudate > 0.05:
            findings.append("肺纹理增粗，散在少量渗出")
        else:
            findings.append("肺野基本清晰，少量纹理增粗")

        if hasattr(disease, 'tissue_hypoxia') and disease.tissue_hypoxia > 0.5:
            findings.append("纵隔轻度移位（肺容积减少）")
    else:
        if state["PaO2"] < 80:
            findings.append("肺野散在斑片影（非特异性渗出）")
        else:
            findings.append("肺野清晰")
            findings.append("未见明显渗出或占位性病变")

    # DCM：心影增大
    if disease and disease.active and hasattr(disease, 'ventricular_dilation'):
        if disease.ventricular_dilation > 0.3:
            findings.append("心影普遍增大（心胸比 > 0.7）")
        if disease.fluid_retention > 0.3:
            findings.append("肺静脉扩张，肺纹理增粗（肺淤血）")

    if state["RR"] > 35:
        findings.append("膈肌低平（过度通气）")

    summary = "；".join(findings) + "。"

    return {
        "name": "X光胸片",
        "test_type": "chest_xray",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _ultrasound(state: dict, creature: VirtualCreature) -> dict:
    """超声 — 器官结构描述"""
    findings = []
    disease = creature.disease

    # 心脏超声
    if state["contractility"] > 1.3:
        findings.append("左室收缩功能增强（高动力状态）")
    elif state["contractility"] < 0.7:
        findings.append("左室收缩功能减低，室壁运动减弱")
    else:
        findings.append("心脏结构正常，室壁运动良好")

    bv_ratio = state["BV"] / creature.heart.total_BV if creature.heart.total_BV > 0 else 1.0
    if bv_ratio < 0.85:
        findings.append("下腔静脉塌陷（低血容量）")
    elif state["CVP"] > 8:
        findings.append("下腔静脉扩张（容量过负荷/右心衰）")

    # 肾脏超声
    if state["GFR"] < 30:
        findings.append("双肾皮质回声增强（肾功能受损）")
    elif state["GFR"] < 50:
        findings.append("肾血流灌注减少")
    else:
        findings.append("双肾大小正常，皮髓质分界清晰")

    # DCM：心室扩张 + 收缩力减低
    if disease and disease.active and hasattr(disease, 'ventricular_dilation'):
        if disease.ventricular_dilation > 0.3:
            findings.append("左室扩张，室壁运动弥漫性减弱（DCM 表现）")
        if disease.contractility_loss > 0.3:
            findings.append("左室缩短分数减低（收缩功能不全）")

    # 肺部超声（如有肺炎或肺淤血）
    if disease and disease.active and hasattr(disease, 'alveolar_exudate'):
        if disease.alveolar_exudate > 0.3:
            findings.append("肺实质样变（B线增多，胸膜线不规则）")
    elif disease and disease.active and hasattr(disease, 'fluid_retention'):
        if disease.fluid_retention > 0.3:
            findings.append("双肺B线增多（肺淤血/肺水肿）")

    # 尿量评估 — 基于实际尿量（按体重归一化）
    urine = state["Urine"]
    bw = creature.w
    if urine < 0.002 * bw:
        findings.append("无尿（尿量 {:.4f} mL/min）".format(urine))
    elif urine < 0.008 * bw:
        findings.append("少尿（尿量 {:.4f} mL/min）".format(urine))
    else:
        findings.append("尿量正常")

    summary = "；".join(findings) + "。"

    return {
        "name": "超声检查",
        "test_type": "ultrasound",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _ct(state: dict, creature: VirtualCreature) -> dict:
    """CT — 同X光但精度更高"""
    findings = []

    disease = creature.disease
    has_pneumonia = (
        disease is not None
        and disease.active
        and hasattr(disease, 'alveolar_exudate')
    )

    if has_pneumonia:
        exudate = disease.alveolar_exudate
        if exudate > 0.7:
            findings.append("双肺大面积实变，累及多个肺叶")
            findings.append("空气支气管征明显，呈大叶性肺炎典型表现")
            findings.append("少量胸腔积液")
        elif exudate > 0.3:
            findings.append("多发磨玻璃影伴实变，以下叶和背侧为主")
            findings.append("支气管充气征可见")
        elif exudate > 0.05:
            findings.append("散在磨玻璃样渗出，范围较小")
        else:
            findings.append("肺野基本正常，少许纹理增粗")

    else:
        findings.append("肺野清晰，未见实质性病变")
        findings.append("纵隔结构正常，无肿大淋巴结")

    # DCM：心影增大
    if disease and disease.active and hasattr(disease, 'ventricular_dilation'):
        if disease.ventricular_dilation > 0.3:
            findings.append("心脏各房室普遍扩大，以左室为主")
        if disease.fluid_retention > 0.3:
            findings.append("肺血管纹理增粗，少量胸腔积液")

    if state["PaO2"] < 70:
        findings.append("低氧血症相关改变")

    summary = "；".join(findings) + "。"

    return {
        "name": "CT",
        "test_type": "ct",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _ecg(state: dict, creature: VirtualCreature) -> dict:
    """心电图 — HR, 节律描述"""
    results = []
    results.append(_result_entry("HR", state["HR"], _flag(state["HR"], "HR")))

    # 节律分析
    if state["HR"] > 160:
        rhythm = "窦性心动过速"
    elif state["HR"] > 140:
        rhythm = "窦性心动过速（轻度）"
    elif state["HR"] < 50:
        rhythm = "窦性心动过缓"
    elif state["HR"] < 60:
        rhythm = "窦性心动过缓（轻度）"
    else:
        rhythm = "窦性心律，节律整齐"

    # 基于疾病状态推断
    disease = creature.disease
    if disease and disease.active and hasattr(disease, 'fever_state'):
        if disease.fever_state > 0.5:
            rhythm += "；发热相关心率增快"

    if state["K"] > 5.5:
        rhythm += "；高钾血症相关T波高尖"
    elif state["K"] < 3.0:
        rhythm += "；低钾血症相关U波"

    results.append({
        "param": "节律",
        "value": rhythm,
        "unit": "",
        "normal_range": "窦性心律",
        "flag": "normal" if "窦性心律" in rhythm and "过速" not in rhythm and "过缓" not in rhythm else "high" if "过速" in rhythm else ("low" if "过缓" in rhythm else "normal"),
    })

    abnormal = [r for r in results if isinstance(r["flag"], str) and r["flag"] != "normal"]
    if not abnormal:
        summary = "心电图正常，窦性心律。"
    else:
        summary = rhythm + "。"

    return {
        "name": "心电图",
        "test_type": "ecg",
        "results": results,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _urinalysis(state: dict, creature: VirtualCreature) -> dict:
    """尿液分析 — USG, UPCR, 沉渣"""
    results = []

    # 尿比重（基于血容量和 GFR 估算）
    total_bv = creature.blood.total_volume_ml
    bv_ratio = state["BV"] / total_bv if total_bv > 0 else 1.0
    if bv_ratio < 0.9:
        usg = 1.035  # 浓缩尿（脱水时代偿）
    elif state["GFR"] < 30:
        usg = 1.015  # 等渗尿（肾衰失去浓缩能力）
    else:
        usg = 1.025
    usg_flag = "normal" if 1.015 <= usg <= 1.040 else ("low" if usg < 1.015 else "high")
    results.append({"param": "USG", "value": usg, "unit": "", "normal_range": "1.015-1.040", "flag": usg_flag})

    # 尿蛋白/肌酐比
    if state["GFR"] < 50:
        upcr = 1.5
        upcr_flag = "high"
    else:
        upcr = 0.3
        upcr_flag = "normal"
    results.append({"param": "UPCR", "value": upcr, "unit": "", "normal_range": "<0.5", "flag": upcr_flag})

    # 沉渣
    if state["GFR"] < 30:
        sediment = "颗粒管型、肾上皮细胞"
        sediment_flag = "abnormal"
    else:
        sediment = "阴性"
        sediment_flag = "normal"
    results.append({"param": "沉渣", "value": sediment, "unit": "", "normal_range": "阴性", "flag": sediment_flag})

    abnormal = [r for r in results if r["flag"] not in ("normal",)]
    if not abnormal:
        summary = "尿液分析正常。"
    else:
        parts = [f"{r['param']}异常（{r['value']}）" for r in abnormal]
        summary = "，".join(parts) + "。"

    return {
        "name": "尿液分析",
        "test_type": "urinalysis",
        "results": results,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _blood_pressure(state: dict, creature: VirtualCreature) -> dict:
    """血压测量 — 直接测量 SBP/DBP/MAP"""
    results = []
    map_val = state["MAP"]
    sbp = map_val * 1.4
    dbp = map_val * 0.8

    results.append({"param": "SBP", "value": round(sbp, 1), "unit": "mmHg", "normal_range": "110-160",
                     "flag": "normal" if 110 <= sbp <= 160 else ("low" if sbp < 110 else "high")})
    results.append({"param": "DBP", "value": round(dbp, 1), "unit": "mmHg", "normal_range": "60-90",
                     "flag": "normal" if 60 <= dbp <= 90 else ("low" if dbp < 60 else "high")})
    results.append(_result_entry("MAP", map_val, _flag(map_val, "MAP")))

    abnormal = [r for r in results if r["flag"] != "normal"]
    if not abnormal:
        summary = f"血压正常（{sbp:.0f}/{dbp:.0f} mmHg）。"
    else:
        parts = [f"{r['param']}{'偏低' if r['flag'] == 'low' else '偏高'}" for r in abnormal]
        summary = "血压异常：" + "，".join(parts) + "。"

    return {
        "name": "血压测量",
        "test_type": "blood_pressure",
        "results": results,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _cytology(state: dict, creature: VirtualCreature) -> dict:
    """细胞学检查 — 鉴别炎症与肿瘤"""
    findings = []
    disease = creature.disease

    if disease and disease.active and hasattr(disease, 'bacterial_load'):
        if disease.bacterial_load > 0.3:
            findings.append("大量中性粒细胞，可见细菌吞噬现象")
            findings.append("化脓性炎症表现，符合细菌性肺炎")
        else:
            findings.append("轻度炎性细胞浸润")
    elif disease and disease.active and hasattr(disease, 'ventricular_dilation'):
        findings.append("未见明显异常细胞")
        findings.append("排除肿瘤性病变")
    else:
        findings.append("细胞学未见明显异常")

    summary = "；".join(findings) + "。"
    return {
        "name": "细胞学检查",
        "test_type": "cytology",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _snap_test(state: dict, creature: VirtualCreature) -> dict:
    """快速 SNAP 检测 — 特异性识别特定病原"""
    findings = []
    disease = creature.disease

    if disease and disease.active and hasattr(disease, 'bacterial_load'):
        if disease.bacterial_load > 0.3:
            findings.append("犬瘟热/副流感快速检测：阳性")
            findings.append("提示病毒性呼吸道感染合并细菌感染")
        else:
            findings.append("快速检测：阴性")
    else:
        findings.append("快速检测：阴性")
        findings.append("未检测到常见病原标志物")

    summary = "；".join(findings) + "。"
    return {
        "name": "快速检测（SNAP）",
        "test_type": "snap_test",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _fna(state: dict, creature: VirtualCreature) -> dict:
    """细针穿刺（FNA）— 采集细胞样本"""
    findings = []
    disease = creature.disease

    if disease and disease.active and hasattr(disease, 'alveolar_exudate'):
        if disease.alveolar_exudate > 0.3:
            findings.append("肺组织穿刺：大量炎性细胞")
            findings.append("符合感染性肺炎细胞学表现")
        else:
            findings.append("少量炎性细胞")
    else:
        findings.append("细胞学样本未见明显异常")
        findings.append("少量正常间皮细胞")

    summary = "；".join(findings) + "。"
    return {
        "name": "细针穿刺（FNA）",
        "test_type": "fna",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _abdominocentesis(state: dict, creature: VirtualCreature) -> dict:
    """腹腔穿刺 — 抽取腹腔积液"""
    findings = []
    disease = creature.disease

    if disease and disease.active and hasattr(disease, 'fluid_retention'):
        if disease.fluid_retention > 0.3:
            findings.append("腹腔穿刺获淡黄色漏出液")
            findings.append("蛋白含量低（<2.5 g/dL），符合漏出液")
            findings.append("提示心源性腹水")
        else:
            findings.append("腹腔未见明显积液")
    else:
        findings.append("腹腔未见明显积液")
        findings.append("穿刺阴性")

    summary = "；".join(findings) + "。"
    return {
        "name": "腹腔穿刺",
        "test_type": "abdominocentesis",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _thoracocentesis(state: dict, creature: VirtualCreature) -> dict:
    """胸腔穿刺 — 抽取胸腔积液"""
    findings = []
    disease = creature.disease

    if disease and disease.active and hasattr(disease, 'alveolar_exudate'):
        if disease.alveolar_exudate > 0.5:
            findings.append("胸腔穿刺获浑浊液体")
            findings.append("细胞计数升高，蛋白含量高")
            findings.append("符合渗出液，提示感染性胸膜炎")
        elif disease.alveolar_exudate > 0.1:
            findings.append("少量胸腔积液，淡黄色")
        else:
            findings.append("胸腔未见明显积液")
    elif disease and disease.active and hasattr(disease, 'fluid_retention'):
        if disease.fluid_retention > 0.3:
            findings.append("双侧少量胸腔积液，漏出液性质")
        else:
            findings.append("胸腔未见明显积液")
    else:
        findings.append("胸腔未见明显积液")
        findings.append("穿刺阴性")

    summary = "；".join(findings) + "。"
    return {
        "name": "胸腔穿刺",
        "test_type": "thoracocentesis",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _echocardiography(state: dict, creature: VirtualCreature) -> dict:
    """超声心动图 — 专业心脏超声"""
    findings = []
    disease = creature.disease

    if disease and disease.active and hasattr(disease, 'ventricular_dilation'):
        vd = disease.ventricular_dilation
        cl = disease.contractility_loss if hasattr(disease, 'contractility_loss') else 0
        if vd > 0.3:
            findings.append(f"左室舒张末期内径增大（LVIDd ↑）")
            findings.append(f"缩短分数（FS）显著减低（{25 - cl * 30:.0f}%）")
            findings.append("室壁运动弥漫性减弱")
            findings.append("符合扩张型心肌病（DCM）表现")
        else:
            findings.append("心脏结构正常")
            findings.append("缩短分数正常范围")
    else:
        findings.append("心脏结构正常，各房室大小在正常范围")
        findings.append("室壁运动良好，缩短分数正常")
        findings.append("瓣膜启闭正常，未见明显反流")

    # 估测肺动脉压
    if state["PaO2"] < 60:
        findings.append("估测肺动脉收缩压升高（肺动脉高压）")

    summary = "；".join(findings) + "。"
    return {
        "name": "超声心动图",
        "test_type": "echocardiography",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _endoscopy(state: dict, creature: VirtualCreature) -> dict:
    """内窥镜检查 — 直视下观察"""
    findings = []
    disease = creature.disease

    if disease and disease.active and hasattr(disease, 'alveolar_exudate'):
        findings.append("气管内可见脓性分泌物")
        findings.append("支气管黏膜充血水肿")
        if disease.alveolar_exudate > 0.5:
            findings.append("叶支气管内可见渗出物")
        findings.append("符合感染性气道病变")
    else:
        findings.append("食道黏膜正常，未见异物或溃疡")
        findings.append("胃黏膜正常，未见肿物")
        findings.append("十二指肠黏膜正常")

    summary = "；".join(findings) + "。"
    return {
        "name": "内窥镜",
        "test_type": "endoscopy",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _mri(state: dict, creature: VirtualCreature) -> dict:
    """MRI — 磁共振成像"""
    findings = []
    disease = creature.disease

    if disease and disease.active and hasattr(disease, 'ventricular_dilation'):
        findings.append("心脏 MRI：左室扩张，心肌变薄")
        findings.append("延迟增强扫描：心肌中层强化（纤维化表现）")
        findings.append("确诊扩张型心肌病")
    else:
        findings.append("MRI 扫描未见明显异常信号")
        findings.append("脑部和脊髓结构正常")

    summary = "；".join(findings) + "。"
    return {
        "name": "MRI",
        "test_type": "mri",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


def _histopathology(state: dict, creature: VirtualCreature) -> dict:
    """组织病理学 — 金标准诊断"""
    findings = []
    disease = creature.disease

    if disease and disease.active and hasattr(disease, 'alveolar_exudate'):
        if disease.alveolar_exudate > 0.3:
            findings.append("肺泡腔内大量中性粒细胞浸润")
            findings.append("肺泡壁充血，纤维素渗出")
            findings.append("细菌菌落可见")
            findings.append("病理诊断：化脓性肺炎")
        else:
            findings.append("轻度肺泡炎性细胞浸润")
    elif disease and disease.active and hasattr(disease, 'ventricular_dilation'):
        findings.append("心肌细胞变性，排列紊乱")
        findings.append("间质纤维化")
        findings.append("病理诊断：扩张型心肌病")
    else:
        findings.append("组织学未见明显异常")

    summary = "；".join(findings) + "。"
    return {
        "name": "组织病理学",
        "test_type": "histopathology",
        "results": findings,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }


# ──────────────────────────────────────────────
# 检查类型 → 生成函数映射
# ──────────────────────────────────────────────
_TEST_DISPATCH = {
    "physical":          _physical,
    "auscultation":      _auscultation,
    "inspection":        _inspection,
    "blood_routine":     _blood_routine,
    "blood_biochem":     _blood_biochem,
    "blood_gas":         _blood_gas,
    "chest_xray":        _chest_xray,
    "ultrasound":        _ultrasound,
    "ct":                _ct,
    "ecg":               _ecg,
    "urinalysis":        _urinalysis,
    "blood_pressure":    _blood_pressure,
    "cytology":          _cytology,
    "snap_test":         _snap_test,
    "fna":               _fna,
    "abdominocentesis":  _abdominocentesis,
    "thoracocentesis":   _thoracocentesis,
    "echocardiography":  _echocardiography,
    "endoscopy":         _endoscopy,
    "mri":               _mri,
    "histopathology":    _histopathology,
}


def translate(test_type: str, creature: VirtualCreature) -> dict:
    """
    根据检查类型返回对应的检查报告。

    Args:
        test_type: 检查类型字符串（见 TASKS.md）
        creature: VirtualCreature 实例

    Returns:
        结构化检查报告 dict
    """
    if test_type not in _TEST_DISPATCH:
        raise ValueError(
            f"未知检查类型: {test_type}。支持: {list(_TEST_DISPATCH.keys())}"
        )

    state = _get_state(creature)
    logger.debug("translate(%s): HR=%.0f PaO2=%.1f", test_type, state["HR"], state["PaO2"])

    return _TEST_DISPATCH[test_type](state, creature)
