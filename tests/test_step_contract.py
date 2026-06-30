"""
tests/test_step_contract.py — R3 StepGuard contract enforcement tests.

Verifies that:
1. StepGuard tracks phase progression correctly
2. require() raises on missing phases
3. require_not() raises on already-completed phases
4. Invariants are tracked separately from phases
5. Intentional divergences are recorded (not raised)
6. Step functions with guard=None skip checks (backward compat)
7. Euler step driver completes all required phases
"""
from __future__ import annotations

import pytest

from src.engine.step_contract import (
    StepGuard,
    StepContractError,
    PHASE_PRE_DISPATCH,
    PHASE_HEART_COMPUTE,
    PHASE_ORGAN_CHAIN,
    PHASE_PHYSIOLOGY_POST,
    PHASE_COUPLING_PUBLISH,
    PHASE_ORGAN_HEALTH_TRACK,
    PHASE_ORGAN_HEALTH_APPLY,
    PHASE_REFRESH_DICTS,
    PHASE_HISTORY,
    INV_BASELINES_SNAPSHOTTED,
    INV_BASELINES_CLEARED,
)


# ── Unit tests for StepGuard itself ──────────────────────────────────────────

class TestStepGuardBasic:
    """Test StepGuard as a standalone contract tracker."""

    def test_mark_and_has(self):
        guard = StepGuard(label="test")
        assert not guard.has(PHASE_HEART_COMPUTE)
        guard.mark(PHASE_HEART_COMPUTE)
        assert guard.has(PHASE_HEART_COMPUTE)

    def test_require_passes_when_phase_completed(self):
        guard = StepGuard(label="test")
        guard.mark(PHASE_HEART_COMPUTE)
        # Should not raise
        guard.require(PHASE_HEART_COMPUTE)

    def test_require_raises_on_missing_phase(self):
        guard = StepGuard(label="test")
        with pytest.raises(StepContractError, match="requires phases.*heart_compute"):
            guard.require(PHASE_HEART_COMPUTE)

    def test_require_not_raises_when_phase_already_done(self):
        guard = StepGuard(label="test")
        guard.mark(PHASE_HEART_COMPUTE)
        with pytest.raises(StepContractError, match="already ran.*heart_compute"):
            guard.require_not(PHASE_HEART_COMPUTE)

    def test_require_not_passes_when_phase_not_done(self):
        guard = StepGuard(label="test")
        # Should not raise
        guard.require_not(PHASE_HEART_COMPUTE)

    def test_completed_phases_preserves_order(self):
        guard = StepGuard(label="test")
        guard.mark(PHASE_PRE_DISPATCH)
        guard.mark(PHASE_HEART_COMPUTE)
        guard.mark(PHASE_HISTORY)
        assert guard.completed_phases() == (
            PHASE_PRE_DISPATCH, PHASE_HEART_COMPUTE, PHASE_HISTORY
        )

    def test_reset_clears_all_state(self):
        guard = StepGuard(label="test")
        guard.mark(PHASE_HEART_COMPUTE)
        guard.set_invariant(INV_BASELINES_SNAPSHOTTED)
        guard.reset()
        assert not guard.has(PHASE_HEART_COMPUTE)
        assert not guard.has_invariant(INV_BASELINES_SNAPSHOTTED)
        assert guard.completed_phases() == ()


