from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from game.runtime import GameRuntime
from src.clinical_interpreter import DefaultClinicalInterpreter
from src.clinical_signs_engine import ClinicalSignsEngine
from src.engine_advancer import EngineAdvancerProtocol, PhysicalMinuteAdvancer
from src.interpretation_refresher import ClinicalSignsRefresher


@dataclass(frozen=True)
class ExternalInterpretationBundle:
    """Outer-owned interpretation support bound to a specific engine."""

    signs_engine: ClinicalSignsEngine
    runtime: GameRuntime


_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def build_external_interpretation_bundle(
    engine: Any,
    *,
    species: str | None = None,
    symptom_definitions: dict | None = None,
    advancer: EngineAdvancerProtocol | None = None,
) -> ExternalInterpretationBundle:
    """
    Build an outer-owned interpretation stack for one engine.

    This does not modify kernel lifecycle ownership yet. It simply makes an
    external ownership path available for application/runtime composition.
    """
    defs = symptom_definitions or _load_symptom_definitions()
    species_name = species or getattr(engine, "species", "dog")
    signs_engine = ClinicalSignsEngine(engine, defs, species_name)

    def _resolve_signs_engine(_: Any) -> ClinicalSignsEngine:
        return signs_engine

    interpreter = DefaultClinicalInterpreter(
        signs_engine_resolver=_resolve_signs_engine,
    )
    refresher = ClinicalSignsRefresher(
        signs_engine_resolver=_resolve_signs_engine,
    )
    signs_engine.compute(getattr(engine, "current_time_s", 0.0))
    runtime = GameRuntime(
        advancer=advancer or PhysicalMinuteAdvancer(),
        interpreter=interpreter,
        refresher=refresher,
    )
    return ExternalInterpretationBundle(
        signs_engine=signs_engine,
        runtime=runtime,
    )


def _load_symptom_definitions() -> dict:
    with open(_DATA_DIR / "symptom_definitions.json", "r", encoding="utf-8") as f:
        return json.load(f)
