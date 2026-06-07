"""
Report Engine — 通用检查报告生成器。

从 data/exam_templates.json 加载检查类型模板，
结合 data/vitals_ranges.json 的生理参数配置，生成结构化检查报告。

架构:
  - 定量检查: vitals 列表 + extra_params → 自动生成结果条目 + flag + tags
  - 叙述性检查: findings_rules + tag_rules → 规则引擎生成描述文本 + 线索
  - 混合检查: 两者结合（如 blood_gas 定量 + 酸碱类型叙述）

所有检查类型共用同一个 generate_report() 入口，不再需要独立生成器函数。

使用方式:
    from src.report_engine import generate_report
    report = generate_report("blood_gas", creature)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Optional

from src.vitals_config import get_vitals_config

if TYPE_CHECKING:
    from src.simulation import VirtualCreature

logger = logging.getLogger(__name__)

# ── 配置加载 ──
_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_TEMPLATES: dict[str, dict] = {}

_vc = get_vitals_config()

_FLAG_CN = {"low": "偏低", "high": "偏高", "critical": "危急"}


def _load_templates(reload: bool = False) -> dict[str, dict]:
    """从 exam_templates.json 加载模板配置。"""
    if _TEMPLATES and not reload:
        return _TEMPLATES
    path = _DATA_DIR / "exam_templates.json"
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    _TEMPLATES.update({k: v for k, v in raw.items() if not k.startswith("_")})
    return _TEMPLATES


def get_template(test_type: str) -> dict:
    """返回指定检查类型的模板元数据。"""
    import json  # noqa: F811 — needed for _load_templates
    templates = _load_templates()
    meta = templates.get(test_type)
    if meta is None:
        raise ValueError(f"未知检查类型: {test_type}")
    return meta


# ──────────────────────────────────────────────
# 共享工具函数
# ──────────────────────────────────────────────


def get_state(creature: VirtualCreature) -> dict:
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

    state = {
        "HR": hr,
        "MAP": map_val,
        "CVP": cvp,
        "CO": co,
        "RR": rr,
        "SpO2": sat * 100,
        "PaO2": pa_o2,
        "PaCO2": pa_co2,
        "pH": ph,
        "GFR": gfr,
        "BUN": bun,
        "Na": b.sodium_mEq_L,
        "K": b.potassium_mEq_L,
        "Glu": b.glucose_mmol_L,
        "Lactate": b.lactate_mmol_L,
        "HCT": (b.red_cell_volume_ml / b.total_volume_ml) * 100,
        "HCO3": creature.fluid.vascular_hco3_meq_l if hasattr(creature, 'fluid') else 24.0,
        "Temp": b.core_temperature_C,
        "BV": bv,
        "contractility": ctr,
        "Urine": urine,
        "PT": _last("coag_PT", b.PT_sec),
        "aPTT": _last("coag_aPTT", b.aPTT_sec),
        "Fibrinogen": _last("coag_fibrinogen", b.fibrinogen_mg_dL),
    }

    # Coagulation state
    if hasattr(creature, 'coagulation') and creature.coagulation is not None:
        state["coagulation_state"] = creature.coagulation.coagulation_state

    # HH 电生理数据（如果 heart 模块有 HH 集成）
    if hasattr(creature.heart, 'hh') and creature.heart.hh is not None:
        hh = creature.heart.hh
        ecg_interp = hh.get_ecg_interpretation(b.potassium_mEq_L)
        state["hh_heart_rate"] = round(hh.heart_rate, 1)
        state["hh_k_toxicity"] = round(hh.k_toxicity_factor, 3)
        state["hh_h_inf"] = round(hh._h_inf, 3)
        state["hh_e_k"] = round(hh._nernst_k(b.potassium_mEq_L), 1)
        # ECG 波形解读字段（供 extra_params 引用）
        state["T波"] = ecg_interp.get("t_wave_amplitude", "normal")
        state["QRS宽度"] = ecg_interp.get("qrs_width", "normal")
        state["P波"] = ecg_interp.get("p_wave", "present")
        state["K_toxicity_stage"] = ecg_interp.get("k_toxicity_stage", "none")

        # Noble 浦肯野纤维数据
        from src.noble_purkinje import NoblePurkinjeFiber
        if isinstance(hh, NoblePurkinjeFiber):
            av_interp = hh.get_av_interpretation(b.potassium_mEq_L)
            state["PR间期"] = av_interp.get("pr_interval_ms", 80.0)
            state["AV传导"] = av_interp.get("av_block_description", "normal_conduction")
            state["传导速度"] = av_interp.get("conduction_velocity", 4.0)
            state["逸搏心率"] = av_interp.get("purkinje_intrinsic_rate_bpm", 30.0)

    return state


def flag(value: float, param: str) -> str:
    """根据正常范围和危急值返回 low / normal / high / critical。"""
    return _vc.classify(param, value)


def result_entry(param: str, value: float, flag_val: str) -> dict:
    """生成单个检查结果的标准化条目。"""
    lo, hi = _vc.get_normal(param)
    unit = _vc.get_unit(param)
    return {
        "param": param,
        "value": round(value, 2),
        "unit": unit,
        "normal_range": f"{lo}-{hi}",
        "flag": flag_val,
    }


def tags_from_results(results: list[dict]) -> list[str]:
    """从定量检查结果的 flag 推导 tags（结构化线索 ID 列表）。"""
    tags: list[str] = []
    for r in results:
        f = r.get("flag", "normal")
        if f != "normal":
            clue_id = _vc.get_clue_id(r["param"], f)
            if clue_id:
                tags.append(clue_id)
    return tags


def _build_report(
    meta: dict,
    results: list,
    summary: str,
    tags: list[str],
    creature: VirtualCreature,
    **extra,
) -> dict:
    """组装标准化报告 dict。"""
    report = {
        "name": meta["name"],
        "test_type": meta["test_type"],
        "results": results,
        "tags": tags,
        "summary": summary,
        "timestamp_s": creature.current_time_s,
    }
    report.update(extra)
    return report


# ──────────────────────────────────────────────
# extra_params 解析器
# ──────────────────────────────────────────────


def _resolve_extra_param(param_cfg: dict, state: dict, ctx: dict[str, Any], creature) -> Any:
    """
    根据 extra_params 配置解析参数值。

    支持来源:
      1. source = "creature.xxx.yyy" — 从 creature 对象属性读取
      2. source = "hardcoded" + default_value — 固定值
      3. source = "computed" + formula/value_formula — 用 ctx 变量计算公式
      4. source = "state.xxx" — 从 state 字典读取
      5. 无 source 但 param 在 state 中 — 自动从 state 读取

    返回值可以是 float 或 str（当 is_text_result=True 时）。
    """
    source = param_cfg.get("source", "")

    # 来源: creature 属性路径
    if source.startswith("creature."):
        parts = source.split(".")
        obj = creature
        for part in parts[1:]:
            if obj is None:
                return param_cfg.get("default_value", 0.0)
            obj = getattr(obj, part, None)
        return obj if obj is not None else param_cfg.get("default_value", 0.0)

    # 来源: state 字典
    if source.startswith("state."):
        key = source.split(".", 1)[1]
        return state.get(key, param_cfg.get("default_value", 0.0))

    # 来源: 固定值
    if source == "hardcoded":
        return param_cfg.get("default_value", 0.0)

    # 来源: 计算公式
    if source == "computed":
        formula = param_cfg.get("value_formula", param_cfg.get("formula", ""))
        if formula:
            result = _eval_formula(formula, ctx, param_cfg.get("default_value", 0.0))
            # 处理文本型结果（如 沉渣）
            if param_cfg.get("is_text_result"):
                text_values = param_cfg.get("text_values", {})
                key = str(int(result)) if isinstance(result, float) and result == int(result) else str(result)
                return text_values.get(key, str(result))
            return result
        return param_cfg.get("default_value", 0.0)

    # 来源: HH ECG 解读（state 中已注入的 ecg_interpretation 字段）
    if source == "hh_ecg_interpretation":
        field = param_cfg.get("field", "")
        return state.get(field, param_cfg.get("default_value", ""))

    # 来源: 直接在 state 中用 param 名查找
    param_name = param_cfg.get("param", "")
    if param_name in state:
        return state[param_name]

    return param_cfg.get("default_value", 0.0)


def _eval_formula(formula: str, ctx: dict[str, Any], fallback: float = 0.0) -> Any:
    """安全计算公式表达式，支持 ctx 中的变量。"""
    try:
        safe_ns: dict[str, Any] = {
            "__builtins__": {
                "hasattr": hasattr,
                "getattr": getattr,
                "float": float,
                "int": int,
                "str": str,
                "round": round,
                "abs": abs,
                "min": min,
                "max": max,
            }
        }
        # 注入 thresholds（支持 thresholds.xxx 点号和扁平变量名两种访问方式）
        thresholds = ctx.get("thresholds", {})
        if isinstance(thresholds, dict):
            safe_ns["thresholds"] = SimpleNamespace(**thresholds)
            for k, v in thresholds.items():
                safe_ns[k] = v
        # 注入 state 变量（支持 state.XXX 点号和扁平变量名两种访问方式）
        state_ctx = ctx.get("state", {})
        if isinstance(state_ctx, dict):
            safe_ns["state"] = SimpleNamespace(**state_ctx)
            for k, v in state_ctx.items():
                safe_ns[k] = v
        # 注入 disease 对象
        disease = ctx.get("disease")
        if disease is not None:
            safe_ns["disease"] = disease
        # 注入 creature
        creature = ctx.get("creature")
        if creature is not None:
            safe_ns["creature"] = creature
        # 注入其他 ctx 顶层变量
        for k, v in ctx.items():
            if k not in ("thresholds", "state", "disease", "creature"):
                safe_ns[k] = v
        result = eval(formula, safe_ns)  # noqa: S307
        return result
    except Exception:
        return fallback


# ──────────────────────────────────────────────
# 定量结果构建器
# ──────────────────────────────────────────────


def _build_quantitative_results(
    meta: dict,
    state: dict,
    ctx: dict[str, Any],
    creature,
) -> list[dict]:
    """
    从 vitals + extra_params 构建定量结果列表。

    流程:
      1. 从 meta["vitals"] 批量生成标准结果条目
      2. 从 meta["extra_params"] 逐个解析并追加结果条目
    """
    results: list[dict] = []

    # 标准 vitals 参数
    for param_name in meta.get("vitals", []):
        if param_name in state:
            val = state[param_name]
            results.append(result_entry(param_name, val, flag(val, param_name)))

    # extra_params — 支持 creature 源、公式计算、固定值、文本型结果
    for param_cfg in meta.get("extra_params", []):
        param_name = param_cfg.get("param", "")
        if not param_name:
            continue

        value = _resolve_extra_param(param_cfg, state, ctx, creature)

        # 确定 flag
        normal_range = param_cfg.get("normal_range", "")
        flag_val = _classify_extra_param(value, normal_range)

        # 数值舍入（文本型不处理）
        if isinstance(value, float):
            display_value = round(value, 2)
        else:
            display_value = value

        entry: dict[str, Any] = {
            "param": param_name,
            "value": display_value,
            "unit": param_cfg.get("unit", ""),
            "normal_range": normal_range,
            "flag": flag_val,
        }
        results.append(entry)

        # 将 extra_params 结果注入 state，使 tag_rules 可以通过 state.XXX 引用
        state[param_name] = value

    return results


def _classify_extra_param(value: float, normal_range: str) -> str:
    """
    根据 normal_range 字符串分类 flag。

    支持格式:
      - "0.5-1.5" → 数值范围
      - "<0.5" → 上限
      - ">10" → 下限
      - 非数值（如 "阴性"）→ 直接比较字符串
    """
    # 非数值型参数（如 沉渣 "阴性"）
    if not isinstance(value, (int, float)):
        return "normal" if value == normal_range else "abnormal"

    # 解析范围
    range_match = re.match(r"^([\d.]+)-([\d.]+)$", normal_range)
    if range_match:
        lo, hi = float(range_match.group(1)), float(range_match.group(2))
        if value < lo:
            return "low"
        elif value > hi:
            return "high"
        return "normal"

    # 上限: "<0.5"
    upper_match = re.match(r"^<([\d.]+)$", normal_range)
    if upper_match:
        hi = float(upper_match.group(1))
        return "high" if value >= hi else "normal"

    # 下限: ">10"
    lower_match = re.match(r"^>([\d.]+)$", normal_range)
    if lower_match:
        lo = float(lower_match.group(1))
        return "low" if value <= lo else "normal"

    return "normal"


# ──────────────────────────────────────────────
# 叙述性结果构建器
# ──────────────────────────────────────────────


def _build_narrative_results(
    meta: dict,
    state: dict,
    ctx: dict[str, Any],
    creature,
) -> tuple[list[str], str]:
    """
    从 findings_rules 构建叙述性结果。

    返回: (findings_list, summary)
    """
    fr = meta.get("findings_rules", {})
    rule_output = _apply_findings_rules(fr, ctx, creature.disease)
    findings = _collect_findings(rule_output)
    summary = "；".join(findings) + "。" if findings else f"{meta['name']}未见明显异常。"
    return findings, summary


# ──────────────────────────────────────────────
# 定量检查的 summary 生成
# ──────────────────────────────────────────────


def _summarize_quantitative(meta: dict, results: list[dict], extra_parts: list[str] = None) -> str:
    """生成定量检查的摘要文本。"""
    abnormal = [r for r in results if r["flag"] != "normal"]
    if not abnormal and not extra_parts:
        if meta["test_type"] == "blood_gas":
            return "血气分析结果正常。"
        return f"{meta['name']}各项指标均在正常范围内。"

    parts = []
    for r in abnormal:
        flag_cn = _FLAG_CN.get(r["flag"], r["flag"])
        parts.append(f"{r['param']}{flag_cn}（{r['value']}{r['unit']}）")
    if extra_parts:
        parts.extend(extra_parts)
    return "，".join(parts) + "。"


# ──────────────────────────────────────────────
# JSON 规则引擎（保留不变）
# ──────────────────────────────────────────────


def _resolve_value(expr: str, ctx: dict[str, Any]) -> Any:
    """
    从上下文中解析表达式值。

    支持:
      - "state.HR"       ->  ctx["state"]["HR"]
      - "thresholds.hr_tachy"  ->  ctx["thresholds"]["hr_tachy"]
      - "disease.alveolar_exudate"  ->  getattr(ctx["disease"], "alveolar_exudate")
      - "bv_ratio"       ->  ctx["bv_ratio"]
      - "creature.blood.creatinine_mg_dL"  ->  ctx["creature"].blood.creatinine_mg_dL
      - 纯数字如 "140"   ->  float(140)
    """
    try:
        return float(expr)
    except ValueError:
        pass

    if expr.startswith("creature."):
        parts = expr.split(".")
        obj = ctx.get("creature")
        for part in parts[1:]:
            if obj is None:
                return None
            obj = getattr(obj, part, None)
        return obj

    if expr.startswith("disease."):
        parts = expr.split(".", 1)
        obj = ctx.get("disease")
        if obj is None:
            return None
        return getattr(obj, parts[1], None)

    if "." in expr:
        obj_name, attr_name = expr.split(".", 1)
        obj = ctx.get(obj_name)
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(attr_name)
        return getattr(obj, attr_name, None)

    return ctx.get(expr)


def _eval_condition(condition: str, ctx: dict[str, Any]) -> bool:
    """
    评估 JSON 中的条件字符串。

    支持的形式:
      - "state.HR > thresholds.hr_tachy"
      - "disease.alveolar_exudate > thresholds.exudate_mild"
      - "disease.ventricular_dilation is not None"
      - "bv_ratio < thresholds.bv_dehydration_severe"
      - 复合条件用 "and" / "or" 连接
    """
    m = re.match(r"^(\w+\.\w+)\s+is\s+not\s+None$", condition)
    if m:
        obj_name, attr_name = m.group(1).split(".")
        obj = ctx.get(obj_name)
        if obj is None:
            return False
        return hasattr(obj, attr_name)

    if " or " in condition:
        return any(_eval_condition(part.strip(), ctx) for part in condition.split(" or "))

    if " and " in condition:
        return all(_eval_condition(part.strip(), ctx) for part in condition.split(" and "))

    m = re.match(r"^(.+?)\s*(>=|<=|>|<|==|!=)\s*(.+)$", condition)
    if not m:
        return False

    left_str = m.group(1).strip()
    op = m.group(2)
    right_str = m.group(3).strip()

    left_val = _resolve_value(left_str, ctx)
    right_val = _resolve_value(right_str, ctx)

    if left_val is None or right_val is None:
        return False

    ops = {
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
    }
    try:
        return ops[op](left_val, right_val)
    except (TypeError, ValueError):
        return False


def _has_disease_attr(disease, attr_name: str) -> bool:
    """检查疾病对象是否有指定属性。"""
    if disease is None:
        return False
    return hasattr(disease, attr_name)


def _format_template(text: str, ctx: dict[str, Any]) -> str:
    """
    格式化模板字符串，如 "{state.Temp:.1f}" -> "39.5"
    使用 Python format mini-language。
    """
    result = text
    pattern = re.compile(r"\{([^}:]+)(?::([^}]+))?\}")
    for m in pattern.finditer(text):
        full_match = m.group(0)
        expr = m.group(1).strip()
        fmt = m.group(2)
        val = _resolve_value(expr, ctx)
        if val is not None:
            if fmt:
                try:
                    formatted = format(val, fmt)
                except (ValueError, TypeError):
                    formatted = str(val)
            else:
                formatted = str(val)
            result = result.replace(full_match, formatted, 1)
    return result


def _eval_fs_formula(formula: str, ctx: dict[str, Any]) -> Any:
    """
    计算公式表达式（含 disease.xxx 属性），将结果注入 ctx["fs_value"]。
    用于 echocardiography 的缩短分数计算。
    """
    try:
        safe_ns: dict[str, Any] = {"__builtins__": {}}
        for k, v in ctx.get("thresholds", {}).items():
            safe_ns[k] = v
        disease = ctx.get("disease")
        if disease is not None:
            safe_ns["disease"] = disease
        result = eval(formula, safe_ns)  # noqa: S307
        ctx["fs_value"] = result
        return result
    except Exception:
        return None


def _apply_tag_rules(
    tag_rules: list[dict],
    ctx: dict[str, Any],
    disease,
) -> list[str]:
    """
    处理 tag_rules，返回匹配的 clue_id 列表。

    "requires" 字段: 只有当疾病有该属性时才评估条件。
    """
    tags: list[str] = []
    for rule in tag_rules:
        clue_id = rule["clue_id"]
        condition = rule["condition"]

        requires = rule.get("requires")
        if requires:
            attr_name = requires.split(".", 1)[1] if "." in requires else requires
            if not _has_disease_attr(disease, attr_name):
                continue

        if _eval_condition(condition, ctx):
            if clue_id not in tags:
                tags.append(clue_id)
    # 追加 ClinicalSignsEngine 产生的 sign_tags（症状层线索，不覆盖现有tag）
    for sig_tag in ctx.get("sign_tags", []):
        if sig_tag and sig_tag not in tags:
            tags.append(sig_tag)
    return tags


def _apply_findings_rules(
    findings_rules: dict[str, list[dict]],
    ctx: dict[str, Any],
    disease,
) -> dict[str, list[str]]:
    """
    处理 findings_rules，返回分组后的发现文本。

    格式:
      "group_name": [
        {"if": "condition", "text": "..."} 或
        {"if": "condition", "texts": ["...", "..."]} 或
        {"else": true, "text": "..."}
      ]

    返回: {group_name: [text, ...]}
    """
    output: dict[str, list[str]] = {}
    group_order = list(findings_rules.keys())

    for group_name in group_order:
        rules = findings_rules[group_name]
        if not isinstance(rules, list):
            continue
        group_findings: list[str] = []
        for rule in rules:
            matched = False
            condition = rule.get("if")

            if condition is not None:
                requires = rule.get("requires")
                if requires:
                    attr_name = requires.split(".", 1)[1] if "." in requires else requires
                    if not _has_disease_attr(disease, attr_name):
                        continue
                matched = _eval_condition(condition, ctx)
            elif rule.get("else"):
                matched = True

            if matched:
                if "fs_formula" in rule:
                    _eval_fs_formula(rule["fs_formula"], ctx)

                if "texts" in rule:
                    for t in rule["texts"]:
                        group_findings.append(_format_template(t, ctx))
                elif "text" in rule:
                    group_findings.append(_format_template(rule["text"], ctx))

                if condition is not None:
                    break

        if group_findings:
            output[group_name] = group_findings

    return output


def _collect_findings(rule_output: dict[str, list[str]]) -> list[str]:
    """将 findings_rules 输出合并为有序列表。"""
    findings: list[str] = []
    for group_name in rule_output:
        findings.extend(rule_output[group_name])
    return findings


# ──────────────────────────────────────────────
# 通用报告生成器（替代 21 个 _gen_* 函数）
# ──────────────────────────────────────────────


def _build_ctx(meta: dict, state: dict, creature) -> dict[str, Any]:
    """构建规则引擎的上下文。"""
    ctx: dict[str, Any] = {
        "state": state,
        "thresholds": meta.get("thresholds", {}),
        "disease": creature.disease,
        "creature": creature,
    }
    # 计算 bv_ratio（多个检查类型需要）
    total_bv = creature.blood.total_volume_ml
    ctx["bv_ratio"] = state["BV"] / total_bv if total_bv > 0 else 1.0
    # 注入 ClinicalSignsEngine 产生的 sign_tags（症状层线索）
    if hasattr(creature, "clinical_signs_engine"):
        ctx["sign_tags"] = creature.clinical_signs_engine.get_sign_tags()
    else:
        ctx["sign_tags"] = []
    return ctx


def _is_narrative(meta: dict) -> bool:
    """
    判断检查类型是否为叙述性（而非纯定量）。

    如果模板有 findings_rules 且没有 vitals（或 vitals 为空），则为叙述性。
    如果有 findings_rules 且有 vitals，则为混合类型（如 blood_gas）。
    """
    has_findings = bool(meta.get("findings_rules"))
    has_vitals = bool(meta.get("vitals"))
    has_extra = bool(meta.get("extra_params"))

    # 纯叙述性: 有 findings_rules，无 vitals，无 extra_params
    if has_findings and not has_vitals and not has_extra:
        return True

    return False


def _generate_narrative_report(meta: dict, state: dict, creature: VirtualCreature) -> dict:
    """生成叙述性检查报告（纯 findings_rules 驱动）。"""
    ctx = _build_ctx(meta, state, creature)

    findings, summary = _build_narrative_results(meta, state, ctx, creature)
    tags = _apply_tag_rules(meta.get("tag_rules", []), ctx, creature.disease)

    return _build_report(meta, findings, summary, tags, creature)


def _generate_quantitative_report(meta: dict, state: dict, creature: VirtualCreature) -> dict:
    """生成定量检查报告（vitals + extra_params 驱动）。"""
    ctx = _build_ctx(meta, state, creature)

    results = _build_quantitative_results(meta, state, ctx, creature)

    # 检查是否有 findings_rules 需要额外处理（如 blood_gas 的酸碱类型）
    extra_parts: list[str] = []
    fr = meta.get("findings_rules", {})
    if fr:
        rule_output = _apply_findings_rules(fr, ctx, creature.disease)
        # 特殊处理: acidosis_type / alkalosis_type 追加到 summary
        if "acidosis_type" in rule_output:
            extra_parts.append(f"提示{rule_output['acidosis_type'][0]}")
        if "alkalosis_type" in rule_output:
            extra_parts.append(f"提示{rule_output['alkalosis_type'][0]}")
        # 特殊处理: ecg 节律
        if meta["test_type"] == "ecg":
            rhythm_parts: list[str] = []
            for group_name in rule_output:
                rhythm_parts.extend(rule_output[group_name])
            rhythm = "".join(rhythm_parts)
            if rhythm:
                # 判断 flag
                if "窦性心律" in rhythm and "过速" not in rhythm and "过缓" not in rhythm:
                    rhythm_flag = "normal"
                elif "过速" in rhythm:
                    rhythm_flag = "high"
                elif "过缓" in rhythm:
                    rhythm_flag = "low"
                else:
                    rhythm_flag = "normal"

                results.append({
                    "param": "节律",
                    "value": rhythm,
                    "unit": "",
                    "normal_range": "窦性心律",
                    "flag": rhythm_flag,
                })

    summary = _summarize_quantitative(meta, results, extra_parts)

    # Tags: 从 tag_rules 生成（优先），fallback 到 tags_from_results
    tags = _apply_tag_rules(meta.get("tag_rules", []), ctx, creature.disease)
    if not tags:
        tags = tags_from_results(results)

    # 特殊处理: ecg 的 K⁺ 标签
    if meta["test_type"] == "ecg":
        k_high = meta.get("thresholds", {}).get("k_high", 5.5)
        k_low = meta.get("thresholds", {}).get("k_low", 3.0)
        if state["K"] > k_high:
            if "potassium_high" not in tags:
                tags.append("potassium_high")
        elif state["K"] < k_low:
            clue = _vc.get_clue_id("K", "low")
            if clue and clue not in tags:
                tags.append(clue)

        # 注入 ECG 波形数据（如果 HH 模块可用）
        if hasattr(creature.heart, 'hh') and creature.heart.hh is not None:
            ecg_waveform = creature.heart.hh.get_ecg_waveform(duration_ms=2000.0, dt=0.01)
            return _build_report(meta, results, summary, tags, creature,
                                 ecg_waveform=ecg_waveform)

    return _build_report(meta, results, summary, tags, creature)


def _generate_mixed_report(meta: dict, state: dict, creature: VirtualCreature) -> dict:
    """
    生成混合类型报告（定量 + 叙述性 findings_rules）。
    用于 blood_gas（定量参数 + 酸碱类型判断）、physical（定量 + 精神状态）等。
    """
    ctx = _build_ctx(meta, state, creature)

    # 先生成定量结果
    results = _build_quantitative_results(meta, state, ctx, creature)

    # 再处理 findings_rules（如酸碱类型、精神状态等）
    extra_parts: list[str] = []
    extra_keys: dict[str, Any] = {}
    fr = meta.get("findings_rules", {})
    if fr:
        rule_output = _apply_findings_rules(fr, ctx, creature.disease)
        # 收集所有 findings 作为 extra summary parts
        all_findings = _collect_findings(rule_output)
        if all_findings:
            extra_parts.extend(all_findings)
        # 将各组 findings 作为顶层 key 注入报告（如 mental_status）
        for group_name, texts in rule_output.items():
            extra_keys[group_name] = "、".join(texts) if texts else ""

    summary = _summarize_quantitative(meta, results, extra_parts)

    tags = _apply_tag_rules(meta.get("tag_rules", []), ctx, creature.disease)
    if not tags:
        tags = tags_from_results(results)

    return _build_report(meta, results, summary, tags, creature, **extra_keys)


# ──────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────


def generate_report(test_type: str, creature: VirtualCreature) -> dict:
    """
    根据检查类型返回对应的检查报告。

    自动判断检查类型（定量/叙述性/混合）并调用对应的生成逻辑。
    不再需要手动注册 _HANDLERS。

    Args:
        test_type: 检查类型字符串
        creature: VirtualCreature 实例

    Returns:
        结构化检查报告 dict
    """
    _load_templates()
    meta = get_template(test_type)
    state = get_state(creature)
    logger.debug("generate_report(%s): HR=%.0f PaO2=%.1f", test_type, state["HR"], state["PaO2"])

    has_findings = bool(meta.get("findings_rules"))
    has_vitals = bool(meta.get("vitals"))
    has_extra = bool(meta.get("extra_params"))

    # 纯叙述性: 有 findings_rules，无 vitals，无 extra_params
    if has_findings and not has_vitals and not has_extra:
        return _generate_narrative_report(meta, state, creature)

    # 混合类型: 有 findings_rules 且有 vitals/extra_params
    if has_findings and (has_vitals or has_extra):
        return _generate_mixed_report(meta, state, creature)

    # 纯定量: 有 vitals/extra_params，无 findings_rules
    return _generate_quantitative_report(meta, state, creature)