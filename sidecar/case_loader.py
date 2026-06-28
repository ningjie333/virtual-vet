"""病例装载器：读 cases.json + 构造引擎与游戏状态。

复用 gui_app.py 中的核心函数（`build_presented_engine`、`_parse_age_days`、
`_lifecycle_mode_for_age`、`create_disease`、`_get_time_budget`），
保证 sidecar 与现有 Flask 应用行为一致。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gui_app import (
    _get_time_budget,
    _lifecycle_mode_for_age,
    _parse_age_days,
)
from game.action_system import GameState
from game.runtime import GameRuntime
from game.runtime_composition import build_external_interpretation_bundle
from src.presentation_state import PresentationRequest, build_presented_engine
from src.simulation import VirtualCreature

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_CASES_CACHE: dict[str, dict] | None = None


@dataclass
class CaseSummary:
    """病历选项卡上展示的元信息（不含敏感诊断细节）。"""

    id: str
    title: str
    difficulty: int
    difficulty_label: str
    species: str
    breed: str
    age: str
    weight_kg: float
    chief_complaint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "difficulty": self.difficulty,
            "difficulty_label": self.difficulty_label,
            "species": self.species,
            "breed": self.breed,
            "age": self.age,
            "weight_kg": self.weight_kg,
            "chief_complaint": self.chief_complaint,
        }


def load_cases() -> list[CaseSummary]:
    """读取 data/cases.json，返回选项卡栏用的病历摘要列表。

    不暴露 disease / disease_onset_s / starting_hints 等字段——
    vet-knowledge 前端只看到病历外壳，诊断考验由玩家完成。
    """
    raw = _load_cases_raw()
    out: list[CaseSummary] = []
    for c in raw["cases"]:
        animal = c["animal"]
        out.append(
            CaseSummary(
                id=c["id"],
                title=c.get("title", c["id"]),
                difficulty=int(c.get("difficulty", 2)),
                difficulty_label=c.get("difficulty_label", "★★☆"),
                species=animal.get("species", "犬"),
                breed=animal.get("breed", ""),
                age=animal.get("age", ""),
                weight_kg=float(animal.get("weight_kg", 20.0)),
                chief_complaint=c.get("chief_complaint", ""),
            )
        )
    return out


def _load_cases_raw() -> dict[str, Any]:
    """加载 cases.json 并缓存（首次加载后内存常驻）。"""
    global _CASES_CACHE
    if _CASES_CACHE is None:
        with open(_DATA_DIR / "cases.json", "r", encoding="utf-8") as f:
            _CASES_CACHE = json.load(f)
    return _CASES_CACHE


def find_case(case_id: str) -> dict[str, Any]:
    """根据 case_id 查找完整病历；未找到抛 KeyError。"""
    raw = _load_cases_raw()
    for c in raw["cases"]:
        if c["id"] == case_id:
            return c
    raise KeyError(case_id)


@dataclass
class SessionContext:
    """单个游戏会话的完整上下文。

    - `engine`: VirtualCreature 实例
    - `state`: GameState（含 phase/time_elapsed_min/death_timer 等）
    - `runtime`: R7 五协作者 GameRuntime
    - `case`: 原始 case 字典（用于序列化 initial snapshot）
    """

    engine: VirtualCreature
    state: GameState
    runtime: GameRuntime
    case: dict[str, Any]


def create_session(case_id: str) -> SessionContext:
    """根据病历创建新会话。

    复用 gui_app.api_new_game 的构造逻辑（去掉 Flask/SQLite 持久化部分）。
    """
    case = find_case(case_id)

    animal = case["animal"]
    weight_kg = float(animal["weight_kg"])
    species_str = animal.get("species", "犬")
    species_map = {
        "犬": "canine",
        "猫": "feline",
        "马": "equine",
        "canine": "canine",
        "feline": "feline",
        "equine": "equine",
    }
    species_en = species_map.get(species_str, "canine")

    age_str = animal.get("age", "3岁")
    age_days = _parse_age_days(age_str, species_str)
    lifecycle_mode = _lifecycle_mode_for_age(age_days, species_en)

    disease_name = case["disease"]
    disease = _create_disease(disease_name)
    extra_disease_names = list(case.get("diseases", []))
    if extra_disease_names and extra_disease_names[0] == disease_name:
        extra_disease_names = extra_disease_names[1:]
    extra_diseases = tuple(_create_disease(n) for n in extra_disease_names)

    history_duration_min = int(
        case.get("history_duration_min", case.get("warmup_minutes", 2))
    )

    engine = build_presented_engine(
        request=PresentationRequest(
            disease_name=disease_name,
            disease=disease,
            weight_kg=weight_kg,
            species=species_en,
            age_days=age_days,
            history_duration_min=history_duration_min,
            extra_diseases=extra_diseases,
            extra_disease_names=tuple(extra_disease_names),
        ),
        engine_factory=lambda **kwargs: VirtualCreature(
            lifecycle_mode=lifecycle_mode,
            legacy_clinical_signs_enabled=False,
            **kwargs,
        ),
    )

    difficulty = int(case.get("difficulty", 2))
    time_budget = _get_time_budget(difficulty)

    state = GameState(
        engine=engine,
        disease_name=disease_name,
        disease_names=[disease_name] + list(extra_disease_names),
        species=species_str,
        time_budget_min=time_budget,
    )

    runtime = build_external_interpretation_bundle(engine).runtime

    return SessionContext(engine=engine, state=state, runtime=runtime, case=case)


def _create_disease(name: str):
    """疾病模块工厂，转发到 gui_app 使用的同一实现。

    gui_app 通过 `from src.diseases import create_disease` 导入；sidecar 也用此路径
    保证一致。封装为函数而非直接 import 是为了未来可替换实现。
    """
    from src.diseases import create_disease

    return create_disease(name)
