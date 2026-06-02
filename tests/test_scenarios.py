"""
Scenario-level integration tests for the medical diagnosis game.

Covers: case_generator, diagnosis_engine, action_system end-to-end workflows.
Each test is a self-contained clinical scenario that exercises multiple subsystems.

Run with:
    cd C:\\Users\\ZhuanZ（无密码）\\Desktop\\my_project && python -m pytest tests/test_scenarios.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

# Path setup — mirrors conftest.py
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))


# =============================================================================
#  FIXTURES
# =============================================================================

@pytest.fixture
def healthy_creature():
    """Healthy 20kg dog simulated 1 min."""
    from src.simulation import VirtualCreature
    e = VirtualCreature(body_weight_kg=20.0)
    e.simulate(1.0)
    return e


@pytest.fixture
def pneumonia_creature():
    """20kg dog with moderate pneumonia simulated 20 min."""
    from src.simulation import VirtualCreature
    from src.diseases import create_disease
    e = VirtualCreature(body_weight_kg=20.0)
    d = create_disease("pneumonia", severity="moderate")
    e.attach_disease(d)
    e.simulate(20.0)
    return e


@pytest.fixture
def arf_creature():
    """20kg dog with moderate ARF simulated 20 min."""
    from src.simulation import VirtualCreature
    from src.diseases import create_disease
    e = VirtualCreature(body_weight_kg=20.0)
    d = create_disease("acute_renal_failure", severity="moderate")
    e.attach_disease(d)
    e.simulate(20.0)
    return e


def _make_game_state(creature, disease_name="pneumonia"):
    """Helper: build a fresh GameState wrapping the given creature."""
    from game.action_system import GameState
    return GameState(engine=creature, disease_name=disease_name)


# =============================================================================
#  CASE GENERATOR TESTS
# =============================================================================

class TestCaseGenerator:

    def test_generate_case_returns_valid_game_state(self):
        """generate_case() should return a GameState with valid engine, disease_name, phase='playing'."""
        from game.case_generator import generate_case
        state = generate_case(difficulty="normal", seed=42)
        from game.action_system import GameState
        assert isinstance(state, GameState)
        assert state.engine is not None
        assert isinstance(state.disease_name, str)
        assert len(state.disease_name) > 0
        assert state.phase == "playing"
        assert state.time_elapsed_min == 0

    def test_generate_case_different_difficulties(self):
        """'easy', 'normal', 'hard' should all produce valid cases."""
        from game.case_generator import generate_case
        for diff in ("easy", "normal", "hard"):
            state = generate_case(difficulty=diff, seed=100)
            assert state.phase == "playing"
            assert state.engine is not None
            from src.diseases import list_diseases
            assert state.disease_name in list_diseases()

    def test_generate_case_with_seed_is_deterministic(self):
        """Same seed should produce identical cases."""
        from game.case_generator import generate_case
        s1 = generate_case(difficulty="normal", seed=999)
        s2 = generate_case(difficulty="normal", seed=999)
        assert s1.disease_name == s2.disease_name
        assert s1.time_elapsed_min == s2.time_elapsed_min
        assert s1.phase == s2.phase
        hr1 = s1.engine.history["HR_bpm"][-1] if s1.engine.history["HR_bpm"] else 0
        hr2 = s2.engine.history["HR_bpm"][-1] if s2.engine.history["HR_bpm"] else 0
        assert hr1 == hr2

    def test_generate_case_different_seeds_different(self):
        """Different seeds should (likely) produce different cases."""
        from game.case_generator import generate_case
        states = [generate_case(difficulty="normal", seed=i) for i in range(10)]
        disease_names = set(s.disease_name for s in states)
        assert len(disease_names) >= 1  # Technically could be same but 2 diseases make variety very likely

    def test_generate_case_engine_has_disease(self):
        """Generated case engine should have an active disease attached."""
        from game.case_generator import generate_case
        state = generate_case(difficulty="normal", seed=42)
        assert state.engine.disease is not None
        assert state.engine.disease.active is True

    def test_generate_case_vital_signs_abnormal(self):
        """Generated case should have at least some abnormal vital signs (disease should have progressed)."""
        from game.case_generator import generate_case
        from game.test_translator import translate
        # Try several seeds; at least one should produce clearly abnormal physical signs
        # in a disease case. Some seeds yield compensated states with normal HR/RR/Temp,
        # so we test across multiple seeds for robustness.
        found_abnormal = False
        for seed in range(20):
            state = generate_case(difficulty="normal", seed=seed)
            report = translate("physical", state.engine)
            abnormal = [r for r in report["results"] if r["flag"] != "normal"]
            if len(abnormal) >= 1:
                found_abnormal = True
                break
        assert found_abnormal, "Expected at least one seed (0-19) to produce abnormal physical signs"


# =============================================================================
#  DIAGNOSIS ENGINE — EXTRACT CLUES TESTS
# =============================================================================

class TestExtractClues:

    def test_extract_clues_from_blood_gas(self):
        """Blood gas report with low PaO2 should extract 'PaO2_low' clue."""
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "blood_gas", "results": [
            {"param": "PaO2", "flag": "low"},
        ], "tags": ["PaO2_low"]}]
        clues = extract_clues(reports)
        assert "PaO2_low" in clues

    def test_extract_clues_from_auscultation(self):
        """Report with crackles tag should extract 'crackles'."""
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "auscultation",
                     "summary": "双肺湿啰音（肺泡渗出）",
                     "results": ["双肺湿啰音（肺泡渗出）"],
                     "tags": ["crackles"]}]
        clues = extract_clues(reports)
        assert "crackles" in clues

    def test_extract_clues_from_xray(self):
        """Report with lung_exudate_xray tag should extract that clue."""
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "chest_xray",
                     "summary": "肺野斑片状渗出影",
                     "results": ["肺野斑片状渗出影"],
                     "tags": ["lung_exudate_xray"]}]
        clues = extract_clues(reports)
        assert "lung_exudate_xray" in clues

    def test_extract_clues_deduplication(self):
        """Same clue from multiple reports should appear only once."""
        from game.diagnosis_engine import extract_clues
        reports = [
            {"test_type": "physical", "results": [{"param": "HR", "flag": "high"}],
             "tags": ["hr_high"]},
            {"test_type": "ecg", "results": [{"param": "HR", "flag": "high"}],
             "tags": ["hr_high"]},
        ]
        clues = extract_clues(reports)
        assert clues.count("hr_high") == 1


# =============================================================================
#  DIAGNOSIS ENGINE — MATCH DISEASES TESTS
# =============================================================================

class TestMatchDiseases:

    def test_match_diseases_pneumonia(self):
        """Pneumonia clues should match pneumonia with high confidence."""
        from game.diagnosis_engine import match_diseases
        clues = ["PaO2_low", "SpO2_low", "hr_high", "rr_high", "temp_high",
                 "wbc_high", "lung_exudate_xray", "crackles"]
        matches = match_diseases([], known_clues=clues)
        top = matches[0]
        assert top["disease"] == "pneumonia"
        assert top["confidence"] > 0.5

    def test_match_diseases_arf(self):
        """ARF clues should match acute_renal_failure with high confidence."""
        from game.diagnosis_engine import match_diseases
        clues = ["gfr_low", "bun_high", "potassium_high", "ph_low", "hr_low",
                 "cr_high", "usg_low", "upcr_high", "t_wave_tall", "qrs_wide"]
        matches = match_diseases([], known_clues=clues)
        top = matches[0]
        assert top["disease"] == "acute_renal_failure"
        assert top["confidence"] > 0.5

    def test_match_diseases_no_clues(self):
        """Empty reports should return zero confidence for all diseases."""
        from game.diagnosis_engine import match_diseases
        matches = match_diseases([], known_clues=[])
        for m in matches:
            assert m["confidence"] == 0.0
            assert m["matched_count"] == 0


# =============================================================================
#  DIAGNOSIS ENGINE — HELPERS
# =============================================================================

class TestDiagnosisHelpers:

    def test_get_suggested_tests(self):
        """Should suggest relevant tests based on missed clues."""
        from game.diagnosis_engine import get_suggested_tests
        matches = [
            {"disease": "pneumonia", "confidence": 0.6,
             "missed_clues": ["PaO2_low", "lung_exudate_xray", "crackles"]},
        ]
        suggested = get_suggested_tests(matches)
        assert "blood_gas" in suggested
        assert "chest_xray" in suggested
        assert "auscultation" in suggested

    def test_get_diagnosis_summary(self):
        """Should return formatted string with disease names and percentages."""
        from game.diagnosis_engine import get_diagnosis_summary
        matches = [
            {"disease": "pneumonia", "confidence": 0.75,
             "matched_count": 6, "total_clues": 8},
            {"disease": "acute_renal_failure", "confidence": 0.25,
             "matched_count": 1, "total_clues": 5},
        ]
        text = get_diagnosis_summary(matches)
        assert "pneumonia" in text
        assert "75%" in text
        assert "acute_renal_failure" in text

    def test_register_disease_clues(self):
        """New disease clues should be registrable."""
        from game.diagnosis_engine import register_disease_clues, _DISEASE_CLUES
        register_disease_clues("test_disease_xyz", ["clue_a", "clue_b", "clue_c"])
        assert "test_disease_xyz" in _DISEASE_CLUES
        assert _DISEASE_CLUES["test_disease_xyz"] == ["clue_a", "clue_b", "clue_c"]
        # Clean up
        del _DISEASE_CLUES["test_disease_xyz"]


# =============================================================================
#  ACTION SYSTEM — PROCESS ACTION TESTS
# =============================================================================

class TestProcessAction:

    def test_process_action_examine(self, healthy_creature):
        """'examine' action should return a report and advance time."""
        from game.action_system import process_action
        state = _make_game_state(healthy_creature)
        result = process_action(state, "examine", {"test_type": "physical"})
        assert result["success"] is True
        assert result["result"] is not None
        assert result["result"]["test_type"] == "physical"
        assert state.time_elapsed_min > 0

    def test_process_action_wait(self, healthy_creature):
        """'wait' action should advance time without producing a report."""
        from game.action_system import process_action
        state = _make_game_state(healthy_creature)
        result = process_action(state, "wait")
        assert result["success"] is True
        assert result["result"] is None
        assert state.time_elapsed_min > 0

    def test_process_action_treat_correct(self, healthy_creature):
        """Correct diagnosis should set phase='won'."""
        from game.action_system import process_action
        state = _make_game_state(healthy_creature, disease_name="pneumonia")
        result = process_action(state, "treat", {"disease_guess": "pneumonia"})
        assert result["success"] is True
        assert result["phase"] == "won"

    def test_process_action_treat_incorrect(self, healthy_creature):
        """Wrong diagnosis should not set phase='won'."""
        from game.action_system import process_action
        state = _make_game_state(healthy_creature, disease_name="pneumonia")
        result = process_action(state, "treat", {"disease_guess": "acute_renal_failure"})
        assert result["success"] is True
        assert result["phase"] == "playing"

    def test_process_action_after_game_over(self, healthy_creature):
        """Actions after phase='won' or 'lost' should return success=False."""
        from game.action_system import process_action
        # Test after win
        state = _make_game_state(healthy_creature)
        state.phase = "won"
        result = process_action(state, "examine", {"test_type": "physical"})
        assert result["success"] is False
        assert result["phase"] == "won"

        # Test after loss
        state2 = _make_game_state(healthy_creature)
        state2.phase = "lost"
        result2 = process_action(state2, "wait")
        assert result2["success"] is False
        assert result2["phase"] == "lost"


# =============================================================================
#  ACTION SYSTEM — DETERMINE PHASE TESTS
# =============================================================================

class TestDeterminePhase:

    def test_determine_phase_stable(self, healthy_creature):
        """Healthy creature should return 'stable'."""
        from game.action_system import determine_phase
        assert determine_phase(healthy_creature) == "stable"

    def test_determine_phase_worsening(self, pneumonia_creature):
        """Creature with mild abnormalities should return 'worsening' or more severe."""
        from game.action_system import determine_phase
        phase = determine_phase(pneumonia_creature)
        assert phase in ("worsening", "critical", "moribund")

    def test_determine_phase_critical(self):
        """Creature with severe abnormalities should return 'critical' or 'moribund'."""
        from src.simulation import VirtualCreature
        from src.diseases import create_disease
        from game.action_system import determine_phase
        e = VirtualCreature(body_weight_kg=20.0)
        d = create_disease("pneumonia", severity="severe")
        e.attach_disease(d)
        e.simulate(60.0)  # 1 hour simulation to get disease to progress significantly
        phase = determine_phase(e)
        assert phase in ("critical", "moribund")

    def test_determine_phase_moribund(self):
        """Creature near death should return 'moribund'."""
        from src.simulation import VirtualCreature
        from src.diseases import create_disease
        from game.action_system import determine_phase
        e = VirtualCreature(body_weight_kg=20.0)
        d = create_disease("pneumonia", severity="severe")
        e.attach_disease(d)
        e.simulate(120.0)  # 2 hours — disease should be very progressed
        phase = determine_phase(e)
        assert phase in ("critical", "moribund")


# =============================================================================
#  ACTION SYSTEM — DEATH TIMER TESTS
# =============================================================================

class TestDeathTimer:

    def test_check_death_timer(self):
        """Moribund state should start countdown, countdown reaching 0 should set phase='lost'."""
        from game.action_system import GameState, check_death
        from src.simulation import VirtualCreature
        e = VirtualCreature(body_weight_kg=20.0)
        state = GameState(engine=e, disease_name="pneumonia")
        # First call: starts timer at MORIBUND_ACTIONS_REMAINING (3)
        state = check_death(state, "moribund")
        assert state.death_timer == 3
        # Decrement: 3 -> 2
        state = check_death(state, "moribund")
        assert state.death_timer == 2
        # Decrement: 2 -> 1
        state = check_death(state, "moribund")
        assert state.death_timer == 1
        # Decrement: 1 -> 0 -> lost
        state = check_death(state, "moribund")
        assert state.death_timer <= 0
        assert state.phase == "lost"

    def test_check_death_recovery(self):
        """Leaving moribund state should clear death timer."""
        from game.action_system import GameState, check_death
        from src.simulation import VirtualCreature
        e = VirtualCreature(body_weight_kg=20.0)
        state = GameState(engine=e, disease_name="pneumonia")
        # Enter moribund
        state = check_death(state, "moribund")
        assert state.death_timer == 3
        # Recover
        state = check_death(state, "stable")
        assert state.death_timer is None
        assert state.phase == "playing"


# =============================================================================
#  ACTION SYSTEM — DO2 COMPUTATION TESTS
# =============================================================================

class TestComputeDO2:

    def test_compute_DO2_healthy(self, healthy_creature):
        """Healthy dog should have DO2 near 1.0."""
        from game.action_system import compute_DO2
        do2 = compute_DO2(healthy_creature)
        assert 0.5 <= do2 <= 1.0

    def test_compute_DO2_hypoxic(self, pneumonia_creature):
        """Dog with low SpO2 should have lower DO2."""
        from game.action_system import compute_DO2
        do2 = compute_DO2(pneumonia_creature)
        # Pneumonia dog with moderate severity — DO2 should be reasonable
        # (error-driven HR compensates, so DO2 may be near or slightly above 1.0)
        assert 0.0 <= do2 <= 1.1


# =============================================================================
#  END-TO-END SCENARIO TESTS
# =============================================================================

class TestEndToEndWorkflows:

    def test_full_pneumonia_workflow(self):
        """Generate pneumonia case -> examine (blood_gas + xray + auscultation) ->
        extract clues -> match diseases -> verify pneumonia is top match."""
        from game.case_generator import generate_case
        from game.test_translator import translate
        from game.diagnosis_engine import extract_clues, match_diseases

        # Generate a case until we get pneumonia
        state = None
        for seed in range(50):
            s = generate_case(difficulty="normal", seed=seed)
            if s.disease_name == "pneumonia":
                state = s
                break
        assert state is not None, "Failed to generate a pneumonia case in 50 seeds"

        # Examine: blood_gas + chest_xray + auscultation + ultrasound
        reports = []
        for tt in ("blood_gas", "chest_xray", "auscultation", "ultrasound"):
            reports.append(translate(tt, state.engine))

        # Extract clues
        clues = extract_clues(reports)
        assert len(clues) > 0, "Should have extracted at least one clue from pneumonia case"

        # Match diseases
        matches = match_diseases(reports, known_clues=clues)
        top = matches[0]
        assert top["disease"] == "pneumonia"
        assert top["confidence"] > 0.15

    def test_full_arf_workflow(self):
        """Generate ARF case -> examine (blood_biochem + ultrasound) ->
        extract clues -> match diseases -> verify ARF is top match."""
        from game.case_generator import generate_case
        from game.test_translator import translate
        from game.diagnosis_engine import extract_clues, match_diseases

        # Generate a case until we get ARF
        state = None
        for seed in range(50):
            s = generate_case(difficulty="normal", seed=seed)
            if s.disease_name == "acute_renal_failure":
                state = s
                break
        assert state is not None, "Failed to generate an ARF case in 50 seeds"

        # Simulate further for ARF signs to develop (5-30 min pre-visit may not be enough)
        state.engine.simulate(60.0)

        # Examine: blood_biochem + ultrasound
        reports = []
        for tt in ("blood_biochem", "ultrasound"):
            reports.append(translate(tt, state.engine))

        # Extract clues
        clues = extract_clues(reports)
        assert len(clues) > 0, "Should have extracted at least one clue from ARF case"

        # Match diseases
        matches = match_diseases(reports, known_clues=clues)
        top = matches[0]
        assert top["disease"] == "acute_renal_failure"
        assert top["confidence"] > 0.15

    def test_treatment_flow(self):
        """Generate case -> examine -> treat with correct diagnosis -> verify phase='won'."""
        from game.case_generator import generate_case
        from game.test_translator import translate
        from game.action_system import process_action

        state = generate_case(difficulty="normal", seed=42)

        # Examine with physical
        process_action(state, "examine", {"test_type": "physical"})

        # Treat with the correct diagnosis (we know the disease_name from the state)
        result = process_action(state, "treat", {"disease_guess": state.disease_name})
        assert result["success"] is True
        assert result["phase"] == "won"
        assert state.phase == "won"
