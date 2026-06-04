"""
Tests for FactorCommand protocol: the unified factor-writing mechanism.

Tests cover:
- FactorCommand dataclass creation and field validation
- _PARAM_PATHS mapping completeness
- VirtualCreature.apply_factor() with multiply / add / set operations
- Unknown target handling (warning, no crash)
- Unknown op handling (warning, no crash)
- Integration: disease module returns list[FactorCommand], engine applies them
"""

import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

import pytest
from src.common_types import _PARAM_PATHS
from src.simulation import VirtualCreature, FactorCommand


# ---------------------------------------------------------------------------
# FactorCommand dataclass
# ---------------------------------------------------------------------------

class TestFactorCommand:
    """Tests for the FactorCommand dataclass."""

    def test_create_factor_command(self):
        cmd = FactorCommand(target="heart.heart_rate", op="multiply", value=1.1)
        assert cmd.target == "heart.heart_rate"
        assert cmd.op == "multiply"
        assert cmd.value == 1.1

    def test_factor_command_is_frozen(self):
        """FactorCommand should be immutable after creation."""
        cmd = FactorCommand(target="heart.heart_rate", op="add", value=10.0)
        with pytest.raises(AttributeError):
            cmd.target = "lung.diffusion_coefficient"

    def test_all_valid_ops(self):
        """All three operation types should be accepted."""
        for op in ("multiply", "add", "set"):
            cmd = FactorCommand(target="heart.heart_rate", op=op, value=1.0)
            assert cmd.op == op


# ---------------------------------------------------------------------------
# _PARAM_PATHS mapping
# ---------------------------------------------------------------------------

class TestParamPaths:
    """Tests for the _PARAM_PATHS mapping table."""

    def test_all_targets_map_to_valid_modules(self):
        """Every target in _PARAM_PATHS should map to a (module, attr) tuple."""
        for target, path in _PARAM_PATHS.items():
            assert isinstance(path, tuple), f"{target}: path must be tuple"
            assert len(path) == 2, f"{target}: path must have 2 elements"
            module_name, attr_name = path
            assert isinstance(module_name, str), f"{target}: module_name must be str"
            assert isinstance(attr_name, str), f"{target}: attr_name must be str"

    def test_all_targets_reachable_on_creature(self):
        """Every target's module and attr should exist on a VirtualCreature."""
        v = VirtualCreature(body_weight_kg=20.0)
        for target, (module_name, attr_name) in _PARAM_PATHS.items():
            module = getattr(v, module_name, None)
            assert module is not None, f"{target}: module '{module_name}' not found"
            assert hasattr(module, attr_name), \
                f"{target}: attr '{attr_name}' not found on {module_name}"

    def test_heart_targets_present(self):
        """Heart-related targets should be in _PARAM_PATHS."""
        heart_targets = [t for t in _PARAM_PATHS if t.startswith("heart.")]
        assert len(heart_targets) >= 5  # HR, contractility, SVR, MAP, CVP, BV, SV

    def test_lung_targets_present(self):
        """Lung-related targets should be in _PARAM_PATHS."""
        lung_targets = [t for t in _PARAM_PATHS if t.startswith("lung.")]
        assert len(lung_targets) >= 3  # diffusion, PaO2, VQ_ratio

    def test_kidney_targets_present(self):
        """Kidney-related targets should be in _PARAM_PATHS."""
        kidney_targets = [t for t in _PARAM_PATHS if t.startswith("kidney.")]
        assert len(kidney_targets) >= 2  # GFR, urine_output

    def test_blood_targets_present(self):
        """Blood-related targets should be in _PARAM_PATHS."""
        blood_targets = [t for t in _PARAM_PATHS if t.startswith("blood.")]
        assert len(blood_targets) >= 3  # potassium, pH, temperature


# ---------------------------------------------------------------------------
# apply_factor()
# ---------------------------------------------------------------------------

