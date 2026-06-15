"""
Clinical stage computation tests — Phase 1 (2026-06-14).

Tests the standalone compute_clinical_stage() function.
No integration with report engine yet (谨慎版).
"""
from __future__ import annotations

import pytest

from src.clinical_stage import compute_clinical_stage, list_supported_diseases


class TestComputeClinicalStagePneumonia:
    """Pneumonia: alveolar_exudate thresholds (0.3, 0.7)."""

    def test_mild(self):
        assert compute_clinical_stage("pneumonia", {"alveolar_exudate": 0.1}) == "mild"

    def test_mild_boundary(self):
        assert compute_clinical_stage("pneumonia", {"alveolar_exudate": 0.29}) == "mild"

    def test_moderate_low(self):
        assert compute_clinical_stage("pneumonia", {"alveolar_exudate": 0.3}) == "moderate"

    def test_moderate_mid(self):
        assert compute_clinical_stage("pneumonia", {"alveolar_exudate": 0.5}) == "moderate"

    def test_moderate_high(self):
        assert compute_clinical_stage("pneumonia", {"alveolar_exudate": 0.69}) == "moderate"

    def test_severe(self):
        assert compute_clinical_stage("pneumonia", {"alveolar_exudate": 0.7}) == "severe"

    def test_severe_high(self):
        assert compute_clinical_stage("pneumonia", {"alveolar_exudate": 0.95}) == "severe"


class TestComputeClinicalStageDCM:
    """DCM: cardiac_fibrosis thresholds (0.2, 0.5)."""

    def test_mild(self):
        assert compute_clinical_stage("dilated_cardiomyopathy", {"cardiac_fibrosis": 0.1}) == "mild"

    def test_moderate(self):
        assert compute_clinical_stage("dilated_cardiomyopathy", {"cardiac_fibrosis": 0.35}) == "moderate"

    def test_severe(self):
        assert compute_clinical_stage("dilated_cardiomyopathy", {"cardiac_fibrosis": 0.7}) == "severe"


class TestComputeClinicalStageARF:
    """ARF: nephron_damage thresholds (0.3, 0.7)."""

    def test_mild(self):
        assert compute_clinical_stage("acute_renal_failure", {"nephron_damage": 0.15}) == "mild"

    def test_moderate(self):
        assert compute_clinical_stage("acute_renal_failure", {"nephron_damage": 0.5}) == "moderate"

    def test_severe(self):
        assert compute_clinical_stage("acute_renal_failure", {"nephron_damage": 0.85}) == "severe"


class TestUnsupportedDisease:
    """Diseases without thresholds return 'unknown'."""

    def test_unknown_disease(self):
        assert compute_clinical_stage("sepsis", {"bacteremia": 0.5}) == "unknown"

    def test_empty_state_vars(self):
        assert compute_clinical_stage("pneumonia", {}) == "mild"  # default 0.0 < 0.3

    def test_missing_primary_var(self):
        # pneumonia expects alveolar_exudate, but we pass fever_state only
        assert compute_clinical_stage("pneumonia", {"fever_state": 0.9}) == "mild"


class TestListSupportedDiseases:
    """list_supported_diseases() returns the 3 configured diseases."""

    def test_returns_list(self):
        diseases = list_supported_diseases()
        assert isinstance(diseases, list)
        assert len(diseases) == 3

    def test_contains_expected(self):
        diseases = set(list_supported_diseases())
        assert diseases == {"pneumonia", "dilated_cardiomyopathy", "acute_renal_failure"}
