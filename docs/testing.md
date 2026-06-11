# Testing Guide

Practical testing policy for the current kernel-first architecture.

If you only need to know which command to run, start with
[test-command-guide.md](test-command-guide.md).

If you need the detailed timing ledger and current hotspot inventory, use
[test-runbook.md](test-runbook.md).

This file is the policy/reference layer: why the suite is split, what each lane
means, and which kinds of validation belong where.

Last reviewed: 2026-06-10

## Core Rule

Test the layer you actually changed.

- kernel tests should validate physiology behavior in physical time
- application tests should validate orchestration, routing, timing policy, and workflow
- application tests should not silently pay full kernel cost unless the point of the test is real progression

## Time Rules In Tests

The project has three time notions:

- physical time: kernel truth
- scenario time: outer-layer action cost and case pacing
- presentation time: UI-only labels

Tests should be explicit about which one they are checking.

## Preferred App-Layer Pattern

When the test cares about workflow rather than real physiology progression, inject a fake runtime seam.

Use this for:

- `process_action()` bookkeeping
- action-cost accumulation
- exam latency queue behavior
- blocked / won / lost flow
- API routing that does not need real disease evolution

Representative files:

- `tests/test_time_management.py`
- `tests/test_game.py`
- `tests/test_pharmacology.py`
- `tests/test_interface.py`

## Real Progression Tests

Use the real engine only when the assertion depends on real physical evolution, such as:

- disease worsening over time
- death timer changes driven by physiology
- end-to-end report content after evolution
- solver-specific recovery or divergence behavior

Marker policy:

- `@pytest.mark.slow`: realistic progression or integration that should stay out of normal development loops
- `@pytest.mark.slower`: endurance, numerics, deterioration, or benchmark-style work

## Channel Model

The repo now uses explicit test channels through `--channel`.

It also supports optional thematic slicing through `--bundle`.

Base lane and bundle ownership now live in `tests/test_manifest.json`.
`tests/conftest.py` reads that manifest and applies runtime policy such as
`slow` / `slower` promotion.
Collected test files must now be explicitly present in the manifest; missing
ownership is treated as a collection-time error, not a silent fallback.

The assignment rule is:

- every collected test file has a base lane: `fast`, `core`, `heavy`, or `benchmark`
- `@pytest.mark.slow` promotes a test to at least `heavy`
- `@pytest.mark.slower` promotes a test to `benchmark`

This is the key improvement over the old marker-only workflow:

- mixed files no longer leak long-running tests into normal regression channels
- day-to-day commands no longer depend on large marker-based deselection noise
- heavy and benchmark work can now be split by subject without hand-written file lists

Registered channels:

- `fast`
- `fast-only`
- `core`
- `core-only`
- `heavy`
- `heavy-only`
- `benchmark`
- `research`
- `all`

Registered bundles currently include:

- `fast-engine`
- `fast-runtime`
- `core-engine`
- `core-runtime`
- `core-solver`
- `heavy-engine`
- `heavy-runtime`
- `benchmark-performance`
- `benchmark-performance-observational`
- `benchmark-solver`
- `benchmark-deterioration`
- `research-disease`
- `research-disease-phosphorus`
- `research-solver-drift`
- `research-solver-parity`
- `research-solver-radau`

For the exact generated lane/bundle inventory, see
[test-manifest-summary.md](test-manifest-summary.md).

## Lane Semantics

The lanes now mean:

- `fast`: smallest daily engineering gate
- `core`: normal cumulative regression gate layered on top of `fast`
- `heavy`: realistic integration and progression validation
- `benchmark`: lighter long-run validation that is still runnable as a deliberate engineering check
- `research`: ultra-heavy solver or disease validation that should not be part of ordinary development loops

The important current split is:

- `benchmark` keeps performance checks, Euler endurance, and untreated deterioration
- `research` owns DKA, phosphorus, Radau endurance, solver drift, and solver parity

For the actual commands to run, use [test-command-guide.md](test-command-guide.md).
For measured timings and bundle-level observations, use
[test-runbook.md](test-runbook.md).

## Legacy Marker Commands

Old commands still work, but they are no longer the preferred operational interface.

Recent concrete legacy output:

- `python -m pytest -m fast -q`
  - `441 passed, 495 deselected in 10.28s`

Why they are weaker:

- pytest still collects the full suite first
- output includes large `deselected` counts
- mixed-file behavior is harder to reason about

Use `--channel` instead.

## Current Heavy/Benchmark Reality

The suite is now cleaner, but it is not fully cheap.

Current hotspots:

- `tests/test_solver_numerics.py -q`
  - still too expensive for routine use
- `tests/test_solver_radau_endurance.py::test_10min_radau_no_nan -q`
  - exceeded `300s`
- `tests/test_solver_drift.py::test_solver_drift_bounded -q`
  - exceeded `240s`
- `tests/test_disease_endurance.py -q`
  - exceeded `300s`
- `tests/test_phosphorus_endurance.py -q`
  - `1 passed, 1 xfailed in 161.97s`

Current observation-only benchmark instability:

- `tests/test_performance_observational.py -q`
  - currently reports `xfail/xpass` instead of acting as a hard gate

Current failing assertions:

- single-step average wall time can exceed the local `1.0 ms` budget
- disease-path runtime exceeds the current hard `4.0s / 500 steps` budget

These facts are exactly why benchmark-style tests should stay outside the normal regression channels.

## Recommended Routing

Use this simple rule:

- editing small formulas, contracts, config validation, or seams -> run `fast`
- editing app/runtime/session/API behavior -> run `fast`, then `core`
- editing disease timing or engine progression semantics -> run `core`, then targeted `heavy`
- editing solver or performance internals -> run `core`, then targeted `heavy`, then targeted `benchmark`, and escalate to `research` only when you are intentionally validating the very expensive channels

## Files Intentionally Excluded From Collection

`tests/conftest.py` intentionally ignores:

- `collect_disease_progression.py`
- `debug_symptoms.py`
- `test_warmup_check.py`

These are diagnostic or research scripts, not ordinary regression gates.
