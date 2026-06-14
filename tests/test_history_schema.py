"""
test_history_schema.py — Step 0b regression test.

Verifies Euler and Radau paths produce the same history schema:
- Same set of keys
- No key collisions (e.g. bare 'sympathetic' vs 'neuro_sympathetic')
- All organ subsystems recorded
- No NaN in any history field
"""
from __future__ import annotations

import math

import pytest

from src.simulation import VirtualCreature


# Canonical schema (must match the keys initialized in simulation.py)
EXPECTED_HISTORY_KEYS = {
    # Cardio
    "time_s", "HR_bpm", "CO_ml_min", "MAP_mmHg", "CVP_mmHg",
    # Respiratory
    "RR", "art_PO2", "art_PCO2", "saturation", "pH",
    # Renal
    "GFR", "urine_ml_min", "BUN", "plasma_Na",
    # Metabolic
    "glucose", "blood_volume_ml",
    # Toxicology
    "contractility_factor", "svr_factor",
    # Organ health
    "heart_health", "lung_health", "kidney_health", "liver_health",
    # Fluid compartments
    "fluid_vascular_ml", "fluid_isf_ml", "fluid_icf_ml", "fluid_nfp_mmHg",
    # Liver / Gut
    "liver_metabolic_activity", "liver_detox_capacity", "liver_glycogen",
    "gut_motility", "gut_barrier", "gut_microbiome",
    # Endocrine
    "T3_ng_dL", "insulin_uU_mL", "cortisol_ug_dL", "metabolic_rate",
    "core_temperature_C",
    # Neuro
    "neuro_sympathetic", "neuro_consciousness", "neuro_seizure",
    "neuro_pain", "neuro_chemodrive",
    # Immune
    "immune_cytokine", "immune_wbc", "immune_crp", "immune_coagulation",
    # Coagulation
    "coag_PT", "coag_aPTT", "coag_fibrinogen",
    # Lymphatic
    "lymph_splenic_reserve", "lymph_lymph_flow",
}


class TestHistorySchema:
    """P0 0b: Euler and Radau must produce identical history schema."""

    def test_euler_history_has_canonical_keys(self):
        """Euler path records all 45 canonical keys."""
        vc = VirtualCreature(body_weight_kg=20.0, solver="euler", record_history=True)
        for _ in range(3):
            vc.step()
        actual_keys = set(vc.history.keys())
        missing = EXPECTED_HISTORY_KEYS - actual_keys
        assert not missing, f"Euler history missing keys: {missing}"

    def test_euler_no_bare_sympathetic_collision(self):
        """P0 0b: bare 'sympathetic' key was colliding with 'neuro_sympathetic'."""
        vc = VirtualCreature(body_weight_kg=20.0, solver="euler", record_history=True)
        for _ in range(3):
            vc.step()
        assert "sympathetic" not in vc.history, "Bare 'sympathetic' key still in history (collision risk)"
        assert "neuro_sympathetic" in vc.history, "Missing canonical 'neuro_sympathetic' key"

    def test_euler_history_lengths_consistent(self):
        """All history arrays have the same length (= number of steps)."""
        vc = VirtualCreature(body_weight_kg=20.0, solver="euler", record_history=True)
        n_steps = 5
        for _ in range(n_steps):
            vc.step()
        lengths = {k: len(v) for k, v in vc.history.items()}
        unique = set(lengths.values())
        assert unique == {n_steps}, f"Length mismatch: {lengths}"

    def test_euler_history_no_nan_or_inf(self):
        """History contains only finite numeric values."""
        vc = VirtualCreature(body_weight_kg=20.0, solver="euler", record_history=True)
        for _ in range(5):
            vc.step()
        for key, vals in vc.history.items():
            for i, v in enumerate(vals):
                assert isinstance(v, (int, float)), f"{key}[{i}] is {type(v).__name__}"
                assert not math.isnan(v), f"NaN in history['{key}'][{i}]"
                assert not math.isinf(v), f"Inf in history['{key}'][{i}]"

    @pytest.mark.skip(reason="scipy 1.17 + Python 3.14 Radau solver hangs (env issue, see src/engine/solvers/radau.py:16-21); Radau fallback path covered by tests/test_solver_fallback.py")
    def test_radau_history_has_canonical_keys(self):
        """Radau path also records all canonical keys (was the broken case)."""
        vc = VirtualCreature(body_weight_kg=20.0, solver="radau", record_history=True)
        # Single Radau step (slow) — checks schema, not trajectories
        vc.step()
        actual_keys = set(vc.history.keys())
        missing = EXPECTED_HISTORY_KEYS - actual_keys
        assert not missing, f"Radau history missing keys: {missing}"

    @pytest.mark.skip(reason="scipy 1.17 + Python 3.14 Radau solver hangs (env issue, see src/engine/solvers/radau.py:16-21); Radau fallback path covered by tests/test_solver_fallback.py")
    def test_radau_no_bare_sympathetic_collision(self):
        """P0 0b: Radau's bare 'sympathetic' was overwriting neuro_sympathetic."""
        vc = VirtualCreature(body_weight_kg=20.0, solver="radau", record_history=True)
        vc.step()
        assert "sympathetic" not in vc.history
        assert "neuro_sympathetic" in vc.history

    @pytest.mark.skip(reason="scipy 1.17 + Python 3.14 Radau solver hangs (env issue, see src/engine/solvers/radau.py:16-21); Radau fallback path covered by tests/test_solver_fallback.py")
    def test_radau_organ_health_recorded(self):
        """P0 0b: Radau was silently dropping organ_health fields."""
        vc = VirtualCreature(body_weight_kg=20.0, solver="radau", record_history=True)
        vc.step()
        for k in ("heart_health", "lung_health", "kidney_health", "liver_health"):
            assert k in vc.history
            assert len(vc.history[k]) == 1
            assert isinstance(vc.history[k][0], float)

    @pytest.mark.skip(reason="scipy 1.17 + Python 3.14 Radau solver hangs (env issue, see src/engine/solvers/radau.py:16-21); Radau fallback path covered by tests/test_solver_fallback.py")
    def test_radau_fluid_compartments_recorded(self):
        """P0 0b: Radau was silently dropping fluid compartment fields."""
        vc = VirtualCreature(body_weight_kg=20.0, solver="radau", record_history=True)
        vc.step()
        for k in ("fluid_vascular_ml", "fluid_isf_ml", "fluid_icf_ml", "fluid_nfp_mmHg"):
            assert k in vc.history, f"Radau dropped fluid field: {k}"
            assert len(vc.history[k]) == 1

    @pytest.mark.skip(reason="scipy 1.17 + Python 3.14 Radau solver hangs (env issue, see src/engine/solvers/radau.py:16-21); Radau fallback path covered by tests/test_solver_fallback.py")
    def test_radau_neuro_five_fields_recorded(self):
        """P0 0b: Radau was only recording 1 of 5 neuro fields."""
        vc = VirtualCreature(body_weight_kg=20.0, solver="radau", record_history=True)
        vc.step()
        for k in ("neuro_sympathetic", "neuro_consciousness", "neuro_seizure",
                  "neuro_pain", "neuro_chemodrive"):
            assert k in vc.history, f"Radau dropped neuro field: {k}"
            assert len(vc.history[k]) == 1