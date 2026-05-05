"""
Tests for Pharmacology → FactorCommand migration.

Tests cover:
- Drug.factor_commands(pd_effect) returns list[FactorCommand]
- PharmacologyState.compute() returns list[FactorCommand]
- Engine applies pharma commands via apply_factor()
- Backward compatibility: old dict-based effects still logged

RED phase: these tests should FAIL before migration.
"""

import sys
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

import pytest
from src.simulation import VirtualCreature, FactorCommand


# ---------------------------------------------------------------------------
# Drug.factor_commands()
# ---------------------------------------------------------------------------

class TestDrugFactorCommands:
    """Each Drug subclass should declare its effects as FactorCommand list."""

    def test_pimobendan_returns_commands(self):
        """Pimobendan should return FactorCommand list for contractility."""
        from src.pharmacology import Pimobendan
        drug = Pimobendan()
        drug.administer(dose_mg_kg=0.25)
        pd = drug.pd_effect()
        cmds = drug.factor_commands(pd)
        assert isinstance(cmds, list)
        assert len(cmds) > 0
        for c in cmds:
            assert isinstance(c, FactorCommand)
        # Pimobendan targets contractility
        targets = [c.target for c in cmds]
        assert "heart.contractility_factor" in targets

    def test_furosemide_returns_commands(self):
        """Furosemide should return FactorCommand list for urine output."""
        from src.pharmacology import Furosemide
        drug = Furosemide()
        drug.administer(dose_mg_kg=1.0)
        pd = drug.pd_effect()
        cmds = drug.factor_commands(pd)
        assert isinstance(cmds, list)
        assert len(cmds) > 0
        targets = [c.target for c in cmds]
        assert "kidney.urine_output" in targets

    def test_epinephrine_returns_commands(self):
        """Epinephrine should return FactorCommand list for SVR and HR."""
        from src.pharmacology import Epinephrine
        drug = Epinephrine()
        drug.administer(dose_mg_kg=0.02)
        pd = drug.pd_effect()
        cmds = drug.factor_commands(pd)
        assert isinstance(cmds, list)
        assert len(cmds) > 0
        targets = [c.target for c in cmds]
        assert "heart.SVR" in targets
        assert "heart.heart_rate" in targets

    def test_fluid_bolus_returns_commands(self):
        """FluidBolus should return FactorCommand list for blood volume."""
        from src.pharmacology import FluidBolus
        drug = FluidBolus()
        drug.administer(volume_ml=200.0)
        pd = drug.pd_effect()
        cmds = drug.factor_commands(pd)
        assert isinstance(cmds, list)
        # Fluid bolus may return empty if concentration is 0 after consumption
        # or return a blood_volume command

    def test_unadministered_drug_returns_empty_commands(self):
        """Drug that hasn't been administered should return empty list."""
        from src.pharmacology import Pimobendan
        drug = Pimobendan()
        pd = drug.pd_effect()
        cmds = drug.factor_commands(pd)
        assert cmds == []

    def test_pimobendan_contractility_op_is_multiply(self):
        """Pimobendan contractility should use multiply op (1.0 + pd)."""
        from src.pharmacology import Pimobendan
        drug = Pimobendan()
        drug.administer(dose_mg_kg=0.25)
        pd = drug.pd_effect()
        cmds = drug.factor_commands(pd)
        contractility_cmds = [c for c in cmds if c.target == "heart.contractility_factor"]
        assert len(contractility_cmds) == 1
        assert contractility_cmds[0].op == "multiply"
        assert contractility_cmds[0].value == pytest.approx(1.0 + pd, rel=1e-3)

    def test_epinephrine_svr_op_is_multiply(self):
        """Epinephrine SVR should use multiply op."""
        from src.pharmacology import Epinephrine
        drug = Epinephrine()
        drug.administer(dose_mg_kg=0.02)
        pd = drug.pd_effect()
        cmds = drug.factor_commands(pd)
        svr_cmds = [c for c in cmds if c.target == "heart.SVR"]
        assert len(svr_cmds) == 1
        assert svr_cmds[0].op == "multiply"

    def test_epinephrine_hr_op_is_multiply(self):
        """Epinephrine HR should use multiply op (1.0 + 0.3 * pd)."""
        from src.pharmacology import Epinephrine
        drug = Epinephrine()
        drug.administer(dose_mg_kg=0.02)
        pd = drug.pd_effect()
        cmds = drug.factor_commands(pd)
        hr_cmds = [c for c in cmds if c.target == "heart.heart_rate"]
        assert len(hr_cmds) == 1
        assert hr_cmds[0].op == "multiply"
        assert hr_cmds[0].value == pytest.approx(1.0 + 0.3 * pd, rel=1e-3)

    def test_furosemide_urine_op_is_multiply(self):
        """Furosemide urine output should use multiply op."""
        from src.pharmacology import Furosemide
        drug = Furosemide()
        drug.administer(dose_mg_kg=1.0)
        pd = drug.pd_effect()
        cmds = drug.factor_commands(pd)
        urine_cmds = [c for c in cmds if c.target == "kidney.urine_output"]
        assert len(urine_cmds) == 1
        assert urine_cmds[0].op == "multiply"

    def test_pimobendan_value_increases_with_dose(self):
        """Higher dose → larger contractility_factor multiplier."""
        from src.pharmacology import Pimobendan
        drug_low = Pimobendan()
        drug_low.administer(dose_mg_kg=0.1)
        pd_low = drug_low.pd_effect()
        cmds_low = drug_low.factor_commands(pd_low)

        drug_high = Pimobendan()
        drug_high.administer(dose_mg_kg=0.5)
        pd_high = drug_high.pd_effect()
        cmds_high = drug_high.factor_commands(pd_high)

        val_low = [c for c in cmds_low if c.target == "heart.contractility_factor"][0].value
        val_high = [c for c in cmds_high if c.target == "heart.contractility_factor"][0].value
        assert val_high > val_low


