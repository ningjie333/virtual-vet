"""
Tests for disease progression modules: PneumoniaModule and AcuteRenalFailureModule.

Tests cover:
- ODE state evolution over time
- Factor dictionary outputs
- Severity-dependent progression rates
- Inactive disease behavior
- Summary output format
- Integration with VirtualCreature simulation
"""

import pytest
import sys
import os

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from src.diseases import create_disease
from src.simulation import VirtualCreature, FactorCommand

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

DUMMY_ENGINE_STATE = {
    "heart": {"heart_rate_bpm": 85.0, "MAP_mmHg": 100.0, "cardiac_output_ml_min": 1700.0},
    "lung": {"arterial_PO2": 95.0},
    "kidney": {"GFR_ml_min": 50.0},
}


def run_compute_n_steps(module, n_steps, dt=0.1):
    """Advance a disease module for n_steps * dt seconds."""
    for _ in range(n_steps):
        module.compute(dt, DUMMY_ENGINE_STATE)


def run_compute_for_seconds(module, seconds: float, dt: float = 1.0):
    """Advance a disease module for a physical duration with a test-friendly step size."""
    n_steps = max(1, int(seconds / dt))
    for _ in range(n_steps):
        module.compute(dt, DUMMY_ENGINE_STATE)


def _find_cmd_value(commands: list[FactorCommand], target: str) -> float | None:
    """Find the value of a FactorCommand by target path."""
    for cmd in commands:
        if cmd.target == target:
            return cmd.value
    return None


# ===========================================================================
# PNEUMONIA TESTS
# ===========================================================================


class TestPneumonia:
    """Tests for PneumoniaModule ODE dynamics and factor outputs."""

    def test_pneumonia_exudate_increases(self):
        """Alveolar exudate should increase over time after activation."""
        pm = create_disease("pneumonia",severity="moderate")
        pm.activate(current_time_s=0.0)
        initial_exudate = pm.alveolar_exudate
        run_compute_for_seconds(pm, 60.0)
        assert pm.alveolar_exudate > initial_exudate

    def test_pneumonia_bacterial_load_decay(self):
        """Bacterial load decays when immune_clearance > growth_rate (moderate preset)."""
        pm = create_disease("pneumonia", severity="moderate")
        pm.activate(current_time_s=0.0)
        initial_load = pm.bacterial_load
        run_compute_for_seconds(pm, 600.0)
        # Moderate preset: immune_clearance > growth_rate, so bacteria decay
        assert pm.bacterial_load < initial_load

    def test_pneumonia_fever_develops(self):
        """After sufficient time, fever_state should be > 0."""
        pm = create_disease("pneumonia",severity="moderate")
        pm.activate(current_time_s=0.0)
        run_compute_for_seconds(pm, 600.0)
        assert pm.fever_state > 0.0

    def test_pneumonia_diffusion_decreases(self):
        """diffusion_coefficient command value should decrease as exudate increases."""
        pm = create_disease("pneumonia",severity="moderate")
        pm.activate(current_time_s=0.0)
        initial_cmds = pm.compute(0.1, DUMMY_ENGINE_STATE)
        initial_diffusion = _find_cmd_value(initial_cmds, "lung.diffusion_coefficient")
        assert initial_diffusion is not None
        run_compute_for_seconds(pm, 60.0)
        later_cmds = pm.compute(0.1, DUMMY_ENGINE_STATE)
        later_diffusion = _find_cmd_value(later_cmds, "lung.diffusion_coefficient")
        assert later_diffusion < initial_diffusion

    def test_pneumonia_hr_offset_is_error_driven(self):
        """heart_rate add should be error-driven (converges toward target)."""
        pm = create_disease("pneumonia", severity="severe")
        pm.activate(current_time_s=0.0)
        hr_offset = _find_cmd_value(pm.compute(0.1, DUMMY_ENGINE_STATE), "heart.heart_rate")
        assert hr_offset is not None
        # Error-driven formula: 0.05 * (target - current_HR)
        # With DUMMY HR=85 and target=100: offset ≈ 0.05 * 15 = 0.75
        assert hr_offset == pytest.approx(0.75, abs=1e-6)

    def test_pneumonia_hypoxia_increases(self):
        """tissue_hypoxia should increase over time."""
        pm = create_disease("pneumonia",severity="moderate")
        pm.activate(current_time_s=0.0)
        initial_hypoxia = pm.tissue_hypoxia
        run_compute_for_seconds(pm, 600.0)
        assert pm.tissue_hypoxia > initial_hypoxia

    def test_pneumonia_severe_faster_than_mild(self):
        """Severe pneumonia should progress faster than mild."""
        mild = create_disease("pneumonia",severity="mild")
        severe = create_disease("pneumonia",severity="severe")
        mild.activate(current_time_s=0.0)
        severe.activate(current_time_s=0.0)
        run_compute_for_seconds(mild, 600.0)
        run_compute_for_seconds(severe, 600.0)
        assert severe.alveolar_exudate > mild.alveolar_exudate

    def test_pneumonia_inactive_returns_empty(self):
        """Inactive disease should return empty list from compute()."""
        pm = create_disease("pneumonia",severity="moderate")
        # Do NOT activate
        result = pm.compute(0.1, DUMMY_ENGINE_STATE)
        assert result == []

    def test_pneumonia_summary(self):
        """summary() should return dict with expected keys."""
        pm = create_disease("pneumonia",severity="moderate")
        pm.activate(current_time_s=0.0)
        s = pm.summary()
        expected_keys = {
            "name",
            "active",
            "alveolar_exudate",
            "bacterial_load",
            "fever_state",
            "tissue_hypoxia",
        }
        assert set(s.keys()) == expected_keys
        assert s["name"] == "pneumonia"
        assert s["active"] is True


