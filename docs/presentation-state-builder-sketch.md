# Presentation State Builder Sketch

Kernel-first sketch for constructing clinically plausible encounter-start states.

Last reviewed: 2026-06-09

## Purpose

This note turns the time-architecture sketch into an implementable refactor path.

It answers:

- what should replace raw `simulate(warmup_minutes)`
- where that logic should live
- what the first interface should look like
- how to migrate existing entry points safely

## Core Principle

The presented patient state is part of kernel usability, not game flavor.

So the builder must not live in:

- `game/`
- frontend code
- per-scenario UI helpers

It should live close to the kernel, because it prepares a clinically meaningful
physiological starting state for the encounter.

## Problem Statement

Current callers often do this:

```python
engine = VirtualCreature(...)
engine.attach_disease(disease)
engine.simulate(warmup_minutes)
```

This is simple, but it conflates:

- disease history construction
- encounter-time simulation
- scenario authoring convenience

It also makes these meanings ambiguous:

- is `warmup_minutes=5` an acute deterioration window?
- is it standing in for several hours of untreated disease?
- is it just a cheap way to make symptoms visible?

That ambiguity is the real design problem.

## Target Responsibility Split

### Kernel

Owns:

- physical-time evolution
- disease-state meaning
- encounter-start state preparation primitives

Does not own:

- case scoring
- difficulty pacing
- UI clock labels

### Presentation State Builder

Owns:

- preparing a plausible encounter-start engine state
- making disease-history assumptions explicit
- separating initialization policy from encounter-time progression

Does not own:

- exams
- action costs
- report latency
- win/loss

### Application Layer

Owns:

- choosing which builder profile to use for a scenario
- passing case metadata such as species, severity, intended encounter stage

Does not own:

- the physiology semantics of how a 6-hour pneumonia differs from a 2-day one

## Recommended Placement

Recommended new module family:

- `src/presentation_state.py`
- or `src/presentation_builder.py`

Why:

- it is downstream of the kernel but still kernel-adjacent
- it is clinically meaningful infrastructure
- it avoids infecting `game/` with disease-history semantics

## First Interface

Start simple.

### Data spec

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class PresentationRequest:
    disease_name: str
    severity: str = "moderate"
    species: str = "canine"
    weight_kg: float = 20.0
    age_days: float | None = None
    encounter_stage: str = "acute_early"
    history_duration_min: float | None = None
```

Notes:

- `encounter_stage` is the preferred semantic input
- `history_duration_min` is allowed as an explicit physical-time override
- stage names are for initialization policy, not game pacing

### Builder contract

```python
class PresentationStateBuilder:
    def build(self, request: PresentationRequest) -> VirtualCreature:
        ...
```

This keeps the public surface minimal.

## Preferred Semantics

The builder should prefer explicit encounter-stage semantics over naked warmup minutes.

Examples:

- `acute_early`
- `acute_progressed`
- `acute_critical`
- `subacute_presenting`
- `chronic_compensated`
- `chronic_decompensated`

Those names can evolve.

The important point is that scenario authors choose a clinical presentation target,
not a hidden numerical replay trick.

## Recommended V1

V1 should be intentionally modest.

It does not need to solve full chronic-disease initialization yet.

### V1 behavior

1. build `VirtualCreature`
2. attach requested disease
3. choose an initialization policy
4. if needed, run bounded warmup internally
5. return an encounter-ready engine

Conceptually:

```python
engine = VirtualCreature(...)
engine.attach_disease(disease)
minutes = policy.resolve_history_minutes(request)
engine.simulate(minutes)
return engine
```

Why this is still valuable:

- callers stop hardcoding raw warmup behavior
- the semantic meaning moves into one place
- future upgrades can replace internal warmup without changing outer callers

## Recommended V1 Policy Object

Do not bake stage mapping into random endpoints.

Suggested internal helper:

```python
class PresentationPolicy:
    def resolve_history_minutes(self, request: PresentationRequest) -> float:
        ...
