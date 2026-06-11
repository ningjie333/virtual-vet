# Test Constraint Audit

Constraint-strength audit for the current test suite.

Last reviewed: 2026-06-10

## Recent Progress

Since the previous audit pass, several previously weak or misleading coupling
checks were upgraded:

- `tests/test_coupling.py` now validates exact resolved command values for:
  - `renin_activity=2.0 -> heart.SVR multiply 1.4`
  - `MAP=70 mmHg -> kidney.GFR multiply 30/41`
- those commands are now also applied in-test and verified against the expected
  downstream parameter change
- `tests/test_cross_module_coupling.py` now uses a severe hemorrhage scenario
  with explicit hypotension, renin, SVR, and GFR-collapse windows instead of
  only checking that “something increased above zero”
- coupling config validation now rejects:
  - unknown target paths
  - unknown runtime source signals
  - unknown expression identifiers in `condition` / `fn`

This does not make the coupling layer “clinical-grade”, but it does remove a
meaningful amount of false confidence from the previous command-exists-only
checks.

Recent outer-layer contract cleanup also improved the app/workflow side:

- `tests/test_game.py` no longer accepts “any valid phase enum” for the
  moderate-ARF fixture; it now checks the concrete phase produced by that
  fixture
- `tests/test_scenarios.py` no longer treats moderate-pneumonia phase as “any
  worsening-or-worse” bucket; it checks the fixture's concrete current phase
- scenario constant tests in `tests/test_scenarios.py` and
  `tests/test_interface.py` now validate exact `cli_daemon.SCENARIOS` event
  payloads instead of only checking that an event exists
- selected interface tests now assert concrete known case/treatment identities
  and exact action time bookkeeping instead of only `len(...) > 0` or
  `time_elapsed_min > 0`

These are still outer-contract tests, not kernel-truth tests, but they now
carry more regression signal and less false reassurance.

Recent kernel-level cleanup removed two sources of false deterioration:

- `src/heart.py` no longer integrates sympathetic / parasympathetic first-order
  state with a coarse-step explicit Euler update that can numerically diverge
  when `dt` exceeds the fastest time constant; it now uses a stable first-order
  relaxation update for the outer Euler path
- `src/simulation.py` no longer calls `disease.compute(dt, ...)` twice per
  Euler step, which had been double-advancing disease state and double-applying
  disease outputs inside one physical time slice

These changes materially alter several former “moderate disease becomes
moribund within ~2 minutes” behaviors, and they should be interpreted as bug
fixes to the simulation path rather than test loosening.

## Purpose

This document does not ask only:

- does a test exist
- does it pass
- is it slow or fast

It asks a stricter question:

- if the kernel or outer workflow becomes wrong, will this test actually ring the alarm

That is the standard that matters for a kernel-first, clinically credibility-seeking project.

## Audit Rubric

Tests are grouped into five constraint levels.

### `Strong`

High alarm value.

- checks exact formulas, exact invariants, exact mappings, or tight quantitative relationships
- failure strongly implies a real bug
- hard to satisfy accidentally

### `Useful`

Good regression value, but not full scientific evidence.

- checks direction, monotonicity, boundedness, or meaningful integration outcomes
- can catch real regressions
- still leaves room for model drift or weak calibration

### `Weak`

Some value, but easy to pass while behavior is still wrong.

- mostly shape checks, existence checks, loose ranges, or “did not crash”
- better than nothing, but should not be mistaken for credibility evidence

### `Misleading`

Looks stronger than it is.

- test names or comments imply validation strength that the actual assertion does not support
- can create false confidence

### `Missing Alarm`

Important failure modes are not meaningfully guarded at all, or current tests are too weak to detect them.

## Executive Summary

The suite is not uniformly weak. It already contains several genuinely valuable constraint families:

- exact formula and invariant tests
- exact protocol / mapping tests
- exact persistence and schema tests
- some short-horizon numerical parity tests

But there is also a large second layer of tests that pass while providing much less protection than their names suggest:

- many interface and game tests validate response shape, not semantic correctness
- several disease and coupling tests validate “something moved” instead of validating the right magnitude or trajectory
- many lifecycle “literature” tests validate reference data presence or internal config consistency, not real engine agreement with literature
- some endurance / survival tests are expensive but still weakly asserted
- performance tests are engineering budgets, not principled or externally justified constraints

