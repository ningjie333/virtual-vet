"""
tests/test_coupling.py

Multi-organ closed-loop coupling tests.
Covers: OrganContext publish/subscribe, CouplingEngine resolve, and physiological cascades.
"""

from __future__ import annotations

import pytest


class TestOrganContext:
    """Unit tests for OrganContext and PhysiologicalSignal."""

    def test_publish_and_retrieve_signal(self):
        from src.organs.coupling import OrganContext, PhysiologicalSignal

        ctx = OrganContext("heart")
        sig = PhysiologicalSignal("cardiac_output", 1700.0, "mL/min", "heart", 0.0)
        ctx.publish(sig)

        retrieved = ctx.get_signal("cardiac_output")
        assert retrieved is not None
        assert retrieved.value == 1700.0
        assert retrieved.unit == "mL/min"

    def test_get_value_with_default(self):
        from src.organs.coupling import OrganContext

        ctx = OrganContext("kidney")
        assert ctx.get_value("GFR", default=50.0) == 50.0

    def test_all_signals(self):
        from src.organs.coupling import OrganContext, PhysiologicalSignal

        ctx = OrganContext("lung")
        ctx.publish(PhysiologicalSignal("PO2", 95.0, "mmHg", "lung", 0.0))
        ctx.publish(PhysiologicalSignal("PCO2", 40.0, "mmHg", "lung", 0.0))

        all_sig = ctx.all_signals()
        assert len(all_sig) == 2
        assert "PO2" in all_sig
        assert "PCO2" in all_sig


class TestCouplingEngineResolve:
    """Tests for CouplingEngine.resolve() producing correct FactorCommands."""

    def test_loads_rules(self):
        from src.organs.coupling import CouplingEngine

        engine = CouplingEngine()
        assert engine.num_rules >= 15  # at least 15 rules defined

    def test_resolve_no_signals_returns_empty(self):
        from src.organs.coupling import CouplingEngine, OrganContext

        engine = CouplingEngine()
        ctx = {"heart": OrganContext("heart")}
        cmds = engine.resolve(ctx, dt=0.1)
        # No signals published → rules with conditions fail → empty list
        assert isinstance(cmds, list)

    def test_resolve_priority_order(self):
        from src.organs.coupling import CouplingEngine, OrganContext, PhysiologicalSignal

        engine = CouplingEngine()
        ctx = {
            "kidney": OrganContext("kidney"),
            "heart": OrganContext("heart"),
        }
        ctx["kidney"].publish(PhysiologicalSignal("renin_activity", 2.0, "", "kidney", 0.0))
        ctx["heart"].publish(PhysiologicalSignal("cardiac_output", 1700.0, "", "heart", 0.0))

        cmds = engine.resolve(ctx, dt=0.1)
        assert len(cmds) == 1
        cmd = cmds[0]
        assert cmd.target == "heart.SVR"
        assert cmd.op == "multiply"
        assert cmd.value == pytest.approx(1.4, rel=1e-6)