```

Initial implementation may use:

- disease defaults
- severity defaults
- explicit request override

For example:

- pneumonia + moderate + `acute_progressed` -> 30 min
- ARF + moderate + `subacute_presenting` -> 180 min

Those mappings are still assumptions, but now they are:

- visible
- reviewable
- replaceable

That is much better than scattered warmup literals.

## V2 Direction

Once V1 centralization is stable, the builder can stop relying only on replay.

Possible V2 capabilities:

- disease-specific calibrated initial state seeding
- cached prepared snapshots
- quasi-steady-state solvers for chronic adaptation
- staged initialization with mixed fast and slow processes

At that point:

- replay remains one tool
- not the whole architecture

## Why This Avoids Hardcoding Better

The important distinction is:

- bad hardcoding: burying a global biological distortion in disease code
- acceptable transitional policy: centralizing explicit encounter-start assumptions in one builder

V1 builder policies are still authored assumptions.

But they are architecturally honest assumptions.

They do not pretend to redefine physiology itself.

## Migration Order

### Step 1. Add builder without changing kernel time semantics

No solver changes.

No disease-rate changes.

Just add the new construction seam.

### Step 2. Migrate `game/case_generator.py`

Current:

- creates engine directly
- attaches disease
- replays `pre_visit_min`

Target:

- asks builder for encounter-ready engine

Reason:

- this is the cleanest non-UI caller
- easiest place to prove the abstraction

### Step 3. Migrate `gui_app.py`

Current:

- creates `VirtualCreature`
- attaches disease
- uses `warmup_minutes`

Target:

- converts request/body or case metadata into `PresentationRequest`
- uses builder

Reason:

- this makes the real app entry point align with kernel-first initialization

### Step 4. Migrate scenario helpers and heavy tests

Especially places that currently:

- hand-roll warmup
- loop over many cases
- use long real progression only to create a presentation state

This is where runtime wins begin to appear.

### Step 5. Later evaluate whether some diseases need non-replay initialization

Only after usage patterns are clear.

Do not prematurely build a giant generalized staging framework.

## What Should Stay Out Of V1

- multi-rate scheduler changes
- chronic remodeling solver redesign
- UI-specific difficulty heuristics
- score-based time compression
- one global multiplier for all diseases

Those are separate design questions.

## Interaction With Current Runtime Seams

This builder complements, not replaces, the runtime refactor.

Current seams:

- `GameRuntime`
- `EngineAdvancerProtocol`
- external interpretation bundle

Those handle:

- encounter-time advancement
- interpretation ownership

The builder handles:

- encounter-start state construction

So the architecture becomes:

1. builder creates presented patient
2. runtime owns advancement + interpretation during encounter

That is a much cleaner lifecycle.

## Recommended Minimal Public API

If we want the smallest practical v1:

```python
def build_presented_engine(
    *,
    disease_name: str,
    severity: str = "moderate",
    species: str = "canine",
    weight_kg: float = 20.0,
    age_days: float | None = None,
    encounter_stage: str = "acute_progressed",
    history_duration_min: float | None = None,
) -> VirtualCreature:
    ...
```

This may be easier to adopt first than a heavier class graph.

Internally it can still delegate to a real builder class later.

## Decision Points You May Want To Lock Down

These are the main choices worth deciding explicitly.

### 1. Public input style

Option A:

- semantic stage names first

Option B:

- explicit physical history duration first

Recommendation:

- support both
- make stage names the preferred scenario-authoring interface

### 2. Builder placement

Option A:

- `src/presentation_state.py`

Option B:

- `src/case_initialization.py`

Recommendation:

- prefer `presentation_state.py` or `presentation_builder.py`
- avoid `game/`

### 3. Return type

Option A:

- just return `VirtualCreature`

Option B:

- return `VirtualCreature` plus metadata about how it was prepared

Recommendation:

- V1 can return engine only
- V2 may add metadata if case explainability becomes important

## Best Next Implementation Move

The cleanest next code step is:

1. add a minimal builder function in `src/`
2. migrate `game/case_generator.py` to use it
3. leave GUI migration for the next step

That sequence keeps risk low while proving the architecture in a real caller.
