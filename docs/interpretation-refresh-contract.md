# Interpretation Refresh Contract

Contract sketch for when and how interpretation state becomes current after kernel time advances.

Last reviewed: 2026-06-09

## Problem

Once interpretation lifecycle moves outward, we need one explicit rule for freshness.

Without that, callers can accidentally read:

- stale sign tags
- stale active signs
- stale clinically interpreted state

So this note defines the refresh contract that the outer layer should eventually enforce.

## Current Implicit Contract

Today the contract is implicit:

- advancing engine time also refreshes `ClinicalSignsEngine`

That works only because the kernel currently owns the refresh side effect.

Once ownership moves outward, this must become explicit.

## Contract Goal

After any application-visible physical time advancement:

- interpretation state must be refreshed before application code reads signs or reports that depend on refreshed sign state

That is the whole contract.

## Recommended Freshness Rule

Recommended rule:

1. advance physical time
2. refresh interpretation state
3. only then read interpreter outputs

Conceptually:

```python
runtime.advance_and_refresh(engine, minutes)
report = runtime.interpreter.report("physical", engine)
```

## Recommended Trigger Points

Refresh should be required after:

- `process_action()` time advancement
- scenario helper advancement used by application tests
- GUI/API flows that advance engine time

Refresh is not required for:

- pure reads with no time advancement
- static inspection of already-current state

## Recommended API Shape

Preferred practical contract:

```python
runtime.advance_and_refresh(engine, minutes)
```

Where internally:

```python
def advance_and_refresh(engine, minutes):
    advancer.advance_minutes(engine, minutes)
    refresher.refresh(engine)
```

This gives one obvious place to enforce freshness.

## Alternative Shapes

### Option A. Explicit two-step call

```python
runtime.advancer.advance_minutes(engine, minutes)
runtime.refresher.refresh(engine)
```

Pros:

- maximally explicit
- easy to test primitives independently

Cons:

- call sites can forget the second line

### Option B. Runtime convenience method

```python
runtime.advance_and_refresh(engine, minutes)
```

Pros:

- easiest to use correctly
- still keeps primitive seams available underneath

Cons:

- runtime gets slightly more orchestration behavior

### Option C. Lazy refresh on interpreter read

```python
runtime.interpreter.report(...)
```

Pros:

- less obvious call-site work

Cons:

- hidden mutation on read
- unclear freshness boundaries
- harder to test and reason about

Recommendation:

- choose Option B
- retain Option A internally as the primitive building block
- avoid Option C

## Required Invariants

Whatever implementation we choose, these invariants should hold:

- reports never depend on older sign state than the engine time they describe
- action results never expose stale `medical_phase` after advancement
- tests can bypass real advancement with fakes without breaking refresh semantics
- no interpretation refresh changes physiological kernel state

## Compatibility Phase

During migration there may be two refresh paths:

- kernel-owned refresh
- outer explicit refresh

That overlap is acceptable temporarily.

But the desired end state is:

- outer refresh is authoritative
- kernel refresh is removed later

## Testing Guidance

The refresh contract should eventually be covered by focused tests:

- advancing through runtime triggers exactly one refresh
- fake runtime can assert refresh calls without real simulation
- reports after advancement see updated sign tags
- stale-read regressions are impossible through the preferred runtime path

## Decision Needed

The main open design choice is small but real:

- should the preferred public seam be `runtime.advance_and_refresh(...)`
- or should the project enforce explicit two-step orchestration at call sites?

Recommendation:

- prefer `runtime.advance_and_refresh(...)`
- keep `advancer` and `refresher` separately injectable underneath

## Short Rule

Advance first.

Refresh second.

Interpret third.
