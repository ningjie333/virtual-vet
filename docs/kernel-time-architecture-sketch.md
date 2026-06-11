# Kernel Time Architecture Sketch

Time-system sketch for a kernel-first, clinically credible physiology engine.

Last reviewed: 2026-06-09

## Goal

Clarify:

- how time works today
- why current behavior is expensive and only partially clinically credible
- what a cleaner kernel-first time architecture should look like

This note is not a gameplay design note.

It treats the physiology kernel as the product core.

## Design Position

The kernel must not use a global "game speed" ratio.

Examples of what we do **not** want:

- `1 game minute = 14 physiological minutes` baked into disease code
- disease ODE rates rescaled because UI turns are too slow
- chronic disease compressed by arbitrary hardcoded multipliers

Those approaches are convenient, but they reduce model meaning.

A clinically credible kernel should instead:

- keep rates and taus in physical units
- separate encounter-time simulation from pre-encounter disease history
- use scheduling and initialization strategies, not semantic rate distortion

## Current Time Model

Today the project already contains three distinct notions of time.

### 1. Physical Time

Kernel-native truth.

Current implementation:

- `src/simulation.py`
  - `current_time_s`
  - `dt`
  - `step()`
  - `advance_seconds(...)`
  - `simulate(...)`

Meaning:

- organ dynamics
- disease progression
- drug PK/PD
- fluid shifts
- lifecycle state

All of these are expressed in physical elapsed time.

### 2. Scenario Time

Outer-layer action and pacing time.

Current implementation:

- `game/action_system.py`
  - `state.time_elapsed_min`
  - action costs such as 5, 10, 20, 45 minutes
- `src/engine_advancer.py`
  - `PhysicalMinuteAdvancer.advance_minutes(...)`

Current default mapping:

- action consumes `N` scenario minutes
- outer runtime advances engine by the same `N` physical minutes

So today, the application policy is effectively:

- `1 scenario minute = 1 physical minute`

Important:

this is an application policy, not a kernel law.

### 3. Presentation Time

Display-only clock semantics.

Current implementation:

- `game/time_manager.py`
- `src/clinical_interpreter.py`

Used for:

- `08:00` start clock
- night/day labels
- formatted UI times

This is not physiological time.

## Current Data Flow

Today the main path is:

1. action layer increases `state.time_elapsed_min`
2. runtime maps scenario minutes to physical engine advancement
3. engine advances in seconds internally
4. interpreter formats display time from `time_elapsed_min`

That means:

- the kernel itself is still physically timed
- the outer app currently chooses a 1:1 minute mapping

## What Is Good About The Current Design

Several important things are already correct.

- The kernel still runs in physical time.
- Disease rates are no longer globally rescaled by gameplay needs.
- Scenario timing is already routed through an outer advancer seam.
- Presentation time is conceptually separate from kernel time.

This is a good foundation.

## What Is Still Weak

### 1. Encounter time and disease natural history are conflated

A real patient may have been sick for:

- hours
- days
- weeks

But the engine is often asked to create that state by directly replaying time from a relatively simple earlier condition using `simulate(warmup_minutes)`.

That is workable for short acute windows.

It is not an elegant basis for:

- long natural-history disease states
- chronic adaptation
- cheap case initialization

### 2. Testing cost grows with scenario workflow

If an application test uses real `process_action(...)` with the default runtime, then:

- a 45-minute CT action advances 45 physical minutes
- at `dt=0.1 s`, that means about 27,000 solver steps

So application workflow tests can accidentally become long kernel endurance tests.

This is why some full runs feel disproportionately slow.

### 3. Warmup is doing too much conceptual work

`warmup_minutes` is currently used as a simple way to say:

- "the patient has already been ill before arrival"

But clinically that can mean very different things:

- early acute deterioration over minutes
- disease evolution over many hours
- chronic structural remodeling over days or longer

Those are not the same temporal problem.

### 4. Night logic is not cleanly placed

Current night behavior is mixed into the game layer.

- `game/action_system.py` mutates `HR_rest`
- `game/time_manager.py` defines a "night progression factor"
- but that progression factor is not actually driving kernel disease rates today

So the conceptual statement "night slows disease progression" exists in policy language more than in a kernel-level physiological model.

### 5. Presentation-time logic is duplicated

Display clock formatting exists in both:

- `game/time_manager.py`
- `src/clinical_interpreter.py`

That is a maintainability smell.

It suggests presentation-time concerns are not yet fully centralized.

## Clinical Credibility Principle

For a clinically credible kernel, the key question is not:

- "How do we make diseases progress fast enough for gameplay?"

The better question is:

- "At what point in the patient's real disease course does the encounter begin?"

That leads to a cleaner design.

## Recommended Time Architecture

Use four layers.

### Layer A. Fast Physiological Time

Kernel-owned.

Native unit:

- seconds

Scope:

- hemodynamics
- gas exchange
- acute neurohumoral feedback
- fast drug effects
- fast organ coupling

This is what `VirtualCreature` already does well.

### Layer B. Biological Natural-History Time

Still kernel-owned, but conceptually distinct from the encounter clock.

Native units may span:

- minutes
- hours
- days

Scope:

- disease burden accumulation
- inflammatory evolution
- tissue injury and repair
- structural remodeling
- chronic compensation / decompensation

Critical rule:

these processes must still be defined in physical units, not game units.

### Layer C. Scenario Time

