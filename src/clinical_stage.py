"""
Clinical stage computation — 从 ODE 状态变量计算临床分期标签。

独立模块，不依赖 ConfigDrivenDiseaseModule，不修改 ode_diseases.json。
阈值硬编码（按疾病查表），验证有效后再考虑外推到 JSON schema。

Phase 1 (2026-06-14): 谨慎实现，仅 pneumonia + DCM + ARF 三个疾病。
其余疾病返回 "unknown"（后续按需扩展）。

使用方式:
    from src.clinical_stage import compute_clinical_stage
    stage = compute_clinical_stage("pneumonia", {"alveolar_exudate": 0.5, ...})
    # → "moderate"
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── 疾病特异性阈值（硬编码，Phase 1） ──────────────────────────────────
# 格式: {disease_name: (primary_var, (mild_threshold, moderate_threshold))}
# mild_threshold 以下 = mild, 之间 = moderate, 以上 = severe
# 阈值来自 severity_design_proposal.md 的临床分期示例 + 生理合理性

_CLINICAL_STAGE_RULES: dict[str, tuple[str, tuple[float, float]]] = {
    # pneumonia: exudate < 0.3 = mild, 0.3-0.7 = moderate, > 0.7 = severe
    # (severity_design_proposal.md 原始示例)
    "pneumonia": ("alveolar_exudate", (0.3, 0.7)),

    # DCM: fibrosis < 0.2 = mild (compensated), 0.2-0.5 = moderate (decompensated),
    # > 0.5 = severe (heart failure). 阈值来自 DCM ODE 的 exudate_K 范围 (0.4-0.95)
    # 的中位数估算。
    "dilated_cardiomyopathy": ("cardiac_fibrosis", (0.2, 0.5)),

    # ARF: nephron_damage < 0.3 = mild (GFR still >70%), 0.3-0.7 = moderate (GFR 30-70%),
    # > 0.7 = severe (GFR <30%). 阈值来自 Nelson & Couto 5e Ch53 的 GFR 分期。
    "acute_renal_failure": ("nephron_damage", (0.3, 0.7)),
}


def compute_clinical_stage(
    disease_name: str,
    state_vars: dict[str, Any],
) -> str:
    """从 ODE 状态变量计算临床分期标签。

    Args:
        disease_name: 疾病名称 (如 "pneumonia")
        state_vars: 疾病 ODE 状态变量快照 (如 {"alveolar_exudate": 0.5, ...})

    Returns:
        "mild" / "moderate" / "severe" / "unknown"
        "unknown" 表示该疾病尚未配置阈值（Phase 1 仅覆盖 3 个疾病）
    """
    rule = _CLINICAL_STAGE_RULES.get(disease_name)
    if rule is None:
        return "unknown"

    primary_var, (mild_thresh, severe_thresh) = rule
    value = state_vars.get(primary_var, 0.0)

    if value < mild_thresh:
        return "mild"
    if value < severe_thresh:
        return "moderate"
    return "severe"


def list_supported_diseases() -> list[str]:
    """返回已配置阈值的疾病列表（调试用）。"""
    return sorted(_CLINICAL_STAGE_RULES.keys())