So the honest overall conclusion is:

- the suite is good as a mixed engineering safety net
- it is not yet a trustworthy clinical-credibility gate
- some passed tests likely hide important model-quality problems because their assertions are too loose

## What Is Already Strong

These areas have real alarm value and should be preserved.

### Exact formulas and low-level physiology math

Examples:

- `tests/test_blood.py`
- `tests/test_lung.py`
- `tests/test_kidney.py`
- `tests/test_coupling_lag_state.py`

Why these are strong:

- they check explicit equations or very tight numeric expectations
- they often compare against analytically expected values
- they are hard to satisfy if the implementation drifts materially

Representative strong constraints:

- blood oxygen content formula in `test_blood.py`
- kidney GFR and sodium-balance relationships in `test_kidney.py`
- Van der Pol lag-state convergence and dt invariance in `test_coupling_lag_state.py`
- pH / saturation / diffusion directionality checks in `test_lung.py`

Verdict:

- `Strong`

### Exact protocol / mapping / mutation mechanics

Examples:

- `tests/test_factor_command.py`
- `tests/test_pharmacology_factor_commands.py`
- `tests/test_blood_volume_conservation.py`
- `tests/test_session_persistence.py`
- `tests/test_config_validation.py`

Why these are strong:

- they verify exact write paths, exact operation semantics, exact schema behavior, or exact invariants
- many of them would fail immediately on real architectural drift

Representative strong constraints:

- `apply_factor()` multiply/add/set semantics
- `_PARAM_PATHS` reachability on `VirtualCreature`
- blood volume staying synchronized between heart and blood compartments
- database CRUD / ordering / foreign-key behavior
- config schema rejection for invalid structures

Verdict:

- `Strong`

### Short-horizon solver parity concept

Examples:

- `tests/test_solver_numerics.py::TestEulerRadauParity`

Why this is strong in principle:

- cross-solver parity is a deep kernel constraint
- if two numerical methods solving the same system diverge materially on short windows, that is a serious signal

But:

- the heavy runtime means this family is not yet a practical everyday guard

Verdict:

- `Strong conceptually`
- `Operationally incomplete` because some relevant heavier numerics channels are too expensive to run routinely

## Useful But Not Yet Credibility-Grade

These tests help, but they do not yet prove clinical or physiological trustworthiness.

### Organ and subsystem directionality tests

Examples:

- `tests/test_heart.py`
- `tests/test_neuro.py`
- `tests/test_immune.py`
- `tests/test_endocrine.py`
- `tests/test_organ_health.py`
- `tests/test_cross_module_coupling.py`

Strength:

- they often validate directionality, thresholds, or plausible response ordering
- they can catch regressions in causal sign

Weakness:

- many use broad ranges rather than calibrated target windows
- many validate “lower than baseline” or “greater than zero”, which is not enough for clinical credibility

Representative examples:

- acidosis reduces MAP or SV in `test_heart.py`
- ARF raises potassium in `test_cross_module_coupling.py`
- immune activation increases cytokines in `test_immune.py`

Verdict:

- `Useful`

### Disease module progression tests

Examples:

- `tests/test_diseases.py`
- `tests/test_disease_endurance.py`
- `tests/test_phosphorus_endurance.py`

Strength:

- they check monotonic progression, severity ordering, and some integration effects
- they are closer to natural-history validation than most app tests

Weakness:

- many assertions are directional only
- only a minority check quantitative targets
- long-horizon disease credibility is still thin and expensive

Examples of useful checks:

- severe progresses faster than mild
- disease reduces diffusion / GFR multipliers
- phosphorus poisoning endurance catches very long-run stability issues

Verdict:

- `Useful`
- not yet enough for “complete disease course credibility”

## Weak Or Mostly Contract-Shape Tests

These should stay, but they should not be counted as kernel evidence.

### Interface and API contract tests

Examples:

- `tests/test_interface.py`
- parts of `tests/test_pharmacology.py`

Strength:

- very good for route stability, status-code behavior, JSON shape, session isolation, and request flow

Weakness:

