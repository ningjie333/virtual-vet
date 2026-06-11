from __future__ import annotations

import os
import sys

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
_SRC = os.path.join(PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from game.action_system import GameState, process_action
from game.runtime_composition import build_external_interpretation_bundle
from game.runtime import GameRuntime
from src.diseases import create_disease
from src.simulation import VirtualCreature


class FakeAdvancer:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def advance_minutes(self, engine, minutes: float) -> None:
        self.calls.append(minutes)


class FakeInterpreter:
    def __init__(self) -> None:
        self.report_calls: list[str] = []
        self.snapshot_calls = 0
        self.phase_calls = 0
        self.summary_calls = 0

    def snapshot(self, engine):
        self.snapshot_calls += 1
        return object()

    def active_signs(self, engine):
        return []

    def sign_tags(self, engine):
        return []

    def report(self, test_type: str, engine):
        self.report_calls.append(test_type)
        return {
            "name": "fake",
            "test_type": test_type,
            "results": [],
            "tags": ["fake_tag"],
            "summary": "fake summary",
            "timestamp_s": engine.current_time_s,
        }

    def phase(self, snapshot):
        self.phase_calls += 1
        return "stable"

    def summary(self, snapshot, elapsed_min: int):
        self.summary_calls += 1
        return {
            "HR_bpm": 123.0,
            "MAP_mmHg": 88.0,
            "SpO2": 99.0,
            "art_PO2": 100.0,
            "art_PCO2": 40.0,
            "pH": 7.4,
            "GFR": 90.0,
            "RR": 22.0,
            "game_time": f"t={elapsed_min}",
            "is_night": False,
        }


class FakeRefresher:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def refresh(self, engine) -> None:
        self.calls.append(engine.current_time_s)


def _healthy_state() -> GameState:
    engine = VirtualCreature(body_weight_kg=20.0)
    return GameState(engine=engine, disease_name="none", time_budget_min=10000)


def test_process_action_can_use_injected_advancer_without_real_simulation(monkeypatch):
    state = _healthy_state()
    advancer = FakeAdvancer()
    refresher = FakeRefresher()
    runtime = GameRuntime(advancer=advancer, refresher=refresher)

    def _should_not_run(*args, **kwargs):
        raise AssertionError("real engine time advance should be bypassed in this test")

    monkeypatch.setattr(state.engine, "simulate", _should_not_run)
    monkeypatch.setattr(state.engine, "advance_seconds", _should_not_run)

    result = process_action(state, "wait", runtime=runtime)

    assert result["success"] is True
    assert result["time_cost_min"] == 10
    assert state.time_elapsed_min == 10
    assert state.engine.current_time_s == 0.0
    assert advancer.calls == [10.0]
    assert refresher.calls == [0.0]


def test_examine_flow_still_works_with_injected_advancer(monkeypatch):
    state = _healthy_state()
    advancer = FakeAdvancer()
    refresher = FakeRefresher()
    runtime = GameRuntime(advancer=advancer, refresher=refresher)

    def _should_not_run(*args, **kwargs):
        raise AssertionError("real engine time advance should be bypassed in this test")

    monkeypatch.setattr(state.engine, "simulate", _should_not_run)
    monkeypatch.setattr(state.engine, "advance_seconds", _should_not_run)

    result = process_action(
        state,
        "examine",
        {"test_type": "physical"},
        runtime=runtime,
    )

    assert result["success"] is True
    assert result["result"]["test_type"] == "physical"
    assert state.reports[0]["test_type"] == "physical"
    assert result["result"]["report_basis"] == "pre_advance"
    assert result["result"]["observed_at_s"] == 0.0
    assert result["result"]["available_after_min"] == 0
    assert result["state_time_s"] == 0.0
    assert advancer.calls == [5.0]
    assert refresher.calls == [0.0]
    assert state.engine.current_time_s == 0.0


def test_process_action_can_use_injected_interpreter(monkeypatch):
    state = _healthy_state()
    advancer = FakeAdvancer()
    interpreter = FakeInterpreter()
    refresher = FakeRefresher()
    runtime = GameRuntime(
        advancer=advancer,
        interpreter=interpreter,
        refresher=refresher,
    )

    def _should_not_run(*args, **kwargs):
        raise AssertionError("real engine time advance should be bypassed in this test")

    monkeypatch.setattr(state.engine, "simulate", _should_not_run)
    monkeypatch.setattr(state.engine, "advance_seconds", _should_not_run)

    result = process_action(
        state,
        "examine",
        {"test_type": "physical"},
        runtime=runtime,
    )

    assert result["success"] is True
    assert result["result"]["test_type"] == "physical"
    assert result["result"]["summary"] == "fake summary"
    assert result["engine_summary"]["HR_bpm"] == 123.0
    assert result["medical_phase"] == "stable"
    assert interpreter.report_calls == ["physical"]
    assert interpreter.snapshot_calls == 1
    assert interpreter.phase_calls == 1
    assert interpreter.summary_calls == 1
    assert refresher.calls == [0.0]


def test_runtime_advance_and_refresh_calls_both_in_order():
    advancer = FakeAdvancer()
    refresher = FakeRefresher()
    runtime = GameRuntime(advancer=advancer, refresher=refresher)
    engine = VirtualCreature(body_weight_kg=20.0)

    runtime.advance_and_refresh(engine, 12.0)

    assert advancer.calls == [12.0]
    assert refresher.calls == [0.0]


def test_external_interpretation_bundle_can_be_owned_outside_engine(monkeypatch):
    state = _healthy_state()
    advancer = FakeAdvancer()
    bundle = build_external_interpretation_bundle(state.engine, advancer=advancer)

    def _should_not_run(*args, **kwargs):
        raise AssertionError("real engine time advance should be bypassed in this test")

    monkeypatch.setattr(state.engine, "simulate", _should_not_run)
    monkeypatch.setattr(state.engine, "advance_seconds", _should_not_run)

    result = process_action(
        state,
        "examine",
        {"test_type": "physical"},
        runtime=bundle.runtime,
    )

    assert result["success"] is True
    assert result["result"]["test_type"] == "physical"
    assert advancer.calls == [5.0]
    assert bundle.runtime.interpreter.sign_tags(state.engine) == []
    assert bundle.signs_engine is not None


def test_external_interpretation_bundle_seeds_signs_once(monkeypatch):
    engine = VirtualCreature(body_weight_kg=20.0)
    calls: list[float] = []

    original_compute = __import__(
        "game.runtime_composition", fromlist=["ClinicalSignsEngine"]
    ).ClinicalSignsEngine.compute

    def _wrapped_compute(self, current_time_s: float):
        calls.append(current_time_s)
        return original_compute(self, current_time_s)

    monkeypatch.setattr(
        "game.runtime_composition.ClinicalSignsEngine.compute",
        _wrapped_compute,
    )

    bundle = build_external_interpretation_bundle(engine)

    assert bundle.signs_engine is not None
    assert calls == [0.0]


def test_virtual_creature_can_disable_legacy_clinical_signs_refresh():
    engine = VirtualCreature(
        body_weight_kg=20.0,
        legacy_clinical_signs_enabled=False,
    )

    engine.attach_disease(create_disease("pneumonia"))
    engine.advance_seconds(0.1)

    assert not hasattr(engine, "clinical_signs_engine")


def test_default_runtime_keeps_existing_time_mapping():
    state = GameState(
        engine=VirtualCreature(body_weight_kg=20.0, dt=10.0),
        disease_name="none",
        time_budget_min=10000,
    )

    result = process_action(state, "wait")

    assert result["success"] is True
    assert result["time_cost_min"] == 10
    assert state.engine.current_time_s == pytest.approx(600.0, abs=5.0)
