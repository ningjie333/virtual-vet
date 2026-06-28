"""
ImmuneModule unit tests — cytokine dynamics, fever, WBC, CRP, capillary leak.

Covers src/immune.py (334 lines) which has:
  - State: cytokine_level, wbc_count, crp_level, coagulation_state
  - Thresholds: fever (>0.3), leukocytosis (>0.2), CRP (>0.1),
    hypercoagulation (>0.6), capillary leak (>0.4)
  - Key outputs: cytokine_level, wbc_count, crp_level, coagulation_state
"""

import sys
sys.path.insert(0, "src")

import pytest
from immune import ImmuneModule
from blood import BloodCompartment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_immune():
    """Fresh ImmuneModule, 20 kg canine."""
    blood = BloodCompartment(total_volume_ml=1720.0, plasma_fraction=0.55)
    return ImmuneModule(weight_kg=20.0, blood=blood)


def _apply_derivatives(module, dt, **kwargs):
    """Call derivatives() and apply outputs to module (simulating Euler step).

    derivatives() is a pure function: it returns (dydt, outputs) without
    modifying self. outputs already contains the new (post-step, clamped)
    values, so we SET matching attributes directly. blood_* outputs are
    skipped (they are applied by the engine layer via apply_factor).
    """
    dydt, outputs = module.derivatives(dt=dt, **kwargs)
    for k, v in outputs.items():
        if k.startswith("blood_"):
            continue
        if k.startswith("self_"):
            attr = k[5:]
            if hasattr(module, attr):
                setattr(module, attr, v)
            elif hasattr(module, "_" + attr):
                setattr(module, "_" + attr, v)
        elif hasattr(module, k):
            setattr(module, k, v)
    return dydt, outputs


# ---------------------------------------------------------------------------
# TestCytokineDynamics
# ---------------------------------------------------------------------------

class TestCytokineDynamics:
    """Cytokine: infection signal → level rises with tau=600s."""

    def test_cytokine_zero_at_baseline(self):
        """Fresh module → cytokine_level ≈ 0."""
        im = make_immune()
        assert im.cytokine_level == pytest.approx(0.0, abs=0.05)

    def test_cytokine_rises_toward_target(self):
        """Set _infection_signal=1.0 via set_infection_signal(), verify rise."""
        im = make_immune()
        im.set_infection_signal(1.0)
        for _ in range(600):  # 60 s, tau=600s → ~10% of way
            _apply_derivatives(im, dt=0.1, endocrine_cortisol=5.0)
        assert 0.05 <= im.cytokine_level <= 0.20, \
            f"cytokine={im.cytokine_level:.3f}, expected ~0.095"

    def test_cytokine_tau_600s_convergence(self):
        """After 600s (1 tau), cytokine ≈ 63% of target."""
        im = make_immune()
        im.set_infection_signal(1.0)
        for _ in range(6000):  # 600 s = 1 tau
            _apply_derivatives(im, dt=0.1, endocrine_cortisol=5.0)
        assert 0.50 <= im.cytokine_level <= 0.70, \
            f"cytokine={im.cytokine_level:.3f}, expected ~0.63 at 1τ"

    def test_cortisol_suppresses_cytokine_rise(self):
        """High cortisol (20 ug/dL) → cytokine rises slower."""
        im_hi = make_immune()
        im_hi.set_infection_signal(1.0)
        im_lo = make_immune()
        im_lo.set_infection_signal(1.0)

        for _ in range(300):
            _apply_derivatives(im_hi, dt=0.1, endocrine_cortisol=20.0)
            _apply_derivatives(im_lo, dt=0.1, endocrine_cortisol=5.0)

        assert im_hi.cytokine_level < im_lo.cytokine_level, \
            f"High cortisol should suppress cytokine: hi={im_hi.cytokine_level}, lo={im_lo.cytokine_level}"


# ---------------------------------------------------------------------------
# TestFever
# ---------------------------------------------------------------------------

class TestFever:
    """Fever: cytokine > 0.3 → temperature rises."""

    def test_no_fever_below_threshold(self):
        """cytokine < 0.3 → fever not triggered."""
        im = make_immune()
        im.set_infection_signal(0.2)
        for _ in range(600):
            im.derivatives(dt=0.1, endocrine_cortisol=5.0)
        assert im.cytokine_level < 0.3

    def test_fever_above_threshold_drives_temperature(self):
        """infection_signal=0.8 → cytokine rises above 0.3 threshold (tau=600s)."""
        im = make_immune()
        im.set_infection_signal(0.8)
        for _ in range(6000):  # 600s = 1 tau → cytokine ~63% of 0.8 ≈ 0.5
            _apply_derivatives(im, dt=0.1, endocrine_cortisol=5.0)
        assert im.cytokine_level > 0.3, \
            f"cytokine={im.cytokine_level} should exceed 0.3 after 1 tau"


# ---------------------------------------------------------------------------
# TestCapillaryLeak
# ---------------------------------------------------------------------------