- many assertions are of the form:
  - field exists
  - status code is not 500
  - list is non-empty
  - response contains expected keys
- these tests often use fake advancers and coarse `dt`, which is correct for app tests but means they are not kernel validation

Verdict:

- `Useful` for app contracts
- `Weak` as physiological evidence

### Game-layer workflow tests

Examples:

- large parts of `tests/test_game.py`
- `tests/test_scenarios.py`
- `tests/test_time_management.py`
- `tests/test_action_runtime_seam.py`

Strength:

- good for action cost bookkeeping, diagnosis flow, result routing, runtime injection seams, and scenario policy

Weakness:

- many checks are shape or bookkeeping checks
- many do not verify that the reported medical meaning is actually right
- fake advancers intentionally bypass the kernel, so these tests should never be cited as physiology evidence

Verdict:

- `Useful` for orchestration
- `Weak` for kernel truth

### Boundary and no-crash tests

Examples:

- `tests/test_boundary.py`
- parts of `tests/test_simulation.py`

Strength:

- catches explosions, NaN/Inf, clamp breakage, and some catastrophic instability

Weakness:

- “did not crash” is a low bar
- clamped values can hide model pathology
- a wrong but bounded model can still pass

Verdict:

- `Useful` as safety rails
- `Weak` as correctness evidence

## Misleading Tests: Passed But Low Alarm Value

These deserve special attention because they can pass while serious problems remain.

### `tests/test_untreated_deterioration.py`

Previous problem:

- it used an almost tautological phase assertion
- it was described like a survival/death test while only running 60 seconds

Current status:

- now reframed honestly as a 60-second untreated-deterioration test
- now compares disease cases against matched healthy controls
- now asserts disease-specific magnitude windows instead of phase tautologies

Remaining limitation:

- it is still not a true survival or endpoint-window validation file

Verdict:

- improved from `Misleading` to `Useful`
- still should not be over-credited as true mortality validation

### `tests/test_species_specific.py::test_pneumonia_raises_hr_in_all_species`

Current key assertion:

- `assert vc.heart.heart_rate > 0`

Problem:

- this does not verify disease effect
- a completely inert disease model would still likely pass as long as HR remains positive

Verdict:

- `Misleading`

### Many coupling integration tests in `tests/test_coupling.py`

Typical patterns:

- `current_time_s > 0`
- signal exists
- command list length `>= 1`

Problem:

- proves the pipeline runs
- does not prove the coupling magnitude, sign, or downstream physiological consequence is right

Verdict:

- `Weak to Misleading` if interpreted as physiology validation

Update:

- this section is now only partially true
- several core coupling tests have been upgraded to exact command-value checks
  and exact post-application effect checks
- the remaining weak portion is mainly:
  - initialization / signal-exists assertions
  - “pipeline runs” assertions

### HR “error-driven” disease tests in `tests/test_diseases.py`

Examples:

- pneumonia HR offset test
- ARF HR offset test

Current key assertion:

- `assert hr_offset > 0.0`

Problem:

- comments describe a specific quantitative formula
- assertion only checks sign, not the claimed formula

This is exactly the kind of passed test that can hide implementation drift.

Verdict:

- `Misleading`

### Large portions of `tests/test_lifecycle_literature.py`

There are two different things mixed together:

- reference-data integrity
- engine-vs-literature validation

Many current tests are actually the first kind:

- string presence in reference JSON
- exact constant presence in config
- checking that documented PMIDs exist

Those are useful documentation guards, but they do not validate physiological behavior of the running engine.

Verdict:

- `Strong` as documentation integrity
- often only `Weak` or `Misleading` if interpreted as literature-backed engine validation

### `tests/test_gate_contract.py`

This file tests the existence of tests, asserts, and markers.

Useful:

- prevents obvious suite rot

Not useful for:

- model truth
- numerical validity
- clinical plausibility

Verdict:

- `Weak`

## Passed Tests That May Still Hide Real Problems

This is the most important practical section.

### Shape checks can mask semantic breakage

Examples:

- `test_interface.py`
- `test_game.py`

If a route still returns JSON with the expected keys, these tests may pass even when:

- the medical phase is wrong
- the summary text is semantically wrong
- the underlying physiology is no longer credible

### Range checks can mask model drift

