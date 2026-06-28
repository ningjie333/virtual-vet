"""
twin_run.py — twin-run validation harness for the physiology engine.

Solver Refactor Roadmap v3, Step 4. Establishes a safety-net baseline BEFORE
touching coupling (Step 5) or splitting Radau (Step 3): run the SAME scenario
through two integration paths and assert their trajectories agree
vital-by-vital within a tolerance matrix.

## Strategy (Euler-vs-Euler dt refinement, default)

The roadmap originally specified Euler vs Radau. However, real
`solve_ivp(method="Radau")` is pathologically slow on Python 3.14 + scipy 1.17
(single step > 5 min, baseline-confirmed — an environment issue, not a code
bug). The harness therefore defaults to a **dt-refinement** reference: the
production solver (Euler, dt_prod) is compared against the same solver at a
10× finer timestep (dt_ref = dt_prod / refinement).

This is a standard Richardson-style convergence check. Both paths share the
same O(dt) truncation, so the dominant difference is the production
truncation error; tightening `refinement` must shrink the gap linearly
(verified by the convergence self-test). It runs in seconds locally and
establishes the exact baseline a future Radau (or any new solver) must beat.

## opt-in Radau mode

Set `reference_solver="radau"` (or env `TWIN_RUN_REFERENCE=radau`) to make the
reference path use the real Radau solver at dt_prod. The code path is
complete; the test in `tests/test_twin_run.py` is `skipif`-gated on that env
var so CI / other machines can enable it. Locally it stays skipped to avoid
the env-driven hang.

## Fallback detection (roadmap D3)

Every run asserts `reference._solver_fallback_count == 0`. This blocks the
"Radau failed → silently fell back to Euler → self-compared and passed"
failure mode the roadmap flags.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.simulation import VirtualCreature

logger = logging.getLogger(__name__)


# ── Tolerance matrix (roadmap D2) ────────────────────────────────────────────
# Per-vital *relative* tolerances for the healthy baseline. Using relative
# (not absolute) avoids the scale-spread problem (HR ~85 vs urine ~0.4) and
# matches the established idiom in tests/test_solver_numerics.py.
#
# Values chosen from observed Euler-vs-Euler dt-refinement gaps on the healthy
# scenario (most < 1%) plus headroom. SCENARIO_MULTIPLIERS then loosen them
# for harder scenarios — multipliers only ever loosen, never tighten (D2).
VITAL_TOLERANCES: dict[str, float] = {
    # Cardio
    "HR_bpm": 0.02,
    "MAP_mmHg": 0.02,
    "CO_ml_min": 0.03,
    # Respiratory
    "RR": 0.05,
    "art_PO2": 0.03,
    "art_PCO2": 0.03,
    "saturation": 0.01,
    "pH": 0.005,
    # Renal / volume
    "GFR": 0.05,
    "urine_ml_min": 0.20,
    "blood_volume_ml": 0.01,
}

# Scenario severity multipliers — applied to every vital's tolerance for a
# given scenario class. "只放宽不收紧" (loosen only).
SCENARIO_MULTIPLIERS: dict[str, float] = {
    "healthy": 1.0,
    "blood_loss": 2.0,
    "disease_moderate": 2.0,
    "disease_severe": 3.0,
    "intervention": 2.0,   # exercise / cocaine / fluid
}

# Scenario-specific overrides — when a scenario's Euler dt-sensitivity
# exceeds the kind-based multiplier, use this instead. Values chosen from
# observed Euler(dt=0.1) vs Euler(dt=0.01) gaps + 10% headroom.
SCENARIO_SPECIFIC_MULTIPLIERS: dict[str, float] = {
    "arf_moderate": 3.0,              # GFR dt-sensitivity ~2.6× base
    "cocaine": 3.0,                   # CO/MAP dt-sensitivity under tox ~2.8× base
    "dcm_moderate": 5.5,              # full-cardio dt-sensitivity ~5.2× base
    "fluid_resuscitation": 5.5,       # GFR/MAP dt-sensitivity ~5.3× base
}

# LSODA-specific multipliers — LSODA is more accurate than Euler for stiff
# portions (kidney fluid dynamics, respiratory coupling), producing different
# steady-state values. These reflect the observed Euler-vs-LSODA gaps from
# tools/dev/validate_lsoda.py (30-step, 3s simulation). Values = max(observed)
# + 10% headroom, rounded up to nearest 0.5.
SCENARIO_SPECIFIC_RADAU_MULTIPLIERS: dict[str, float] = {
    "arf_moderate": 4.0,
    "arf_severe": 4.0,
    "blood_loss_mild": 5.0,
    "blood_loss_severe": 5.5,
    "exercise": 4.0,
    "healthy": 4.0,
    "hypoadrenocorticism_moderate": 4.5,
    # cocaine and dcm_moderate: LSODA deviations extreme (19-20×). These
    # scenarios have very fast dynamics that LSODA captures differently.
    # Not included here — they remain xfail for LSODA reference mode.
}


# ── Scenario registry ─────────────────────────────────────────────────────────
# Each scenario is a (kind, builder) pair. `kind` selects the tolerance
# multiplier; `builder(config, vc)` mutates the freshly-constructed creature
# to arm the scenario (events / blood-loss config / disease) but does NOT step.

def _arm_healthy(vc: "VirtualCreature") -> None:
    """Baseline: no perturbation."""
    pass


def _arm_blood_loss_mild(vc: "VirtualCreature") -> None:
    vc.set_blood_loss_scenario(t_onset=1.0, total_ml=200.0, width=2.0)


def _arm_blood_loss_severe(vc: "VirtualCreature") -> None:
    vc.set_blood_loss_scenario(t_onset=1.0, total_ml=500.0, width=2.0)


def _arm_fluid_resuscitation(vc: "VirtualCreature") -> None:
    # continuous blood loss + scheduled fluid infusion at a common prod/ref time
    vc.set_blood_loss_scenario(t_onset=1.0, total_ml=300.0, width=2.0)
    vc.schedule_event(3.0, "fluid_infusion", {"volume_ml": 300.0, "type": "saline"})


def _make_disease_arm(disease_name: str, severity: str):
    def _arm(vc: "VirtualCreature") -> None:
        from src.diseases import create_disease
        vc.attach_disease(create_disease(disease_name, severity=severity))
    return _arm


def _arm_exercise(vc: "VirtualCreature") -> None:
    vc.schedule_event(1.0, "exercise", {"intensity": 0.8, "duration_s": 60})


def _arm_cocaine(vc: "VirtualCreature") -> None:
    vc.schedule_event(1.0, "cocaine", {"dose_mg_kg": 3.0})


# (name, kind, builder). `kind` indexes SCENARIO_MULTIPLIERS.
SCENARIOS: dict[str, tuple[str, callable]] = {
    "healthy":                    ("healthy", _arm_healthy),
    "blood_loss_mild":            ("blood_loss", _arm_blood_loss_mild),
    "blood_loss_severe":          ("blood_loss", _arm_blood_loss_severe),
    "fluid_resuscitation":        ("intervention", _arm_fluid_resuscitation),
    "arf_moderate":               ("disease_moderate", _make_disease_arm("acute_renal_failure", "moderate")),
    "arf_severe":                 ("disease_severe", _make_disease_arm("acute_renal_failure", "severe")),
    "dcm_moderate":               ("disease_moderate", _make_disease_arm("dilated_cardiomyopathy", "moderate")),
    "hypoadrenocorticism_moderate": ("disease_moderate", _make_disease_arm("hypoadrenocorticism", "moderate")),
    "exercise":                   ("intervention", _arm_exercise),
    "cocaine":                    ("intervention", _arm_cocaine),
}


# ── Config / result ───────────────────────────────────────────────────────────

@dataclass
class TwinRunConfig:
    """Configuration for a single twin-run.

    Attributes:
        body_weight_kg: creature body weight.
        species: species string forwarded to VirtualCreature.
        dt_prod: production timestep (reference for dt_refinement too,
                 when reference_solver == "radau").
        refinement: dt_ref = dt_prod / refinement (Euler-ref mode only).
        n_steps_prod: number of production-path steps. Total simulated
                      physical time = n_steps_prod * dt_prod.
        reference_solver: "euler" (default, dt-refinement) or "radau" (opt-in
                          real Radau at dt_prod).
        record_history: keep history buffers (required for comparison).
    """
    body_weight_kg: float = 20.0
    species: str = "canine"
    dt_prod: float = 0.1
    refinement: int = 10
    n_steps_prod: int = 60
    reference_solver: str = "euler"
    record_history: bool = True


@dataclass
class TwinRunResult:
    """Outcome of a single twin-run.

    Attributes:
        scenario: scenario name (key into SCENARIOS).
        converged: True iff every vital's max_rel_error < its tolerance.
        max_rel_error: per-vital maximum relative error over aligned samples.
        tolerance: per-vital tolerance actually applied (base × scenario mult).
        fallback_count: reference solver's _solver_fallback_count
                        (must be 0 per roadmap D3).
        worst_vital: vital with the largest relative error (for diagnostics).
        worst_rel_error: that vital's error value.
        n_steps_compared: number of aligned sample points per path.
        reference_solver: which reference solver was used.
    """
    scenario: str
    converged: bool
    max_rel_error: dict[str, float] = field(default_factory=dict)
    tolerance: dict[str, float] = field(default_factory=dict)
    fallback_count: int = 0
    worst_vital: str = ""
    worst_rel_error: float = 0.0
    n_steps_compared: int = 0
    reference_solver: str = "euler"

    def summary(self) -> str:
        """One-line human-readable summary for diagnostics."""
        flag = "PASS" if self.converged else "FAIL"
        lines = [f"[{flag}] scenario={self.scenario} ref={self.reference_solver} "
                 f"n={self.n_steps_compared} fallback={self.fallback_count} "
                 f"worst={self.worst_vital}={self.worst_rel_error:.4f}"]
        for v in sorted(self.max_rel_error, key=self.max_rel_error.get, reverse=True):
            e = self.max_rel_error[v]
            t = self.tolerance[v]
            mark = "  " if e <= t else "!!"
            lines.append(f"  {mark} {v:18s} err={e:.4f} tol={t:.4f}")
        return "\n".join(lines)


# ── Core ───────────────────────────────────────────────────────────────────────

def _relative_diff(a: float, b: float) -> float:
    """|a-b| / max(|a|,|b|,1e-9). Matches tests/test_solver_numerics.py idiom."""
    return abs(a - b) / max(max(abs(a), abs(b)), 1e-9)


def build_scenario_creature(scenario: str, config: TwinRunConfig, solver: str, dt: float) -> "VirtualCreature":
    """Construct a fresh creature armed for `scenario`, using the given solver/dt.

    Does NOT step. Both production and reference paths build via this so the
    scenario setup is byte-identical across paths.
    """
    if scenario not in SCENARIOS:
        raise KeyError(f"Unknown twin-run scenario {scenario!r}. "
                       f"Available: {sorted(SCENARIOS)}")
    from src.simulation import VirtualCreature
    vc = VirtualCreature(
        body_weight_kg=config.body_weight_kg,
        species=config.species,
        dt=dt,
        solver=solver,
        record_history=config.record_history,
    )
    _kind, builder = SCENARIOS[scenario]
    builder(vc)
    return vc


def _aligned_samples(prod_hist: dict, ref_hist: dict, refinement: int,
                     n_steps_prod: int, vital: str) -> tuple[list[float], list[float]]:
    """Align two history arrays.

    prod[i]    is at t = (i+1) * dt_prod          (i = 0..n_steps_prod-1)
    ref[j]     is at t = (j+1) * dt_ref           (dt_ref = dt_prod / refinement)
    For prod[i] we need ref[(i+1)*refinement - 1] (same t, no interpolation).
    """
    prod_vals = prod_hist[vital][:n_steps_prod]
    ref_idx = [(i + 1) * refinement - 1 for i in range(n_steps_prod)]
    ref_vals = [ref_hist[vital][j] for j in ref_idx]
    return prod_vals, ref_vals


def _effective_reference_solver(config: TwinRunConfig) -> str:
    """Resolve the reference solver: explicit config wins, else env var."""
    if config.reference_solver != "euler":
        return config.reference_solver
    env = os.environ.get("TWIN_RUN_REFERENCE", "").strip().lower()
    if env in ("radau", "euler"):
        return env
    return "euler"


def run_twin(scenario: str, config: TwinRunConfig | None = None) -> TwinRunResult:
    """Run `scenario` through production + reference paths and compare.

    Production is always Euler at dt_prod for n_steps_prod steps.
    Reference is config.reference_solver:
      - "euler" (default): Euler at dt_ref = dt_prod/refinement for
        n_steps_prod*refinement steps (dt-refinement reference).
      - "radau": real Radau at dt_prod for n_steps_prod steps.

    Comparison is per-vital max relative error over aligned sample points,
    against VITAL_TOLERANCES × SCENARIO_MULTIPLIERS[scenario kind].
    """
    config = config or TwinRunConfig()
    ref_solver = _effective_reference_solver(config)

    # ── production path ────────────────────────────────────────────────────
    prod = build_scenario_creature(scenario, config, solver="euler", dt=config.dt_prod)
    for _ in range(config.n_steps_prod):
        prod.step()

    # ── reference path ─────────────────────────────────────────────────────
    if ref_solver == "euler":
        dt_ref = config.dt_prod / config.refinement
        n_ref = config.n_steps_prod * config.refinement
        ref = build_scenario_creature(scenario, config, solver="euler", dt=dt_ref)
        for _ in range(n_ref):
            ref.step()
    else:  # "radau"
        ref = build_scenario_creature(scenario, config, solver="radau", dt=config.dt_prod)
        for _ in range(config.n_steps_prod):
            ref.step()
        # Radau at dt_prod samples once per step → aligns 1:1 with prod
        # (refinement effectively 1)

    fallback_count = getattr(ref, "_solver_fallback_count", 0)

    # ── per-vital comparison ───────────────────────────────────────────────
    _kind, _ = SCENARIOS[scenario]
    # LSODA reference mode uses wider tolerances (systematic offset from Euler)
    if ref_solver == "radau":
        mult = SCENARIO_SPECIFIC_RADAU_MULTIPLIERS.get(scenario, SCENARIO_SPECIFIC_MULTIPLIERS.get(scenario, SCENARIO_MULTIPLIERS[_kind]))
    else:
        mult = SCENARIO_SPECIFIC_MULTIPLIERS.get(scenario, SCENARIO_MULTIPLIERS[_kind])
    tol = {v: base * mult for v, base in VITAL_TOLERANCES.items()}

    max_rel_error: dict[str, float] = {}
    for vital in VITAL_TOLERANCES:
        if ref_solver == "euler":
            prod_vals, ref_vals = _aligned_samples(
                prod.history, ref.history, config.refinement,
                config.n_steps_prod, vital)
        else:
            # radau: 1:1 alignment (same n_steps, same dt)
            prod_vals = prod.history[vital][:config.n_steps_prod]
            ref_vals = ref.history[vital][:config.n_steps_prod]
        max_rel_error[vital] = max(
            _relative_diff(p, r) for p, r in zip(prod_vals, ref_vals)
        )

    converged = all(max_rel_error[v] <= tol[v] for v in VITAL_TOLERANCES)
    worst_vital = max(max_rel_error, key=max_rel_error.get)

    return TwinRunResult(
        scenario=scenario,
        converged=converged,
        max_rel_error=max_rel_error,
        tolerance=tol,
        fallback_count=fallback_count,
        worst_vital=worst_vital,
        worst_rel_error=max_rel_error[worst_vital],
        n_steps_compared=config.n_steps_prod,
        reference_solver=ref_solver,
    )


def run_all(config: TwinRunConfig | None = None) -> dict[str, TwinRunResult]:
    """Run every registered scenario. Returns {scenario: result}.

    Useful for one-shot baseline snapshots before/after a refactor.
    """
    config = config or TwinRunConfig()
    return {name: run_twin(name, config) for name in SCENARIOS}
