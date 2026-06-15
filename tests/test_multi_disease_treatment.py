"""
Multi-disease treatment tests — Q4 (2026-06-14).

Verifies the treatment system correctly handles comorbidity cases:
  - Q4.1=C: Auto-infer — player submits diagnosis list, system auto-admins all protocols
  - Q4.2=B: Primary diagnosis must be correct to win; comorbidity is bonus
  - Q4.3=B: Runtime merge — single-disease protocols admined in guess order

Tests use the treatment module directly (no Flask) for fast, isolated verification.
"""
from __future__ import annotations

import pytest

from game.treatment import (
    _resolve_guesses,
    apply_treatment,
    is_correct_treatment,
)
from game.action_system import GameState
from src.simulation import VirtualCreature
from src.diseases import create_disease


# ─── Helpers ──────────────────────────────────────────────────────────────


def _make_state(disease_name: str, disease_names: list[str] | None = None,
                weight_kg: float = 20.0) -> GameState:
    """Create a minimal GameState for treatment testing."""
    vc = VirtualCreature(body_weight_kg=weight_kg, species="canine", dt=5.0,
                         legacy_clinical_signs_enabled=False)
    vc.attach_disease(create_disease(disease_name))
    if disease_names and len(disease_names) > 1:
        for extra in disease_names[1:]:
            vc.attach_disease(create_disease(extra))
    return GameState(
        engine=vc,
        disease_name=disease_name,
        disease_names=disease_names or [disease_name],
    )


# ─── Q4.1=C: _resolve_guesses ────────────────────────────────────────────


class TestResolveGuesses:
    """_resolve_guesses normalizes str or list input to list."""

    def test_string_input(self):
        assert _resolve_guesses("pneumonia") == ["pneumonia"]

    def test_list_input(self):
        assert _resolve_guesses(["pneumonia", "dcm"]) == ["pneumonia", "dcm"]

    def test_empty_string(self):
        assert _resolve_guesses("") == []

    def test_empty_list(self):
        assert _resolve_guesses([]) == []

    def test_list_with_empty_strings_filtered(self):
        assert _resolve_guesses(["pneumonia", "", "dcm"]) == ["pneumonia", "dcm"]


# ─── Q4.2=B: is_correct_treatment (backward compat) ──────────────────────


class TestIsCorrectTreatment:
    """is_correct_treatment checks primary disease (backward compat)."""

    def test_correct_single_disease(self):
        state = _make_state("pneumonia")
        assert is_correct_treatment(state, "pneumonia") is True

    def test_wrong_single_disease(self):
        state = _make_state("pneumonia")
        assert is_correct_treatment(state, "dcm") is False


# ─── Q4.2=B: apply_treatment win condition ────────────────────────────────


class TestApplyTreatmentWinCondition:
    """Q4.2=B: Primary diagnosis must be in guess list to win."""

    def test_single_disease_correct(self):
        """Single-disease case: correct guess → won."""
        state = _make_state("pneumonia")
        result = apply_treatment(state, "pneumonia")
        assert result["correct"] is True
        assert result["phase"] == "won"
        assert result["comorbidity_correct"] is None  # no comorbidity

    def test_single_disease_wrong(self):
        """Single-disease case: wrong guess → playing."""
        state = _make_state("pneumonia")
        result = apply_treatment(state, "dcm")
        assert result["correct"] is False
        assert result["phase"] == "playing"

    def test_comorbidity_primary_correct_alone_wins(self):
        """Multi-disease: primary in guess list → won (even without comorbidity)."""
        state = _make_state("dilated_cardiomyopathy",
                            disease_names=["dilated_cardiomyopathy", "pneumonia"])
        result = apply_treatment(state, ["dilated_cardiomyopathy"])
        assert result["correct"] is True
        assert result["phase"] == "won"
        assert result["comorbidity_correct"] is False  # comorbidity not guessed

    def test_comorbidity_both_correct_wins_with_bonus(self):
        """Multi-disease: both in guess list → won + bonus message."""
        state = _make_state("dilated_cardiomyopathy",
                            disease_names=["dilated_cardiomyopathy", "pneumonia"])
        result = apply_treatment(state, ["dilated_cardiomyopathy", "pneumonia"])
        assert result["correct"] is True
        assert result["phase"] == "won"
        assert result["comorbidity_correct"] is True
        assert "额外奖励" in result["message"]

    def test_comorbidity_only_comorbidity_loses(self):
        """Multi-disease: only comorbidity guessed (not primary) → playing."""
        state = _make_state("dilated_cardiomyopathy",
                            disease_names=["dilated_cardiomyopathy", "pneumonia"])
        result = apply_treatment(state, ["pneumonia"])
        assert result["correct"] is False
        assert result["phase"] == "playing"


# ─── Q4.3=B: Runtime merge — protocol admin order ────────────────────────


class TestRuntimeMerge:
    """Q4.3=B: Protocols admined in guess list order."""

    def test_single_disease_admins_protocol(self):
        """Single disease → admin that disease's protocol."""
        state = _make_state("pneumonia")
        result = apply_treatment(state, "pneumonia")
        assert len(result["drugs_given"]) > 0  # pneumonia has a protocol

    def test_multi_disease_admins_both_protocols(self):
        """Multi-disease → admin both protocols (order = guess order)."""
        state = _make_state("dilated_cardiomyopathy",
                            disease_names=["dilated_cardiomyopathy", "pneumonia"])
        result = apply_treatment(state, ["dilated_cardiomyopathy", "pneumonia"])
        # Both diseases have protocols → drugs_given should have entries from both
        assert len(result["drugs_given"]) > 0
        # DCM protocol: pimobendan + furosemide
        # Pneumonia protocol: fluid_bolus
        given_set = set(result["drugs_given"])
        assert "pimobendan" in given_set, f"DCM drug pimobendan missing: {given_set}"
        assert "furosemide" in given_set, f"DCM drug furosemide missing: {given_set}"
        assert "fluid_bolus" in given_set, f"Pneumonia drug fluid_bolus missing: {given_set}"

    def test_supportive_care_still_works(self):
        """supportive_care string → fluid bolus (backward compat)."""
        state = _make_state("pneumonia")
        result = apply_treatment(state, "supportive_care")
        assert result["phase"] == "playing"
        assert "fluid_bolus" in result["drugs_given"]


# ─── Backward compatibility ───────────────────────────────────────────────


class TestBackwardCompat:
    """Existing single-disease treatment still works after Q4 refactor."""

    def test_string_guess_still_works(self):
        """String disease_guess (not list) → same behavior as before."""
        state = _make_state("pneumonia")
        result = apply_treatment(state, "pneumonia")
        assert result["correct"] is True
        assert result["phase"] == "won"
        assert result["actual_disease"] == "pneumonia"
        assert result["chosen_disease"] == "pneumonia"
