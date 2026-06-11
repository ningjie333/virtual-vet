from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.simulation import VirtualCreature


@dataclass(frozen=True)
class PresentationRequest:
    """Kernel-adjacent request for constructing an encounter-start engine state."""

    disease_name: str
    disease: object
    weight_kg: float = 20.0
    species: str = "canine"
    age_days: float | None = None
    encounter_stage: str = "acute_progressed"
    history_duration_min: float | None = None


def build_presented_engine(
    *,
    request: PresentationRequest,
    engine_factory: Callable[..., VirtualCreature] | None = None,
) -> VirtualCreature:
    """
    Build an encounter-ready engine from explicit presentation-state inputs.

    V1 keeps the kernel's physical-time semantics unchanged.
    It simply centralizes pre-encounter replay behind one seam so callers stop
    scattering raw `attach_disease()` + `simulate(...)` logic.
    """
    engine_factory = engine_factory or VirtualCreature

    engine_kwargs = {
        "body_weight_kg": request.weight_kg,
        "species": request.species,
    }
    if request.age_days is not None:
        engine_kwargs["age_days"] = request.age_days

    engine = engine_factory(**engine_kwargs)
    engine.attach_disease(request.disease)

    history_minutes = _resolve_history_duration_min(request)
    if history_minutes > 0:
        engine.simulate(history_minutes)

    return engine


def _resolve_history_duration_min(request: PresentationRequest) -> float:
    """
    Resolve encounter-start replay in physical minutes.

    V1 policy is intentionally simple:
    - explicit override wins
    - otherwise use conservative stage defaults
    """
    if request.history_duration_min is not None:
        return max(0.0, float(request.history_duration_min))

    return _default_history_duration_min(request.encounter_stage)


def _default_history_duration_min(encounter_stage: str) -> float:
    stage_defaults = {
        "acute_early": 5.0,
        "acute_progressed": 15.0,
        "acute_critical": 30.0,
        "subacute_presenting": 180.0,
        "chronic_compensated": 720.0,
        "chronic_decompensated": 1440.0,
    }
    return stage_defaults.get(encounter_stage, stage_defaults["acute_progressed"])
