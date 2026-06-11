# Kernel-First Design

Integrated design note for the current project direction.

Last reviewed: 2026-06-09

## Purpose

This document consolidates the current design direction into one readable source
for:

- project positioning
- layer boundaries
- time semantics
- encounter-start state construction
- runtime ownership
- testing strategy

It is intended as a practical design narrative, not just a sketch.

If you need the shortest authoritative rules, read
[architecture.md](architecture.md) first.

If you need the project's main design explanation, this is the document to stay in.

If you need the detailed time-only or builder-only follow-on notes, continue to:

- [kernel-time-architecture-sketch.md](kernel-time-architecture-sketch.md)
- [presentation-state-builder-sketch.md](presentation-state-builder-sketch.md)
- [testing.md](testing.md)

## Product Position

The physiology kernel is the product core.

The game, GUI, session flow, diagnosis gameplay, and teaching UX are outer
application layers built around that core.

This has one hard implication:

- gameplay convenience must not redefine kernel biology

In particular, the project should not distort disease rate meaning, solver
semantics, or temporal interpretation just to make the outer loop feel better.

## Design Goals

The current direction aims for five things at once:

1. clinically legible outputs
2. kernel-level physiological meaning
3. clean outer composition boundaries
4. testability at multiple speeds
5. room for future research-grade validation

These goals create tension, so the architecture must be explicit.

The practical consequence is simple:

- when kernel credibility and outer-loop convenience conflict, the outer layer yields

## Layer Model

### 1. Physiology Kernel

Primary location:

- `src/simulation.py`
- organ modules under `src/`
- `src/diseases/`
- `src/engine/`

Responsibilities:

- evolve physiological state in physical time
- maintain solver behavior and module coupling
- apply disease and intervention effects through kernel write interfaces
- expose state for downstream consumers

Must not own:

- time budgets
- turn pacing
- exam latency
- win/loss rules
- session storage
- UI clock semantics

### 2. Clinical Interpretation Layer

Primary location:

- `src/clinical_interpreter.py`
- `src/clinical_signs_engine.py`
- `src/report_engine.py`
- `src/clinical_state.py`
- `src/clinical_snapshot.py`

Responsibilities:

- turn engine state into clinically readable observations
- generate reports and summaries
- classify medical phase
- expose sign tags and teaching-facing interpretation

This layer is downstream of the kernel.

It may observe physiology.

It must not define physiology.

### 3. Runtime Composition Layer

Primary location:

- `game/runtime.py`
- `game/runtime_composition.py`
- `src/engine_advancer.py`
- `src/interpretation_refresher.py`

Responsibilities:

- own advancement policy for application use
- own interpreter wiring
- own post-advance refresh behavior
- keep outer collaboration seams injectable and testable

Current preferred public seam:

- `runtime.advance_and_refresh(engine, minutes)`

Lower-level collaborators remain injectable:

- `advancer`
- `interpreter`
- `refresher`

### 4. Application / Game Layer

Primary location:

- `game/`
- `gui_app.py`
- frontend code

Responsibilities:

- cases
- actions
- diagnosis workflow
- scenario pacing
- session persistence
- player-visible flow

This layer is allowed to drive the kernel.

It is not allowed to redefine kernel truth.

## Time Design

The project currently uses three active notions of time and one emerging one.

### A. Physical Time

Kernel-native truth.

Current forms:

- `current_time_s`
- `dt`
- `advance_seconds(...)`
- `simulate(...)`

Physical time governs:

- organ dynamics
- disease progression
- drug effects
- fluid balance
- lifecycle state

Rule:

- if a behavior changes physiology, it must be explainable in physical time

### B. Scenario Time

Outer-layer pacing time.

Current forms:

- `state.time_elapsed_min`
- action costs
- wait durations
- report latency

Current default policy:

- `1 scenario minute = 1 physical minute`

This is acceptable as an application default for acute encounter flow.

It is not a kernel law.

### C. Presentation Time

Display-only time.

Examples:

- `08:00`
- night/day labels
- logs and timestamps

Presentation time may be derived from scenario time.

It is not itself physiology.

### D. Natural-History Time

This is the important emerging concept.

A real patient may already have been sick for:

- minutes
- hours
- days
- weeks

The kernel should eventually represent this as clinically meaningful
pre-encounter history construction, not merely as a gameplay warmup trick.

That is the core reason the project rejects a hidden global time multiplier.

## Current Time Strengths

Several important design choices are already correct.

- The kernel still runs in physical time.
- Disease rates are no longer globally rescaled for gameplay.
- Scenario advancement is already routed through an outer seam.
- Interpretation is already mostly consumed through runtime-owned interfaces.

These are the right foundations for a credible kernel-first design.

## Current Time Weaknesses

### 1. Pre-encounter history is still mostly replay

Many callers historically created a patient like this:

```python
engine = VirtualCreature(...)
engine.attach_disease(disease)
engine.simulate(warmup_minutes)
```

That approach is simple, but it conflates:

- disease history construction
- encounter-time simulation
- scenario authoring convenience

### 2. Application tests can become hidden endurance runs

If an application workflow advances real engine time naively, a single action
may trigger thousands of physical steps.

That is valid only when real progression is the thing being tested.

### 3. Presentation-time logic has historically leaked across layers

Clock formatting and night semantics have not always had one centralized home.

### 4. Night progression semantics remain a gray area

There is still a difference between:

- saying night should affect gameplay pacing
- saying circadian state is modeled as physiology

Those should not be blurred.

In short:

- the project is already correct to keep kernel rates physical
- the remaining work is mostly about cleaner construction, ownership, and test layering

## Design Position On Time Compression

The project should not use a global magic ratio such as:

- `1 game minute = 14 physiological minutes`

inside kernel disease code.

Why:

- it hides biology behind a gameplay knob
- it weakens interpretation of rates and taus
- it makes validation harder to reason about

Instead, the correct question is:

- what clinical state is the patient already in when the encounter begins?

That leads to a much cleaner architecture.

## Encounter-Start State Construction

This is now a first-class design topic.

### Current direction

The project now has a kernel-adjacent construction seam:

- `src/presentation_state.py`

Current public surface:

- `PresentationRequest`
- `build_presented_engine(...)`

This seam exists so callers stop scattering raw warmup replay logic.

### What this seam means

The presented patient state is not game flavor.

It is part of making the kernel clinically usable.

That is why the builder lives under `src/`, not under `game/`.

### Current V1 behavior

V1 is intentionally conservative.

It still allows bounded replay internally, but centralizes the meaning in one
place.

That gives three benefits immediately:

- callers stop hardcoding encounter-start replay
- the assumption becomes visible and reviewable
- later improvements can replace replay without changing all entry points

### Current migration status

The builder path is already in use in real code.

Adopted paths:

- `game/case_generator.py`
- `gui_app.py` case-start path
- `gui_app.py` debug disease-params path

This means encounter-start construction is no longer only a design sketch.

It has already begun replacing ad hoc warmup logic in live entry points.

This is one of the most important practical shifts in the current architecture,
because it moves disease-history assumptions toward an explicit, reviewable seam.

## Interpretation Ownership

The target ownership model is:

- kernel owns physiology
- interpretation owns meaning extraction
- runtime/app composition owns wiring and refresh timing

Current preferred outer runtime shape:

- advancer
- interpreter
- refresher

Current preferred public operation:

- `advance_and_refresh(...)`

At the app boundary, the preferred call shape is:

- `runtime.advance_and_refresh(engine, minutes)`

The kernel still retains some compatibility-owned interpretation lifecycle
behavior, but those behaviors are now explicitly gathered behind legacy helper
seams in `src/simulation.py`.

That is an intentional transition step, not the target end state.

## Testing Design

The testing strategy now follows the architecture instead of fighting it.

### Tier 0: Fast Unit

Purpose:

- mappings
- config rules
- report structure
- lightweight pure logic