# ===========================================================================
# ACUTE RENAL FAILURE TESTS
# ===========================================================================


class TestAcuteRenalFailure:
    """Tests for AcuteRenalFailureModule ODE dynamics and factor outputs."""

    def test_arf_nephron_damage_increases(self):
        """Nephron damage should increase above initial value."""
        arf = create_disease("acute_renal_failure",severity="moderate")
        arf.activate(current_time_s=0.0)
        initial_damage = arf.nephron_damage
        assert initial_damage > 0.0  # 初始值基于文献校准
        run_compute_for_seconds(arf, 60.0)
        assert arf.nephron_damage > initial_damage

    def test_arf_gfr_decline_increases(self):
        """gfr_decline should increase over time."""
        arf = create_disease("acute_renal_failure",severity="moderate")
        arf.activate(current_time_s=0.0)
        initial_decline = arf.gfr_decline
        run_compute_for_seconds(arf, 60.0)
        assert arf.gfr_decline > initial_decline

    def test_arf_gfr_decline_nonlinear(self):
        """gfr_decline should follow damage^1.5 relationship."""
        arf = create_disease("acute_renal_failure",severity="moderate")
        arf.activate(current_time_s=0.0)
        run_compute_for_seconds(arf, 60.0)
        expected = min(arf.nephron_damage ** 1.5, 1.0)
        assert abs(arf.gfr_decline - expected) < 0.001

    def test_arf_potassium_increases(self):
        """potassium_shift should increase as GFR declines."""
        arf = create_disease("acute_renal_failure",severity="moderate")
        arf.activate(current_time_s=0.0)
        run_compute_for_seconds(arf, 600.0)
        assert arf.potassium_shift > 0.0

    def test_arf_acidosis_develops(self):
        """metabolic_acidosis should increase over time."""
        arf = create_disease("acute_renal_failure",severity="moderate")
        arf.activate(current_time_s=0.0)
        initial_acidosis = arf.metabolic_acidosis
        run_compute_for_seconds(arf, 600.0)
        assert arf.metabolic_acidosis > initial_acidosis

    def test_arf_gfr_multiplier_decreases(self):
        """GFR multiplier command value (= 1 - gfr_decline) should decrease."""
        arf = create_disease("acute_renal_failure",severity="moderate")
        arf.activate(current_time_s=0.0)
        initial_gfr_mul = _find_cmd_value(arf.compute(0.1, DUMMY_ENGINE_STATE), "kidney._disease_gfr_multiplier")
        assert initial_gfr_mul is not None
        run_compute_for_seconds(arf, 60.0)
        later_gfr_mul = _find_cmd_value(arf.compute(0.1, DUMMY_ENGINE_STATE), "kidney._disease_gfr_multiplier")
        assert later_gfr_mul < initial_gfr_mul

    def test_arf_severe_faster_than_mild(self):
        """Severe ARF should progress faster than mild."""
        mild = create_disease("acute_renal_failure",severity="mild")
        severe = create_disease("acute_renal_failure",severity="severe")
        mild.activate(current_time_s=0.0)
        severe.activate(current_time_s=0.0)
        run_compute_for_seconds(mild, 600.0)
        run_compute_for_seconds(severe, 600.0)
        assert severe.nephron_damage > mild.nephron_damage

    def test_arf_hr_offset_is_error_driven(self):
        """ARF heart_rate add should be error-driven (target=baseline, pulls HR toward 86.7)."""
        arf = create_disease("acute_renal_failure", severity="severe")
        arf.activate(current_time_s=0.0)
        hr_value = _find_cmd_value(arf.compute(0.1, DUMMY_ENGINE_STATE), "heart.heart_rate")
        assert hr_value is not None
        # Error-driven: 0.05 * (86.7 - 85.0) ≈ 0.085 (positive, pulling toward target)
        assert hr_value == pytest.approx(0.085, abs=1e-6)

    def test_arf_inactive_returns_empty(self):
        """Inactive disease should return empty list from compute()."""
        arf = create_disease("acute_renal_failure",severity="moderate")
        result = arf.compute(0.1, DUMMY_ENGINE_STATE)
        assert result == []

    def test_arf_summary(self):
        """summary() should return dict with expected keys."""
        arf = create_disease("acute_renal_failure",severity="moderate")
        arf.activate(current_time_s=0.0)
        s = arf.summary()
        expected_keys = {
            "name",
            "active",
            "nephron_damage",
            "gfr_decline",
            "potassium_shift",
            "metabolic_acidosis",
            "uremic_stomatitis",
            "urine_output",
        }
        assert set(s.keys()) == expected_keys
        assert s["name"] == "acute_renal_failure"
        assert s["active"] is True


