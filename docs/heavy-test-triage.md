# Heavy Test Triage

Practical classification of the repo's long-running physiology tests.

Last reviewed: 2026-06-10

## Core Principle

Long-running tests are expected in a physiology engine.

They are justified when they validate things that short tests cannot:

- long-horizon numerical stability
- slow multi-timescale physiological feedback
- disease natural history or endpoint windows
- solver equivalence over meaningful physical time

The real question is not "should long tests exist?" but:

- is the assertion strong enough to justify the runtime?
- is the test placed in the right lane?
- is the test being interpreted correctly?

## Category 1: Keep As Hard Long Validation

These are expensive, but they test something that a clinically serious kernel
really does need.

| Test area | Current file(s) | Why it is worth keeping | Current caution |
|---|---|---|---|
| Long-horizon solver stability | `tests/test_solver_endurance.py`, `tests/test_solver_radau_endurance.py`, `tests/test_solver_drift.py` | catches NaN/Inf, drift, and Euler/Radau divergence that only appears over minutes of physical time | should stay benchmark-only and split by runtime |
| Solver parity concept | `tests/test_solver_numerics.py` | "same ODE system, two solvers" is a high-value architecture contract | current implementation is too expensive; keep the concept, redesign the sampling strategy |
| Long disease natural-history regressions | `tests/test_disease_endurance.py` | DKA blood-volume crash and death-window regressions are exactly the kind of slow failure a kernel must guard | needs stronger disease-specific endpoint rationale over time |
| Toxicology recovery time-course | `tests/test_simulation.py` slower cocaine tests | tests a real temporal claim: one pathway decays slower than another | belongs to heavy/benchmark physiology validation, not app smoke |
| Cross-module causal chains | `tests/test_cross_module_coupling.py` | verifies multi-organ logic like ARF -> hyperkalemia and blood loss -> RAAS -> SVR | runtime is justified because the assertions are mechanism-focused |
| Species-invariant disease effect | `tests/test_species_specific.py` slow disease test | protects that disease directionality survives species parameterization | keep targeted and narrow |

## Category 2: Keep, But As Engineering Regression Rather Than Clinical Evidence

These are useful and should remain, but they should not be over-credited as
clinical validation.

| Test area | Current file(s) | Why keep it | Why it is not clinical evidence |
|---|---|---|---|
| Throughput and memory regression | `tests/test_performance.py` | catches gross runtime and memory regressions | these are engineering budgets, not physiology truth |
| Rapid-fire non-crash and history growth | `tests/test_engine_stability.py` | protects engine robustness and bookkeeping correctness | tells us nothing direct about clinical realism |
| Radau fallback | `tests/test_solver_fallback.py` | protects failure handling and continuity of engine time advancement | this is resilience, not physiology fidelity |
| Boundary/no-crash coverage | most of `tests/test_boundary.py` | valuable as safety net for extreme inputs and clamps | mostly robustness, not realism |
| Heavy app integration | slow parts of `tests/test_pharmacology.py`, `tests/test_scenarios.py`, `tests/test_time_management.py` | validates runtime composition and end-to-end flows | should not be cited as kernel credibility evidence |

## Category 3: Downgrade To Observation-Only

These are worth measuring, but they are too machine-sensitive or too
environment-sensitive to be treated as hard repository truths.

| Test area | Current file(s) | Reason to downgrade |
|---|---|---|
| Single-step wall-clock budget | `tests/test_performance_observational.py::test_step_execution_time_budget` | highly sensitive to local machine state and background load |
| Absolute disease-path wall-clock budget | `tests/test_performance_observational.py::test_disease_path_absolute_budget` | absolute seconds are not stable without a reference benchmark environment |

This downgrade has already started in the repo, and it is the right direction.

## Category 4: Rewrite Or Reposition

These are not necessarily useless, but their current name, file, lane, or
assertion strength is misleading enough that they should be revised.

| Test area | Current file(s) | Problem | Recommended fix |
|---|---|---|---|
| "Survival" file is not really survival | `tests/test_untreated_deterioration.py` | the file explicitly tests only 60 seconds of untreated divergence; it is not true survival or death-window validation | rename/reframe as untreated short-horizon deterioration, or replace with real endpoint-window survival tests |
| Long no-NaN boundary test is misfiled | `tests/test_solver_endurance.py::test_100min_euler_no_nan` | this is a long solver stability test and should live with solver endurance work, not boundary semantics | keep it in a dedicated solver/numerics benchmark file |
| Solver parity sampling is too expensive | `tests/test_solver_numerics.py` | concept is strong, but one full case can exceed 120 s; cost is too high for the current case matrix | reduce scenario count, shorten horizon, or compare sampled states instead of full heavy dual-step loops |
| Phosphorus long-horizon assertions are weak | `tests/test_phosphorus_endurance.py::TestPhosphorusPoisoningIntegration` | thresholds like `disease_map < baseline_map + 5.0` and `disease_ph < baseline_ph + 0.1` are directionally useful but weak for such expensive runs | keep isolated from DKA hard-gate checks and tighten to clinically interpretable endpoint windows or trajectory features |
| Slow app E2E tests can be over-read | slow sections in `tests/test_pharmacology.py` and `tests/test_scenarios.py` | they are useful, but their runtime can make them look like deep physiology validation when they are mostly orchestration checks | keep them as runtime/app validation and document them that way |

## Current High-Value Reading Of The Suite

If you want the strongest current long-test signal in this repo, the most
defensible tests are:

1. long solver endurance without NaN/Inf
2. bounded solver drift between Euler and Radau
3. DKA crash/death-time regressions
4. toxicology recovery ordering over time
5. explicit cross-module causal chains

If you want the weakest current long-test signal, the main risk areas are:

1. tests whose runtime is large but whose assertion is only directional
2. tests whose file name overclaims what is being validated
3. app-level E2E tests being mistaken for kernel-level evidence
4. hardware-sensitive wall-clock budgets being treated as scientific facts

## Recommended Next Actions

1. Keep solver endurance, parity, toxicology recovery, and DKA natural-history checks as explicit benchmark validation.
2. Rewrite `tests/test_untreated_deterioration.py` so the name and claim match the actual assertion.
3. Move the long no-NaN run out of `tests/test_boundary.py` into the solver stability family.
4. Tighten `phosphorus_poisoning` long-horizon assertions so the runtime buys stronger signal.
5. Continue treating absolute wall-clock budgets as observational until a benchmark policy defines machine, metric, and threshold semantics.
