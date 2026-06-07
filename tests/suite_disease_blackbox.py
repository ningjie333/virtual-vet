"""
Disease Black-Box Stability Suite

Verifies that ALL registered diseases in data/ode_diseases.json produce
physiologically meaningful effects when attached to VirtualCreature.

Test categories:
  1. Each disease produces non-empty list[FactorCommand] when active
  2. Each disease causes at least one physiological parameter to deviate >10% from baseline
  3. Severity (mild/moderate/severe) produces dose-dependent parameter changes
  4. No disease causes unbounded parameter divergence (all params stay finite)

Load all diseases dynamically from data/ode_diseases.json via create_disease().
"""

import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulation import VirtualCreature
from src.diseases import create_disease, list_diseases


# ── Constants ──────────────────────────────────────────────────────────────────

BODY_WEIGHT_KG = 20.0
SPECIES = "canine"
DT = 0.1
STEPS_WARMUP = 2500    # 2.5 min warmup at dt=0.1s
STEPS_TRACK = 5000     # 5 min tracking period
TOTAL_STEPS = STEPS_WARMUP + STEPS_TRACK  # 7.5 min total

# Sample interval (every 50 steps = 5s intervals)
SAMPLE_INTERVAL = 50
SAMPLE_START = STEPS_WARMUP  # start sampling after warmup