Examples:

- many heart / lung / coupling / simulation tests

If a value is only required to stay inside a broad “physiological” envelope, the system can drift substantially while still passing.

This is especially risky for:

- compensatory loops
- chronic disease trajectories
- lifecycle aging effects

### Shared-config self-consistency can mask wrong science

Examples:

- `test_lifecycle_literature.py`
- some config-driven disease tests

If the implementation and the reference constants come from the same internal JSON or same internal assumptions, the test can prove internal consistency without proving external correctness.

### Heavy tests can still be low-yield

Examples:

- `test_untreated_deterioration.py`
- some endurance checks with broad final assertions

Runtime cost alone does not make a test strong.

A long test that only checks “no NaN” or “phase is one of allowed values” can consume minutes while guarding very little.

## Area-By-Area Audit

### 1. Kernel formula and invariant layer

Files:

- `test_blood.py`
- `test_lung.py`
- `test_kidney.py`
- `test_factor_command.py`
- `test_pharmacology_factor_commands.py`
- `test_blood_volume_conservation.py`
- `test_coupling_lag_state.py`

Assessment:

- best part of the suite
- should remain the backbone of the daily kernel gate

Overall verdict:

- mostly `Strong`

### 2. Subsystem physiology behavior layer

Files:

- `test_heart.py`
- `test_fluid.py`
- `test_neuro.py`
- `test_immune.py`
- `test_endocrine.py`
- `test_liver.py`
- `test_lymphatic.py`
- `test_organ_health.py`

Assessment:

- meaningful regression value
- many directionality checks are good
- many thresholds remain broad
- not enough exact calibration anchors

Overall verdict:

- mostly `Useful`

### 3. Disease and natural-history layer

Files:

- `test_diseases.py`
- `test_disease_endurance.py`
- `test_phosphorus_endurance.py`
- `test_simulation.py`
- `test_untreated_deterioration.py`

Assessment:

- mixed quality
- some good mechanism checks
- some weak sign-only assertions
- survival test currently underpowered relative to its runtime

Overall verdict:

- mixed `Useful`, `Weak`, and `Misleading`

### 4. Solver and numerical validation layer

Files:

- `test_solver_numerics.py`
- `test_solver_endurance.py`
- `test_solver_radau_endurance.py`
- `test_solver_drift.py`
- long-run stability parts of `test_boundary.py`

Assessment:

- conceptually critical
- current structure is right
- operational cost is still too high in several channels
- some heavy checks remain hard to run regularly

Overall verdict:

- `Strong conceptually`
- currently `under-exercised`

### 5. Lifecycle and literature layer

Files:

- `test_lifecycle.py`
- `test_lifecycle_v2.py`
- `test_lifecycle_literature.py`
- `test_species_specific.py`

Assessment:

- mixed documentation, config, and engine behavior checks in one conceptual bucket
- some true engine constraints exist
- many tests validate constants or relations chosen by the project itself
- several do not independently validate literature fidelity

Overall verdict:

- mixed `Useful`, `Weak`, and `Misleading`

### 6. Coupling layer

Files:

- `test_coupling.py`
- `test_cross_module_coupling.py`

Assessment:

- validates that coupling machinery exists and runs
- now includes some exact command-value checks and exact post-application
  mutation checks
- still has limited quantitative validation of full downstream physiological
  trajectories after coupling acts inside the closed loop
- should continue evolving from “command exists” toward “physiology changed by
  expected amount/window over time”

Overall verdict:

- currently `Useful`
- stronger than before for plumbing and command semantics
- still not yet `Strong` for full coupling correctness

### 7. App, workflow, and persistence layer

Files:

- `test_interface.py`
- `test_game.py`
- `test_scenarios.py`
- `test_time_management.py`
- `test_action_runtime_seam.py`
- `test_session_persistence.py`

Assessment:

- strong for outer contracts and architecture seams
- not intended to validate kernel credibility
- should remain clearly documented as outer-layer tests

Overall verdict:

- `Strong` for interface/persistence contracts
- `Weak` if misused as physiology evidence

### 8. Performance layer

Files:

- `test_performance.py`

Assessment:

- useful regression sentinel
- not externally justified
- sensitive to machine/runtime state
- not a reliable truth criterion

