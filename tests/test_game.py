"""
Tests for the game logic layer: test_translator, diagnosis_engine, treatment,
action_system, case_generator, and data integrity.

Run with:
    cd /path/to/project && python -m pytest tests/test_game.py -v
"""

from __future__ import annotations

import json
import os
import sys

import pytest

# Path setup
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
_SRC = os.path.join(PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")


class FakeAdvancer:
    """Fast app-layer seam for action-system tests."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def advance_minutes(self, engine, minutes: float) -> None:
        self.calls.append(minutes)


# =============================================================================
#  FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def healthy_creature():
    """Healthy 20kg dog simulated 1 min."""
    from src.simulation import VirtualCreature
    e = VirtualCreature(body_weight_kg=20.0, dt=5.0)
    e.simulate(1.0)
    return e

@pytest.fixture(scope="session")
def pneumonia_creature():
    """20kg dog with moderate pneumonia simulated 20 min."""
    from src.simulation import VirtualCreature
    from src.diseases import create_disease
    e = VirtualCreature(body_weight_kg=20.0, dt=5.0)
    d = create_disease("pneumonia", severity="moderate")
    e.attach_disease(d)
    e.simulate(20.0)
    return e

@pytest.fixture(scope="session")
def arf_creature():
    """20kg dog with severe ARF simulated 60 min.

    session-scoped: computed once, shared across all tests in the session.
    Tests must not mutate the creature (treat as read-only).
    """
    from src.simulation import VirtualCreature
    from src.diseases import create_disease
    e = VirtualCreature(body_weight_kg=20.0, dt=5.0)
    d = create_disease("acute_renal_failure", severity="severe")
    e.attach_disease(d)
    e.simulate(60.0)
    return e


@pytest.fixture(scope="session")
def arf_creature_for_phase():
    """Lightweight ARF fixture for quick phase-contract checks."""
    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    e = VirtualCreature(body_weight_kg=20.0, dt=5.0)
    d = create_disease("acute_renal_failure", severity="moderate")
    e.attach_disease(d)
    e.simulate(5.0)
    return e


# =============================================================================
#  SECTION 1: Test Translator — _flag()
# =============================================================================

class TestFlag:
    """Classify raw values into low / normal / high / critical — parametrized from vitals_ranges.json."""

    @pytest.mark.parametrize("value,param,expected", [
        # pH
        (7.40, "pH", "normal"),
        (7.35, "pH", "normal"),
        (7.34, "pH", "low"),
        (7.45, "pH", "normal"),
        (7.46, "pH", "high"),
        (7.0,  "pH", "critical"),
        (6.9,  "pH", "critical"),
        # HR
        (90,   "HR", "normal"),
        (60,   "HR", "normal"),
        (120,  "HR", "normal"),
        (121,  "HR", "high"),
        (185,  "HR", "critical"),
        # RR
        (20,   "RR", "normal"),
        # MAP
        (100,  "MAP", "normal"),
        (45,   "MAP", "critical"),
        # Electrolytes
        (6.0,  "K",   "high"),
        (3.0,  "K",   "low"),
        (4.5,  "K",   "normal"),
        (160,  "Na",  "high"),
        (135,  "Na",  "low"),
        # Blood gas
        (70,   "PaO2", "low"),
        (90,   "PaO2", "normal"),
        (50,   "PaCO2", "high"),
        (92,   "SpO2", "low"),
        (80,   "SpO2", "critical"),
        (85,   "SpO2", "low"),
        (84,   "SpO2", "critical"),
        (86,   "SpO2", "low"),
        # Renal
        (50,   "BUN", "high"),
        (40,   "GFR", "low"),
        # Temperature
        (39.5, "Temp", "high"),
        (41.5, "Temp", "critical"),
        # Lactate
        (3.0,  "Lactate", "high"),
        (5.5,  "Lactate", "critical"),
    ])
    def test_flag(self, value, param, expected):
        from src.report_engine import flag as _flag
        assert _flag(value, param) == expected, f"_flag({value}, {param}) → {_flag(value, param)}, expected {expected}"


class TestResultEntry:
    """Test _result_entry() helper."""

    def test_basic(self):
        from src.report_engine import result_entry as _result_entry
        e = _result_entry("HR", 95.5, "normal")
        assert e["param"] == "HR"
        assert e["value"] == 95.5
        assert e["unit"] == "bpm"
        assert e["flag"] == "normal"
        assert e["normal_range"] == "60-120"

    def test_rounding(self):
        from src.report_engine import result_entry as _result_entry
        e = _result_entry("pH", 7.4567, "high")
        assert e["value"] == 7.46

    def test_range_string(self):
        from src.report_engine import result_entry as _result_entry
        e = _result_entry("K", 4.2, "normal")
        assert e["normal_range"] == "3.5-5.5"


class TestNormalRanges:
    """Validate vitals_ranges.json data integrity."""

    def test_all_ranges_valid(self):
        from src.vitals_config import get_vitals_config
        vc = get_vitals_config()
        for param in vc.params:
            lo, hi = vc.get_normal(param)
            assert lo < hi, f"{param}: {lo} >= {hi}"

    def test_expected_params(self):
        from src.vitals_config import get_vitals_config
        vc = get_vitals_config()
        expected = ["HR", "MAP", "CVP", "RR", "SpO2", "PaO2", "PaCO2",
                     "pH", "GFR", "BUN", "Na", "K", "Glu", "Lactate",
                     "HCT", "WBC", "PLT", "Temp"]
        for p in expected:
            assert p in vc.params, f"Missing: {p}"


class TestCriticalThresholds:
    """Validate critical thresholds in vitals_ranges.json."""

    def test_spo2_asymmetric(self):
        from src.vitals_config import get_vitals_config
        vc = get_vitals_config()
        crit = vc.get_critical("SpO2")
        assert crit is not None
        lo, hi = crit
        assert lo == 85
        assert hi == 100

    def test_ph_range(self):
        from src.vitals_config import get_vitals_config
        vc = get_vitals_config()
        crit = vc.get_critical("pH")
        assert crit is not None
        assert crit == (7.1, 7.6)


# =============================================================================
#  SECTION 2: translate() with real engine
# =============================================================================

@pytest.mark.slow
class TestTranslate:
    """Test translate() produces valid reports from a VirtualCreature."""

    def test_physical_structure(self, healthy_creature):
        from game.test_translator import translate
        r = translate("physical", healthy_creature)
        assert r["test_type"] == "physical"
        assert r["name"] == "体格检查"
        assert "results" in r
        assert "summary" in r
        assert "mental_status" in r
        assert "timestamp_s" in r

    def test_physical_has_hr_rr_temp(self, healthy_creature):
        from game.test_translator import translate
        r = translate("physical", healthy_creature)
        params = [e["param"] for e in r["results"]]
        assert "HR" in params
        assert "RR" in params
        assert "Temp" in params

    def test_physical_healthy_all_normal(self, healthy_creature):
        from game.test_translator import translate
        r = translate("physical", healthy_creature)
        for e in r["results"]:
            assert e["flag"] == "normal", f"{e['param']}={e['flag']}"

    def test_auscultation_structure(self, healthy_creature):
        from game.test_translator import translate
        r = translate("auscultation", healthy_creature)
        assert r["test_type"] == "auscultation"
        assert "summary" in r
        assert isinstance(r["results"], list)

    def test_inspection_structure(self, healthy_creature):
        from game.test_translator import translate
        r = translate("inspection", healthy_creature)
        assert r["test_type"] == "inspection"
        assert "summary" in r

    def test_blood_routine_structure(self, healthy_creature):
        from game.test_translator import translate
        r = translate("blood_routine", healthy_creature)
        params = [e["param"] for e in r["results"]]
        assert "HCT" in params
        assert "WBC" in params
        assert "PLT" in params

    def test_blood_biochem_structure(self, healthy_creature):
        from game.test_translator import translate
        r = translate("blood_biochem", healthy_creature)
        params = [e["param"] for e in r["results"]]
        assert "BUN" in params
        assert "Glu" in params
        assert "Na" in params
        assert "K" in params

    def test_blood_gas_structure(self, healthy_creature):
        from game.test_translator import translate
        r = translate("blood_gas", healthy_creature)
        params = [e["param"] for e in r["results"]]
        assert "PaO2" in params
        assert "PaCO2" in params
        assert "pH" in params
        assert "Lactate" in params
        assert "SpO2" in params

    def test_chest_xray_structure(self, healthy_creature):
        from game.test_translator import translate
        assert translate("chest_xray", healthy_creature)["test_type"] == "chest_xray"

    def test_ultrasound_structure(self, healthy_creature):
        from game.test_translator import translate
        assert translate("ultrasound", healthy_creature)["test_type"] == "ultrasound"

    def test_ct_structure(self, healthy_creature):
        from game.test_translator import translate
        assert translate("ct", healthy_creature)["test_type"] == "ct"

    def test_ecg_structure(self, healthy_creature):
        from game.test_translator import translate
        r = translate("ecg", healthy_creature)
        assert r["test_type"] == "ecg"
        params = [e["param"] for e in r["results"]]
        assert "HR" in params
        assert "节律" in params

    # --- Pneumonia-specific ---
    def test_pneumonia_xray_has_lung_ref(self, pneumonia_creature):
        from game.test_translator import translate
        r = translate("chest_xray", pneumonia_creature)
        assert "肺" in r["summary"]

    def test_pneumonia_auscultation_substantial(self, pneumonia_creature):
        from game.test_translator import translate
        r = translate("auscultation", pneumonia_creature)
        assert len(r["summary"]) > 10

    def test_pneumonia_wbc_elevated(self, pneumonia_creature):
        from game.test_translator import translate
        r = translate("blood_routine", pneumonia_creature)
        wbc = [e for e in r["results"] if e["param"] == "WBC"]
        assert len(wbc) > 0
        assert wbc[0]["value"] >= 12.0

    # --- ARF-specific ---
    def test_arf_has_bun_entry(self, arf_creature):
        from game.test_translator import translate
        r = translate("blood_biochem", arf_creature)
        bun = [e for e in r["results"] if e["param"] == "BUN"]
        assert len(bun) > 0

    def test_arf_ultrasound_substantial(self, arf_creature):
        from game.test_translator import translate
        r = translate("ultrasound", arf_creature)
        assert len(r["summary"]) > 10

    # --- Error handling ---
    def test_unknown_test_raises_value_error(self, healthy_creature):
        from game.test_translator import translate
        with pytest.raises(ValueError, match="未知检查类型"):
            translate("bogus", healthy_creature)

    def test_all_test_types_produce_valid_reports(self, healthy_creature):
        from src.exam_registry import get_exam_registry
        for tt in get_exam_registry().exam_types:
            from game.test_translator import translate
            r = translate(tt, healthy_creature)
            assert "test_type" in r
            assert "summary" in r


# =============================================================================
#  SECTION 3: Diagnosis Engine — extract_clues
# =============================================================================

class TestExtractClues:

    def test_blood_gas_clues(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "blood_gas", "results": [
            {"param": "PaO2", "flag": "low"},
            {"param": "PaCO2", "flag": "high"},
            {"param": "SpO2", "flag": "low"},
        ], "tags": ["PaO2_low", "PaCO2_high", "SpO2_low"]}]
        clues = extract_clues(reports)
        assert "PaO2_low" in clues
        assert "PaCO2_high" in clues
        assert "SpO2_low" in clues

    def test_physical_clues(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "physical", "results": [
            {"param": "HR", "flag": "high"},
            {"param": "RR", "flag": "high"},
            {"param": "Temp", "flag": "high"},
        ], "tags": ["hr_high", "rr_high", "temp_high"]}]
        clues = extract_clues(reports)
        assert "hr_high" in clues
        assert "rr_high" in clues
        assert "temp_high" in clues

    def test_auscultation_crackles(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "auscultation",
                     "summary": "双肺湿啰音（肺泡渗出）",
                     "results": ["双肺湿啰音（肺泡渗出）"],
                     "tags": ["crackles"]}]
        assert "crackles" in extract_clues(reports)

    def test_xray_exudate(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "chest_xray",
                     "summary": "肺野斑片状渗出影",
                     "results": ["肺野斑片状渗出影"],
                     "tags": ["lung_exudate_xray"]}]
        assert "lung_exudate_xray" in extract_clues(reports)

    def test_ct_exudate(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "ct",
                     "summary": "多发磨玻璃影伴实变",
                     "results": ["多发磨玻璃影伴实变"],
                     "tags": ["lung_exudate_ct"]}]
        assert "lung_exudate_ct" in extract_clues(reports)

    def test_ultrasound_lung(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "ultrasound",
                     "summary": "肺实质样变（B线增多）",
                     "results": ["肺实质样变（B线增多）"],
                     "tags": ["lung_exudate_us"]}]
        assert "lung_exudate_us" in extract_clues(reports)

    def test_ultrasound_kidney(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "ultrasound",
                     "summary": "肾血流灌注减少",
                     "results": ["肾血流灌注减少"],
                     "tags": ["gfr_low"]}]
        assert "gfr_low" in extract_clues(reports)

    def test_biochem_renal_clues(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "blood_biochem", "results": [
            {"param": "BUN", "flag": "high"},
            {"param": "K", "flag": "high"},
        ], "tags": ["bun_high", "potassium_high"]}]
        clues = extract_clues(reports)
        assert "bun_high" in clues
        assert "potassium_high" in clues

    def test_normal_results_no_clues(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "physical", "results": [
            {"param": "HR", "flag": "normal"},
            {"param": "RR", "flag": "normal"},
        ]}]
        assert extract_clues(reports) == []

    def test_deduplication(self):
        from game.diagnosis_engine import extract_clues
        reports = [
            {"test_type": "physical", "results": [{"param": "HR", "flag": "high"}],
             "tags": ["hr_high"]},
            {"test_type": "ecg", "results": [{"param": "HR", "flag": "high"}],
             "tags": ["hr_high"]},
        ]
        clues = extract_clues(reports)
        assert clues.count("hr_high") == 1

    def test_critical_flag_maps_low(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "blood_gas",
                     "results": [{"param": "PaO2", "flag": "critical"}],
                     "tags": ["PaO2_low"]}]
        assert "PaO2_low" in extract_clues(reports)

    def test_inspection_cyanosis(self):
        from game.diagnosis_engine import extract_clues
        reports = [{"test_type": "inspection",
                     "summary": "黏膜发绀（严重低氧）",
                     "tags": ["SpO2_low"]}]
        assert "SpO2_low" in extract_clues(reports)


# =============================================================================
#  SECTION 4: Diagnosis Engine — match_diseases
# =============================================================================

class TestMatchDiseases:

    def test_pneumonia_high_confidence(self):
        from game.diagnosis_engine import match_diseases
        clues = ["PaO2_low", "SpO2_low", "hr_high", "rr_high", "temp_high",
                 "wbc_high", "lung_exudate_xray", "crackles"]
        matches = match_diseases([], known_clues=clues)
        pn = next(m for m in matches if m["disease"] == "pneumonia")
        assert pn["confidence"] > 0.5
        assert pn["matched_count"] >= 8

    def test_arf_high_confidence(self):
        from game.diagnosis_engine import match_diseases
        clues = ["gfr_low", "bun_high", "potassium_high", "ph_low", "hr_low",
                 "cr_high", "usg_low", "upcr_high", "t_wave_tall_ecg", "qrs_wide_ecg"]
        matches = match_diseases([], known_clues=clues)
        arf = next(m for m in matches if m["disease"] == "acute_renal_failure")
        assert arf["confidence"] > 0.5
        assert arf["matched_count"] >= 5

    def test_sorted_by_confidence(self):
        from game.diagnosis_engine import match_diseases
        matches = match_diseases([], known_clues=["gfr_low", "bun_high",
                                                    "potassium_high", "ph_low"])
        for i in range(len(matches) - 1):
            assert matches[i]["confidence"] >= matches[i + 1]["confidence"]

    def test_no_clues_zero_confidence(self):
        from game.diagnosis_engine import match_diseases
        matches = match_diseases([], known_clues=[])
        for m in matches:
            assert m["confidence"] == 0.0
            assert m["matched_count"] == 0

    def test_missed_clues_populated(self):
        from game.diagnosis_engine import match_diseases
        matches = match_diseases([], known_clues=["PaO2_low", "SpO2_low"])
        pn = next(m for m in matches if m["disease"] == "pneumonia")
        assert len(pn["missed_clues"]) > 0

    def test_auto_extract_from_reports(self):
        from game.diagnosis_engine import match_diseases
        reports = [{"test_type": "blood_gas", "results": [
            {"param": "PaO2", "flag": "low"},
            {"param": "SpO2", "flag": "low"},
        ], "tags": ["PaO2_low", "SpO2_low"]}]
        matches = match_diseases(reports)
        pn = next(m for m in matches if m["disease"] == "pneumonia")
        assert pn["confidence"] > 0

    def test_all_diseases_returned(self):
        from game.diagnosis_engine import match_diseases
        matches = match_diseases([], known_clues=["hr_high"])
        diseases = [m["disease"] for m in matches]
        assert "pneumonia" in diseases
        assert "acute_renal_failure" in diseases


# =============================================================================
#  SECTION 5: Diagnosis Engine — helpers
# =============================================================================

class TestDiagnosisHelpers:

    def test_get_diagnosis_summary_format(self):
        from game.diagnosis_engine import get_diagnosis_summary
        matches = [
            {"disease": "pneumonia", "confidence": 0.75, "matched_count": 6, "total_clues": 8},
            {"disease": "acute_renal_failure", "confidence": 0.25, "matched_count": 1, "total_clues": 5},
        ]
        text = get_diagnosis_summary(matches)
        assert "pneumonia" in text
        assert "75%" in text

    def test_get_diagnosis_summary_empty(self):
        from game.diagnosis_engine import get_diagnosis_summary
        text = get_diagnosis_summary([])
        assert "暂无" in text

    def test_get_suggested_tests(self):
        from game.diagnosis_engine import get_suggested_tests
        matches = [
            {"disease": "pneumonia", "confidence": 0.6,
             "missed_clues": ["PaO2_low", "lung_exudate_xray"]},
        ]
        suggested = get_suggested_tests(matches)
        assert "blood_gas" in suggested
        assert "chest_xray" in suggested

    def test_get_clue_description_known(self):
        from game.diagnosis_engine import get_clue_description
        assert get_clue_description("PaO2_low") == "低氧血症"

    def test_get_clue_description_unknown(self):
        from game.diagnosis_engine import get_clue_description
        assert get_clue_description("nonexistent_clue") == "nonexistent_clue"

    def test_get_suggested_tests_dcm_cardiomegaly_xray(self):
        """DCM missed clue cardiomegaly_xray should suggest chest_xray."""
        from game.diagnosis_engine import get_suggested_tests
        matches = [
            {"disease": "dilated_cardiomyopathy", "confidence": 0.3,
             "missed_clues": ["cardiomegaly_xray"]},
        ]
        suggested = get_suggested_tests(matches)
        assert "chest_xray" in suggested

    def test_get_suggested_tests_dcm_cardiomegaly_us(self):
        """DCM missed clue cardiomegaly_us should suggest ultrasound."""
        from game.diagnosis_engine import get_suggested_tests
        matches = [
            {"disease": "dilated_cardiomyopathy", "confidence": 0.3,
             "missed_clues": ["cardiomegaly_us"]},
        ]
        suggested = get_suggested_tests(matches)
        assert "ultrasound" in suggested

    def test_get_suggested_tests_dcm_map_low(self):
        """DCM missed clue map_low should suggest physical."""
        from game.diagnosis_engine import get_suggested_tests
        matches = [
            {"disease": "dilated_cardiomyopathy", "confidence": 0.3,
             "missed_clues": ["map_low"]},
        ]
        suggested = get_suggested_tests(matches)
        assert "physical" in suggested

    def test_get_suggested_tests_dcm_cvp_high(self):
        """DCM missed clue cvp_high should suggest physical."""
        from game.diagnosis_engine import get_suggested_tests
        matches = [
            {"disease": "dilated_cardiomyopathy", "confidence": 0.3,
             "missed_clues": ["cvp_high"]},
        ]
        suggested = get_suggested_tests(matches)
        assert "physical" in suggested

    def test_get_suggested_tests_dcm_weak_pulse(self):
        """DCM missed clue weak_pulse should suggest physical."""
        from game.diagnosis_engine import get_suggested_tests
        matches = [
            {"disease": "dilated_cardiomyopathy", "confidence": 0.3,
             "missed_clues": ["weak_pulse"]},
        ]
        suggested = get_suggested_tests(matches)
        assert "physical" in suggested

    def test_get_suggested_tests_uses_clue_catalog(self, monkeypatch):
        """Suggested-test routing should come from the clue catalog."""
        import game.diagnosis_engine as diagnosis_engine

        monkeypatch.setitem(diagnosis_engine._CATALOG_SUGGESTED_TESTS, "PaO2_low", ["blood_gas_catalog"])

        matches = [
            {"disease": "pneumonia", "confidence": 0.6, "missed_clues": ["PaO2_low"]},
        ]
        suggested = diagnosis_engine.get_suggested_tests(matches)
        assert "blood_gas_catalog" in suggested


# =============================================================================
#  SECTION 6: Treatment
# =============================================================================

class TestTreatment:

    @pytest.fixture
    def pneumonia_state(self):
        from src.simulation import VirtualCreature
        from src.diseases import create_disease
        from game.action_system import GameState
        e = VirtualCreature(body_weight_kg=20.0, dt=2.0)
        d = create_disease("pneumonia", severity="moderate")
        e.attach_disease(d)
        e.simulate(2.0)
        return GameState(engine=e, disease_name="pneumonia")

    def test_correct_diagnosis(self, pneumonia_state):
        from game.treatment import apply_treatment
        result = apply_treatment(pneumonia_state, "pneumonia")
        assert result["correct"] is True
        assert result["phase"] == "won"
        assert "正确" in result["message"]

    def test_incorrect_diagnosis(self, pneumonia_state):
        from game.treatment import apply_treatment
        result = apply_treatment(pneumonia_state, "acute_renal_failure")
        assert result["correct"] is False
        assert result["phase"] == "playing"
        assert "误诊" in result["message"]

    def test_is_correct_treatment_true(self, pneumonia_state):
        from game.treatment import is_correct_treatment
        assert is_correct_treatment(pneumonia_state, "pneumonia") is True

    def test_is_correct_treatment_false(self, pneumonia_state):
        from game.treatment import is_correct_treatment
        assert is_correct_treatment(pneumonia_state, "acute_renal_failure") is False

    def test_treatment_result_has_all_keys(self, pneumonia_state):
        from game.treatment import apply_treatment
        result = apply_treatment(pneumonia_state, "pneumonia")
        for key in ("success", "correct", "actual_disease", "chosen_disease", "phase", "message"):
            assert key in result

    def test_actual_disease_in_result(self, pneumonia_state):
        from game.treatment import apply_treatment
        result = apply_treatment(pneumonia_state, "pneumonia")
        assert result["actual_disease"] == "pneumonia"
        assert result["chosen_disease"] == "pneumonia"


# =============================================================================
#  SECTION 6B: Drug-based treatment protocol (P1 收尾)
# =============================================================================


class TestDrugTreatmentProtocol:
    """
    apply_treatment() should administer the correct drug protocol
    for each disease instead of just matching disease name strings.
    """

    @pytest.fixture
    def dcm_state(self):
        """DCM (dilated cardiomyopathy) game state."""
        from src.simulation import VirtualCreature
        from src.diseases import create_disease
        from game.action_system import GameState
        from src.pharmacology import PharmacologyState
        e = VirtualCreature(body_weight_kg=35.0, dt=2.0)
        d = create_disease("dilated_cardiomyopathy", severity="moderate")
        e.attach_disease(d)
        e.simulate(2.0)
        e.pharmacology = PharmacologyState(weight_kg=35.0)
        return GameState(engine=e, disease_name="dilated_cardiomyopathy")

    @pytest.fixture
    def pneumonia_state_pharma(self):
        """Pneumonia game state with pharmacology attached."""
        from src.simulation import VirtualCreature
        from src.diseases import create_disease
        from game.action_system import GameState
        from src.pharmacology import PharmacologyState
        e = VirtualCreature(body_weight_kg=20.0, dt=2.0)
        d = create_disease("pneumonia", severity="moderate")
        e.attach_disease(d)
        e.simulate(2.0)
        e.pharmacology = PharmacologyState(weight_kg=20.0)
        return GameState(engine=e, disease_name="pneumonia")

    @pytest.fixture
    def arf_state(self):
        """Acute renal failure game state."""
        from src.simulation import VirtualCreature
        from src.diseases import create_disease
        from game.action_system import GameState
        from src.pharmacology import PharmacologyState
        e = VirtualCreature(body_weight_kg=30.0, dt=2.0)
        d = create_disease("acute_renal_failure", severity="moderate")
        e.attach_disease(d)
        e.simulate(2.0)
        e.pharmacology = PharmacologyState(weight_kg=30.0)
        return GameState(engine=e, disease_name="acute_renal_failure")

    def test_dcm_treatment_gives_pimobendan_and_furosemide(self, dcm_state):
        """Correct DCM treatment should administer pimobendan + furosemide."""
        from game.treatment import apply_treatment
        apply_treatment(dcm_state, "dilated_cardiomyopathy")
        drug_names = [d.name for d in dcm_state.engine.pharmacology.active_drugs]
        assert "pimobendan" in drug_names
        assert "furosemide" in drug_names

    def test_dcm_treatment_increases_contractility(self, dcm_state):
        """After DCM treatment, contractility_factor should increase."""
        from game.treatment import apply_treatment
        baseline_cf = dcm_state.engine.heart.contractility_factor
        apply_treatment(dcm_state, "dilated_cardiomyopathy")
        # After treatment + one step, contractility should be higher
        dcm_state.engine.step()
        assert dcm_state.engine.heart.contractility_factor > baseline_cf

    def test_pneumonia_treatment_gives_fluid_bolus(self, pneumonia_state_pharma):
        """Correct pneumonia treatment should administer fluid bolus."""
        from game.treatment import apply_treatment
        apply_treatment(pneumonia_state_pharma, "pneumonia")
        drug_names = [d.name for d in pneumonia_state_pharma.engine.pharmacology.active_drugs]
        assert "fluid_bolus" in drug_names

    def test_arf_treatment_gives_fluid_bolus(self, arf_state):
        """Correct ARF treatment should administer fluid bolus."""
        from game.treatment import apply_treatment
        apply_treatment(arf_state, "acute_renal_failure")
        drug_names = [d.name for d in arf_state.engine.pharmacology.active_drugs]
        assert "fluid_bolus" in drug_names

    def test_incorrect_diagnosis_no_drugs(self, dcm_state):
        """Incorrect diagnosis should NOT administer any drugs."""
        from game.treatment import apply_treatment
        apply_treatment(dcm_state, "pneumonia")
        assert len(dcm_state.engine.pharmacology.active_drugs) == 0

    def test_dcm_treatment_returns_correct_result(self, dcm_state):
        """apply_treatment with correct DCM diagnosis should return correct=True."""
        from game.treatment import apply_treatment
        result = apply_treatment(dcm_state, "dilated_cardiomyopathy")
        assert result["correct"] is True
        assert result["phase"] == "won"

    def test_supportive_care_still_works(self, dcm_state):
        """Supportive care (fluid bolus) should still work for any disease."""
        from game.treatment import apply_treatment
        baseline_bv = dcm_state.engine.heart.circulating_volume_ml
        result = apply_treatment(dcm_state, "supportive_care")
        assert result["success"] is True
        assert result["phase"] == "playing"
        dcm_state.engine.step()
        assert dcm_state.engine.heart.circulating_volume_ml > baseline_bv


# =============================================================================
#  SECTION 7: Action System — determine_phase & check_death
# =============================================================================

class TestDeterminePhase:

    def test_healthy_dog_is_stable(self, healthy_creature):
        from game.action_system import determine_phase
        phase = determine_phase(healthy_creature)
        assert phase == "stable"

    def test_arf_dog_phase_matches_fixture_contract(self, arf_creature_for_phase):
        """Moderate-ARF phase fixture should map to the current semantic contract."""
        from game.action_system import determine_phase
        phase = determine_phase(arf_creature_for_phase)
        assert phase == "moribund"

    def test_all_phases_valid_value(self):
        """determine_phase must return one of the four valid phases."""
        # We test with creatures; the set of valid returns is fixed
        valid = {"stable", "worsening", "critical", "moribund"}
        from game.action_system import determine_phase
        from src.simulation import VirtualCreature
        e = VirtualCreature(body_weight_kg=20.0)
        e.simulate(1.0)
        assert determine_phase(e) in valid


class TestCheckDeath:

    def test_moribund_starts_timer(self):
        from game.action_system import GameState, check_death
        from src.simulation import VirtualCreature
        e = VirtualCreature(body_weight_kg=20.0)
        state = GameState(engine=e, disease_name="pneumonia")
        state = check_death(state, "moribund")
        assert state.death_timer == 3

    def test_moribund_decrements_timer(self):
        from game.action_system import GameState, check_death
        from src.simulation import VirtualCreature
        e = VirtualCreature(body_weight_kg=20.0)
        state = GameState(engine=e, disease_name="pneumonia")
        state = check_death(state, "moribund")
        state = check_death(state, "moribund")
        assert state.death_timer == 2

    def test_timer_zero_triggers_loss(self):
        """First call starts timer at MORIBUND_ACTIONS_REMAINING (3).
        Each subsequent call decrements. After 4 total calls (set + 3 decrements),
        the timer reaches 0 and phase becomes 'lost'."""
        from game.action_system import GameState, check_death
        from src.simulation import VirtualCreature
        e = VirtualCreature(body_weight_kg=20.0)
        state = GameState(engine=e, disease_name="pneumonia")
        # Start timer (sets to 3), then decrement 3 times: 3->2->1->0
        state = check_death(state, "moribund")  # timer = 3
        state = check_death(state, "moribund")  # timer = 2
        state = check_death(state, "moribund")  # timer = 1
        state = check_death(state, "moribund")  # timer = 0 -> lost
        assert state.death_timer <= 0
        assert state.phase == "lost"

    def test_recovery_clears_timer(self):
        from game.action_system import GameState, check_death
        from src.simulation import VirtualCreature
        e = VirtualCreature(body_weight_kg=20.0)
        state = GameState(engine=e, disease_name="pneumonia")
        state = check_death(state, "moribund")
        state = check_death(state, "stable")
        assert state.death_timer is None

    def test_non_moribund_preserves_none_timer(self):
        from game.action_system import GameState, check_death
        from src.simulation import VirtualCreature
        e = VirtualCreature(body_weight_kg=20.0)
        state = GameState(engine=e, disease_name="pneumonia")
        state = check_death(state, "worsening")
        assert state.death_timer is None
        assert state.phase == "playing"


class TestProcessAction:

    @pytest.fixture
    def runtime(self):
        from game.runtime import GameRuntime

        advancer = FakeAdvancer()
        return GameRuntime(advancer=advancer), advancer

    def test_examine_action(self, runtime):
        from game.action_system import GameState, process_action
        from src.simulation import VirtualCreature

        game_runtime, advancer = runtime
        state = GameState(engine=VirtualCreature(body_weight_kg=20.0), disease_name="pneumonia")
        result = process_action(state, "examine", {"test_type": "physical"}, runtime=game_runtime)
        assert result["success"] is True
        assert result["result"] is not None
        assert result["result"]["test_type"] == "physical"
        assert state.time_elapsed_min == 5  # physical = 5 min
        assert advancer.calls == [5.0]

    def test_treat_correct_action(self, runtime):
        from game.action_system import GameState, process_action
        from src.simulation import VirtualCreature

        game_runtime, advancer = runtime
        state = GameState(engine=VirtualCreature(body_weight_kg=20.0), disease_name="pneumonia")
        result = process_action(state, "treat", {"disease_guess": "pneumonia"}, runtime=game_runtime)
        assert result["success"] is True
        assert result["phase"] == "won"
        assert advancer.calls == [5.0]

    def test_treat_wrong_action(self, runtime):
        from game.action_system import GameState, process_action
        from src.simulation import VirtualCreature

        game_runtime, advancer = runtime
        state = GameState(engine=VirtualCreature(body_weight_kg=20.0), disease_name="pneumonia")
        result = process_action(state, "treat", {"disease_guess": "acute_renal_failure"}, runtime=game_runtime)
        assert result["success"] is True
        assert result["phase"] == "playing"
        assert advancer.calls == [5.0]

    def test_wait_action(self, runtime):
        from game.action_system import GameState, process_action
        from src.simulation import VirtualCreature

        game_runtime, advancer = runtime
        state = GameState(engine=VirtualCreature(body_weight_kg=20.0), disease_name="pneumonia")
        result = process_action(state, "wait", runtime=game_runtime)
        assert result["success"] is True
        assert state.time_elapsed_min == 10  # wait = 10 min
        assert advancer.calls == [10.0]

    def test_invalid_action_type(self):
        from game.action_system import GameState, process_action
        from src.simulation import VirtualCreature

        state = GameState(engine=VirtualCreature(body_weight_kg=20.0), disease_name="pneumonia")
        result = process_action(state, "fly")
        assert result["success"] is False

    def test_action_after_win_blocked(self):
        from game.action_system import GameState, process_action
        from src.simulation import VirtualCreature

        state = GameState(engine=VirtualCreature(body_weight_kg=20.0), disease_name="pneumonia")
        state.phase = "won"
        result = process_action(state, "examine", {"test_type": "physical"})
        assert result["success"] is False
        assert result["phase"] == "won"

    def test_action_after_loss_blocked(self):
        from game.action_system import GameState, process_action
        from src.simulation import VirtualCreature

        state = GameState(engine=VirtualCreature(body_weight_kg=20.0), disease_name="pneumonia")
        state.phase = "lost"
        result = process_action(state, "examine", {"test_type": "physical"})
        assert result["success"] is False
        assert result["phase"] == "lost"

    def test_engine_summary_in_result(self, runtime):
        from game.action_system import GameState, process_action
        from src.simulation import VirtualCreature

        game_runtime, advancer = runtime
        state = GameState(engine=VirtualCreature(body_weight_kg=20.0), disease_name="pneumonia")
        result = process_action(state, "examine", {"test_type": "physical"}, runtime=game_runtime)
        summary = result["engine_summary"]
        assert "HR_bpm" in summary
        assert "MAP_mmHg" in summary
        assert "SpO2" in summary
        assert "pH" in summary
        assert advancer.calls == [5.0]

    def test_medical_phase_in_result(self, runtime):
        from game.action_system import GameState, process_action
        from src.simulation import VirtualCreature

        game_runtime, advancer = runtime
        state = GameState(engine=VirtualCreature(body_weight_kg=20.0), disease_name="pneumonia")
        result = process_action(state, "wait", runtime=game_runtime)
        assert result["medical_phase"] in ("stable", "worsening", "critical", "moribund")
        assert advancer.calls == [10.0]


class TestComputeDO2:
    """Test DO2 computation."""

    def test_healthy_dog_do2_near_one(self, healthy_creature):
        from game.action_system import compute_DO2
        do2 = compute_DO2(healthy_creature)
        assert 0.5 <= do2 <= 1.0

    def test_do2_clamped_to_valid_range(self, healthy_creature):
        from game.action_system import compute_DO2
        do2 = compute_DO2(healthy_creature)
        assert 0.0 <= do2 <= 1.0


# =============================================================================
#  SECTION 8: GameState dataclass
# =============================================================================

class TestGameState:

    def test_default_values(self):
        from game.action_system import GameState
        from src.simulation import VirtualCreature
        e = VirtualCreature(body_weight_kg=20.0)
        s = GameState(engine=e, disease_name="pneumonia")
        assert s.time_elapsed_min == 0
        assert s.phase == "playing"
        assert s.death_timer is None
        assert s.reports == []
        assert s.treatment_applied is None


# =============================================================================
#  SECTION 9: Disease Modules — basic properties
# =============================================================================

class TestDiseaseModules:

    def test_pneumonia_exists(self):
        from src.diseases import list_diseases
        assert "pneumonia" in list_diseases()

    def test_arf_exists(self):
        from src.diseases import list_diseases
        assert "acute_renal_failure" in list_diseases()

    def test_pneumonia_create_default(self):
        from src.diseases import create_disease
        d = create_disease("pneumonia")
        assert d.name == "pneumonia"
        assert d.active is False

    def test_arf_create_default(self):
        from src.diseases import create_disease
        d = create_disease("acute_renal_failure")
        assert d.name == "acute_renal_failure"
        assert d.active is False

    def test_pneumonia_severity_presets(self):
        from src.diseases import create_disease
        for sev in ("mild", "moderate", "severe"):
            d = create_disease("pneumonia", severity=sev)
            assert d.active is False

    def test_arf_severity_presets(self):
        from src.diseases import create_disease
        for sev in ("mild", "moderate", "severe"):
            d = create_disease("acute_renal_failure", severity=sev)
            assert d.active is False

    def test_pneumonia_state_variables(self):
        from src.diseases import create_disease
        d = create_disease("pneumonia")
        assert hasattr(d, "alveolar_exudate")
        assert hasattr(d, "bacterial_load")
        assert hasattr(d, "fever_state")
        assert hasattr(d, "tissue_hypoxia")

    def test_arf_state_variables(self):
        from src.diseases import create_disease
        d = create_disease("acute_renal_failure")
        assert hasattr(d, "nephron_damage")
        assert hasattr(d, "gfr_decline")
        assert hasattr(d, "potassium_shift")
        assert hasattr(d, "metabolic_acidosis")

    def test_unknown_disease_raises(self):
        from src.diseases import create_disease
        with pytest.raises(KeyError):
            create_disease("nonexistent_disease")

    def test_pneumonia_activate(self):
        from src.diseases import create_disease
        d = create_disease("pneumonia")
        d.activate(100.0)
        assert d.active is True
        assert d.activated_at_s == 100.0

    def test_pneumonia_deactivate(self):
        from src.diseases import create_disease
        d = create_disease("pneumonia")
        d.activate(100.0)
        d.deactivate()
        assert d.active is False
        assert d.activated_at_s == 0.0

    def test_register_unknown_raises(self):
        from src.diseases import register_disease
        class FakeDisease:
            pass
        with pytest.raises(TypeError):
            register_disease("fake", FakeDisease)


# =============================================================================
#  SECTION 10: Full Round-Trip — translate -> clues -> match
# =============================================================================

@pytest.mark.slow
class TestRoundTrip:

    def test_pneumonia_round_trip(self, pneumonia_creature):
        """translate -> clues -> match should identify pneumonia."""
        from game.test_translator import translate
        from game.diagnosis_engine import extract_clues, match_diseases

        reports = []
        for tt in ("physical", "blood_gas", "auscultation", "chest_xray", "ultrasound"):
            reports.append(translate(tt, pneumonia_creature))

        clues = extract_clues(reports)
        matches = match_diseases(reports, known_clues=clues)
        matches.sort(key=lambda m: m["confidence"], reverse=True)
        top = matches[0]
        assert top["disease"] == "pneumonia"
        assert top["confidence"] > 0.2

    def test_arf_round_trip(self, arf_creature):
        """translate -> clues -> match should identify ARF."""
        from game.test_translator import translate
        from game.diagnosis_engine import extract_clues, match_diseases

        reports = []
        for tt in ("physical", "blood_biochem", "blood_gas", "ultrasound"):
            reports.append(translate(tt, arf_creature))

        clues = extract_clues(reports)
        matches = match_diseases(reports, known_clues=clues)
        matches.sort(key=lambda m: m["confidence"], reverse=True)
        top = matches[0]
        assert top["disease"] == "acute_renal_failure"
        assert top["confidence"] > 0.2

    def test_healthy_no_clues(self, healthy_creature):
        """Healthy dog should produce no diagnostic clues."""
        from game.test_translator import translate
        from game.diagnosis_engine import extract_clues, match_diseases

        report = translate("physical", healthy_creature)
        clues = extract_clues([report])
        assert clues == []


# =============================================================================
#  SECTION 11: Data Integrity — JSON files
# =============================================================================

class TestDataCases:
    """Validate data/cases.json."""

    @pytest.fixture
    def cases_data(self):
        path = os.path.join(DATA_DIR, "cases.json")
        if not os.path.exists(path):
            pytest.skip("data/cases.json not found")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_cases_has_cases_key(self, cases_data):
        assert "cases" in cases_data
        assert isinstance(cases_data["cases"], list)
        assert len(cases_data["cases"]) > 0

    def test_case_required_fields(self, cases_data):
        required = ["id", "title", "difficulty", "animal", "chief_complaint",
                     "history", "disease"]
        for case in cases_data["cases"]:
            for field in required:
                assert field in case, f"Case {case.get('id', '?')} missing field: {field}"

    def test_case_animal_fields(self, cases_data):
        for case in cases_data["cases"]:
            animal = case["animal"]
            for field in ("species", "breed", "name", "age", "weight_kg", "sex"):
                assert field in animal, f"Case {case['id']} animal missing: {field}"

    def test_case_difficulty_valid(self, cases_data):
        for case in cases_data["cases"]:
            assert case["difficulty"] in (1, 2, 3)

    def test_case_disease_references_valid(self, cases_data):
        """Each case disease must be in known treatment keys or disease registry."""
        from src.diseases import list_diseases
        known_diseases = set(list_diseases())
        for case in cases_data["cases"]:
            assert case["disease"] in known_diseases, \
                f"Case {case['id']} has unknown disease: {case['disease']}"

    def test_case_ids_unique(self, cases_data):
        ids = [c["id"] for c in cases_data["cases"]]
        assert len(ids) == len(set(ids))


class TestDataExaminations:
    """Validate data/examinations.json."""

    @pytest.fixture
    def exams_data(self):
        path = os.path.join(DATA_DIR, "examinations.json")
        if not os.path.exists(path):
            pytest.skip("data/examinations.json not found")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_exams_not_empty(self, exams_data):
        assert len(exams_data) > 0

    def test_exam_required_fields(self, exams_data):
        for key, exam in exams_data.items():
            for field in ("name", "category", "tier", "time_cost_min", "description"):
                assert field in exam, f"Exam {key} missing: {field}"

    def test_exam_time_cost_positive(self, exams_data):
        for key, exam in exams_data.items():
            assert exam["time_cost_min"] > 0, f"Exam {key}: non-positive time_cost_min"

    def test_exam_latency_nonnegative(self, exams_data):
        for key, exam in exams_data.items():
            assert exam["latency_min"] >= 0, f"Exam {key}: negative latency_min"

    def test_exam_name_present(self, exams_data):
        for key, exam in exams_data.items():
            assert exam["name"], f"Exam {key}: empty name"

    def test_exam_test_types_match_translator(self, exams_data):
        """All exam keys must be valid exam_registry types."""
        from src.exam_registry import get_exam_registry
        reg = get_exam_registry()
        for key in exams_data:
            assert key in reg.exam_types, f"Exam key '{key}' not in exam_registry"


class TestDataTreatments:
    """Validate data/treatments.json."""

    @pytest.fixture
    def treats_data(self):
        path = os.path.join(DATA_DIR, "treatments.json")
        if not os.path.exists(path):
            pytest.skip("data/treatments.json not found")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_treatments_not_empty(self, treats_data):
        assert len(treats_data) > 0

    def test_treatment_required_fields(self, treats_data):
        for key, treat in treats_data.items():
            for field in ("name", "description", "correct_for", "on_apply"):
                assert field in treat, f"Treatment {key} missing: {field}"

    def test_treatment_on_apply_structure(self, treats_data):
        for key, treat in treats_data.items():
            oa = treat["on_apply"]
            assert "type" in oa, f"Treatment {key} on_apply missing: type"
            assert "params" in oa, f"Treatment {key} on_apply missing: params"

    def test_treatment_correct_for_valid_or_null(self, treats_data):
        """correct_for must be None or a registered disease name."""
        from src.diseases import list_diseases
        known = set(list_diseases())
        for key, treat in treats_data.items():
            cf = treat["correct_for"]
            if cf is not None:
                assert cf in known, f"Treatment {key}: correct_for='{cf}' not a known disease"


class TestCrossReference:
    """Cross-reference: diseases in cases/treatments should match registry."""

    def test_treatments_cover_case_diseases(self):
        """Every disease used in cases.json should have at least one matching treatment."""
        cases_path = os.path.join(DATA_DIR, "cases.json")
        treats_path = os.path.join(DATA_DIR, "treatments.json")
        if not os.path.exists(cases_path) or not os.path.exists(treats_path):
            pytest.skip("Required JSON files not found")

        with open(cases_path, "r", encoding="utf-8") as f:
            case_diseases = set(c["disease"] for c in json.load(f)["cases"])
        with open(treats_path, "r", encoding="utf-8") as f:
            treat = json.load(f)
        treated_diseases = set(t["correct_for"] for t in treat.values() if t["correct_for"])

        for d in case_diseases:
            assert d in treated_diseases, \
                f"Disease '{d}' in cases.json has no matching treatment in treatments.json"