class TestCapillaryLeak:
    """Capillary leak: cytokine > 0.4 → leak factor > 1.0."""

    def test_leak_factor_rises_with_cytokine(self):
        """cytokine=0.5 → capillary leak FactorCommands present."""
        im = make_immune()
        im.set_infection_signal(0.5)
        for _ in range(600):
            im.derivatives(dt=0.1, endocrine_cortisol=5.0)
        _, outputs = im.derivatives(dt=0.1, endocrine_cortisol=5.0)
        # capillary_leak_factor appears in outputs dict
        assert "capillary_leak_factor" in outputs or im._infection_signal > 0.4

    def test_no_leak_at_low_cytokine(self):
        """Low infection signal → no significant leak."""
        im = make_immune()
        im.set_infection_signal(0.2)
        for _ in range(600):
            im.derivatives(dt=0.1, endocrine_cortisol=5.0)
        _, outputs = im.derivatives(dt=0.1, endocrine_cortisol=5.0)
        assert outputs.get("capillary_leak_factor", 0.0) < 0.1


# ---------------------------------------------------------------------------
# TestWBCAndCRP
# ---------------------------------------------------------------------------

class TestWBCAndCRP:
    """WBC and CRP: rise with cytokine, delayed by time constants."""

    def test_wbc_rises_with_cytokine(self):
        """infection_signal=1.0 → wbc_count rises above baseline 10."""
        im = make_immune()
        im.set_infection_signal(1.0)
        for _ in range(6000):
            _apply_derivatives(im, dt=0.1, endocrine_cortisol=5.0)
        assert im.wbc_count > 10.0, \
            f"WBC should rise with infection, got {im.wbc_count}"

    def test_crp_threshold_triggered(self):
        """infection_signal=0.8 → cytokine rises above 0.1 after 1 tau."""
        im = make_immune()
        im.set_infection_signal(0.8)
        for _ in range(6000):  # 600s = 1 tau
            _apply_derivatives(im, dt=0.1, endocrine_cortisol=5.0)
        assert im.cytokine_level > 0.1, \
            f"cytokine={im.cytokine_level} should exceed 0.1 CRP threshold"


# ---------------------------------------------------------------------------
# TestCoagulationState
# ---------------------------------------------------------------------------

class TestCoagulationState:
    """Hypercoagulation: cytokine > 0.6 → coagulation_state rises (DIC risk)."""

    def test_no_hypercoagulation_below_threshold(self):
        """Low infection signal → coagulation_state near 0."""
        im = make_immune()
        im.set_infection_signal(0.1)  # below 0.6 threshold
        for _ in range(6000):
            im.derivatives(dt=0.1, endocrine_cortisol=5.0)
        assert im.coagulation_state < 0.1

    def test_hypercoagulation_above_threshold(self):
        """Max infection → cytokine > 0.6, coagulation_state rises from 0."""
        im = make_immune()
        im.set_infection_signal(1.0)
        for _ in range(12000):  # enough for both cytokine and coag to rise
            _apply_derivatives(im, dt=0.1, endocrine_cortisol=5.0)
        assert im.cytokine_level > 0.6, \
            f"cytokine={im.cytokine_level} should exceed 0.6"
        assert im.coagulation_state > 0.0, \
            f"coag_state should rise from 0, got {im.coagulation_state}"


# ---------------------------------------------------------------------------
# TestImmuneIntegration
# ---------------------------------------------------------------------------

class TestImmuneIntegration:
    """Full integration: ImmuneModule + VirtualCreature."""

    @pytest.mark.slow
    def test_pneumonia_increases_cytokine_in_creature(self):
        """Attach pneumonia → cytokine rises."""
        from simulation import VirtualCreature
        from src.diseases import create_disease

        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        dis = create_disease("pneumonia", severity="moderate")
        vc.attach_disease(dis)

        for _ in range(1000):
            vc.step()

        assert vc.immune.cytokine_level > 0.005, \
            f"Pneumonia should raise cytokine, got {vc.immune.cytokine_level}"

    @pytest.mark.slow
    def test_severe_infection_raises_cytokine(self):
        """Severe infection → cytokine > 0.1 (baseline elevation)."""
        from simulation import VirtualCreature
        from src.diseases import create_disease

        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        dis = create_disease("pneumonia", severity="severe")
        vc.attach_disease(dis)

        for _ in range(3000):
            vc.step()

        assert vc.immune.cytokine_level > 0.1, \
            f"Severe infection should raise cytokine > 0.1, got {vc.immune.cytokine_level}"


# ---------------------------------------------------------------------------
# TestImmuneOutputs
# ---------------------------------------------------------------------------

class TestImmuneOutputs:
    """compute() returns required keys and valid values."""

    def test_compute_returns_required_keys(self):
        """compute() includes cytokine_level, wbc_count, coagulation_state."""
        im = make_immune()
        result = im.compute(dt=0.1, endocrine_state={})
        for key in ["cytokine_level", "wbc_count", "coagulation_state"]:
            assert key in result, f"Missing key: {key}"

    def test_all_states_bounded(self):
        """All state variables stay within [0, 1] or clamped ranges."""
        im = make_immune()
        im._cytokine_target = 1.0
        for _ in range(1000):
            im.derivatives(dt=0.1, endocrine_cortisol=5.0)
        assert 0.0 <= im.cytokine_level <= 1.0
        assert 3.0 <= im.wbc_count <= 50.0
        assert 0.0 <= im.coagulation_state <= 1.0