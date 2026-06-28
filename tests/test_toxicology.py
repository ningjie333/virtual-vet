"""
P0: ToxicologyModule dedicated tests.

Coverage targets:
- compute() "no injection" branch (t_since_injection_min is None)
- summary() "no injection" vs "dosed" branches
- Dose-dependent max_depression and max_svr_factor clamp logic
- Two-pathway kinetics verification (contractility decay < SVR decay)
- High-dose edge cases (6 mg/kg)
"""

import math
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from toxicology import ToxicologyModule


class TestToxicologyInit:
    """Default state before any drug administration."""

    def test_default_state_no_injection(self):
        tox = ToxicologyModule(weight_kg=20.0)
        assert tox.contractility_depression == 0.0
        assert tox.svr_factor == 1.0
        assert tox._t_since_injection_min is None

    def test_summary_no_injection(self):
        tox = ToxicologyModule(weight_kg=20.0)
        s = tox.summary()
        assert s["cocaine_dosed"] is False
        assert s["contractility_factor"] == 1.0
        assert s["svr_factor"] == 1.0

    def test_compute_no_injection_returns_baseline(self):
        tox = ToxicologyModule(weight_kg=20.0)
        result = tox.compute(dt=0.1)
        assert result["cocaine_active"] is False
        assert result["contractility_factor"] == 1.0
        assert result["svr_factor"] == 1.0


class TestAdministerCocaine:
    """Dose-dependent effect initialization."""

    def test_standard_dose_starts_timer(self):
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)
        assert tox._t_since_injection_min == 0.0

    def test_dose_proportional_contractility_depression(self):
        """Higher dose → deeper depression, but clamped at 60%."""
        tox_low = ToxicologyModule(weight_kg=20.0)
        tox_low.administer_cocaine(dose_mg_kg=1.5)
        low_max = abs(tox_low._max_depression)

        tox_std = ToxicologyModule(weight_kg=20.0)
        tox_std.administer_cocaine(dose_mg_kg=3.0)
        std_max = abs(tox_std._max_depression)

        assert low_max < std_max, "Higher dose should produce deeper depression"
        assert std_max <= 0.60, "Depression must not exceed 60% clamp"

    def test_dose_proportional_svr_activation(self):
        """Higher dose → higher SVR, but clamped at 3.5×."""
        tox_low = ToxicologyModule(weight_kg=20.0)
        tox_low.administer_cocaine(dose_mg_kg=1.5)
        low_svr = tox_low._max_svr_factor

        tox_std = ToxicologyModule(weight_kg=20.0)
        tox_std.administer_cocaine(dose_mg_kg=3.0)
        std_svr = tox_std._max_svr_factor

        assert low_svr < std_svr, "Higher dose should produce higher SVR"
        assert std_svr <= 3.5, "SVR must not exceed 3.5× clamp"

    def test_max_depression_clamp_60_percent(self):
        """Extremely high dose (100×) must be clamped at 60%."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=100.0)
        assert abs(tox._max_depression) <= 0.60

    def test_max_svr_clamp_3_5x(self):
        """Extremely high dose SVR must be clamped at 3.5×."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=100.0)
        assert tox._max_svr_factor <= 3.5


class TestCocaineKinetics:
    """Two-pathway decay kinetics (Liu et al. 1993)."""

    def test_contractility_decay_5min(self):
        """At t=5 min, contractility depression ≈ 37% of peak (τ=5 min)."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)
        max_dep = abs(tox._max_depression)

        # Advance 5 min
        for _ in range(int(5 * 60 / 0.1)):
            tox.compute(dt=0.1)

        expected = max_dep * math.exp(-5.0 / 5.0)  # ≈ 0.368 × max_dep
        assert abs(tox.contractility_depression) == pytest.approx(expected, abs=0.02)

    def test_contractility_decay_15min(self):
        """At t=15 min, contractility depression ≈ 5% of peak (τ=5 min)."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)
        max_dep = abs(tox._max_depression)

        for _ in range(int(15 * 60 / 0.1)):
            tox.compute(dt=0.1)

        expected = max_dep * math.exp(-15.0 / 5.0)  # ≈ 0.050 × max_dep
        assert abs(tox.contractility_depression) == pytest.approx(expected, abs=0.01)

    def test_svr_decay_30min(self):
        """At t=30 min, SVR effect ≈ 37% of peak (τ=30 min)."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)
        peak_svr = tox._max_svr_factor

        for _ in range(int(30 * 60 / 0.1)):
            tox.compute(dt=0.1)

        expected_svr = 1.0 + (peak_svr - 1.0) * math.exp(-30.0 / 30.0)
        assert tox.svr_factor == pytest.approx(expected_svr, abs=0.02)

    def test_svr_persists_longer_than_contractility(self):
        """At t=15 min, SVR residual > contractility residual (τ_SVR > τ_ct)."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)

        for _ in range(int(15 * 60 / 0.1)):
            tox.compute(dt=0.1)

        contractility_residual = abs(tox.contractility_depression) / abs(tox._max_depression)
        svr_residual = (tox.svr_factor - 1.0) / (tox._max_svr_factor - 1.0)

        assert svr_residual > contractility_residual, (
            f"SVR residual ({svr_residual:.4f}) should exceed "
            f"contractility residual ({contractility_residual:.4f}) at t=15 min"
        )

    def test_contractility_factor_returns_to_1_after_60min(self):
        """After 60 min, contractility_factor should be ≈ 1.0 (full recovery)."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)

        for _ in range(int(60 * 60 / 0.1)):
            result = tox.compute(dt=0.1)

        assert result["contractility_factor"] == pytest.approx(1.0, abs=0.01)

    def test_svr_factor_returns_to_1_after_180min(self):
        """After 180 min (6 half-lives), SVR factor ≈ 1.0."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)

        for _ in range(int(180 * 60 / 0.1)):
            result = tox.compute(dt=0.1)

        assert result["svr_factor"] == pytest.approx(1.0, abs=0.01)


