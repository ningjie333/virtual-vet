# Interpretation Lifecycle Sketch

Lifecycle-focused refactor note for clinical interpretation ownership.

Last reviewed: 2026-06-09

## Scope

This note is only about lifecycle ownership.

It is not about:

- changing report content
- changing sign formulas
- changing phase thresholds
- changing gameplay pacing

Those interface-level concerns have mostly already been separated.

The remaining question is:

who creates, owns, and refreshes interpretation objects?

## Current Lifecycle

Today, interpretation object lifecycle is still partially owned by the kernel.

Current flow:

1. outer layer creates `VirtualCreature`
2. outer layer calls `attach_disease(...)`
3. `VirtualCreature.attach_disease()` creates `ClinicalSignsEngine`
4. engine time advancement calls `clinical_signs_engine.compute(...)`
5. outer layer later reads signs, reports, and summaries

Concrete current ownership points:

- `src/simulation.py:attach_disease()`
  - creates `self.clinical_signs_engine`
- `src/simulation.py`
  - multiple step/simulate paths call `self.clinical_signs_engine.compute(...)`

As of 2026-06-09, these kernel-owned behaviors have been explicitly gathered
behind compatibility helpers in `src/simulation.py`:

- `_ensure_legacy_clinical_signs_engine()`
- `_refresh_legacy_clinical_signs()`

This is not the final target architecture.
It is a boundary-tightening step so that legacy ownership is visible,
named, and easier to remove later.

So the kernel currently owns:

- interpretation object creation
- interpretation object refresh timing

Even though interpretation outputs are already consumed through cleaner outer interfaces.

## Why This Is Still A Gray Area

This is workable, but not architecturally clean.

### 1. Kernel owns downstream meaning

The kernel should own physiological truth.

`ClinicalSignsEngine` is not truth generation.
It is meaning generation from truth.

So when the kernel creates and refreshes it, the dependency direction is blurred.

### 2. Time advancement has hidden side effects

A caller may think:

- `attach_disease()` only attaches a disease
- `simulate()` only advances physiology

But today they also:

- create interpretation objects
- refresh observable-sign state

That makes lifecycle harder to reason about.

### 3. Alternative interpretation stacks are harder to compose

If we later want:

- a clinical game interpreter
- a teaching interpreter
- a research export interpreter
- a no-interpretation batch runner

the kernel-owned lifecycle becomes a constraint.

### 4. Boundary reading becomes misleading

A new reader can easily conclude that `ClinicalSignsEngine` is part of the core solver model.

That is not the desired mental model.

## Desired Lifecycle

Target principle:

- kernel owns state evolution
- interpretation layer owns meaning extraction
- application/composition layer owns wiring

Target flow:

1. outer layer creates `VirtualCreature`
2. outer layer creates interpretation support objects
3. outer layer advances physical time
4. outer layer explicitly refreshes interpretation state
5. outer layer consumes interpretation outputs

In other words:

- engine does not create interpretation objects
- engine does not decide when interpretation objects refresh
- outer composition decides both

## Preferred Ownership Model

The most coherent end state is an outer clinical session composition.

Conceptually:

```python
engine = VirtualCreature(...)
signs = ClinicalSignsEngine(engine, defs, species)
interpreter = DefaultClinicalInterpreter(signs_engine=signs)
runtime = GameRuntime(advancer=..., interpreter=interpreter)
```

Then a time advancement flow becomes conceptually:

```python
runtime.advancer.advance_minutes(engine, minutes)
signs.compute(engine.current_time_s)
report = runtime.interpreter.report("physical", engine)
```

The exact object shape can vary.

The important part is ownership:

- creation happens outside the kernel
- refresh happens outside the kernel

## Minimal Refactor Direction

This does not need a big-bang rewrite.

### Step 1. Make lifecycle explicit in docs

Done by this note.

This avoids pretending the current kernel-owned lifecycle is the target design.

### Step 2. Introduce an outer refresher seam

Add an outer-layer mechanism that can say:

- after engine time advances, refresh interpretation state

This can live in runtime or a small coordinator object.

### Step 3. Allow interpreter/signs construction outside `VirtualCreature`

Make it possible to create:

- `ClinicalSignsEngine`
- interpreter

without relying on `attach_disease()` side effects.

This is the key structural unlock.

### Step 4. Migrate application paths to outer ownership

Once outer composition paths exist:

- game flow
- GUI flow
- scenario helpers

can stop relying on kernel-owned interpretation objects.

### Step 5. Remove kernel-owned lifecycle

Only after outer ownership is proven stable:

- remove `ClinicalSignsEngine` creation from `attach_disease()`
- remove kernel-side automatic `compute(...)` refreshes
- update remaining direct callers that still read `engine.clinical_signs_engine`

That is the final cleanup, not the first move.

## What Should Not Change During This Refactor

The lifecycle refactor should not, by itself, change:

- report wording
- sign thresholds
- sign onset/offset math
- medical phase scoring
- disease dynamics
- gameplay minute mapping

If any of those change during lifecycle work, scope has leaked.

## Risk To Watch

The main risk is not numerical accuracy.

The main risk is stale interpretation state.

If refresh ownership moves outward, we must make sure that:

- every real engine advancement that matters also refreshes signs
- tests that directly call `engine.simulate()` remain valid
- no caller reads sign/report state before refresh

So the practical design question is:

what is the single explicit refresh contract?

That contract matters more than the exact class layout.

## Short Design Rule

The kernel may expose state.

The interpretation layer may observe state.

The application layer should decide when interpretation is instantiated and refreshed.
