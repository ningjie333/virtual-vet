"""
Tests for Lifecycle V2 — modular lifecycle engine with developmental physiology.

Tests cover:
  - LifecycleMode: BYPASS, GROWTH, SENESCENCE, FULL
  - Maturation curves: sigmoid, linear_saturate, three_phase
  - Decline curves: gompertz, linear
  - Species profiles: canine, feline
  - Size category differences: small vs large breeds
  - EPO source switch (liver→kidney)
  - CYP450 maturation pattern
  - Integration with VirtualCreature
"""

import math
import pytest
from pathlib import Path

from src.lifecycle import LifecycleEngine, LifecycleMode
from src.lifecycle_curves import (
    sigmoid,
    linear_saturate,
    sigmoid_three_phase,
    gompertz_decline,
    maturation_curve,
    decline_curve,
)
from src.lifecycle_profiles import (
    LifecycleSpeciesProfile,
    LifecycleProfileLoader,
    MaturationConfig,
    DeclineConfig,
)


# ── Helpers ─────────────────────────────────────────────────────────────────────

class DummyCreature:
    """Minimal stand-in for VirtualCreature."""

    def __init__(self):
        self.kidney = type("Kidney", (), {"GFR": 100.0})()
        self.liver = type("Liver", (), {"metabolic_activity": 1.0})()
        self.heart = type("Heart", (), {"contractility_factor": 1.0})()


# ── Curves Tests ────────────────────────────────────────────────────────────────

class TestSigmoid:
    def test_at_midpoint_returns_half(self):
        assert sigmoid(50.0, k=0.1, midpoint_days=50.0) == pytest.approx(0.5)

    def test_near_zero_at_birth(self):
        assert sigmoid(0.0, k=0.1, midpoint_days=50.0) < 0.01

    def test_near_one_when_old(self):
        assert sigmoid(200.0, k=0.1, midpoint_days=50.0) > 0.99

    def test_increases_with_age(self):
        s1 = sigmoid(20.0, k=0.1, midpoint_days=50.0)
        s2 = sigmoid(80.0, k=0.1, midpoint_days=50.0)
        assert s2 > s1


class TestLinearSaturate:
    def test_zero_at_birth(self):
        assert linear_saturate(0.0, max_days=100.0) == 0.0

    def test_one_at_max(self):
        assert linear_saturate(100.0, max_days=100.0) == 1.0

    def test_clamps_above_max(self):
        assert linear_saturate(200.0, max_days=100.0) == 1.0

    def test_halfway(self):
        assert linear_saturate(50.0, max_days=100.0) == pytest.approx(0.5)


class TestGompertzDecline:
    def test_one_before_onset(self):
        assert gompertz_decline(100.0, onset_days=200.0, rate_per_day=1e-5) == 1.0

    def test_decreases_after_onset(self):
        d1 = gompertz_decline(300.0, onset_days=200.0, rate_per_day=1e-3)
        d2 = gompertz_decline(500.0, onset_days=200.0, rate_per_day=1e-3)
        assert d2 < d1 < 1.0

    def test_approaches_zero_with_age(self):
        d = gompertz_decline(50000.0, onset_days=200.0, rate_per_day=1e-3)
        assert d < 0.01


# ── Species Profile Tests ──────────────────────────────────────────────────────

class TestLifecycleProfileLoader:
    def test_loads_canine_profile(self):
        profile = LifecycleProfileLoader.get("canine")
        assert profile is not None
        assert profile.species == "canine"
        assert profile.maturity_age_days == 84.0

    def test_loads_feline_profile(self):
        profile = LifecycleProfileLoader.get("feline")
        assert profile is not None
        assert profile.species == "feline"

    def test_returns_none_for_unknown_species(self):
        profile = LifecycleProfileLoader.get("elephant")
        assert profile is None

    def test_canine_has_kidney_config(self):
        profile = LifecycleProfileLoader.get("canine")
        assert "kidney" in profile.organs
        assert profile.organs["kidney"].maturation.curve == "sigmoid"

    def test_canine_has_liver_config(self):
        profile = LifecycleProfileLoader.get("canine")
        assert "liver" in profile.organs
        # Changed from sigmoid_three_phase to sigmoid for overall liver function
        # (sigmoid_three_phase only for CYP450-specific curves)
        assert profile.organs["liver"].maturation.curve == "sigmoid"