# Key parameters to track (covers cardiovascular, respiratory, renal, electrolyte,
# liver, and coagulation axes — all diseases should touch at least one)
TRACKED_PARAMS = ["HR", "MAP", "PCO2", "pH", "GFR", "K", "ALT", "albumin", "ammonia", "PT"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_param(vc: VirtualCreature, key: str):
    """Sample a physiological parameter from the creature."""
    if key == "HR":
        return vc.heart.heart_rate
    if key == "MAP":
        return vc.heart.mean_arterial_pressure
    if key == "PCO2":
        return vc.blood.arterial_PCO2_mmHg
    if key == "pH":
        return vc.blood.arterial_pH
    if key == "GFR":
        return vc.kidney.GFR
    if key == "K":
        return vc.blood.potassium_mEq_L
    if key == "ALT":
        return vc.blood.ALT_U_L
    if key == "albumin":
        return vc.blood.albumin_g_dL
    if key == "ammonia":
        return vc.blood.ammonia_umol_L
    if key == "PT":
        return vc.blood.PT_sec
    raise KeyError(f"Unknown param: {key}")


def _all_finite(values) -> bool:
    """Check that all values in a series are finite (not inf/nan)."""
    return all(math.isfinite(v) for v in values)


def _pct_change(baseline: float, final: float) -> float:
    """Percent change from baseline. Returns 0 if baseline is near-zero."""
    if abs(baseline) < 1e-9:
        return 0.0
    return abs(final - baseline) / abs(baseline) * 100.0


def _has_meaningful_change(baseline: float, series: list) -> bool:
    """Check if any value in series differs from baseline by > threshold_pct."""
    threshold = 0.10  # 10%
    for val in series:
        if abs(val) < 1e-9:
            continue
        pct = abs(val - baseline) / abs(baseline)
        if pct > threshold:
            return True
    return False


def _max_abs_deviation(baseline: float, series: list) -> float:
    """Return max absolute % deviation from baseline."""
    if not series:
        return 0.0
    max_dev = 0.0
    for val in series:
        if abs(baseline) < 1e-9:
            dev = abs(val)
        else:
            dev = abs(val - baseline) / abs(baseline)
        if dev > max_dev:
            max_dev = dev
    return max_dev


# ── Test Classes ───────────────────────────────────────────────────────────────

@pytest.mark.suite_disease_blackbox
@pytest.mark.stability
class TestDiseaseBlackBox:
    """
    Black-box validation of all registered diseases.

    Each test attaches a disease to a VirtualCreature (canine, 20kg), runs the
    simulation, and verifies the disease produces measurable physiological effects.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """Shared fixture: create a baseline healthy creature."""
        self.vc = VirtualCreature(
            body_weight_kg=BODY_WEIGHT_KG,
            species=SPECIES,
            dt=DT,
        )
        # Let the creature stabilize before measuring baseline
        for _ in range(STEPS_WARMUP):
            self.vc.step()
        # Record baseline values
        self.baseline = {key: _get_param(self.vc, key) for key in TRACKED_PARAMS}

    def _attach_and_run(self, disease_name: str, severity: str = "moderate"):
        """Attach disease, run full simulation, return tracked series."""
        disease = create_disease(disease_name, severity=severity)
        self.vc.attach_disease(disease)

        # Disease auto-activates on attach via VirtualCreature.attach_disease
        # (ConfigDrivenDiseaseModule sets active=True in its logic)
        # Force activation if not already active
        if not disease.active:
            disease.activate(0.0)

        tracked = {key: [] for key in TRACKED_PARAMS}
        for step in range(TOTAL_STEPS):
            self.vc.step()
            if step >= SAMPLE_START and (step - SAMPLE_START) % SAMPLE_INTERVAL == 0:
                for key in TRACKED_PARAMS:
                    tracked[key].append(_get_param(self.vc, key))

        return tracked, disease

    @pytest.mark.parametrize("disease_name", list_diseases())
    def test_disease_produces_factor_commands(self, disease_name):
        """
        Test 1: Each registered disease produces non-empty list[FactorCommand]
        when active and compute() is called.
        """
        disease = create_disease(disease_name, severity="moderate")
        disease.activate(0.0)

        # Build a minimal engine_state snapshot
        engine_state = {
            "heart": {
                "heart_rate_bpm": 90.0,
                "MAP_mmHg": 100.0,
                "cardiac_output_ml_min": 1800.0,
                "SVR": 1.0,
                "CVP": 5.0,
                "contractility_factor": 1.0,
            },
            "lung": {"diffusion_coefficient": 1.0, "arterial_PO2": 100.0},
            "kidney": {"GFR_ml_min": 50.0, "_disease_gfr_multiplier": 1.0},
            "blood": {
                "potassium_mEq_L": 4.2,
                "arterial_pH": 7.40,
                "HCO3": 24.0,
                "arterial_PCO2_mmHg": 40.0,
            },
        }

        cmds = disease.compute(dt=0.1, engine_state=engine_state)
        assert isinstance(cmds, list), (
            f"{disease_name}: compute() must return list[FactorCommand], got {type(cmds)}"
        )
        assert len(cmds) > 0, (
            f"{disease_name}: compute() returned empty list — disease produces no FactorCommands"
        )
        # Verify each command has required FactorCommand fields
        for cmd in cmds:
            assert hasattr(cmd, "target"), f"{disease_name}: FactorCommand missing 'target'"
            assert hasattr(cmd, "op"), f"{disease_name}: FactorCommand missing 'op'"
            assert hasattr(cmd, "value"), f"{disease_name}: FactorCommand missing 'value'"

    @pytest.mark.parametrize("disease_name", list_diseases())
    def test_disease_deviates_from_baseline(self, disease_name):
        """
        Test 2: Each disease attached to creature causes at least ONE tracked
        parameter to deviate >10% from baseline.
        """
        tracked, disease = self._attach_and_run(disease_name, severity="moderate")

        assert _all_finite(tracked["HR"]), (
            f"{disease_name}: HR became non-finite: {tracked['HR'][-5:]}"
        )
        assert _all_finite(tracked["MAP"]), (
            f"{disease_name}: MAP became non-finite: {tracked['MAP'][-5:]}"
        )
        assert _all_finite(tracked["pH"]), (
            f"{disease_name}: pH became non-finite: {tracked['pH'][-5:]}"
        )

        deviations = {}
        for key in TRACKED_PARAMS:
            deviations[key] = _max_abs_deviation(self.baseline[key], tracked[key])

        max_dev_key = max(deviations, key=lambda k: deviations[k])
        max_dev_pct = deviations[max_dev_key] * 100.0

        assert max_dev_pct > 10.0, (
            f"{disease_name}: No parameter changed >10% from baseline. "
            f"Baseline vs last values: "
            + ", ".join(
                f"{k}={self.baseline[k]:.2f}→{tracked[k][-1]:.2f} ({deviations[k]*100:.1f}%)"
                for k in TRACKED_PARAMS
            )
        )

    @pytest.mark.parametrize("disease_name", list_diseases())
    def test_no_unbounded_divergence(self, disease_name):
        """
        Test 4: No disease causes unbounded parameter divergence.
        All tracked parameters stay finite throughout the simulation.
        """
        tracked, disease = self._attach_and_run(disease_name, severity="moderate")

        for key in TRACKED_PARAMS:
            series = tracked[key]
            assert len(series) > 0, f"{disease_name}: No samples collected for {key}"
            assert _all_finite(series), (
                f"{disease_name}: {key} contains non-finite values. "
                f"last 10: {series[-10:]}"
            )

        # Additional sanity checks: HR and MAP should be in physiologically plausible ranges
        hr_series = tracked["HR"]
        map_series = tracked["MAP"]

        # HR: 10-300 bpm plausible range (severe hyperkalemia/Addison's can approach ~10 bpm)
        for hr in hr_series:
            assert 10 <= hr <= 300, (
                f"{disease_name}: HR={hr:.0f} outside plausible range [10,300]"
            )

        # MAP: 30-200 mmHg plausible range
        for map_val in map_series:
            assert 30 <= map_val <= 200, (
                f"{disease_name}: MAP={map_val:.0f} outside plausible range [30,200]"
            )


@pytest.mark.suite_disease_blackbox
@pytest.mark.stability
class TestSeverityDoseResponse:
    """
    Test 3: Disease severity (mild/moderate/severe) produces dose-dependent
    parameter changes — more severe should cause larger deviations.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """Create a baseline healthy creature for each test."""
        self.vc = VirtualCreature(
            body_weight_kg=BODY_WEIGHT_KG,
            species=SPECIES,
            dt=DT,
        )
        for _ in range(STEPS_WARMUP):
            self.vc.step()
        self.baseline = {key: _get_param(self.vc, key) for key in TRACKED_PARAMS}

    def _run_disease_severity(self, disease_name: str, severity: str):
        """Run a disease with given severity, return max deviation across tracked params."""
        vc = VirtualCreature(body_weight_kg=BODY_WEIGHT_KG, species=SPECIES, dt=DT)
        for _ in range(STEPS_WARMUP):
            vc.step()

        disease = create_disease(disease_name, severity=severity)
        vc.attach_disease(disease)
        if not disease.active:
            disease.activate(0.0)

        tracked = {key: [] for key in TRACKED_PARAMS}
        for step in range(TOTAL_STEPS):
            vc.step()
            if step >= SAMPLE_START and (step - SAMPLE_START) % SAMPLE_INTERVAL == 0:
                for key in TRACKED_PARAMS:
                    tracked[key].append(_get_param(vc, key))

        max_dev = 0.0
        for key in TRACKED_PARAMS:
            dev = _max_abs_deviation(self.baseline[key], tracked[key])
            if dev > max_dev:
                max_dev = dev
        return max_dev

    @pytest.mark.parametrize("disease_name", list_diseases())
    def test_severity_produces_dose_response(self, disease_name):
        """
        Verify: severe >= moderate >= mild in terms of max % deviation from baseline.

        Only test for diseases that have all three severity presets.
        Skip diseases with only moderate/severe (e.g. sepsis only has moderate/severe).
        """
        import json
        from pathlib import Path

        config_path = Path(__file__).resolve().parents[1] / "data" / "ode_diseases.json"
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        disease_conf = config.get(disease_name, {})
        presets = disease_conf.get("severity_presets", {})
        has_mild = "mild" in presets
        has_moderate = "moderate" in presets
        has_severe = "severe" in presets

        if not (has_mild and has_moderate and has_severe):
            pytest.skip(
                f"{disease_name}: only has {[k for k in presets.keys()]} — "
                f"skip dose-response test (need mild/moderate/severe)"
            )

        dev_mild = self._run_disease_severity(disease_name, "mild")
        dev_moderate = self._run_disease_severity(disease_name, "moderate")
        dev_severe = self._run_disease_severity(disease_name, "severe")

        assert dev_mild <= dev_moderate * 1.2, (
            f"{disease_name}: mild dev ({dev_mild*100:.1f}%) should be <= moderate "
            f"({dev_moderate*100:.1f}%)"
        )
        assert dev_moderate <= dev_severe * 1.2, (
            f"{disease_name}: moderate dev ({dev_moderate*100:.1f}%) should be <= severe "
            f"({dev_severe*100:.1f}%)"
        )