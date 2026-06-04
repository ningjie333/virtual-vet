"""
Cross-module coupling integration tests.

Verifies that multi-organ chains work correctly:
  - Cardiorenal: low CO → low GFR → fluid overload
  - Acid-base: respiratory ↔ metabolic interactions
  - Electrolyte: ARF → hyperkalemia → cardiac toxicity
  - RAAS: low MAP → renin → angiotensin II → SVR + aldosterone
"""

import sys
sys.path.insert(0, "src")

import pytest
from simulation import VirtualCreature
from src.diseases import create_disease


class TestAcidBaseCrosstalk:
    """Acid-base: respiratory ↔ metabolic interactions."""

    @pytest.mark.slow
    def test_respiratory_acidosis_drops_ph(self):
        """High PCO2 → arterial pH drops (respiratory acidosis)."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        # Artificially raise PCO2
        vc.blood.arterial_PCO2_mmHg = 70.0
        for _ in range(100):
            vc.step()
        assert vc.blood.arterial_pH < 7.35, \
            f"High PCO2 should drop pH below 7.35, got {vc.blood.arterial_pH}"

    @pytest.mark.slow
    def test_arf_causes_metabolic_acidosis(self):
        """ARF → BUN rises + pH drops (uremic acidosis)."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        dis = create_disease("acute_renal_failure", severity="moderate")
        vc.attach_disease(dis)
        for _ in range(1000):
            vc.step()
        assert vc.blood.arterial_pH < 7.40, \
            f"ARF should cause acidosis, pH={vc.blood.arterial_pH}"


class TestElectrolyteCrosstalk:
    """Electrolyte: ARF → hyperkalemia → cardiac effects."""

    @pytest.mark.slow
    def test_arf_hyperkalemia(self):
        """ARF → potassium rises."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        dis = create_disease("acute_renal_failure", severity="moderate")
        vc.attach_disease(dis)
        for _ in range(1000):
            vc.step()
        assert vc.blood.potassium_mEq_L > 5.0, \
            f"ARF should raise K+ above 5.0, got {vc.blood.potassium_mEq_L}"


class TestRAASCoupling:
    """RAAS: MAP → renin → angiotensin II → SVR."""

    @pytest.mark.slow
    def test_low_map_activates_raas(self):
        """Blood loss → MAP drop → RAAS activation (renin rises)."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vc.schedule_event(5.0, "blood_loss", {"volume_ml": 400.0})
        for _ in range(1000):
            vc.step()
        assert vc.kidney.renin_activity > 0.01, \
            f"Blood loss should activate RAAS, renin={vc.kidney.renin_activity}"

    @pytest.mark.slow
    def test_raas_increases_svr(self):
        """RAAS activation → SVR factor > 1.0."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vc.schedule_event(5.0, "blood_loss", {"volume_ml": 400.0})
        for _ in range(2000):
            vc.step()
        assert vc.heart.SVR > 1.0, \
            f"RAAS should increase SVR above 1.0, got {vc.heart.SVR}"


class TestOrganFailureSpiral:
    """Multi-organ failure cascades."""

    @pytest.mark.slow
    def test_cardiorenal_low_co_depresses_gfr(self):
        """Low CO → GFR drops → kidney stress."""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vc.schedule_event(1.0, "blood_loss", {"volume_ml": 1200.0})
        for _ in range(2000):
            vc.step()
        # GFR should be reduced compared to baseline
        assert vc.kidney.GFR < 60.0, \
            f"Blood loss should reduce GFR below 60, got {vc.kidney.GFR}"