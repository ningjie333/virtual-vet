"""
Multi-disease diagnosis API tests — 方向三 continuation (2026-06-14).

Verifies that the diagnosis engine + game API correctly surface multiple
diseases when a comorbidity case (case_020 / case_021) is active.

Scope:
  - /api/hint shows BOTH diseases when both have confidence > 0.30
  - /api/diagnosis returns target_diseases = full disease list
  - match_diseases() engine itself naturally surfaces both (no engine changes
    needed — it was already returning all diseases sorted by confidence)

Out of scope (separate tasks):
  - Treatment for multi-disease (treatments.json has per-disease protocols;
    for first cut, treating any one disease in the list counts as progress)
  - Win/loss conditions with partial correct diagnosis
  - Per-disease feedback after treatment
"""
from __future__ import annotations

import json

import pytest

from game.diagnosis_engine import match_diseases


# ─── Engine-level tests (no Flask, just the algorithm) ─────────────────────


class TestMatchDiseasesReturnsMultiple:
    """match_diseases() engine: verifies it surfaces BOTH diseases when
    reports contain clues for multiple diseases.
    """

    @staticmethod
    def _make_report(tags: list[str]) -> dict:
        return {"tags": tags, "findings": [], "params": {}}

    def test_dcm_and_pneumonia_clues_both_appear_in_top(self):
        """Mixed DCM + pneumonia clues → both should be in top 2 matches."""
        # DCM-specific clues: cardiomegaly_xray, weak_pulse
        # Pneumonia-specific clues: PaO2_low, SpO2_low, crackles, lung_exudate_xray
        # Shared clues: hr_high, lung_exudate_us
        reports = [
            self._make_report(["cardiomegaly_xray", "weak_pulse", "hr_high"]),
            self._make_report(["PaO2_low", "SpO2_low", "lung_exudate_xray", "crackles",
                               "lung_exudate_us", "rr_high", "temp_high"]),
        ]
        matches = match_diseases(reports)
        top_2 = {m["disease"] for m in matches[:2]}
        assert "dilated_cardiomyopathy" in top_2, (
            f"DCM should be in top 2, got {[(m['disease'], m['confidence']) for m in matches[:2]]}"
        )
        assert "pneumonia" in top_2, (
            f"Pneumonia should be in top 2, got {[(m['disease'], m['confidence']) for m in matches[:2]]}"
        )

    def test_single_disease_clues_dont_trigger_multi(self):
        """Pure pneumonia clues should NOT cause DCM to surface as notable
        (confidence should be low, not in top by significant margin)."""
        reports = [
            self._make_report(["PaO2_low", "SpO2_low", "lung_exudate_xray",
                               "crackles", "temp_high", "wbc_high"]),
        ]
        matches = match_diseases(reports)
        # Pneumonia is top, DCM is far below
        assert matches[0]["disease"] == "pneumonia"
        # DCM confidence should be MUCH lower (only hr_high from shared)
        dcm = next(m for m in matches if m["disease"] == "dilated_cardiomyopathy")
        assert dcm["confidence"] < 0.4, (
            f"Pure pneumonia clues shouldn't strongly trigger DCM (got {dcm['confidence']})"
        )


# ─── Game-layer API tests (Flask test client + test_interface fixtures) ─


# Re-use the same fixtures as test_interface.py
pytest_plugins = ["tests.test_interface"]


@pytest.fixture
def app_module(request):
    """Import gui_app + a fresh test client. Mirrors the fixture in test_interface.py."""
    import sys
    sys.path.insert(0, ".")
    import gui_app as gui
    return gui