### Tier 1: Engine Contract

Purpose:

- short-horizon kernel behavior
- finite outputs
- directional sanity
- step contract checks

### Tier 2: Scenario Integration

Purpose:

- runtime flow
- app-to-engine orchestration
- API contracts
- report latency
- case routing

These tests should use:

- fake runtime seams when they do not need real progression
- coarse test-only `dt` where workflow is the point

### Tier 3: Validation / Endurance

Purpose:

- long-horizon stability
- solver parity
- disease progression credibility
- endurance checks

These tests are intentionally slower and should stay explicitly marked.

The key idea is simple:

- fast tests protect momentum
- slow tests protect credibility

Both matter, but they should not be confused with each other.

## Current Executable Test Split

The repo now supports a practical four-entry testing model:

### Fast

Use for normal editing loops.

```bash
python -m pytest --channel fast -q
```

### Core

Use for application/runtime/API work.

```bash
python -m pytest --channel core -q
```

### Heavy / Benchmark

Use for physiological credibility and solver-focused changes.

```bash
python -m pytest tests -q -m "slow or slower"
```

### Full

Use for maximum confidence before merges or after high-impact boundary changes.

```bash
python -m pytest tests -q
```

## Research Scripts vs Regression Tests

Not every file under `tests/` should be collected as a normal regression gate.

The repository now intentionally excludes several exploratory scripts from pytest
collection, including:

- `tests/collect_disease_progression.py`
- `tests/debug_symptoms.py`
- `tests/test_warmup_check.py`

These remain useful, but they are not stable day-to-day regression tests.

If they later become important gates, they should be rewritten as real pytest
tests with:

- explicit assertions
- explicit marker policy
- explicit runtime/step-size intent

## What Has Changed Already

The current design direction is not hypothetical anymore.

Already implemented:

- app-layer runtime seam
- injectable advancer/interpreter/refresher
- `advance_seconds(...)` kernel API
- external interpretation bundle path
- GUI migration to runtime-owned interpretation
- case generator migration to presentation-state builder
- GUI encounter-state migration to presentation-state builder
- interface test isolation and acceleration
- explicit `slow` / `slower` marker registration
- research/debug script separation from regression collection

This matters because the project is no longer merely discussing kernel-first
design.

It is actively moving toward it.

That is the most important status update behind this document.

In other words:

- the architecture has already crossed from proposal into active migration

## Remaining Gray Areas

### 1. Legacy interpretation lifecycle still touches the kernel

Compatibility seams still exist in `src/simulation.py`.

That is acceptable for now, but not the desired final ownership model.

### 2. Presentation time still has duplication risk

Clock-related logic should continue moving toward one presentation-time home.

### 3. Circadian semantics remain underdefined

Night/day behavior should eventually become either:

- explicit modeled physiology

or:

- explicit outer-layer pacing policy

but not a confusing hybrid.

### 4. V1 presentation builder still relies partly on replay

That is fine as a transition.

Long-term chronic or subacute initialization may need more direct preparation
methods than bounded replay.

## Short Rules

1. The kernel is the product core.
2. Kernel rates stay in physical units.
3. Gameplay may drive time advancement, but may not redefine biology.
4. Encounter-start state construction belongs near the kernel, not in the game layer.
5. Interpretation should be outer-owned even if compatibility seams still remain.
6. Application tests should not pay full kernel cost unless real progression is the point.
7. Slow validation should be explicit, not accidental.

## Reading Map

Use this order when working on the design:

1. `README.md`
2. `docs/architecture.md`
3. `docs/kernel-first-design.md`
4. `docs/kernel-time-architecture-sketch.md`
5. `docs/presentation-state-builder-sketch.md`
6. `docs/testing.md`

Use this order when implementing:

1. `docs/architecture.md`
2. `docs/kernel-first-design.md`
3. `docs/presentation-state-builder-sketch.md`
4. `docs/testing.md`

This document is intended to be the bridge between the concise authoritative
architecture note and the narrower implementation sketches.
