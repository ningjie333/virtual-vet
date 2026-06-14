"""
Multi-disease regression tests — Q2 spec (2026-06-14).

Verifies the chained-rebase merge semantics for VirtualCreature.attach_disease
when multiple DiseaseModules are attached. The spec:

  - multiply 链 = 复合（DCM 0.7 × 肺炎 0.8 = 0.56）
  - add 链     = 累加（+5 + +10 = +15）
  - set 链     = 后写者赢（last-wins，最相关的临床上下文）

These tests are the contract for VirtualCreature.diseases (list) and
apply_factor()'s chained-rebase behavior. Any change that breaks these
tests means a regression in Q2 merge semantics.

See:
  docs/severity_design_proposal.md §"技术问题核实结果" / Q2 (decision: A)
  src/diseases/__init__.py::DiseaseModule (Q2 spec docstring)
"""
from __future__ import annotations

import pytest

from src.simulation import VirtualCreature
from src.diseases import DiseaseModule
from src.common_types import FactorCommand


# ─── Test helpers ────────────────────────────────────────────────────────


class _CmdDisease(DiseaseModule):
    """A DiseaseModule that returns a fixed list of FactorCommands every step.

    Use in tests to assert exact chained-rebase behavior on a target.
    """

    def __init__(self, name: str, cmds: list[FactorCommand]):
        super().__init__(name=name)
        self._cmds = list(cmds)

    def compute(self, dt: float, engine_state: dict) -> list[FactorCommand]:
        return list(self._cmds) if self.active else []


# ─── Test cases ──────────────────────────────────────────────────────────


class TestMultiDiseaseAttach:
    """Q1 spec: attach_disease 支持多病叠加 (self.diseases: list)."""

    def test_attach_appends_to_list(self):
        """Two attach_disease() calls → 2 entries in self.diseases, in order."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=5.0)
        d1 = _CmdDisease("d1", [])
        d2 = _CmdDisease("d2", [])
        vc.attach_disease(d1)
        vc.attach_disease(d2)
        assert vc.diseases == [d1, d2]
        assert vc.disease is d1  # backward-compat property: first disease

    def test_disease_property_none_when_empty(self):
        """Empty diseases list → .disease returns None (backward compat)."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=5.0)
        assert vc.disease is None
        assert vc.diseases == []

    def test_attach_activates_each(self):
        """Each attached disease should be activated (active=True)."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=5.0)
        d1 = _CmdDisease("d1", [])
        d2 = _CmdDisease("d2", [])
        vc.attach_disease(d1)
        vc.attach_disease(d2)
        assert d1.active is True
        assert d2.active is True


class TestChainedRebaseMultiply:
    """Q2 spec: multiply ops chain multiplicatively."""

    def test_two_diseases_multiply_same_target(self):
        """DCM ×0.7 + 肺炎 ×0.8 → cardiac_output final = base × 0.56."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=5.0)
        d1 = _CmdDisease("dcm", [FactorCommand("heart.cardiac_output", "multiply", 0.7)])
        d2 = _CmdDisease("pneumonia", [FactorCommand("heart.cardiac_output", "multiply", 0.8)])
        vc.attach_disease(d1)
        vc.attach_disease(d2)
        baseline_co = vc.heart.cardiac_output
        vc.step()
        # The chained-rebase formula: base × 0.7 × 0.8 = base × 0.56
        expected_co = baseline_co * 0.7 * 0.8
        # Allow small numerical drift from physics solve in same step
        assert abs(vc.heart.cardiac_output - expected_co) < 1.0, (
            f"Expected ~{expected_co:.1f}, got {vc.heart.cardiac_output:.1f}"
        )