class TestStepGuardInvariants:
    """Test invariant tracking (booleans, not ordered)."""

    def test_set_and_check_invariant(self):
        guard = StepGuard(label="test")
        assert not guard.has_invariant(INV_BASELINES_SNAPSHOTTED)
        guard.set_invariant(INV_BASELINES_SNAPSHOTTED)
        assert guard.has_invariant(INV_BASELINES_SNAPSHOTTED)

    def test_require_invariant_passes(self):
        guard = StepGuard(label="test")
        guard.set_invariant(INV_BASELINES_SNAPSHOTTED)
        guard.require_invariant(INV_BASELINES_SNAPSHOTTED)  # no raise

    def test_require_invariant_raises(self):
        guard = StepGuard(label="test")
        with pytest.raises(StepContractError, match="requires invariants.*baselines_snapshotted"):
            guard.require_invariant(INV_BASELINES_SNAPSHOTTED)

    def test_require_invariant_not_raises(self):
        guard = StepGuard(label="test")
        guard.set_invariant(INV_BASELINES_CLEARED)
        with pytest.raises(StepContractError, match="baselines_cleared.*already set"):
            guard.require_invariant_not(INV_BASELINES_CLEARED)

    def test_snapshot_after_clear_raises(self):
        """The key R3 invariant: cannot snapshot baselines after clearing them."""
        guard = StepGuard(label="test")
        guard.set_invariant(INV_BASELINES_CLEARED)
        with pytest.raises(StepContractError, match="baselines_cleared.*already set"):
            guard.require_invariant_not(INV_BASELINES_CLEARED)


class TestStepGuardDivergences:
    """Test intentional divergence tracking."""

    def test_divergence_recorded_not_raised(self):
        guard = StepGuard(label="test")
        guard.divergence_ok("immune_order", "test reason")
        assert len(guard.divergences()) == 1
        name, reason = guard.divergences()[0]
        assert name == "immune_order"
        assert "test reason" in reason

    def test_multiple_divergences(self):
        guard = StepGuard(label="test")
        guard.divergence_ok("immune_order", "reason 1")
        guard.divergence_ok("disease_order", "reason 2")
        assert len(guard.divergences()) == 2

    def test_reset_clears_divergences(self):
        guard = StepGuard(label="test")
        guard.divergence_ok("immune_order", "test")
        guard.reset()
        assert len(guard.divergences()) == 0


class TestStepGuardDisabled:
    """Test that disabled guard skips all checks (backward compat)."""

    def test_disabled_guard_skips_require(self):
        guard = StepGuard(label="test", enabled=False)
        # Should NOT raise even though phase not marked
        guard.require(PHASE_HEART_COMPUTE)

    def test_disabled_guard_skips_require_not(self):
        guard = StepGuard(label="test", enabled=False)
        guard.mark(PHASE_HEART_COMPUTE)
        # Should NOT raise even though phase already done
        guard.require_not(PHASE_HEART_COMPUTE)

    def test_disabled_guard_skips_mark(self):
        guard = StepGuard(label="test", enabled=False)
        guard.mark(PHASE_HEART_COMPUTE)
        assert not guard.has(PHASE_HEART_COMPUTE)


# ── Integration tests: step functions with guard ─────────────────────────────