# ===========================================================================
# DISEASE INTEGRATION WITH SIMULATION
# ===========================================================================


class TestDiseaseIntegrationWithSimulation:
    """Integration tests: diseases modify VirtualCreature physiology."""

    @pytest.mark.slow
    def test_pneumonia_affects_simulation(self):
        """Attach pneumonia; lung.diffusion_coefficient should decrease vs baseline.

        Tests the mechanism (DL reduction) rather than final saturation because
        the A-a gradient formula in the current lung model dampens the saturation
        impact of small DL changes. The key effect of pneumonia — reducing DL —
        is what we verify here.
        """
        mature_age_days = 1095.0  # ~3 yr — ensures organ_multiplier ≈ 1.0

        # Baseline: no disease
        baseline = VirtualCreature(body_weight_kg=20.0, age_days=mature_age_days, dt=5.0)
        for _ in range(12):
            baseline.step()
        baseline_dl = baseline.lung.diffusion_coefficient

        # With pneumonia
        creature = VirtualCreature(body_weight_kg=20.0, age_days=mature_age_days, dt=5.0)
        pneumonia = create_disease("pneumonia", severity="moderate")
        creature.attach_disease(pneumonia)
        for _ in range(12):
            creature.step()
        disease_dl = creature.lung.diffusion_coefficient

        assert disease_dl < baseline_dl, (
            f"pneumonia should reduce diffusion_coefficient; got disease={disease_dl:.4f} "
            f">= baseline={baseline_dl:.4f}"
        )

    @pytest.mark.slow
    def test_pneumonia_oxygenation_checkpoint_after_60s(self):
        """After 60 s, pneumonia should produce a meaningful oxygenation deficit.

        This is a sparse checkpoint test rather than a full natural-history claim.
        It is designed to be clinically aligned in direction and magnitude without
        pretending to reproduce one exact cohort mean.
        """
        baseline = VirtualCreature(body_weight_kg=20.0, dt=0.1)
        creature = VirtualCreature(body_weight_kg=20.0, dt=0.1)
        creature.attach_disease(create_disease("pneumonia", severity="moderate"))

        for _ in range(600):
            baseline.step()
            creature.step()

        baseline_pao2 = baseline.blood.arterial_PO2_mmHg
        disease_pao2 = creature.blood.arterial_PO2_mmHg
        baseline_spo2 = baseline.blood.arterial_saturation
        disease_spo2 = creature.blood.arterial_saturation

        assert disease_pao2 <= baseline_pao2 - 5.0, (
            f"pneumonia should lower PaO2 by a clinically meaningful margin after 60 s: "
            f"baseline={baseline_pao2:.2f}, disease={disease_pao2:.2f}"
        )
        assert disease_spo2 <= baseline_spo2 - 0.005, (
            f"pneumonia should lower saturation after 60 s: "
            f"baseline={baseline_spo2:.4f}, disease={disease_spo2:.4f}"
        )

    @pytest.mark.slow
    def test_arf_affects_simulation(self):
        """Attach ARF; GFR falls and azotemia / electrolyte / acid-base worsen."""
        # Baseline: no disease
        baseline = VirtualCreature(body_weight_kg=20.0, dt=5.0)
        for _ in range(12):
            baseline.step()
        baseline_gfr = baseline.history["GFR"][-1]
        baseline_bun = baseline.history["BUN"][-1]
        baseline_k = baseline.blood.potassium_mEq_L
        baseline_ph = baseline.blood.arterial_pH

        # With ARF
        creature = VirtualCreature(body_weight_kg=20.0, dt=5.0)
        arf = create_disease("acute_renal_failure",severity="moderate")
        creature.attach_disease(arf)
        for _ in range(12):
            creature.step()
        disease_gfr = creature.history["GFR"][-1]
        disease_bun = creature.history["BUN"][-1]
        disease_k = creature.blood.potassium_mEq_L
        disease_ph = creature.blood.arterial_pH

        assert disease_gfr < baseline_gfr
        assert disease_bun > baseline_bun
        assert disease_k > baseline_k
        assert disease_ph < baseline_ph

    @pytest.mark.slow
    def test_arf_checkpoint_after_60s(self):
        """After 60 s, ARF should show a multi-domain renal deterioration pattern."""
        baseline = VirtualCreature(body_weight_kg=20.0, dt=0.1)
        creature = VirtualCreature(body_weight_kg=20.0, dt=0.1)
        creature.attach_disease(create_disease("acute_renal_failure", severity="moderate"))

        for _ in range(600):
            baseline.step()
            creature.step()

        assert creature.kidney.GFR <= baseline.kidney.GFR - 20.0, (
            f"ARF should meaningfully reduce GFR after 60 s: "
            f"baseline={baseline.kidney.GFR:.2f}, disease={creature.kidney.GFR:.2f}"
        )
        assert creature.blood.bun_mg_dL >= baseline.blood.bun_mg_dL + 3.0, (
            f"ARF should raise BUN after 60 s: "
            f"baseline={baseline.blood.bun_mg_dL:.2f}, disease={creature.blood.bun_mg_dL:.2f}"
        )
        assert creature.blood.potassium_mEq_L >= baseline.blood.potassium_mEq_L + 0.05, (
            f"ARF should raise potassium after 60 s: "
            f"baseline={baseline.blood.potassium_mEq_L:.3f}, disease={creature.blood.potassium_mEq_L:.3f}"
        )
        assert creature.blood.arterial_pH <= baseline.blood.arterial_pH - 0.01, (
            f"ARF should lower pH after 60 s: "
            f"baseline={baseline.blood.arterial_pH:.4f}, disease={creature.blood.arterial_pH:.4f}"
        )

    @pytest.mark.slow
    def test_disease_event_activation(self):
        """Use schedule_event to activate disease mid-simulation.

        Since schedule_event doesn't natively support disease activation,
        we verify that a disease attached at t=0 and activated via
        attach_disease changes physiology compared to no disease.
        Alternative: manually test that activate() mid-run takes effect.
        """
        # Creature without disease for first 300 steps
        creature = VirtualCreature(body_weight_kg=20.0, dt=5.0)
        for _ in range(6):
            creature.step()
        pre_gfr = creature.history["GFR"][-1]

        # Now attach ARF (activates immediately)
        arf = create_disease("acute_renal_failure",severity="moderate")
        creature.attach_disease(arf)

        # Run another 600 steps with disease active
        for _ in range(12):
            creature.step()
        post_gfr = creature.history["GFR"][-1]

        assert post_gfr < pre_gfr