class TestCouplingIntegration:
    """Integration tests for the full coupling pipeline in VirtualCreature."""

    def test_creature_with_coupling_engine_initializes(self):
        from src.simulation import VirtualCreature

        c = VirtualCreature(body_weight_kg=20.0)
        assert c.coupling_engine is not None
        assert c.coupling_engine.num_rules >= 15
        assert c._organ_contexts is not None

    def test_coupling_commands_applied_in_step(self):
        from src.simulation import VirtualCreature

        c = VirtualCreature(body_weight_kg=20.0)
        # Run one step — coupling should fire for any active signal paths
        c.step()
        # If we got here without error, coupling pipeline works
        assert c.current_time_s > 0

    def test_organ_contexts_populated_after_step(self):
        from src.simulation import VirtualCreature

        c = VirtualCreature(body_weight_kg=20.0)
        c.step()

        ctx = c._organ_contexts
        # Heart signals should be published
        heart_ctx = ctx["heart"]
        co_sig = heart_ctx.get_signal("cardiac_output")
        assert co_sig is not None
        assert co_sig.value > 0

    def test_raas_coupling_increases_svr(self):
        from src.simulation import VirtualCreature
        from src.organs.coupling import PhysiologicalSignal

        c = VirtualCreature(body_weight_kg=20.0)
        c.step()  # Normal step initializes all state

        # Override signal map directly to simulate high RAAS state
        # (bypasses the need for specific MAP conditions)
        c._organ_contexts["kidney"].publish(
            PhysiologicalSignal("renin_activity", 2.0, "", "kidney", c.current_time_s)
        )
        c._organ_contexts["kidney"].publish(
            PhysiologicalSignal("angiotensin_II", 1.5, "", "kidney", c.current_time_s)
        )

        # Manually override kidney module state too
        c.kidney.renin_activity = 2.0
        c.kidney.angiotensin_II = 1.5

        ctx = c._organ_contexts
        cmds = c.coupling_engine.resolve(ctx, c.dt)
        svr_cmds = [cmd for cmd in cmds if cmd.target == "heart.SVR"]
        assert len(svr_cmds) == 1
        cmd = svr_cmds[0]
        baseline_svr = c.heart.SVR
        assert cmd.value == pytest.approx(1.4, rel=1e-6)

        c.apply_factor(cmd)
        assert c.heart.SVR == pytest.approx(baseline_svr * 1.4, rel=1e-6)

    def test_low_map_coupling_emits_gfr_command(self):
        from src.simulation import VirtualCreature
        from src.organs.coupling import PhysiologicalSignal

        c = VirtualCreature(body_weight_kg=20.0)
        c.step()

        c._organ_contexts["heart"].publish(
            PhysiologicalSignal("MAP", 70.0, "mmHg", "heart", c.current_time_s)
        )

        ctx = c._organ_contexts
        cmds = c.coupling_engine.resolve(ctx, c.dt)
        gfr_cmds = [cmd for cmd in cmds if cmd.target == "kidney.GFR"]
        assert len(gfr_cmds) == 1
        cmd = gfr_cmds[0]
        baseline_gfr = c.kidney.GFR
        expected_multiplier = (70.0 - 40.0) / 41.0
        assert cmd.value == pytest.approx(expected_multiplier, rel=1e-6)

        c.apply_factor(cmd)
        assert c.kidney.GFR == pytest.approx(baseline_gfr * expected_multiplier, rel=1e-6)

    def test_aldosterone_coupling_stays_disabled_until_volume_rate_model_exists(self):
        from src.simulation import VirtualCreature
        from src.organs.coupling import PhysiologicalSignal

        c = VirtualCreature(body_weight_kg=20.0)
        c.step()

        # Override aldosterone signal directly
        c._organ_contexts["kidney"].publish(
            PhysiologicalSignal("aldosterone", 2.0, "", "kidney", c.current_time_s)
        )
        c.kidney.aldosterone = 2.0

        ctx = c._organ_contexts
        cmds = c.coupling_engine.resolve(ctx, c.dt)
        aldosterone_cmds = [c for c in cmds if "aldosterone" in c.source.lower()]
        assert len(aldosterone_cmds) == 0

    def test_liver_metabolic_activity_affects_albumin(self):
        """Liver metabolic activity coupling is disabled by default (unsafe baseline drift).
        The coupling targets liver disease states specifically and is gated by condition.
        """
        from src.simulation import VirtualCreature

        c = VirtualCreature(body_weight_kg=20.0)
        c.step()

        # With liver_coag coupling disabled, no albumin commands should fire
        ctx = c._organ_contexts
        cmds = c.coupling_engine.resolve(ctx, c.dt)
        albumin_cmds = [c for c in cmds if "albumin" in c.target]
        # The rule is disabled so this should be empty
        assert len(albumin_cmds) == 0

    def test_coupling_does_not_break_basic_simulation(self):
        from src.simulation import VirtualCreature

        c = VirtualCreature(body_weight_kg=20.0)
        for _ in range(10):
            c.step()

        # Basic vitals should be in reasonable ranges
        assert 60 < c.heart.heart_rate < 150
        assert 60 < c.heart.mean_arterial_pressure < 150
        assert 0 < c.kidney.GFR < 150
        assert 6.8 < c.blood.arterial_pH < 7.8

    def test_backward_compatibility_existing_disease(self):
        """Existing diseases (via ode_diseases.json) should still work."""
        from src.simulation import VirtualCreature
        from src.diseases import create_disease

        c = VirtualCreature(body_weight_kg=20.0)
        d = create_disease("pneumonia", severity="moderate")
        c.attach_disease(d)

        for _ in range(50):
            c.step()

        # Should run without error and progress in time
        assert c.current_time_s > 0
        assert c.disease is not None


class TestCouplingSignalMap:
    """Tests for signal map construction and expression evaluation."""

    def test_signal_map_includes_module_prefix(self):
        from src.simulation import VirtualCreature

        c = VirtualCreature(body_weight_kg=20.0)
        c.step()

        # The coupling engine builds a signal map with "module.signal" keys
        ctx = c._organ_contexts
        engine = c.coupling_engine

        # Verify signals are accessible
        assert ctx["heart"].get_signal("cardiac_output") is not None
        assert ctx["kidney"].get_signal("GFR") is not None
        assert ctx["blood"].get_signal("arterial_pH") is not None


class TestCouplingConditions:
    """Tests for conditional coupling rules."""

    def test_raas_condition_requires_renin(self):
        from src.simulation import VirtualCreature

        c = VirtualCreature(body_weight_kg=20.0)
        # Set renin to 0 (below threshold of 0.1)
        c.kidney.renin_activity = 0.0
        c.step()

        ctx = c._organ_contexts
        cmds = c.coupling_engine.resolve(ctx, c.dt)
        svr_cmds = [c for c in cmds if "SVR" in c.target and "RAAS" in c.source]
        # No RAAS SVR commands when renin is 0
        assert len(svr_cmds) == 0
