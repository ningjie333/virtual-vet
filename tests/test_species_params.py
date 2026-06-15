"""
Species-aware parameter tests — Q3 (2026-06-14).

Verifies the new species-aware lookup helpers and constants added to
src/parameters.py as part of Q3 (species parameter completeness).

Tests:
  - species_hr() / species_rr() / species_paco2() / fever_threshold_c()
  - total_blood_volume_ml() with species parameter
  - Constants exist and have expected values
"""
from __future__ import annotations

import pytest

from src.parameters import (
    BLOOD_VOLUME_ML_KG_CANINE,
    BLOOD_VOLUME_ML_KG_FELINE,
    BLOOD_VOLUME_ML_KG_EQUINE,
    FEVER_THRESHOLD_C_CANINE,
    FEVER_THRESHOLD_C_FELINE,
    FEVER_THRESHOLD_C_EQUINE,
    HEART_RATE_REST_BPM_CANINE,
    HEART_RATE_REST_BPM_FELINE,
    HEART_RATE_REST_BPM_EQUINE,
    HEART_RATE_STRESS_BPM_CANINE,
    HEART_RATE_STRESS_BPM_FELINE,
    HEART_RATE_STRESS_BPM_EQUINE,
    RESPIRATORY_RATE_REST_CANINE,
    RESPIRATORY_RATE_REST_FELINE,
    RESPIRATORY_RATE_REST_EQUINE,
    RESPIRATORY_RATE_STRESS_CANINE,
    RESPIRATORY_RATE_STRESS_FELINE,
    RESPIRATORY_RATE_STRESS_EQUINE,
    ARTERIAL_PCO2_NORMAL_CANINE,
    ARTERIAL_PCO2_NORMAL_FELINE,
    ARTERIAL_PCO2_NORMAL_EQUINE,
    fever_threshold_c,
    species_hr,
    species_paco2,
    species_rr,
    total_blood_volume_ml,
)


class TestSpeciesConstants:
    """Q3 constants exist and have physiologically plausible values."""

    def test_blood_volume_canine(self):
        assert BLOOD_VOLUME_ML_KG_CANINE == 86.0

    def test_blood_volume_feline(self):
        assert BLOOD_VOLUME_ML_KG_FELINE == 55.0

    def test_blood_volume_equine(self):
        assert BLOOD_VOLUME_ML_KG_EQUINE == 76.0

    def test_fever_threshold_canine(self):
        assert FEVER_THRESHOLD_C_CANINE == 39.2

    def test_fever_threshold_feline(self):
        assert FEVER_THRESHOLD_C_FELINE == 39.5

    def test_fever_threshold_equine(self):
        assert FEVER_THRESHOLD_C_EQUINE == 38.5

    def test_hr_rest_canine_explicit(self):
        assert HEART_RATE_REST_BPM_CANINE == 85

    def test_hr_stress_canine_explicit(self):
        assert HEART_RATE_STRESS_BPM_CANINE == 180

    def test_rr_rest_canine_explicit(self):
        assert RESPIRATORY_RATE_REST_CANINE == 18

    def test_rr_stress_canine_explicit(self):
        assert RESPIRATORY_RATE_STRESS_CANINE == 40

    def test_rr_stress_equine(self):
        assert RESPIRATORY_RATE_STRESS_EQUINE == 60

    def test_paco2_canine_explicit(self):
        assert ARTERIAL_PCO2_NORMAL_CANINE == 40.0


class TestSpeciesHr:
    """species_hr() 3-way lookup."""

    def test_canine_rest(self):
        assert species_hr("canine") == 85

    def test_feline_rest(self):
        assert species_hr("feline") == 150

    def test_equine_rest(self):
        assert species_hr("equine") == 35

    def test_canine_stress(self):
        assert species_hr("canine", stress=True) == 180

    def test_feline_stress(self):
        assert species_hr("feline", stress=True) == 250

    def test_equine_stress(self):
        assert species_hr("equine", stress=True) == 70

    def test_default_is_canine(self):
        assert species_hr() == 85


class TestSpeciesRr:
    """species_rr() 3-way lookup."""

    def test_canine_rest(self):
        assert species_rr("canine") == 18

    def test_feline_rest(self):
        assert species_rr("feline") == 25

    def test_equine_rest(self):
        assert species_rr("equine") == 12

    def test_canine_stress(self):
        assert species_rr("canine", stress=True) == 40

    def test_feline_stress(self):
        assert species_rr("feline", stress=True) == 50

    def test_equine_stress(self):
        assert species_rr("equine", stress=True) == 60


class TestSpeciesPaco2:
    """species_paco2() 3-way lookup."""

    def test_canine(self):
        assert species_paco2("canine") == 40.0

    def test_feline(self):
        assert species_paco2("feline") == 35.0

    def test_equine(self):
        assert species_paco2("equine") == 42.0


class TestFeverThresholdC:
    """fever_threshold_c() 3-way lookup."""

    def test_canine(self):
        assert fever_threshold_c("canine") == 39.2

    def test_feline(self):
        assert fever_threshold_c("feline") == 39.5

    def test_equine(self):
        assert fever_threshold_c("equine") == 38.5


class TestTotalBloodVolumeMl:
    """total_blood_volume_ml() species-aware upgrade."""

    def test_canine_default(self):
        assert total_blood_volume_ml(20.0) == 86.0 * 20.0

    def test_canine_explicit(self):
        assert total_blood_volume_ml(20.0, "canine") == 86.0 * 20.0

    def test_feline(self):
        assert total_blood_volume_ml(4.0, "feline") == 55.0 * 4.0

    def test_equine(self):
        assert total_blood_volume_ml(500.0, "equine") == 76.0 * 500.0
