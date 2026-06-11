# Interpretation Migration Sequence

Execution-oriented migration sketch for finishing the interpretation refactor without destabilizing the kernel.

Last reviewed: 2026-06-09

## Goal

Finish the interpretation architecture in a controlled order:

- interface first
- refresh contract second
- lifecycle ownership last

## Current Status

Already completed:

1. physical-time advancement seam
2. runtime-based interpreter seam
3. shared clinical-state adapter
4. application-facing report/phase/summary routing through the interpreter
5. legacy API marking for old entry points

Not yet completed:

1. explicit outer refresh seam
2. outer-owned interpretation object construction
3. removal of kernel-owned interpretation lifecycle

## Recommended Sequence

### Phase A. Interface Closure

Status:

- mostly done

Meaning:

- new code reads clinical meaning through the interpreter seam

Main artifacts:

- `src/clinical_state.py`
- `src/clinical_interpreter.py`
- `game/runtime.py`

### Phase B. Refresh Contract

Status:

- not yet implemented

Target:

- runtime gains explicit refresh orchestration

Suggested work:

1. add `InterpretationRefresherProtocol`
2. add default refresher implementation
3. add `GameRuntime.advance_and_refresh(...)`
4. switch `process_action()` to use it
5. add focused refresh-contract tests

Expected outcome:

- application-visible advancement has one explicit freshness path

### Phase C. Outer Construction

Status:

- not yet implemented

Target:

- interpretation support can be created outside `VirtualCreature`

Suggested work:

1. make `DefaultClinicalInterpreter` optionally accept explicit sign-engine access
2. add outer composition helper for:
   - engine
   - signs engine
   - interpreter
   - runtime
3. migrate game / GUI / scenario helpers to this composition path

Expected outcome:

- outer layers can own interpretation composition before kernel cleanup begins

### Phase D. Kernel Lifecycle Removal

Status:

- intentionally deferred

Target:

- `simulation.py` no longer constructs or refreshes interpretation objects

Suggested work:

1. remove `ClinicalSignsEngine` creation from `attach_disease()`
2. remove kernel-side `compute(...)` calls
3. keep explicit outer refresh as the only freshness path
4. run slow scenario validation

Expected outcome:

- kernel becomes interpretation-lifecycle agnostic

## File Touch Map

Likely files for Phase B:

- `game/runtime.py`
- `game/action_system.py`
- new refresher file under `src/` or `game/`
- focused tests around runtime/action seam

Likely files for Phase C:

- composition helper file
- `gui_app.py`
- scenario/test helpers

Likely files for Phase D:

- `src/simulation.py`
- callers that relied on implicit sign refresh

## Safety Rules

During migration:

- do not change disease math
- do not change sign thresholds
- do not change report semantics unless explicitly intended
- keep fake-runtime test paths fast
- validate slow scenario paths after each ownership shift

## Recommended Stop Points

Good checkpoint boundaries:

1. after Phase B
   - explicit refresh contract exists
   - behavior should be unchanged

2. after Phase C
   - outer ownership exists
   - kernel compatibility still intact

3. after Phase D
   - kernel lifecycle cleanup complete

These are good review gates.

## Decision Needed

Only one decision is blocking the next concrete implementation phase:

- should the preferred public seam be a runtime convenience method like `advance_and_refresh(...)`
- or should the project require explicit separate `advancer` and `refresher` calls at each call site?

Recommendation:

- choose the runtime convenience method
- keep the primitive seams separate underneath

## Short Rule

Do not start kernel lifecycle cleanup until the refresh contract and outer construction path already exist.