class TestApplyFactor:
    """Tests for VirtualCreature.apply_factor()."""

    def test_multiply_heart_rate(self):
        """multiply op should scale the target attribute."""
        v = VirtualCreature(body_weight_kg=20.0)
        initial_hr = v.heart.heart_rate
        cmd = FactorCommand(target="heart.heart_rate", op="multiply", value=1.5)
        v.apply_factor(cmd)
        assert v.heart.heart_rate == pytest.approx(initial_hr * 1.5, rel=1e-4)

    def test_add_to_heart_rate(self):
        """add op should increment the target attribute."""
        v = VirtualCreature(body_weight_kg=20.0)
        initial_hr = v.heart.heart_rate
        cmd = FactorCommand(target="heart.heart_rate", op="add", value=20.0)
        v.apply_factor(cmd)
        assert v.heart.heart_rate == pytest.approx(initial_hr + 20.0, rel=1e-4)

    def test_set_blood_potassium(self):
        """set op should assign the target attribute to the exact value."""
        v = VirtualCreature(body_weight_kg=20.0)
        cmd = FactorCommand(target="blood.potassium", op="set", value=6.5)
        v.apply_factor(cmd)
        assert v.blood.potassium_mEq_L == pytest.approx(6.5, rel=1e-4)

    def test_multiply_lung_diffusion(self):
        """multiply lung diffusion coefficient."""
        v = VirtualCreature(body_weight_kg=20.0)
        initial = v.lung.diffusion_coefficient
        cmd = FactorCommand(target="lung.diffusion_coefficient", op="multiply", value=0.5)
        v.apply_factor(cmd)
        assert v.lung.diffusion_coefficient == pytest.approx(initial * 0.5, rel=1e-4)

    def test_multiply_kidney_gfr(self):
        """multiply kidney GFR."""
        v = VirtualCreature(body_weight_kg=20.0)
        initial = v.kidney.GFR
        cmd = FactorCommand(target="kidney.GFR", op="multiply", value=0.3)
        v.apply_factor(cmd)
        assert v.kidney.GFR == pytest.approx(initial * 0.3, rel=1e-4)

    def test_set_blood_ph(self):
        """set blood pH to a specific value."""
        v = VirtualCreature(body_weight_kg=20.0)
        cmd = FactorCommand(target="blood.pH", op="set", value=7.15)
        v.apply_factor(cmd)
        assert v.blood.arterial_pH == pytest.approx(7.15, rel=1e-4)

    def test_unknown_target_does_not_crash(self):
        """Unknown target should log warning and return without error."""
        v = VirtualCreature(body_weight_kg=20.0)
        cmd = FactorCommand(target="brain.awareness", op="set", value=0.5)
        # Should not raise
        v.apply_factor(cmd)

    def test_unknown_op_does_not_crash(self):
        """Unknown op should log warning and return without error."""
        v = VirtualCreature(body_weight_kg=20.0)
        initial_hr = v.heart.heart_rate
        cmd = FactorCommand(target="heart.heart_rate", op="divide", value=2.0)
        v.apply_factor(cmd)
        # Value should be unchanged
        assert v.heart.heart_rate == pytest.approx(initial_hr, rel=1e-4)

    def test_multiple_factors_in_sequence(self):
        """Multiple factors applied in sequence should all take effect."""
        v = VirtualCreature(body_weight_kg=20.0)
        v.apply_factor(FactorCommand(target="heart.heart_rate", op="multiply", value=1.2))
        v.apply_factor(FactorCommand(target="heart.heart_rate", op="add", value=10.0))
        v.apply_factor(FactorCommand(target="lung.diffusion_coefficient", op="multiply", value=0.7))

        assert v.heart.heart_rate > 0
        assert v.lung.diffusion_coefficient < 25.0  # normal is 25.0

    def test_apply_factor_during_step(self):
        """apply_factor should work correctly within a step() cycle."""
        v = VirtualCreature(body_weight_kg=20.0)
        v.step()  # normal step
        hr_after_step = v.heart.heart_rate

        # Now apply a disease-like factor
        v.apply_factor(FactorCommand(target="heart.heart_rate", op="add", value=30.0))
        assert v.heart.heart_rate == pytest.approx(hr_after_step + 30.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Integration: disease returns list[FactorCommand>, engine applies
# ---------------------------------------------------------------------------

class TestFactorCommandIntegration:
    """Integration: disease module produces FactorCommand list, engine consumes it."""

    def test_pneumonia_returns_commands(self):
        """PneumoniaModule.compute() should return list[FactorCommand]."""
        from src.diseases import create_disease
        pm = create_disease("pneumonia",severity="moderate")
        pm.activate(current_time_s=0.0)
        commands = pm.compute(0.1, {"heart": {}, "lung": {}, "kidney": {}})
        assert isinstance(commands, list)
        assert len(commands) > 0
        for cmd in commands:
            assert isinstance(cmd, FactorCommand)

    def test_arf_returns_commands(self):
        """AcuteRenalFailureModule.compute() should return list[FactorCommand]."""
        from src.diseases import create_disease
        arf = create_disease("acute_renal_failure",severity="moderate")
        arf.activate(current_time_s=0.0)
        commands = arf.compute(0.1, {"heart": {}, "lung": {}, "kidney": {}})
        assert isinstance(commands, list)
        assert len(commands) > 0
        for cmd in commands:
            assert isinstance(cmd, FactorCommand)

    def test_dcm_returns_commands(self):
        """DilatedCardiomyopathyModule.compute() should return list[FactorCommand]."""
        from src.diseases import create_disease
        dcm = create_disease("dilated_cardiomyopathy",severity="moderate")
        dcm.activate(current_time_s=0.0)
        commands = dcm.compute(0.1, {"heart": {}, "lung": {}, "kidney": {}})
        assert isinstance(commands, list)
        assert len(commands) > 0
        for cmd in commands:
            assert isinstance(cmd, FactorCommand)

    def test_inactive_disease_returns_empty_list(self):
        """Inactive disease should return empty list (not empty dict)."""
        from src.diseases import create_disease
        pm = create_disease("pneumonia",severity="moderate")
        # Do NOT activate
        commands = pm.compute(0.1, {"heart": {}, "lung": {}, "kidney": {}})
        assert commands == []

    def test_commands_applied_to_creature(self):
        """Commands from a disease should modify creature physiology when applied."""
        from src.diseases import create_disease

        v = VirtualCreature(body_weight_kg=20.0)
        initial_spo2 = v.blood.arterial_saturation

        pm = create_disease("pneumonia",severity="moderate")
        pm.activate(current_time_s=0.0)

        # Run 600 steps, applying disease commands each step
        for _ in range(600):
            commands = pm.compute(0.1, {
                "heart": {"heart_rate_bpm": v.heart.heart_rate,
                          "MAP_mmHg": v.heart.mean_arterial_pressure,
                          "cardiac_output_ml_min": v.heart.cardiac_output},
                "lung": {"arterial_PO2": v.blood.arterial_PO2_mmHg},
                "kidney": {"GFR_ml_min": v.kidney.GFR},
            })
            for cmd in commands:
                v.apply_factor(cmd)
            v.step()

        # SpO2 should have decreased due to pneumonia
        assert v.blood.arterial_saturation < initial_spo2