# ===========================================================================
# PHOSPHORUS POISONING TESTS
# ===========================================================================


class TestPhosphorusPoisoning:
    """Tests for PhosphorusPoisoningModule ODE dynamics and factor outputs."""

    def test_toxicity_increases(self):
        """Cellular toxicity should increase over time after activation."""
        from src.diseases import create_disease
        pm = create_disease("phosphorus_poisoning", severity="moderate")
        pm.activate(current_time_s=0.0)
        initial = pm.cellular_toxicity
        run_compute_for_seconds(pm, 60.0)
        assert pm.cellular_toxicity > initial

    def test_toxicity_clamped_to_1(self):
        """Cellular toxicity should never exceed 1.0."""
        from src.diseases import create_disease
        pm = create_disease("phosphorus_poisoning", severity="severe")
        pm.activate(current_time_s=0.0)
        run_compute_for_seconds(pm, 3600.0)
        assert pm.cellular_toxicity <= 1.0

    def test_myocardial_depression_increases(self):
        """Myocardial depression should increase over time."""
        from src.diseases import create_disease
        pm = create_disease("phosphorus_poisoning", severity="moderate")
        pm.activate(current_time_s=0.0)
        run_compute_for_seconds(pm, 60.0)
        assert pm.myocardial_depression > 0.0

    def test_acidosis_develops(self):
        """Metabolic acidosis should develop after sufficient time."""
        from src.diseases import create_disease
        pm = create_disease("phosphorus_poisoning", severity="moderate")
        pm.activate(current_time_s=0.0)
        run_compute_for_seconds(pm, 600.0)
        assert pm.metabolic_acidosis > 0.0

    def test_renal_injury_develops(self):
        """Renal injury should develop over time."""
        from src.diseases import create_disease
        pm = create_disease("phosphorus_poisoning", severity="moderate")
        pm.activate(current_time_s=0.0)
        run_compute_for_seconds(pm, 600.0)
        assert pm.renal_injury > 0.0

    def test_contractility_factor_decreases(self):
        """Contractility factor command value should decrease as toxicity rises."""
        from src.diseases import create_disease
        pm = create_disease("phosphorus_poisoning", severity="moderate")
        pm.activate(current_time_s=0.0)
        initial_cmds = pm.compute(0.1, DUMMY_ENGINE_STATE)
        initial_ctr = _find_cmd_value(initial_cmds, "heart.contractility_factor")
        assert initial_ctr is not None
        run_compute_for_seconds(pm, 600.0)
        later_cmds = pm.compute(0.1, DUMMY_ENGINE_STATE)
        later_ctr = _find_cmd_value(later_cmds, "heart.contractility_factor")
        assert later_ctr < initial_ctr

    def test_gfr_multiplier_decreases(self):
        """GFR multiplier command should decrease as renal injury progresses."""
        from src.diseases import create_disease
        pm = create_disease("phosphorus_poisoning", severity="moderate")
        pm.activate(current_time_s=0.0)
        initial_gfr = _find_cmd_value(pm.compute(0.1, DUMMY_ENGINE_STATE), "kidney._disease_gfr_multiplier")
        assert initial_gfr is not None
        run_compute_for_seconds(pm, 600.0)
        later_gfr = _find_cmd_value(pm.compute(0.1, DUMMY_ENGINE_STATE), "kidney._disease_gfr_multiplier")
        assert later_gfr < initial_gfr

    def test_hco3_decreases(self):
        """Blood HCO3 command value should decrease (metabolic acidosis)."""
        from src.diseases import create_disease
        pm = create_disease("phosphorus_poisoning", severity="severe")
        pm.activate(current_time_s=0.0)
        initial_hco3 = _find_cmd_value(pm.compute(0.1, DUMMY_ENGINE_STATE), "blood.HCO3")
        assert initial_hco3 is not None
        run_compute_for_seconds(pm, 1200.0)
        later_hco3 = _find_cmd_value(pm.compute(0.1, DUMMY_ENGINE_STATE), "blood.HCO3")
        assert later_hco3 < initial_hco3

    def test_severe_faster_than_mild(self):
        """Severe phosphorus poisoning should progress faster than mild."""
        from src.diseases import create_disease
        mild = create_disease("phosphorus_poisoning", severity="mild")
        severe = create_disease("phosphorus_poisoning", severity="severe")
        mild.activate(current_time_s=0.0)
        severe.activate(current_time_s=0.0)
        run_compute_for_seconds(mild, 600.0)
        run_compute_for_seconds(severe, 600.0)
        assert severe.cellular_toxicity > mild.cellular_toxicity

    def test_inactive_returns_empty(self):
        """Inactive disease should return empty list from compute()."""
        from src.diseases import create_disease
        pm = create_disease("phosphorus_poisoning", severity="moderate")
        result = pm.compute(0.1, DUMMY_ENGINE_STATE)
        assert result == []

    def test_summary(self):
        """summary() should return dict with expected keys."""
        from src.diseases import create_disease
        pm = create_disease("phosphorus_poisoning", severity="moderate")
        pm.activate(current_time_s=0.0)
        s = pm.summary()
        expected_keys = {
            "name",
            "active",
            "cellular_toxicity",
            "myocardial_depression",
            "metabolic_acidosis",
            "renal_injury",
            "pain_level",
            "toxicity",
            "intravascular_hemolysis",
            "upper_gi_hemorrhage",
        }
        assert set(s.keys()) == expected_keys
        assert s["name"] == "phosphorus_poisoning"
        assert s["active"] is True