class TestStepFunctionContracts:
    """Test that step_common functions enforce contracts when guard is provided."""

    def test_run_organ_compute_chain_requires_heart_compute(self, tmp_path):
        """run_organ_compute_chain should raise if PHASE_HEART_COMPUTE not marked."""
        from src.engine.step_common import run_organ_compute_chain
        from src.simulation import VirtualCreature

        engine = VirtualCreature()
        guard = StepGuard(label="test")
        # Don't mark PHASE_HEART_COMPUTE
        gut_state = engine.gut.compute(engine.dt, engine.heart.cardiac_output)
        heart_state = {"heart_rate_bpm": 80, "MAP_mmHg": 90, "cardiac_output_ml_min": 4000}
        lung_state = {"arterial_PO2": 95}
        with pytest.raises(StepContractError, match="requires phases.*heart_compute"):
            run_organ_compute_chain(
                engine, engine.dt, gut_state, heart_state, lung_state, guard=guard
            )

    def test_run_organ_compute_chain_passes_with_heart_compute(self, tmp_path):
        """run_organ_compute_chain should succeed when PHASE_HEART_COMPUTE is marked."""
        from src.engine.step_common import run_organ_compute_chain
        from src.simulation import VirtualCreature

        engine = VirtualCreature()
        guard = StepGuard(label="test")
        guard.mark(PHASE_HEART_COMPUTE)
        gut_state = engine.gut.compute(engine.dt, engine.heart.cardiac_output)
        heart_state = {"heart_rate_bpm": 80, "MAP_mmHg": 90, "cardiac_output_ml_min": 4000}
        lung_state = {"arterial_PO2": 95}
        result = run_organ_compute_chain(
            engine, engine.dt, gut_state, heart_state, lung_state, guard=guard
        )
        assert PHASE_ORGAN_CHAIN in guard.completed_phases()
        assert "liver" in result

    def test_run_coupling_requires_physiology_post(self, tmp_path):
        """run_coupling should raise if PHASE_PHYSIOLOGY_POST not marked."""
        from src.engine.step_common import run_coupling
        from src.simulation import VirtualCreature

        engine = VirtualCreature()
        guard = StepGuard(label="test")
        # Don't mark PHASE_PHYSIOLOGY_POST
        with pytest.raises(StepContractError, match="requires phases.*physiology_post"):
            run_coupling(engine, engine.dt, signal_time=0.0, guard=guard)

    def test_refresh_state_dicts_requires_organ_health_apply(self, tmp_path):
        """refresh_state_dicts should raise if PHASE_ORGAN_HEALTH_APPLY not marked."""
        from src.engine.step_common import refresh_state_dicts
        from src.simulation import VirtualCreature

        engine = VirtualCreature()
        guard = StepGuard(label="test")
        heart_state = {"heart_rate_bpm": 80}
        with pytest.raises(StepContractError, match="requires phases.*organ_health_apply"):
            refresh_state_dicts(engine, heart_state, guard=guard)

    def test_guard_none_skips_checks(self, tmp_path):
        """Functions with guard=None should skip all contract checks (backward compat)."""
        from src.engine.step_common import run_organ_compute_chain
        from src.simulation import VirtualCreature

        engine = VirtualCreature()
        # Should NOT raise even though no guard phases marked
        gut_state = engine.gut.compute(engine.dt, engine.heart.cardiac_output)
        heart_state = {"heart_rate_bpm": 80, "MAP_mmHg": 90, "cardiac_output_ml_min": 4000}
        lung_state = {"arterial_PO2": 95}
        result = run_organ_compute_chain(
            engine, engine.dt, gut_state, heart_state, lung_state, guard=None
        )
        assert "liver" in result


class TestStepGuardNoneBackwardCompat:
    """Test that all step functions work with guard=None (default)."""

    def test_run_pre_dispatch_guard_none(self):
        from src.engine.step_common import run_pre_dispatch
        from src.simulation import VirtualCreature
        engine = VirtualCreature()
        # Should not raise
        run_pre_dispatch(engine, guard=None)

    def test_run_physiology_post_guard_none(self):
        from src.engine.step_common import run_physiology_post
        from src.simulation import VirtualCreature
        engine = VirtualCreature()
        # Should not raise (no prerequisite check with guard=None)
        run_physiology_post(engine, engine.dt, guard=None)

    def test_snapshot_baselines_guard_none(self):
        from src.engine.factor_pipeline import snapshot_baselines, clear_baselines
        from src.simulation import VirtualCreature
        engine = VirtualCreature()
        snapshot_baselines(engine, guard=None)
        clear_baselines(guard=None)


# ── Integration tests: Euler driver completes all phases ─────────────────────

class TestEulerStepCompletesAllPhases:
    """Verify that _step_euler marks all required phases via the guard."""

    def test_euler_step_completes_without_contract_violation(self):
        """A single Euler step should complete without raising StepContractError."""
        from src.simulation import VirtualCreature
        engine = VirtualCreature(record_history=False)
        # This will raise StepContractError if any contract is violated
        engine.step()
        # If we get here, all contracts passed

    def test_euler_multiple_steps_no_violation(self):
        """Multiple Euler steps should complete without contract violations."""
        from src.simulation import VirtualCreature
        engine = VirtualCreature(record_history=False)
        for _ in range(10):
            engine.step()
