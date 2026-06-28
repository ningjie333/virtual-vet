# Architecture

Authoritative architecture note for the current project shape.

Last reviewed: 2026-06-09

## Core Principle

The physiology kernel is the product core.

The game, case orchestration, diagnosis workflow, time budgeting, session persistence, and UI are outer application layers. They may drive the kernel, but they must not redefine kernel time semantics, solver meaning, or disease rate definitions for gameplay convenience.

This document is intentionally concise and authoritative.

Use it for:

- current layer boundaries
- dependency direction
- time semantics
- testing tiers

Use [kernel-first-design.md](kernel-first-design.md) when you want the fuller
design narrative that connects these rules into one story.

## Layer Model

### Kernel

Location:

- `src/simulation.py`
- organ modules under `src/`
- `src/diseases/`
- `src/engine/`
- `src/common_types.py`
- `src/parameters.py`

Responsibilities:

- evolve physiological state in physical time
- maintain solver behavior and module coupling
- define disease-state evolution and intervention write interfaces
- expose engine state to downstream consumers

Must not own:

- action budgets
- per-case pacing
- exam latency
- win/loss logic
- session storage
- UI clocks or display labels

### Clinical Interpretation Layer

Location:

- `src/clinical_signs_engine.py`
- `src/report_engine.py`
- `src/debug_params.py`

Responsibilities:

- derive observable signs from engine state
- generate structured and narrative reports
- provide teaching/debug views over kernel state

This layer is still downstream of the kernel. It should not change kernel equations or solver semantics.

Preferred public interpretation seam for new code:

- runtime-owned interpreter access, not direct app-layer reconstruction of medical summaries

Detailed interface and migration notes live in:

- [clinical-interpretation-layer.md](clinical-interpretation-layer.md)
- [runtime-composition-sketch.md](runtime-composition-sketch.md)
- [interpretation-lifecycle-sketch.md](interpretation-lifecycle-sketch.md)
- [interpretation-refresh-contract.md](interpretation-refresh-contract.md)
- [interpretation-migration-sequence.md](interpretation-migration-sequence.md)

### Application / Game Layer

Location:

- `game/`
- `gui_app.py`
- `vet-game-frontend/vite-project/`
- case, exam, and treatment JSON files used by the application flow

Responsibilities:

- case selection and orchestration
- diagnosis gameplay
- scenario pacing
- player-visible clock
- session persistence and replay
- frontend UX

## Allowed Dependency Direction

Allowed:

- application/game -> clinical interpretation
- application/game -> kernel
- clinical interpretation -> kernel

Disallowed:

- kernel -> game/application
- kernel equations depending on AP, time budget, round count, or UI state
- disease rate constants rescaled inside the kernel to fit gameplay pacing

## Time Semantics

Time must be understood as three separate concepts.

### 1. Physical Time

Kernel-native time.

Examples:

- `current_time_s`
- `dt`
- ODE state evolution
- organ and disease progression

Rule:

- if a behavior changes physiology, it must be expressible in physical time

### 2. Scenario Time

Outer-layer scheduling time.

Examples:

- "wait 10 min"
- "CT consumes 45 min"
- "warm up the case by 5 min"

Rule:

- the outer layer may decide how much physical time to advance
- the outer layer must not redefine kernel rate meaning

### 3. Presentation Time

Display-only time.

Examples:

- `08:00`
- night/day labels
- UI timestamps
- action log strings

Rule:

- presentation time may be derived from scenario time
- it is not itself a kernel mechanism

## Current Time Mapping

As of 2026-06-09:

- the gameplay shell uses real-minute scenario costs
- a gameplay action advances the engine by the same number of minutes
- therefore, current gameplay behavior is effectively `1 gameplay minute = 1 engine minute`

This mapping belongs to the application layer, not the kernel definition.

## Time Design Direction

The project is explicitly moving away from ad hoc case-start replay as the only
way to express pre-encounter disease history.

Current design direction:

- keep kernel disease and organ rates in physical units
- do not introduce a hidden global gameplay-to-biology multiplier
- treat "what state is the patient already in when the encounter begins?" as a
  distinct construction problem

This is why encounter-start state construction is now being moved behind a
kernel-adjacent seam:

- `src/presentation_state.py`
  - `PresentationRequest`
  - `build_presented_engine(...)`

This seam is currently transitional and may still use bounded replay
internally, but it is architecturally important because it separates:

- pre-encounter history construction
- encounter-time simulation
- outer gameplay pacing

See [kernel-first-design.md](kernel-first-design.md) for the integrated design
narrative and [presentation-state-builder-sketch.md](presentation-state-builder-sketch.md)
for the implementation-oriented path.

## Solver Status

As of 2026-06-09:

- `VirtualCreature` contains both Euler and Radau execution paths
- the application shell currently uses the default solver path, which is Euler
- Radau remains an important validation and research path, but should not be implicitly documented as the current gameplay default

Documentation must distinguish:

- what the kernel can do
- what the current application path actually uses

## Testing Tiers

The project should separate testing by intent instead of letting all application tests become heavy simulation tests.

### Tier 0: Fast Unit Tests

Target:

- sub-second to a few seconds per file

Examples:

- config validation
- factor routing
- clue extraction
- report field structure
- simple mapping logic

Rule:

- should not require long simulated durations

### Tier 1: Engine Contract Tests

Target:

- short-horizon numerical checks

Examples:

- one-step or short-run state updates
- disease variable directionality
- finite outputs
- solver contract sanity

Rule:

- keep horizons short unless the test is explicitly about long-run behavior

### Tier 2: Scenario Integration Tests

Target:

- slower, but intentional

Examples:

- `process_action()` time advancement
- report latency behavior
- warmup behavior
- application-to-engine integration

Rule:

- use explicit `slow` or `slower` markers when they trigger large simulated durations
- default application-layer action tests to fake runtime seams when real progression is not the assertion target
- allow coarser test-only `dt` values in app-layer integration tests when the goal is workflow coverage rather than numerical fidelity

### Tier 3: Validation / Endurance Tests

Target:

- may take minutes

Examples:

- 6000+ step stability runs
- solver parity checks
- disease endurance progression
- long-horizon NaN/Inf detection

Rule:

- these are acceptable as slow tests
- they should not be mistaken for ordinary day-to-day application tests

## Testing Conventions

The current preferred testing conventions are:

- use `GameRuntime` / `FakeAdvancer` seams for `process_action()` tests that validate bookkeeping, routing, phase flow, or report latency policy
- reserve real engine advancement for tests that explicitly validate disease progression, full report evolution, or end-to-end integration
- use explicit `@pytest.mark.slow` / `@pytest.mark.slower` markers for real long-horizon application tests
- permit coarser test-only `dt` values in app-layer tests when the assertion is qualitative and not solver-fidelity-sensitive
- exclude exploratory research/debug scripts from ordinary pytest collection unless they are rewritten as explicit regression tests

This keeps the clinically grounded kernel isolated from game-layer testing convenience while still allowing the outer application tests to run on a usable timescale.

See [testing.md](testing.md) for the concrete rules and command patterns now used in the repository.

## Current Gray Areas

These are known boundary imperfections, not the desired end state.

### Clinical sign engine initialization in kernel flow

**Status: Resolved (R6 Layer A, 2026-06-28).**

`attach_disease()` previously initialized `ClinicalSignsEngine` inline, coupling kernel lifecycle to a downstream interpretation concern. R6 Layer A removed the import and converted `_ensure_legacy_clinical_signs_engine` / `_refresh_legacy_clinical_signs` to no-op stubs. Interpretation setup now lives exclusively in the outer composition layer via `build_external_interpretation_bundle` (game/runtime_composition.py). `legacy_clinical_signs_enabled` defaults to `False`.

### Session-oriented snapshot logic on the engine object

**Status: Partially mitigated (R6 Layer B, 2026-06-28).**

`to_persistence_snapshot()` still lives on the kernel `VirtualCreature`, but an outer-layer adapter `game/persistence_adapter.py::build_persistence_snapshot(engine)` now wraps it. App code (`gui_app.py::_snapshot_json`) delegates to the adapter rather than calling the kernel method directly. This is a thin wrapper (not full migration) — full decoupling would require moving snapshot shaping out of the kernel, deferred pending test access patterns.

Why it is gray:

- those are application concerns, not physiology-kernel concerns

Preferred direction:

- move snapshot shaping into an adapter or persistence layer

### Game-managed night modifiers directly touching engine baselines

Night logic currently lives in the application/game layer and directly modifies cardiac baseline values.

Why it is gray:

- if circadian effects are meant as physiology, they should become modeled environment inputs
- if they are only gameplay pacing, they should not masquerade as kernel physiology

### Historical documents still describing superseded time models

Some older files still describe AP-based pacing or earlier wait semantics.

Rule:

- treat this document and the root `README.md` as authoritative
- treat older narrative files as historical records unless explicitly updated

## Documentation Authority

Current source of truth:

- root `README.md`
- `docs/architecture.md`
- `docs/kernel-first-design.md` as the main explanatory narrative

Recommended reading order for current time/design questions:

1. `README.md`
   - overall project positioning
2. `docs/architecture.md`
   - authoritative layer boundaries, time semantics, and testing tiers
3. [kernel-first-design.md](kernel-first-design.md)
   - integrated design narrative across layers, time, runtime, and tests
4. [kernel-time-architecture-sketch.md](kernel-time-architecture-sketch.md)
   - main time-system design note
5. [presentation-state-builder-sketch.md](presentation-state-builder-sketch.md)
   - encounter-start state construction and warmup replacement path
6. [testing.md](testing.md)
   - executable test split and regression command entry points

Historical or narrower-scope documents may remain useful, but they are not authoritative for current layer boundaries or time semantics unless they are explicitly synchronized.