class TestCocaineComputeOutput:
    """compute() return dict completeness."""

    def test_compute_returns_all_keys(self):
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)
        for _ in range(10):
            result = tox.compute(dt=0.1)

        assert "contractility_factor" in result
        assert "svr_factor" in result
        assert "cocaine_active" in result
        assert result["cocaine_active"] is True
        assert "t_since_injection_min" in result
        assert "depression_ratio" in result
        assert "svr_ratio" in result

    def test_depression_ratio_monotonic_decay(self):
        """depression_ratio should monotonically decrease over time."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)

        ratios = []
        for _ in range(20):
            result = tox.compute(dt=0.1)
            ratios.append(result["depression_ratio"])

        assert all(ratios[i] >= ratios[i + 1] - 1e-10 for i in range(len(ratios) - 1)), \
            "depression_ratio should be monotonically decreasing"

    def test_svr_ratio_monotonic_decay(self):
        """svr_ratio should monotonically decrease over time."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)

        ratios = []
        for _ in range(20):
            result = tox.compute(dt=0.1)
            ratios.append(result["svr_ratio"])

        assert all(ratios[i] >= ratios[i + 1] - 1e-10 for i in range(len(ratios) - 1)), \
            "svr_ratio should be monotonically decreasing"


class TestCocaineSummary:
    """summary() output correctness."""

    def test_summary_after_injection(self):
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=3.0)
        for _ in range(5):
            tox.compute(dt=0.1)

        s = tox.summary()
        assert s["cocaine_dosed"] is True
        assert "t_since_injection_min" in s
        assert s["contractility_factor"] < 1.0
        assert s["svr_factor"] > 1.0

    def test_summary_keys_consistent(self):
        """summary() returns same keys regardless of injection state."""
        tox_no = ToxicologyModule(weight_kg=20.0)
        s_no = tox_no.summary()
        assert s_no["cocaine_dosed"] is False
        assert "contractility_factor" in s_no
        assert "svr_factor" in s_no

        tox_yes = ToxicologyModule(weight_kg=20.0)
        tox_yes.administer_cocaine(dose_mg_kg=3.0)
        for _ in range(5):
            tox_yes.compute(dt=0.1)
        s_yes = tox_yes.summary()
        assert s_yes["cocaine_dosed"] is True
        assert "contractility_factor" in s_yes
        assert "svr_factor" in s_yes
        assert "t_since_injection_min" in s_yes


class TestHighDoseEffects:
    """High-dose (6 mg/kg) cocaine — Liu et al. 1993 high-dose comparison."""

    def test_high_dose_deeper_depression(self):
        """6 mg/kg produces deeper depression than 3 mg/kg."""
        tox_std = ToxicologyModule(weight_kg=20.0)
        tox_std.administer_cocaine(dose_mg_kg=3.0)

        tox_high = ToxicologyModule(weight_kg=20.0)
        tox_high.administer_cocaine(dose_mg_kg=6.0)

        assert abs(tox_high._max_depression) > abs(tox_std._max_depression), \
            "High dose should produce deeper contractility depression"

    def test_high_dose_higher_svr(self):
        """6 mg/kg produces higher SVR than 3 mg/kg."""
        tox_std = ToxicologyModule(weight_kg=20.0)
        tox_std.administer_cocaine(dose_mg_kg=3.0)

        tox_high = ToxicologyModule(weight_kg=20.0)
        tox_high.administer_cocaine(dose_mg_kg=6.0)

        assert tox_high._max_svr_factor > tox_std._max_svr_factor, \
            "High dose should produce higher SVR activation"

    def test_high_dose_decay_rates_unchanged(self):
        """Higher dose should not change decay time constants."""
        tox = ToxicologyModule(weight_kg=20.0)
        tox.administer_cocaine(dose_mg_kg=6.0)
        max_dep = abs(tox._max_depression)

        for _ in range(int(5 * 60 / 0.1)):
            tox.compute(dt=0.1)

        expected = max_dep * math.exp(-5.0 / 5.0)
        assert abs(tox.contractility_depression) == pytest.approx(expected, abs=0.02)