class TestChainedRebaseAdd:
    """Q2 spec: add ops chain additively."""

    def test_two_diseases_add_same_target(self):
        """+5 + +10 → heart_rate +15."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=5.0)
        baseline_hr = vc.heart.heart_rate
        d1 = _CmdDisease("pain", [FactorCommand("heart.heart_rate", "add", 5.0)])
        d2 = _CmdDisease("fever", [FactorCommand("heart.heart_rate", "add", 10.0)])
        vc.attach_disease(d1)
        vc.attach_disease(d2)
        vc.step()
        # Note: HR may also be affected by baroreflex in same step; the
        # critical assertion is that BOTH adds were applied (not just one).
        # We assert the delta is at least 15 (could be more if baroreflex
        # also adds) — verifying both adds happened.
        actual_delta = vc.heart.heart_rate - baseline_hr
        assert actual_delta >= 15.0 - 1.0, (
            f"Expected HR delta ≥ ~15 (both adds), got {actual_delta:.2f}"
        )


class TestChainedRebaseSet:
    """Q2 spec: set ops are last-writer-wins."""

    def test_two_diseases_set_same_target_last_wins(self):
        """Two `set` on same target → later attach wins."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=5.0)
        d1 = _CmdDisease("d1", [FactorCommand("heart.heart_rate", "set", 120.0)])
        d2 = _CmdDisease("d2", [FactorCommand("heart.heart_rate", "set", 140.0)])
        vc.attach_disease(d1)
        vc.attach_disease(d2)
        vc.step()
        # After step, HR should be ~140 (d2's set wins), then baroreflex
        # may correct slightly toward MAP setpoint. The point is d2's set
        # is the dominant write — NOT a chain (set doesn't combine).
        # We assert HR is closer to 140 than to 120.
        assert abs(vc.heart.heart_rate - 140.0) < abs(vc.heart.heart_rate - 120.0), (
            f"Expected HR closer to 140 (d2's set), got {vc.heart.heart_rate}"
        )


class TestMultiDiseaseOrderMatters:
    """Q2 spec: attach order determines chained-rebase order (first = baseline)."""

    def test_order_matters_for_multiply_chain(self):
        """Same two diseases attached in different order → same final result
        (multiplicative chains are commutative).

        This guards against accidentally introducing ordering-dependent
        behavior in chained-rebase multiply chains.
        """
        # Order A: DCM then 肺炎
        vc_a = VirtualCreature(body_weight_kg=20.0, species="canine", dt=5.0)
        vc_a.attach_disease(_CmdDisease("dcm", [FactorCommand("heart.cardiac_output", "multiply", 0.7)]))
        vc_a.attach_disease(_CmdDisease("pneumonia", [FactorCommand("heart.cardiac_output", "multiply", 0.8)]))
        baseline_a = vc_a.heart.cardiac_output
        vc_a.step()
        result_a = vc_a.heart.cardiac_output

        # Order B: 肺炎 then DCM (same diseases, swapped)
        vc_b = VirtualCreature(body_weight_kg=20.0, species="canine", dt=5.0)
        vc_b.attach_disease(_CmdDisease("pneumonia", [FactorCommand("heart.cardiac_output", "multiply", 0.8)]))
        vc_b.attach_disease(_CmdDisease("dcm", [FactorCommand("heart.cardiac_output", "multiply", 0.7)]))
        baseline_b = vc_b.heart.cardiac_output
        vc_b.step()
        result_b = vc_b.heart.cardiac_output

        # Both should land at base × 0.7 × 0.8 = base × 0.56
        expected_a = baseline_a * 0.56
        expected_b = baseline_b * 0.56
        assert abs(result_a - expected_a) < 1.0, f"order A: expected ~{expected_a:.1f}, got {result_a:.1f}"
        assert abs(result_b - expected_b) < 1.0, f"order B: expected ~{expected_b:.1f}, got {result_b:.1f}"


class TestMultiDiseaseBackwardCompat:
    """Single-disease still works after the Q1 refactor."""

    def test_single_disease_compute_still_runs(self):
        """One disease attached → its compute() is called once per step."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=5.0)
        d1 = _CmdDisease("solo", [FactorCommand("heart.heart_rate", "add", 5.0)])
        vc.attach_disease(d1)
        baseline_hr = vc.heart.heart_rate
        vc.step()
        # The +5 add should be applied
        assert vc.heart.heart_rate >= baseline_hr + 5.0 - 1.0

    def test_no_disease_runs_no_disease_code(self):
        """Empty diseases list → no error, step() works normally."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=5.0)
        assert vc.diseases == []
        for _ in range(5):
            vc.step()  # must not raise
        assert vc.heart.heart_rate > 0  # still producing valid vitals
