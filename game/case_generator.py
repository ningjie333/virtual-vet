"""
Case Generator — 随机病例生成器。

生成完整的游戏开局：随机动物 + 随机疾病 + 初始化引擎 + 疾病发展期 → GameState。
"""

from __future__ import annotations

import logging
import os
import json
import random
from typing import Optional

from src.diseases import list_diseases, create_disease
from src.presentation_state import PresentationRequest, build_presented_engine
from game.action_system import GameState

logger = logging.getLogger(__name__)

# ── 内建动物数据（8 种犬类） ──
DEFAULT_ANIMALS = [
    {"species": "犬", "breed": "拉布拉多",   "weight_kg": 28.0, "age_years": 3},
    {"species": "犬", "breed": "边境牧羊犬", "weight_kg": 18.0, "age_years": 2},
    {"species": "犬", "breed": "德国牧羊犬", "weight_kg": 32.0, "age_years": 4},
    {"species": "犬", "breed": "金毛",       "weight_kg": 30.0, "age_years": 5},
    {"species": "犬", "breed": "泰迪",       "weight_kg": 6.5,  "age_years": 6},
    {"species": "犬", "breed": "柯基",       "weight_kg": 12.0, "age_years": 3},
    {"species": "犬", "breed": "哈士奇",     "weight_kg": 22.0, "age_years": 2},
    {"species": "犬", "breed": "中华田园犬", "weight_kg": 20.0, "age_years": 4},
]

# 难度 → 严重度概率映射
_SEVERITY_WEIGHTS = {
    "easy":   {"mild": 0.7, "moderate": 0.3, "severe": 0.0},
    "normal": {"mild": 0.2, "moderate": 0.5, "severe": 0.3},
    "hard":   {"mild": 0.0, "moderate": 0.3, "severe": 0.7},
}


def _load_animals() -> list[dict]:
    """加载动物数据：优先 data/animals.json，回退到内建默认"""
    json_path = os.path.join(os.path.dirname(__file__), "..", "data", "animals.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and isinstance(data, list):
                logger.info("从 %s 加载了 %d 种动物", json_path, len(data))
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("加载 animals.json 失败: %s，使用内建数据", e)
    return DEFAULT_ANIMALS


def _pick_disease(difficulty: str, rng: random.Random) -> tuple[str, object]:
    """随机选疾病 + 严重度。返回 (disease_name, disease_instance)"""
    available = list_diseases()
    if not available:
        raise RuntimeError("没有可用的疾病模块（src.diseases.list_diseases() 返回空）")

    disease_name = rng.choice(available)

    weights = _SEVERITY_WEIGHTS.get(difficulty, _SEVERITY_WEIGHTS["normal"])
    severities = list(weights.keys())
    probs = list(weights.values())

    # 过滤掉权重为 0 的选项
    active = [(s, p) for s, p in zip(severities, probs) if p > 0]
    if not active:
        severity = "moderate"
    else:
        sevs, ps = zip(*active)
        severity = rng.choices(sevs, weights=ps, k=1)[0]

    disease = create_disease(disease_name, severity=severity)
    logger.debug("选择疾病: %s (%s)", disease_name, severity)
    return disease_name, disease


def _init_engine(weight_kg: float, disease, rng: random.Random):
    """
    创建引擎，附着疾病，让疾病发展一段时间（模拟就诊前病程）。
    发展期 5-30 分钟，重度疾病发展更长。
    """
    pre_visit_min = rng.uniform(5, 30)
    engine = build_presented_engine(
        request=PresentationRequest(
            disease_name=disease.name,
            disease=disease,
            weight_kg=weight_kg,
            history_duration_min=pre_visit_min,
        )
    )

    logger.info(
        "引擎初始化: weight=%.1fkg, 疾病发展 %.1f min, HR=%.0f, SpO2=%.1f%%",
        weight_kg, pre_visit_min,
        engine.history["HR_bpm"][-1] if engine.history["HR_bpm"] else 0,
        (engine.history["saturation"][-1] * 100) if engine.history["saturation"] else 0,
    )
    return engine


def generate_case(difficulty: str = "normal", seed: int = None) -> GameState:
    """
    生成一个随机病例。

    Args:
        difficulty: "easy" | "normal" | "hard"
        seed: 随机种子（None = 真随机）

    Returns:
        GameState 实例（引擎已初始化、疾病已附着、仿真已推进一段疾病发展期）
    """
    rng = random.Random(seed)

    animals = _load_animals()
    animal = rng.choice(animals)
    disease_name, disease = _pick_disease(difficulty, rng)
    engine = _init_engine(animal["weight_kg"], disease, rng)

    state = GameState(
        engine=engine,
        disease_name=disease_name,
        phase="playing",
        death_timer=None,
        reports=[],
        treatment_applied=None,
    )

    logger.info(
        "病例生成: %s %s %.1fkg %d岁 | %s | seed=%s",
        animal["species"], animal["breed"], animal["weight_kg"], animal["age_years"],
        disease_name, seed,
    )

    return state