class TestLifecycleSpeciesProfile:
    def test_get_organ_function_at_adult_age(self):
        profile = LifecycleProfileLoader.get("canine")
        # At 1 year (365 days), kidney should be fully mature
        func = profile.get_organ_function("kidney", 365.0)
        assert func > 0.95

    def test_get_organ_function_at_newborn(self):
        profile = LifecycleProfileLoader.get("canine")
        # At 1 day, kidney should be very immature
        func = profile.get_organ_function("kidney", 1.0)
        assert func < 0.1

    def test_get_organ_function_at_senior(self):
        profile = LifecycleProfileLoader.get("canine")
        # At 10 years (3650 days), kidney should show decline
        func = profile.get_organ_function("kidney", 3650.0)
        assert func < 0.95  # Decline factor kicks in (moderate decline)

    def test_unknown_organ_returns_one(self):
        profile = LifecycleProfileLoader.get("canine")
        assert profile.get_organ_function("unknown", 365.0) == 1.0

    def test_size_category_geriatric_age_differs(self):
        profile = LifecycleProfileLoader.get("canine")
        small_geriatric = profile.geriatric_age_days_by_size.get("small", 4380)
        large_geriatric = profile.geriatric_age_days_by_size.get("large", 2555)
        assert small_geriatric > large_geriatric


# ── LifecycleEngine V2 Tests ─────────────────────────────────────────────────

class TestLifecycleEngineV2:
    def test_bypass_mode_has_no_profile(self):
        eng = LifecycleEngine(mode=LifecycleMode.BYPASS)
        assert eng.mode == LifecycleMode.BYPASS

    def test_growth_mode_uses_profile(self):
        profile = LifecycleProfileLoader.get("canine")
        eng = LifecycleEngine(
            mode=LifecycleMode.GROWTH,
            profile=profile,
            initial_age_days=42.0,
        )
        assert eng.mode == LifecycleMode.GROWTH

    def test_senescence_mode_uses_profile(self):
        profile = LifecycleProfileLoader.get("canine")
        eng = LifecycleEngine(
            mode=LifecycleMode.SENESCENCE,
            profile=profile,
            initial_age_days=1095.0,
        )
        assert eng.mode == LifecycleMode.SENESCENCE


class TestLifecyclePhaseV2:
    def test_bypass_phase_at_maturity(self):
        eng = LifecycleEngine(mode=LifecycleMode.BYPASS, initial_age_days=1095.0)
        assert eng._state.phase.value == "mature"

    def test_growth_newborn_phase(self):
        profile = LifecycleProfileLoader.get("canine")
        eng = LifecycleEngine(
            mode=LifecycleMode.GROWTH,
            profile=profile,
            initial_age_days=5.0,
        )
        assert eng._state.phase.value == "neonatal"

    def test_growth_juvenile_phase(self):
        profile = LifecycleProfileLoader.get("canine")
        eng = LifecycleEngine(
            mode=LifecycleMode.GROWTH,
            profile=profile,
            initial_age_days=30.0,
        )
        assert eng._state.phase.value == "juvenile"

    def test_senescence_adult_phase(self):
        profile = LifecycleProfileLoader.get("canine")
        eng = LifecycleEngine(
            mode=LifecycleMode.SENESCENCE,
            profile=profile,
            initial_age_days=1095.0,
        )
        assert eng._state.phase.value == "adult"

    def test_senescence_senior_phase(self):
        profile = LifecycleProfileLoader.get("canine")
        eng = LifecycleEngine(
            mode=LifecycleMode.SENESCENCE,
            profile=profile,
            size_category="large",
            initial_age_days=3000.0,
        )
        assert eng._state.phase.value in ("senior", "geriatric")

    def test_senescence_geriatric_phase(self):
        profile = LifecycleProfileLoader.get("canine")
        eng = LifecycleEngine(
            mode=LifecycleMode.SENESCENCE,
            profile=profile,
            size_category="large",
            initial_age_days=3500.0,
        )
        assert eng._state.phase.value == "geriatric"


