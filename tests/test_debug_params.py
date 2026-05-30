"""
Tests for Debug Params — 生理参数调试器后端逻辑。
"""

import pytest
from pathlib import Path
import json


# ── 品种数据加载测试 ─────────────────────────────────────────────────────────

class TestBreedDataLoading:
    def test_breed_standards_json_exists(self):
        path = Path(__file__).parent.parent / "data" / "breed_standards.json"
        assert path.exists(), "breed_standards.json not found"

    def test_breed_standards_json_valid(self):
        path = Path(__file__).parent.parent / "data" / "breed_standards.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "canine" in data
        assert "feline" in data
        assert "equine" in data

    def test_canine_has_labrador(self):
        path = Path(__file__).parent.parent / "data" / "breed_standards.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "labrador" in data["canine"]
        assert data["canine"]["labrador"]["display"] == "拉布拉多"


# ── get_available_species 测试 ──────────────────────────────────────────────

class TestGetAvailableSpecies:
    def test_returns_species_without_metadata(self):
        from src.debug_params import get_available_species
        result = get_available_species()
        assert "_schema" not in result
        assert "_comment" not in result
        assert "canine" in result
        assert "feline" in result

    def test_canine_has_breeds(self):
        from src.debug_params import get_available_species
        result = get_available_species()
        assert "labrador" in result["canine"]
        assert "golden_retriever" in result["canine"]
        assert "chihuahua" in result["canine"]


# ── get_breed_weight 测试 ──────────────────────────────────────────────────

class TestGetBreedWeight:
    def test_returns_default_weight(self):
        from src.debug_params import get_breed_weight
        weight = get_breed_weight("canine", "labrador")
        assert weight == 30.0

    def test_returns_none_for_unknown_breed(self):
        from src.debug_params import get_breed_weight
        weight = get_breed_weight("canine", "unknown_breed")
        assert weight is None

    def test_returns_none_for_unknown_species(self):
        from src.debug_params import get_breed_weight
        weight = get_breed_weight("unknown_species", "labrador")
        assert weight is None


# ── compute_debug_params 测试 ──────────────────────────────────────────────

class TestComputeDebugParams:
    def test_basic_computation(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=1095,
            weight_kg=30.0,
        )
        assert "input" in result
        assert "organs" in result
        assert "summary" in result
        assert result["input"]["species"] == "canine"
        assert result["input"]["breed"] == "labrador"
        assert result["input"]["age_days"] == 1095
        assert result["input"]["weight_kg"] == 30.0

    def test_uses_default_weight_when_not_provided(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=1095,
        )
        assert result["input"]["weight_kg"] == 30.0

    def test_has_all_organ_systems(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=1095,
            weight_kg=30.0,
        )
        expected_organs = [
            "heart", "lung", "kidney", "blood", "fluid",
            "gut", "liver", "endocrine", "neuro", "immune",
            "coagulation", "lymphatic"
        ]
        for organ in expected_organs:
            assert organ in result["organs"], f"Missing organ: {organ}"

    def test_heart_has_required_params(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=1095,
            weight_kg=30.0,
        )
        heart = result["organs"]["heart"]
        assert "heart_rate" in heart
        assert "stroke_volume" in heart
        assert "cardiac_output" in heart
        assert "mean_arterial_pressure" in heart
        assert "SVR" in heart

    def test_values_are_numeric(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=1095,
            weight_kg=30.0,
        )
        for organ_name, params in result["organs"].items():
            for param_name, param_info in params.items():
                assert isinstance(param_info["value"], (int, float)), \
                    f"{organ_name}.{param_name} is not numeric: {param_info['value']}"

    def test_summary_counts_correct(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=1095,
            weight_kg=30.0,
        )
        total = 0
        for params in result["organs"].values():
            total += len(params)
        assert result["summary"]["total"] == total

    def test_lifecycle_applied_for_old_dog(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=4000,  # ~11 years old
            weight_kg=30.0,
        )
        # 老年犬应该有 lifecycle 信息
        if result["lifecycle"]:
            assert "phase" in result["lifecycle"]
            assert result["lifecycle"]["phase"] in ["senior", "geriatric"]

    def test_lifecycle_applied_for_puppy(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=30,  # 1 month old
            weight_kg=5.0,
        )
        # 幼犬应该有 lifecycle 信息
        if result["lifecycle"]:
            assert "phase" in result["lifecycle"]
            assert result["lifecycle"]["phase"] in ["neonatal", "juvenile"]


# ── 参数值范围测试 ──────────────────────────────────────────────────────────

class TestParameterRanges:
    def test_hr_in_reasonable_range(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=1095,
            weight_kg=30.0,
        )
        hr = result["organs"]["heart"]["heart_rate"]["value"]
        assert 40 <= hr <= 200, f"HR out of range: {hr}"

    def test_gfr_positive(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=1095,
            weight_kg=30.0,
        )
        gfr = result["organs"]["kidney"]["GFR"]["value"]
        assert gfr > 0, f"GFR should be positive: {gfr}"

    def test_blood_ph_in_range(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=1095,
            weight_kg=30.0,
        )
        ph = result["organs"]["blood"]["arterial_pH"]["value"]
        assert 6.8 <= ph <= 7.8, f"pH out of range: {ph}"

    def test_contractility_factor_positive(self):
        from src.debug_params import compute_debug_params
        result = compute_debug_params(
            species="canine",
            breed="labrador",
            age_days=1095,
            weight_kg=30.0,
        )
        cf = result["organs"]["heart"]["contractility_factor"]["value"]
        assert cf > 0, f"Contractility factor should be positive: {cf}"
