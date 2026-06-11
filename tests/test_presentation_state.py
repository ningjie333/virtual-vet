from __future__ import annotations

import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
SRC = os.path.join(PROJECT_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from src.diseases import create_disease
from src.presentation_state import (
    PresentationRequest,
    build_presented_engine,
)


class FakeEngine:
    def __init__(self, *, body_weight_kg: float, species: str, age_days=None):
        self.body_weight_kg = body_weight_kg
        self.species = species
        self.age_days = age_days
        self.attached = None
        self.simulated_minutes: list[float] = []

    def attach_disease(self, disease) -> None:
        self.attached = disease

    def simulate(self, minutes: float) -> None:
        self.simulated_minutes.append(minutes)


def test_build_presented_engine_uses_explicit_history_minutes():
    disease = create_disease("pneumonia", severity="moderate")
    engine = build_presented_engine(
        request=PresentationRequest(
            disease_name="pneumonia",
            disease=disease,
            weight_kg=12.0,
            history_duration_min=42.0,
        ),
        engine_factory=FakeEngine,
    )

    assert engine.body_weight_kg == 12.0
    assert engine.attached is disease
    assert engine.simulated_minutes == [42.0]


def test_build_presented_engine_uses_stage_default_when_no_override():
    disease = create_disease("pneumonia", severity="moderate")
    engine = build_presented_engine(
        request=PresentationRequest(
            disease_name="pneumonia",
            disease=disease,
            encounter_stage="acute_critical",
        ),
        engine_factory=FakeEngine,
    )

    assert engine.attached is disease
    assert engine.simulated_minutes == [30.0]


def test_build_presented_engine_skips_negative_history_override():
    disease = create_disease("pneumonia", severity="moderate")
    engine = build_presented_engine(
        request=PresentationRequest(
            disease_name="pneumonia",
            disease=disease,
            history_duration_min=-5.0,
        ),
        engine_factory=FakeEngine,
    )

    assert engine.attached is disease
    assert engine.simulated_minutes == []