Overall verdict:

- `Useful` as engineering guardrail
- `Weak` as architectural or scientific evidence

## Highest-Priority Missing Alarms

These are the biggest gaps if the goal is a clinically credible kernel.

### Missing 1: Quantitative disease trajectory checkpoints

What is missing:

- disease-specific expected windows at multiple physical times
- not just “worse than before”, but approximate expected magnitude bands

Examples needed:

- pneumonia at 5 min / 30 min / 2 h
- ARF at 10 min / 60 min / 6 h
- phosphorus poisoning early / middle / late course

### Missing 2: Intervention response truth tables

What is missing:

- after intervention X, variable Y should improve or worsen by Z amount within T time

Examples:

- fluid bolus should change MAP / CVP / urine trajectory within expected windows
- epinephrine should alter HR / SVR / MAP with expected onset and decay
- oxygen / ventilation changes should modify blood gases on plausible timescales

### Missing 3: Cross-module quantitative conservation

What is missing:

- broader conservation-like checks beyond blood volume sync

Possible future targets:

- acid-base bookkeeping consistency
- electrolyte/mass balance over time windows
- fluid redistribution accounting

### Missing 4: Quantitative coupling effect tests

What is missing:

- not just that RAAS emits commands
- but that a defined renin input produces a bounded expected SVR / volume response

### Missing 5: Better “clinical endpoint” validation

Current problem:

- some death / phase / survival tests do not assert clinically meaningful endpoint windows

What is needed:

- endpoint timing windows
- endpoint criterion windows
- reversible vs irreversible transition checks

## Recommended Refactor Of The Test Philosophy

### A. Keep three labels in your head

Every test should be explicitly understood as one of:

- `kernel truth`
- `engineering safety`
- `outer contract`

The current suite contains all three, but they are still too easy to mentally mix together.

### B. Split “literature integrity” from “engine literature validation”

Current problem:

- one file can make both claims at once

Better split:

- reference JSON integrity tests
- engine-against-reference behavior tests

Those are different kinds of evidence.

### C. Replace sign-only disease assertions with magnitude-window assertions

Examples to upgrade:

- `hr_offset > 0`
- `heart_rate > 0`
- `confidence > 0.2`
- `phase in (...)`

These are too easy to satisfy.

### D. Demote low-yield heavy tests or rewrite them

Most obvious target:

- `tests/test_untreated_deterioration.py`

It has now partially improved by becoming an honest short-horizon
deterioration file.

It still should eventually either:

- become a real endpoint-window validation file
- or stay explicitly scoped as a short-horizon deterioration suite

## Concrete Priority List

### `P0` Rewrite or demote misleading tests

Targets:

- `tests/test_untreated_deterioration.py`
- weak disease sign-only assertions in `tests/test_diseases.py`
- weak species disease assertions in `tests/test_species_specific.py`
- remaining command-exists-only coupling assertions in `tests/test_coupling.py`

### `P1` Create quantitative disease trajectory checkpoints

Goal:

- a sampled natural-history gold suite with sparse checkpoints and tolerance bands

This is the biggest missing piece for kernel credibility.

### `P1` Split lifecycle evidence into two suites

Split into:

- documentation/reference integrity
- engine behavior validation

### `P1` Add intervention-response validation

Goal:

- kernel should be tested not only for deterioration, but for clinically plausible response to treatment and support

### `P2` Formalize benchmark policy

For `test_performance.py`:

- define environment
- define statistics
- define whether it is hard gate or informational benchmark

## Bottom Line

The current suite is already valuable, but its value is uneven.

The parts with the highest real constraint strength are:

- exact formulas
- invariants
- protocol mechanics
- schema/persistence contracts
- some short-horizon numerical parity checks

The parts most likely to create false confidence are:

- heavy tests with weak final assertions
- sign-only disease assertions
- “exists / non-empty / > 0” style coupling checks
- lifecycle “literature” tests that validate reference presence more than engine truth
- app/API tests being mentally over-credited as kernel evidence

So the correct interpretation today is:

- the suite is a decent engineering safety net
- it is not yet a rigorous clinical-credibility validation framework
- several passed tests should be upgraded before they are trusted as evidence that the kernel is “right”