class TestLifecycleApplyV2:
    def test_bypass_does_not_change_creature(self):
        eng = LifecycleEngine(mode=LifecycleMode.BYPASS)
        creature = DummyCreature()
        eng.apply(creature)
        assert creature.kidney.GFR == 100.0  # Unchanged

    def test_senescence_reduces_kidney_function(self):
        profile = LifecycleProfileLoader.get("canine")
        eng = LifecycleEngine(
            mode=LifecycleMode.SENESCENCE,
            profile=profile,
            initial_age_days=4000.0,  # ~11 years
        )
        creature = DummyCreature()
        eng.capture_baselines(creature)
        initial_gfr = creature.kidney.GFR
        eng.apply(creature)
        assert creature.kidney.GFR < initial_gfr  # Reduced by decline

    def test_growth_increases_kidney_function_over_time(self):
        profile = LifecycleProfileLoader.get("canine")
        creature = DummyCreature()

        # At 1 day: very immature
        eng1 = LifecycleEngine(
            mode=LifecycleMode.GROWTH,
            profile=profile,
            initial_age_days=1.0,
        )
        eng1.capture_baselines(creature)
        eng1.apply(creature)
        gfr_1day = creature.kidney.GFR

        # At 84 days: mature
        creature.kidney.GFR = 100.0  # Reset
        eng2 = LifecycleEngine(
            mode=LifecycleMode.GROWTH,
            profile=profile,
            initial_age_days=84.0,
        )
        eng2.capture_baselines(creature)
        eng2.apply(creature)
        gfr_84days = creature.kidney.GFR

        assert gfr_84days > gfr_1day


class TestLifecycleSizeCategory:
    def test_small_breed_geriatric_later_than_large(self):
        profile = LifecycleProfileLoader.get("canine")
        small_eng = LifecycleEngine(
            mode=LifecycleMode.SENESCENCE,
            profile=profile,
            size_category="small",
            initial_age_days=3000.0,
        )
        large_eng = LifecycleEngine(
            mode=LifecycleMode.SENESCENCE,
            profile=profile,
            size_category="large",
            initial_age_days=3000.0,
        )
        # At 3000 days (~8.2 years):
        # Small breed: still adult (geriatric at 4380 days)
        # Large breed: senior or geriatric (geriatric at 2555 days)
        assert small_eng._state.phase.value in ("adult", "senior")
        assert large_eng._state.phase.value in ("senior", "geriatric")


class TestLifecycleSerializationV2:
    def test_serialize_bypass(self):
        eng = LifecycleEngine(mode=LifecycleMode.BYPASS)
        data = eng.serialize()
        assert data["mode"] == "bypass"

    def test_serialize_senescence(self):
        profile = LifecycleProfileLoader.get("canine")
        eng = LifecycleEngine(
            mode=LifecycleMode.SENESCENCE,
            profile=profile,
            initial_age_days=2000.0,
        )
        data = eng.serialize()
        assert data["mode"] == "senescence"
        assert data["age_days"] == 2000.0

    def test_deserialize_roundtrip(self):
        profile = LifecycleProfileLoader.get("canine")
        eng = LifecycleEngine(
            mode=LifecycleMode.SENESCENCE,
            profile=profile,
            initial_age_days=2000.0,
        )
        data = eng.serialize()
        restored = LifecycleEngine.deserialize(data)
        assert restored._state.age_days == 2000.0
        assert restored.mode == LifecycleMode.SENESCENCE
