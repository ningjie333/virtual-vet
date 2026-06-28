"""
R3: Step ordering contracts.

Problem (root cause R3):
    10+ ordering constraints between step phases exist only as code
    comments and physical line order in `_step_euler` / `run_radau_step`.
    Reordering, refactoring, or adding new phases silently breaks
    invariants (e.g., Radau path was missing `snapshot_baselines`,
    `clear_baselines`, and `refresh_state_dicts` for the entire P0.2/R1
    era — undetected because no contract enforced their presence).

Solution:
    `StepGuard` tracks phase completion and state invariants per step
    invocation. Step functions assert prerequisites at entry and mark
    completion at exit. The guard is OPTIONAL — legacy callers (tests
    invoking helpers directly) can pass `guard=None` to skip checks.

Design philosophy:
    This is NOT a scheduler. The Euler/Radau drivers still sequence
    phases. `StepGuard` only catches ordering bugs at runtime, in
    tests, and during refactoring. It is the minimum viable contract
    layer — no decorator magic, no topological sort, no metaprogramming.

Two kinds of contract state:
    1. Phase progression — ordered list of completed phases
       (e.g., `PHASE_HEART_COMPUTE` before `PHASE_DISEASE`)
    2. State invariants — boolean flags
       (e.g., `INV_BASELINES_SNAPSHOTTED` before any `multiply` op)

Intentional divergences (Euler vs Radau) are documented via
`StepGuard.divergence_ok()` calls — these are NOT contract violations
but are recorded so the divergence is explicit and inspectable.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.simulation import VirtualCreature


# ── Canonical phase names (the contract vocabulary) ─────────────────────────
# These constants are the ONLY sanctioned spellings for phase markers.
# Using string literals elsewhere is allowed but discouraged — import
# these constants for type-checked call sites.

# Pre-organ dispatch
PHASE_PRE_DISPATCH = "pre_dispatch"          # events + lifecycle + blood_loss
PHASE_TOX = "tox"                            # toxicology.compute()
PHASE_PHARMA = "pharma"                      # pharmacology.compute()
PHASE_HEART_COMPUTE = "heart_compute"        # heart.compute() OR solve_ivp unpack
PHASE_DISEASE = "disease"                    # disease modules (Euler: pre-organ; Radau: post-coupling)
PHASE_LUNG_COMPUTE = "lung_compute"          # lung.compute()
PHASE_KIDNEY_COMPUTE = "kidney_compute"      # kidney.compute()
PHASE_GUT_COMPUTE = "gut_compute"            # gut.compute()

# Organ compute chain (liver → endocrine → coagulation → lymphatic → neuro)
PHASE_ORGAN_CHAIN = "organ_chain"

# Immune — NOTE: ordering diverges between Euler (before coupling) and
# Radau (after coupling). See `mark_immune()` for divergence tracking.
PHASE_IMMUNE = "immune"

# Coupling — R4: Euler path uses a 2-substep Gauss-Seidel relaxation.
#   substep 1 (Step 4.95): reads PREVIOUS step's published signals (lagged)
#   substep 2 (Step 8):    reads FRESH signals just published by run_coupling
# Both substeps are required for Euler stability (twin-run proven; removing
# substep 1 flips blood_loss_severe from PASS to FAIL). Radau path uses
# intra-step Newton iteration instead (see state_vector.unified_rhs).
PHASE_COUPLING_RESOLVE_1 = "coupling_resolve_1"   # Euler substep 1: lagged resolve
PHASE_PHYSIOLOGY_POST = "physiology_post"          # run_physiology_post (urine loss + fluid + sync)
PHASE_COUPLING_RESOLVE_2 = "coupling_resolve_2"   # Euler substep 2: fresh resolve (after publish)
PHASE_COUPLING_PUBLISH = "coupling_publish"        # run_coupling completion (publish + resolve_2 + refresh)

# Post-coupling
PHASE_ORGAN_HEALTH_TRACK = "organ_health_track"    # organ_health.track()
PHASE_ORGAN_HEALTH_APPLY = "organ_health_apply"    # apply organ_health factor
PHASE_REFRESH_DICTS = "refresh_dicts"              # refresh_state_dicts (R1)

# Final
PHASE_HISTORY = "history"                          # _record_history()
PHASE_TIME_ADVANCE = "time_advance"                # current_time_s += dt

# ── State invariants (booleans, not ordered) ─────────────────────────────────
INV_BASELINES_SNAPSHOTTED = "baselines_snapshotted"
INV_BASELINES_CLEARED = "baselines_cleared"

# ── Known intentional divergences (Euler vs Radau) ───────────────────────────
# These are NOT violations — they are documented mathematical differences
# between explicit (Euler) and implicit (Radau) solver paths.
DIVERGENCE_IMMUNE_ORDER = "immune_order"          # Euler: immune before coupling; Radau: after
DIVERGENCE_DISEASE_ORDER = "disease_order"         # Euler: disease before organ compute; Radau: after coupling
DIVERGENCE_COUPLING_RESOLVE_COUNT = "resolve_count"  # Euler: 2x resolve; Radau: 1x
DIVERGENCE_CHEMORECEPTOR_LAG = "chemoreceptor_lag"  # Euler: 1-step lag (Gauss-Seidel); Radau: integrated
DIVERGENCE_ORGAN_HEALTH_MECHANISM = "organ_health_mechanism"  # Euler: setattr; Radau: apply_factor multiply


class StepContractError(RuntimeError):
    """Raised when a step ordering contract is violated.

    Catch this in tests to assert contract enforcement. In production,
    it indicates a step-driver bug (missing phase or wrong order).
    """


class StepGuard:
    """Tracks phase progression and state invariants for one step invocation.

    Lifecycle:
        guard = StepGuard(label="euler")
        guard.require(PHASE_HEART_COMPUTE)         # entry check
        guard.mark(PHASE_DISEASE)                  # exit marker
        guard.set_invariant(INV_BASELINES_SNAPSHOTTED)
        guard.require_invariant(INV_BASELINES_SNAPSHOTTED)
        guard.reset()                                # next step

    All methods are no-ops if the guard is in "disabled" mode (rare; used
    only by legacy test helpers that intentionally bypass contracts).
    """

    def __init__(self, label: str = "step", *, enabled: bool = True):
        self.label = label
        self.enabled = enabled
        self._phases: "OrderedDict[str, bool]" = OrderedDict()
        self._invariants: dict[str, bool] = {}
        self._divergences: list[tuple[str, str]] = []  # (name, reason)

    # ── phase progression ────────────────────────────────────────────────
    def mark(self, phase: str) -> "StepGuard":
        """Record that `phase` has completed. Idempotent."""
        if not self.enabled:
            return self
        self._phases[phase] = True
        return self

    def has(self, phase: str) -> bool:
        return self._phases.get(phase, False)

    def require(self, *phases: str) -> "StepGuard":
        """Assert all `phases` have run. Raises StepContractError if any missing."""
        if not self.enabled:
            return self
        missing = [p for p in phases if not self.has(p)]
        if missing:
            raise StepContractError(
                f"[{self.label}] contract violated: requires phases {missing}, "
                f"completed = {list(self._phases.keys())}"
            )
        return self

    def require_not(self, *phases: str) -> "StepGuard":
        """Assert that `phases` have NOT run yet (precondition)."""
        if not self.enabled:
            return self
        already = [p for p in phases if self.has(p)]
        if already:
            raise StepContractError(
                f"[{self.label}] contract violated: phases {already} already ran, "
                f"but this step must run BEFORE them. completed = {list(self._phases.keys())}"
            )
        return self

    # ── state invariants ─────────────────────────────────────────────────
    def set_invariant(self, name: str, value: bool = True) -> "StepGuard":
        if not self.enabled:
            return self
        self._invariants[name] = value
        return self

    def has_invariant(self, name: str) -> bool:
        return self._invariants.get(name, False)

    def require_invariant(self, *names: str) -> "StepGuard":
        """Assert all named invariants are set. Raises if any missing."""
        if not self.enabled:
            return self
        missing = [n for n in names if not self.has_invariant(n)]
        if missing:
            raise StepContractError(
                f"[{self.label}] contract violated: requires invariants {missing}, "
                f"current invariants = {dict(self._invariants)}"
            )
        return self

    def require_invariant_not(self, *names: str) -> "StepGuard":
        """Assert named invariants are NOT set (e.g., snapshot before clear)."""
        if not self.enabled:
            return self
        already = [n for n in names if self.has_invariant(n)]
        if already:
            raise StepContractError(
                f"[{self.label}] contract violated: invariants {already} already set, "
                f"but this step must run BEFORE them."
            )
        return self

    # ── intentional divergences (Euler vs Radau) ─────────────────────────
    def divergence_ok(self, name: str, reason: str) -> "StepGuard":
        """Record an intentional divergence between solver paths.

        Use this to document WHY a phase ordering differs between Euler
        and Radau. The divergence is recorded (not raised) so it can be
        inspected via `guard.divergences()` for auditing.
        """
        if not self.enabled:
            return self
        self._divergences.append((name, reason))
        return self

    def divergences(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._divergences)

    # ── introspection ───────────────────────────────────────────────────
    def completed_phases(self) -> tuple[str, ...]:
        return tuple(self._phases.keys())

    def invariants(self) -> dict[str, bool]:
        return dict(self._invariants)

    def reset(self) -> None:
        """Clear all state for the next step invocation."""
        self._phases.clear()
        self._invariants.clear()
        self._divergences.clear()

    def __repr__(self) -> str:
        return (
            f"StepGuard(label={self.label!r}, enabled={self.enabled}, "
            f"phases={list(self._phases.keys())}, "
            f"invariants={dict(self._invariants)}, "
            f"divergences={len(self._divergences)})"
        )