# ---------------------------------------------------------------------------
# PharmacologyState.compute() returns list[FactorCommand]
# ---------------------------------------------------------------------------

class TestPharmacologyStateCompute:
    """PharmacologyState.compute() should return list[FactorCommand]."""

    def test_compute_returns_list_of_factor_command(self):
        """compute() should return list[FactorCommand]."""
        from src.pharmacology import PharmacologyState
        vc = VirtualCreature(body_weight_kg=20.0)
        ph = PharmacologyState(weight_kg=20.0)
        ph.administer_drug("pimobendan", dose_mg_kg=0.25)
        result = ph.compute(dt=0.1, creature=vc)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, FactorCommand)

    def test_compute_no_drugs_returns_empty(self):
        """No drugs administered → empty list."""
        from src.pharmacology import PharmacologyState
        vc = VirtualCreature(body_weight_kg=20.0)
        ph = PharmacologyState(weight_kg=20.0)
        result = ph.compute(dt=0.1, creature=vc)
        assert result == []

    def test_compute_pimobendan_targets_contractility(self):
        """Pimobendan in state → commands target contractility_factor."""
        from src.pharmacology import PharmacologyState
        vc = VirtualCreature(body_weight_kg=20.0)
        ph = PharmacologyState(weight_kg=20.0)
        ph.administer_drug("pimobendan", dose_mg_kg=0.25)
        cmds = ph.compute(dt=0.1, creature=vc)
        targets = [c.target for c in cmds]
        assert "heart.contractility_factor" in targets

    def test_compute_epinephrine_targets_svr_and_hr(self):
        """Epinephrine in state → commands target SVR and HR."""
        from src.pharmacology import PharmacologyState
        vc = VirtualCreature(body_weight_kg=20.0)
        ph = PharmacologyState(weight_kg=20.0)
        ph.administer_drug("epinephrine", dose_mg_kg=0.02)
        cmds = ph.compute(dt=0.1, creature=vc)
        targets = [c.target for c in cmds]
        assert "heart.SVR" in targets
        assert "heart.heart_rate" in targets


# ---------------------------------------------------------------------------
# Integration: simulation step applies pharma via apply_factor()
# ---------------------------------------------------------------------------

class TestPharmaIntegration:
    """Full integration: drug administered → step → physiological effect via FactorCommand."""

    def test_pimobendan_increases_contractility_via_factor(self):
        """After administering pimobendan + step, contractility_factor should increase."""
        from src.pharmacology import PharmacologyState

        vc = VirtualCreature(body_weight_kg=20.0)
        vc.pharmacology = PharmacologyState(weight_kg=20.0)
        vc.pharmacology.administer_drug("pimobendan", dose_mg_kg=0.25)

        baseline_cf = vc.heart.contractility_factor
        vc.step()

        assert vc.heart.contractility_factor > baseline_cf

    def test_epinephrine_increases_svr_via_factor(self):
        """After administering epinephrine + step, SVR factor in history should increase."""
        from src.pharmacology import PharmacologyState

        vc = VirtualCreature(body_weight_kg=20.0)
        vc.pharmacology = PharmacologyState(weight_kg=20.0)
        vc.pharmacology.administer_drug("epinephrine", dose_mg_kg=0.02)

        vc.step()

        # SVR is modulated via svr_factor (effective_SVR = SVR * svr_factor)
        # heart.compute() overwrites self.SVR (baroreflex), so check history
        svr_history = vc.history.get("svr_factor", [])
        assert len(svr_history) > 0
        assert max(svr_history) > 1.0

    def test_furosemide_increases_urine_via_factor(self):
        """After administering furosemide + step, urine output should increase."""
        from src.pharmacology import PharmacologyState

        vc = VirtualCreature(body_weight_kg=20.0)
        vc.pharmacology = PharmacologyState(weight_kg=20.0)
        vc.pharmacology.administer_drug("furosemide", dose_mg_kg=1.0)

        baseline_uo = vc.kidney.urine_output
        vc.step()

        assert vc.kidney.urine_output > baseline_uo

    def test_pharma_effects_via_apply_factor_not_direct_write(self):
        """Pharma effects should go through apply_factor(), not direct attribute writes."""
        from src.pharmacology import PharmacologyState

        vc = VirtualCreature(body_weight_kg=20.0)
        vc.pharmacology = PharmacologyState(weight_kg=20.0)
        vc.pharmacology.administer_drug("pimobendan", dose_mg_kg=0.25)

        # Manually call compute and apply_factor to verify the path
        cmds = vc.pharmacology.compute(dt=0.1, creature=vc)
        for cmd in cmds:
            vc.apply_factor(cmd)

        # contractility_factor should be modified
        assert vc.heart.contractility_factor != 1.0  # was 1.0 at init

    def test_multiple_drugs_all_apply(self):
        """Multiple drugs should all produce FactorCommands that get applied."""
        from src.pharmacology import PharmacologyState

        vc = VirtualCreature(body_weight_kg=20.0)
        vc.pharmacology = PharmacologyState(weight_kg=20.0)
        vc.pharmacology.administer_drug("pimobendan", dose_mg_kg=0.25)
        vc.pharmacology.administer_drug("epinephrine", dose_mg_kg=0.02)

        baseline_cf = vc.heart.contractility_factor

        vc.step()

        assert vc.heart.contractility_factor > baseline_cf
        # Epinephrine SVR effect via svr_factor history
        svr_history = vc.history.get("svr_factor", [])
        assert len(svr_history) > 0
        assert max(svr_history) > 1.0
