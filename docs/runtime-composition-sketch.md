# Runtime Composition Sketch

Composition-focused sketch for the outer runtime that drives the physiology kernel and clinical interpretation layer.

Last reviewed: 2026-06-09

## Purpose

This note answers:

- what objects belong in the outer runtime?
- what should `GameRuntime` own?
- where should interpretation refresh coordination live?

It does not redefine physiology, reports, or sign rules.

## Current Runtime Shape

Current code already has a useful seam:

- `game/runtime.py`
  - `GameRuntime`
  - `default_runtime()`
- `src/engine_advancer.py`
  - physical-time advancement seam
- `src/clinical_interpreter.py`
  - clinical interpretation seam

Current conceptual shape:

```python
GameRuntime(
    advancer=PhysicalMinuteAdvancer(),
    interpreter=DefaultClinicalInterpreter(),
)
```

This is already enough for:

- action tests
- report generation through the interpreter
- app-layer time control

What it does not yet own is the explicit interpretation refresh contract.

## Current Composition Gap

Right now:

- runtime owns advancement strategy
- runtime owns interpretation interface
- kernel still owns sign-engine lifecycle and refresh timing

So runtime composition is only half complete.

The missing piece is:

- who explicitly refreshes interpretation state after physical time advances?

## Desired Runtime Responsibility

Recommended outer-runtime responsibilities:

- decide how much physical time advances
- decide which interpreter stack is active
- decide when interpretation state refreshes
- expose one clean application-facing orchestration seam

Not runtime responsibilities:

- solving physiology
- disease equations
- report wording
- sign formulas

## Recommended Object Model

Recommended target outer composition:

```python
GameRuntime(
    advancer=EngineAdvancerProtocol,
    interpreter=ClinicalInterpreterProtocol,
    refresher=InterpretationRefresherProtocol,
)
```

Conceptually:

- `advancer`
  - advances kernel physical time only
- `interpreter`
  - reads meaning from engine state
- `refresher`
  - updates interpretation-side cached state after advancement

This keeps responsibilities orthogonal.

## Recommended Supporting Protocol

Suggested outer refresh protocol:

```python
from typing import Protocol, Any


class InterpretationRefresherProtocol(Protocol):
    def refresh(self, engine: Any) -> None: ...
```

Typical default implementation:

- if a signs engine exists, call `compute(engine.current_time_s)`
- if future interpretation objects need refresh, do that here too

This is intentionally narrow.

It is not a second interpreter.

It is an orchestration hook.

## Recommended Flow

Target application flow:

```python
runtime.advancer.advance_minutes(engine, minutes)
runtime.refresher.refresh(engine)
snapshot = runtime.interpreter.snapshot(engine)
phase = runtime.interpreter.phase(snapshot)
summary = runtime.interpreter.summary(snapshot, elapsed_min)
```

This makes the refresh step visible and testable.

## Why Not Hide Refresh Inside The Interpreter

That looks convenient at first, but it weakens the model.

Problems:

- read operations start mutating hidden state
- order-of-operations becomes implicit
- tests become harder to reason about
- "read meaning" and "refresh meaning cache" stop being distinct concepts

So the preferred model is:

- refresh explicitly
- read explicitly

## Why Not Hide Refresh Inside The Advancer

That is viable, but it fuses two concerns:

- physical time advancement
- interpretation refresh orchestration

That can be acceptable in a convenience wrapper, but it should not be the only seam.

Preferred layering:

- primitive advancer: advances physics only
- outer coordinator/runtime method: advance then refresh

## Recommended Runtime Convenience Method

To keep call sites clean, the runtime may expose a convenience method while still preserving separation internally:

```python
class GameRuntime:
    advancer: EngineAdvancerProtocol
    interpreter: ClinicalInterpreterProtocol
    refresher: InterpretationRefresherProtocol

    def advance_and_refresh(self, engine, minutes: float) -> None:
        self.advancer.advance_minutes(engine, minutes)
        self.refresher.refresh(engine)
```

This is the recommended practical shape.

It keeps call sites small without smearing responsibilities together.

## Outer Ownership Target

Longer-term, the cleanest composition root likely looks like:

```python
engine = VirtualCreature(...)
signs_engine = ClinicalSignsEngine(engine, defs, species)
interpreter = DefaultClinicalInterpreter(signs_engine=signs_engine)
runtime = GameRuntime(
    advancer=PhysicalMinuteAdvancer(),
    interpreter=interpreter,
    refresher=ClinicalSignsRefresher(signs_engine),
)
```

At that point:

- engine does not construct interpretation objects
- runtime/app composition does

## Migration Notes

This composition can be adopted in stages:

1. add `refresher` seam to runtime
2. route application time advancement through `advance_and_refresh(...)`
3. keep kernel-owned refresh temporarily as compatibility
4. move interpretation object creation out of the kernel later

## Main Design Rule

The runtime should orchestrate.

The advancer should advance.

The interpreter should interpret.

The refresher should refresh.
