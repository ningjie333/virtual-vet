"""
Tests for the LifecycleEngine — result-driven aging system.
"""

import math

import pytest

from src.lifecycle import (
    LifecycleEngine,
    LifecyclePhase,
    LifecycleParams,
    _CANINE_PARAMS,
    _FELINE_PARAMS,
    _EQUINE_PARAMS,
    _SPECIES_PARAMS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

class _DummyModule:
    """Minimal stand-in for organ modules (heart, lung, kidney, etc.)."""
    def __init__(self):
        self.contractility_factor = 1.0
        self.diffusion_coefficient = 25.0
        self.GFR = 60.0
        self.metabolic_activity = 1.0
        self.detox_capacity = 1.0
        self.cyp450_activity = 1.0
        self.gut_motility = 0.8
        self.barrier_integrity = 1.0
        self.microbiome_activity = 0.6
        self.PLT = 200.0


class DummyCreature:
    """Minimal stand-in for VirtualCreature with the attributes LifecycleEngine touches."""

    def __init__(self):
        self.heart = _DummyModule()
        self.lung = _DummyModule()
        self.kidney = _DummyModule()
        self.liver = _DummyModule()
        self.gut = _DummyModule()
        self.blood = _DummyModule()

    def apply_factor(self, cmd):
        target = cmd.target
        value = cmd.value
        module_name, attr_name = target.split(".", 1)
        setattr(getattr(self, module_name), attr_name, value)


# ── LifecycleParams ───────────────────────────────────────────────────────────

class TestLifecycleParams:
    def test_all_species_defined(self):
        assert "canine" in _SPECIES_PARAMS
        assert "feline" in _SPECIES_PARAMS
        assert "equine" in _SPECIES_PARAMS

    def test_canine_shorter_lifespan_than_feline(self):
        canine_life = _CANINE_PARAMS.decline_rate
        feline_life = _FELINE_PARAMS.decline_rate
        # Higher rate → faster decline → shorter life
        assert canine_life > feline_life

    def test_feline_shorter_than_equine(self):
        feline_life = _FELINE_PARAMS.decline_rate
        equine_life = _EQUINE_PARAMS.decline_rate
        assert feline_life > equine_life

    def test_end_life_function_same_for_all(self):
        # All species use the same end_life_function threshold
        assert _CANINE_PARAMS.end_life_function == 0.3
        assert _FELINE_PARAMS.end_life_function == 0.3
        assert _EQUINE_PARAMS.end_life_function == 0.3


# ── LifecycleEngine — Initialization ─────────────────────────────────────────

class TestLifecycleInit:
    def test_newborn_initial_phase(self):
        eng = LifecycleEngine(species="canine", initial_age_days=0.0)
        assert eng.state.phase == LifecyclePhase.NEONATAL

    def test_newborn_growth_factor(self):
        eng = LifecycleEngine(species="canine", initial_age_days=0.0)
        assert 0.09 < eng.growth_factor() < 0.11  # ~0.1 at birth

    def test_advance_time_updates_age(self):
        eng = LifecycleEngine(species="canine", initial_age_days=0.0)
        eng.advance_time(365.0)  # advance 1 year
        assert 364.0 < eng.state.age_days < 366.0


# ── LifecycleEngine — Growth ──────────────────────────────────────────────────

class TestGrowth:
    def test_growth_factor_at_birth(self):
        eng = LifecycleEngine(species="canine", initial_age_days=0.0)
        gf = eng.growth_factor()
        assert 0.09 < gf < 0.11  # ~0.1

    def test_growth_factor_increases_with_age(self):
        eng = LifecycleEngine(species="canine", initial_age_days=0.0)
        gf_0 = eng.growth_factor()
        eng.advance_time(365.0)  # 1 year
        gf_1 = eng.growth_factor()
        assert gf_1 > gf_0

    def test_growth_factor_near_mature(self):
        eng = LifecycleEngine(species="canine", initial_age_days=1095.0)  # ~3 yr
        gf = eng.growth_factor()
        assert gf > 0.9  # near mature

    def test_growth_factor_never_exceeds_one(self):
        eng = LifecycleEngine(species="canine", initial_age_days=0.0)
        for age in range(0, 5000, 100):
            eng.state.age_days = age
            assert eng.growth_factor() <= 1.0 + 1e-9


# ── LifecycleEngine — Decline ────────────────────────────────────────────────

class TestDecline:
    def test_decline_multiplier_at_maturity(self):
        eng = LifecycleEngine(species="canine", initial_age_days=1095.0)  # mature
        assert eng._decline_multiplier() == 1.0

    def test_decline_multiplier_decreases_after_maturity(self):
        eng = LifecycleEngine(species="canine", initial_age_days=1095.0)
        dm_mature = eng._decline_multiplier()
        # Advance to 8 years old (5 years post-mature)
        eng.advance_time((8 * 365.0) - 1095.0)
        dm_old = eng._decline_multiplier()
        assert dm_old < dm_mature

    def test_decline_multiplier_at_end_life(self):
        # At ~20 years for canine (17yr post-mature), dm ≈ exp(-0.0693*17) ≈ 0.31
        # This is near (but not below) end_life_function=0.3
        eng = LifecycleEngine(species="canine", initial_age_days=20 * 365.0)
        dm = eng._decline_multiplier()
        assert 0.25 < dm < 0.35  # ~0.31

    def test_death_at_very_old_age(self):
        # At ~24.7yr canine (21.7yr post-mature), dm = exp(-0.0693*21.7) ≈ 0.30 → death
        eng = LifecycleEngine(species="canine", initial_age_days=24.7 * 365.0)
        death_cause = eng.death_check()
        assert death_cause is not None
        assert eng.is_dead()

    def test_equine_decline_slower_than_canine(self):
        canine_eng = LifecycleEngine(species="canine", initial_age_days=10 * 365.0)
        equine_eng = LifecycleEngine(species="equine", initial_age_days=10 * 365.0)
        # At same age (but different post-maturity), equine should have higher multiplier
        canine_dm = canine_eng._decline_multiplier()
        equine_dm = equine_eng._decline_multiplier()
        # At 10 years old: canine is 7yr post-mature, equine is 4yr post-mature
        assert equine_dm > canine_dm

    def test_organ_multiplier_combines_growth_and_decline(self):
        eng = LifecycleEngine(species="canine", initial_age_days=1095.0)  # mature
        # At mature: growth ≈ 1.0, decline = 1.0, so multiplier ≈ 1.0
        assert 0.95 < eng.organ_multiplier("heart") <= 1.0


# ── LifecycleEngine — Phases ─────────────────────────────────────────────────

class TestPhases:
    def test_neonatal_at_birth(self):
        eng = LifecycleEngine(species="canine", initial_age_days=0.0)
        assert eng.state.phase == LifecyclePhase.NEONATAL

    def test_juvenile_phase(self):
        eng = LifecycleEngine(species="canine", initial_age_days=0.0)
        eng.advance_time(0.6 * 365.0)  # ~0.6 yr
        assert eng.state.phase == LifecyclePhase.JUVENILE

    def test_young_adult_phase(self):
        eng = LifecycleEngine(species="canine", initial_age_days=0.0)
        eng.advance_time(1.5 * 365.0)  # ~1.5 yr
        assert eng.state.phase == LifecyclePhase.YOUNG_ADULT

    def test_mature_phase(self):
        eng = LifecycleEngine(species="canine", initial_age_days=3.5 * 365.0)  # ~3.5 yr
        assert eng.state.phase == LifecyclePhase.MATURE

    def test_senior_phase(self):
        eng = LifecycleEngine(species="canine", initial_age_days=6.0 * 365.0)  # ~6 yr
        assert eng.state.phase == LifecyclePhase.SENIOR

    def test_geriatric_phase(self):
        # At ~15yr: dm = exp(-0.0693*12) ≈ 0.435 < 0.6 → GERIATRIC
        eng = LifecycleEngine(species="canine", initial_age_days=15.0 * 365.0)
        assert eng.state.phase == LifecyclePhase.GERIATRIC


# ── LifecycleEngine — Death ───────────────────────────────────────────────────

class TestDeath:
    def test_not_dead_at_maturity(self):
        eng = LifecycleEngine(species="canine", initial_age_days=1095.0)
        assert eng.death_check() is None
        assert not eng.is_dead()

    def test_not_dead_in_senior(self):
        eng = LifecycleEngine(species="canine", initial_age_days=6.0 * 365.0)
        assert eng.death_check() is None

    def test_dead_at_extreme_age(self):
        eng = LifecycleEngine(species="canine", initial_age_days=24.7 * 365.0)
        death_cause = eng.death_check()
        assert death_cause is not None
        assert eng.is_dead()
        assert eng.state.death_cause is not None


# ── LifecycleEngine — Organ Reserve ─────────────────────────────────────────

class TestOrganReserve:
    def test_organ_reserve_at_birth(self):
        eng = LifecycleEngine(species="canine", initial_age_days=0.0)
        # At birth: multiplier ≈ 0.1, reserve = max(0, 0.1 - 0.3) = 0
        for organ in eng.state.organ_function:
            assert eng.organ_reserve_pct(organ) == 0.0

    def test_organ_reserve_at_mature(self):
        eng = LifecycleEngine(species="canine", initial_age_days=1095.0)
        # At mature: multiplier ≈ 1.0, reserve = 1.0 - 0.3 = 0.7
        for organ in eng.state.organ_function:
            assert 0.65 < eng.organ_reserve_pct(organ) < 0.75

    def test_organ_reserve_depletes_with_age(self):
        eng = LifecycleEngine(species="canine", initial_age_days=1095.0)
        reserve_young = eng.organ_reserve_pct("heart")
        eng.advance_time(5 * 365.0)  # 5 years later
        reserve_old = eng.organ_reserve_pct("heart")
        assert reserve_old < reserve_young


# ── LifecycleEngine — apply_age_factors ─────────────────────────────────────

class TestApplyAgeFactors:
    def test_captures_original_baselines(self):
        # Note: heart.contractility_factor is no longer controlled by lifecycle
        # (removed because direct set overwrote drug effects); use kidney.GFR instead.
        creature = DummyCreature()
        eng = LifecycleEngine(species="canine", initial_age_days=1095.0)
        eng.capture_baselines(creature)
        eng.apply_age_factors(creature)
        assert "kidney.GFR" in eng._original_baselines

    def test_sets_age_adjusted_values(self):
        # heart.contractility_factor moved out of lifecycle control; use kidney.GFR.
        creature = DummyCreature()
        eng = LifecycleEngine(species="canine", initial_age_days=6.0 * 365.0)
        eng.capture_baselines(creature)
        eng.apply_age_factors(creature)
        # At 6 yr: multiplier ≈ exp(-0.0693*3) ≈ 0.81
        mult = eng.organ_multiplier("kidney")
        assert 0.7 < mult < 0.9
        baseline_gfr = eng._original_baselines["kidney.GFR"]
        assert creature.kidney.GFR == pytest.approx(baseline_gfr * mult, rel=1e-3)

    def test_does_not_override_original_baselines(self):
        # heart.contractility_factor moved out of lifecycle control; use kidney.GFR.
        creature = DummyCreature()
        eng = LifecycleEngine(species="canine", initial_age_days=6.0 * 365.0)
        eng.capture_baselines(creature)
        eng.apply_age_factors(creature)
        first_gfr = creature.kidney.GFR
        creature.kidney.GFR = 999  # tamper
        eng.apply_age_factors(creature)
        # Should still use original baseline (1.0), not the tampered value
        assert creature.kidney.GFR == pytest.approx(first_gfr)


# ── LifecycleEngine — Serialization ───────────────────────────────────────────

class TestSerialization:
    def test_serialize_roundtrip(self):
        eng = LifecycleEngine(species="canine", initial_age_days=1500.0)
        eng.advance_time(100.0)
        data = eng.serialize()
        restored = LifecycleEngine.deserialize(data)
        assert restored.state.age_days == eng.state.age_days
        assert restored.state.phase == eng.state.phase
        assert restored.params.species == eng.params.species
        # Use pytest.approx for floating-point values serialized with rounding
        for organ in eng.state.organ_function:
            assert restored.state.organ_function[organ] == pytest.approx(
                eng.state.organ_function[organ], abs=1e-3
            )

    def test_serialize_preserves_original_baselines(self):
        creature = DummyCreature()
        eng = LifecycleEngine(species="canine", initial_age_days=1095.0)
        eng.capture_baselines(creature)
        eng.apply_age_factors(creature)
        data = eng.serialize()
        assert "_original_baselines" in data
        assert len(data["_original_baselines"]) > 0


# ── LifecycleEngine — Species Differences ─────────────────────────────────────

class TestSpeciesDifferences:
    def test_canine_earliest_senior_onset(self):
        """Canine reaches SENIOR phase before feline/equine at same calendar age."""
        age = 8 * 365.0  # 8 years
        canine = LifecycleEngine(species="canine", initial_age_days=age)
        feline = LifecycleEngine(species="feline", initial_age_days=age)
        equine = LifecycleEngine(species="equine", initial_age_days=age)
        # At 8yr: canine (5yr post-mat) more senior than feline (5yr post-mat) or equine (2yr post-mat)
        canine_dm = canine._decline_multiplier()
        feline_dm = feline._decline_multiplier()
        equine_dm = equine._decline_multiplier()
        # More post-maturity years → lower multiplier
        assert canine_dm < feline_dm
        assert feline_dm < equine_dm

    def test_all_phases_reachable_canine(self):
        """Verify a canine can pass through all phases from birth to death."""
        ages_and_phases = [
            (0.0, LifecyclePhase.NEONATAL),
            (0.6 * 365.0, LifecyclePhase.JUVENILE),
            (1.5 * 365.0, LifecyclePhase.YOUNG_ADULT),
            (3.5 * 365.0, LifecyclePhase.MATURE),
            (6.0 * 365.0, LifecyclePhase.SENIOR),
            (15.0 * 365.0, LifecyclePhase.GERIATRIC),
        ]
        for age_days, expected_phase in ages_and_phases:
            eng = LifecycleEngine(species="canine", initial_age_days=age_days)
            assert eng.state.phase == expected_phase, \
                f"At age {age_days/365:.1f}yr: expected {expected_phase}, got {eng.state.phase}"