Outer-layer owned.

Scope:

- action cost
- report latency
- wait actions
- case flow pacing

This layer may decide how much physical time to request from the kernel.

It must not redefine disease meaning.

### Layer D. Presentation Time

Display-only.

Scope:

- wall-clock labels
- logs
- UI time of day

This should be centralized and derived, not duplicated.

## The Key Architectural Move

Do **not** force the clinical encounter engine to numerically replay the full disease history every time.

Instead, separate:

### 1. Pre-Encounter State Construction

Build a clinically plausible presented patient state.

Possible mechanisms:

- calibrated disease initial states
- disease-duration-aware initialization
- stored/warm-start snapshots
- steady-state or quasi-steady-state preparation
- offline case compilation for repeated teaching scenarios

### 2. Encounter-Time Simulation

Once the case begins, simulate the next:

- minutes
- hours

in real physical time.

This is much closer to how actual clinical care works:

- the patient arrives already sick
- the clinician manages the next acute window

That means we do not need a fake universal time ratio just to make disease visible.

## Recommended Kernel Shape

### Public kernel contract

Keep the kernel public contract simple and physical:

- `advance_seconds(seconds)`
- `simulate(minutes)` as compatibility wrapper only

Preferred long-term naming direction:

- `advance_seconds(...)` is the authoritative API
- `simulate(...)` remains a convenience alias, not the conceptual source of truth

### Internal kernel temporal structure

Over time, the kernel should move toward an explicit temporal orchestrator.

Conceptually:

```python
engine.advance_seconds(T)
```

internally becomes:

```python
temporal_orchestrator.advance(
    total_seconds=T,
    fast_stepper=...,
    slow_process_scheduler=...,
)
```

Where:

- fast physiology may still step at sub-second or second cadence
- slower disease or remodeling processes may update on coarser physical intervals
- all rates remain interpretable in real units

This is a multi-rate kernel strategy, not a gameplay distortion strategy.

## Recommended Initialization Shape

Introduce a kernel-adjacent clinical initialization concept.

Suggested name:

- `PresentationStateBuilder`

Responsibilities:

- create a patient state at encounter start
- apply disease duration / severity assumptions in clinically meaningful units
- produce a warmed or compiled engine state ready for acute simulation

Important:

this is not a game system.

It is part of making the kernel clinically usable.

The game can call it, but should not define it.

## Why This Is More Elegant

Because it avoids three kinds of hardcoding.

### 1. No global magic multiplier

There is no single `14x` or `20x` switch that secretly changes biology.

### 2. No game-driven disease semantics

The game may ask for a 10-minute wait.

It does not get to decide that "10 minutes means 3 days of renal injury."

### 3. No requirement to replay everything online

Long disease history can be prepared as an initialization problem,
not paid repeatedly as an encounter-time runtime cost.

## Practical Consequences

If we follow this direction:

- acute emergency cases can still run minute-to-minute in real physical time
- chronic or subacute cases can start from compiled/presented states
- application tests no longer need full disease playback unless that is the exact test goal
- full-kernel validation remains possible, but becomes an explicit validation tier

## Migration Path

### Step 1. Freeze the current truth in docs

Document clearly that:

- kernel time is physical
- the current 1:1 minute mapping is outer policy
- there is no approved global disease-rate multiplier

This note does that.

### Step 2. Centralize presentation time

Unify duplicated clock formatting and night-label helpers so presentation time has one home.

### Step 3. Introduce clinical initialization as a first-class concept

Add a kernel-adjacent builder for encounter-start state preparation.

Initial version can still use warmup internally.

The architectural gain is that "patient arrives after X disease history" becomes explicit.

### Step 4. Reclassify warmup

`warmup_minutes` should stop meaning "the general answer to disease time."

Instead it becomes one transitional implementation strategy for initialization.

### Step 5. Add multi-rate kernel scheduling only where needed

Do this only for genuine kernel needs:

- long-horizon disease evolution
- chronic adaptation
- performance-sensitive validation runs

Do not use it as a hidden game-speed hack.

### Step 6. Keep testing tiers honest

Application tests should mostly use fake runtime seams.

Real disease progression tests should be intentionally marked as slow validation.

## Immediate Implications For This Repository

### Current default policy is acceptable, but narrow

`PhysicalMinuteAdvancer` is an acceptable default for acute encounter flow.

It is not sufficient as the long-term answer for all clinical time scales.

### `warmup_minutes` should be treated as transitional

It is useful, but it should evolve into a cleaner presented-state initialization pathway.

### Night progression claims need cleanup

Either:

- remove the claim that night slows disease progression

or:

- implement that behavior as a real kernel-level physiological model

The current middle state is conceptually muddy.

## Short Rule Set

1. Keep kernel rates in physical units.
2. Never solve gameplay pacing by distorting disease semantics.
3. Separate pre-encounter history construction from encounter-time simulation.
4. Use multi-rate scheduling for numerical efficiency, not for narrative convenience.
5. Treat presentation time as derived UI policy, not physiology.

## Recommended Next Code Moves

1. Centralize presentation-time helpers now.
2. Introduce a first `PresentationStateBuilder` interface, even if v1 still delegates to warmup.
3. Move case generation and GUI case start toward that builder instead of raw `simulate(warmup_minutes)`.
4. Later decide whether the kernel itself needs a true multi-rate scheduler for slow biological processes.