class TestHintShowsMultipleDiseases:
    """/api/hint 在多病 case 下应展示 top 2+（高于 0.30 置信度）"""

    def test_comorbidity_case_020_hint_lists_both_diseases(
        self, app_module, client,  # fixtures from tests/test_interface.py
    ):
        """case_020 (DCM + pneumonia): after relevant examinations,
        /api/hint should mention BOTH DCM and 肺炎 in the candidate list.

        We directly inject clue-rich reports into state to bypass the test
        factory's partial simulation. Engine-level test (above) already
        proves the matching algorithm works for multi-disease cases.
        """
        # Start comorbidity case
        resp = client.post(
            "/api/new-game",
            data=json.dumps({"case_id": "case_020"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

        # Inject reports with clues for BOTH diseases (bypass fast-factory)
        import gui_app as gui
        state = gui._game_sessions["case_020"]
        state.reports = [
            {"tags": ["cardiomegaly_xray", "weak_pulse", "hr_high", "qrs_wide"],
             "findings": [], "params": {}},
            {"tags": ["PaO2_low", "SpO2_low", "lung_exudate_xray", "crackles",
                      "lung_exudate_us", "rr_high", "temp_high", "wbc_high"],
             "findings": [], "params": {}},
        ]

        hint_resp = client.get("/api/hint?session_id=case_020")
        assert hint_resp.status_code == 200
        data = json.loads(hint_resp.data)
        assert "hint" in data
        hint_text = data["hint"]
        # Multi-disease format includes "可能的疾病（按置信度）"
        assert "可能的疾病" in hint_text, (
            f"comorbidity case should use multi-disease hint format: {hint_text[:200]}"
        )
        # Both diseases should be mentioned
        assert "心肌病" in hint_text or "扩张型" in hint_text, (
            f"DCM should appear in hint: {hint_text[:200]}"
        )
        assert "肺炎" in hint_text, (
            f"Pneumonia should appear in hint: {hint_text[:200]}"
        )

    def test_single_disease_case_001_hint_shows_only_pneumonia(
        self, app_module, client,
    ):
        """Single-disease case (case_001 pneumonia) should NOT change format
        — still show top 1 (backward compat with old UI).
        """
        resp = client.post(
            "/api/new-game",
            data=json.dumps({"case_id": "case_001"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        for tt in ("physical", "chest_xray", "blood_gas", "auscultation"):
            client.post(
                "/api/examine",
                data=json.dumps({"session_id": "case_001", "test_type": tt}),
                content_type="application/json",
            )
        hint_resp = client.get("/api/hint?session_id=case_001")
        data = json.loads(hint_resp.data)
        hint_text = data["hint"]
        # Single-disease: old format "最可能的疾病：肺炎（X%）"
        assert "最可能的疾病" in hint_text, (
            f"Single-disease case should use old '最可能的疾病' format: {hint_text[:200]}"
        )
        assert "肺炎" in hint_text


class TestDiagnosisReturnsTargetDiseases:
    """/api/diagnosis 应返回 target_diseases 字段（client 用）"""

    def test_comorbidity_case_020_target_diseases_includes_both(
        self, app_module, client,
    ):
        """case_020 (DCM + pneumonia): target_diseases = ['dilated_cardiomyopathy', 'pneumonia']"""
        client.post(
            "/api/new-game",
            data=json.dumps({"case_id": "case_020"}),
            content_type="application/json",
        )
        resp = client.get("/api/diagnosis?session_id=case_020")
        data = json.loads(resp.data)
        assert "target_diseases" in data, "api_diagnosis must include target_diseases (方向三 2026-06-14)"
        assert set(data["target_diseases"]) == {"dilated_cardiomyopathy", "pneumonia"}, (
            f"case_020 target_diseases should be both: {data['target_diseases']}"
        )

    def test_single_disease_case_001_target_diseases_has_one(
        self, app_module, client,
    ):
        """Single-disease case: target_diseases = ['pneumonia'] (just the primary)."""
        client.post(
            "/api/new-game",
            data=json.dumps({"case_id": "case_001"}),
            content_type="application/json",
        )
        resp = client.get("/api/diagnosis?session_id=case_001")
        data = json.loads(resp.data)
        assert data["target_diseases"] == ["pneumonia"]
