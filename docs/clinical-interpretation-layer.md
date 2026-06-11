# Clinical Interpretation Layer Sketch

Concrete refactor sketch for the layer between the physiology kernel and the outer game/application shell.

Last reviewed: 2026-06-09

## Why This Layer Exists

The kernel answers:

- what is the physiological state?
- how does it evolve in physical time?

The application/game answers:

- what can the player do next?
- how much scenario time does it cost?
- did the player win, lose, or wait too long?

The clinical interpretation layer answers:

- what would a clinician observe right now?
- what signs are active?
- what should an exam report say?
- how severe does this case look from a medical-facing summary?

This layer should translate kernel state into clinically legible outputs without letting gameplay concerns infect kernel design.

## Current Code That Already Behaves Like This Layer

### Existing interpretation-like code

- `src/clinical_state.py`
  - `extract_clinical_state(creature)`
  - `build_clinical_snapshot(creature)`
- `src/report_engine.py`
  - `get_state(creature)`
  - `generate_report(test_type, creature)`
- `src/clinical_signs_engine.py`
  - `compute(current_time_s)`
  - `get_active_signs()`
  - `get_sign_tags()`
- `game/action_system.py`
  - `determine_phase(engine)`
  - `_engine_summary(engine, elapsed_min)`

### Why the boundary is still blurry

- `game/action_system.py` still computes medical phase by directly reading engine internals
- `_engine_summary()` still directly assembles clinical-facing values out of raw engine state
- `src/simulation.py` still creates `ClinicalSignsEngine` inside `attach_disease()`
- `src/report_engine.get_state()` is effectively a snapshot adapter, but it is not yet treated as a first-class interface

Update as of 2026-06-09:

- the shared state adapter now lives in `src/clinical_state.py`
- `DefaultClinicalInterpreter` is the preferred public interface
- `determine_phase()`, `_engine_summary()`, and `game.test_translator.translate()` now remain only as legacy compatibility entry points

## Desired Layer Split

### 1. Kernel

Owns:

- state variables
- solvers
- organ coupling
- disease progression
- physical time

Must not own:

- report templates
- symptom wording
- phase labels like `"worsening"` or `"moribund"` as game/application policy
- session-facing summaries

### 2. Clinical Interpretation Layer

Owns:

- stable clinical snapshot extraction
- active sign derivation
- exam report generation
- medical-facing severity / phase interpretation
- clinician-facing summary formatting

Must not own:

- win/loss
- time budget
- exam ordering workflow
- session persistence

### 3. Application / Game Layer

Owns:

- player actions
- scenario time and latency
- case orchestration
- diagnosis workflow
- phase transitions in the game sense

Should consume interpretation outputs instead of re-reading kernel internals ad hoc.

## Proposed Interfaces

## 1. Clinical Snapshot

Suggested file:

- `src/clinical_snapshot.py`

Suggested shape:

```python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClinicalSnapshot:
    time_s: float
    species: str
    weight_kg: float

    hr_bpm: float
    map_mmhg: float
    cvp_mmhg: float
    rr_bpm: float
    spo2_pct: float
    pao2_mmhg: float
    paco2_mmhg: float
    ph: float
    gfr_ml_min: float
    urine_ml_min: float
    bun_mg_dl: float
    lactate_mmol_l: float
    temperature_c: float

    co_ml_min: float
    blood_volume_ml: float
    contractility_factor: float
    diffusion_coefficient: float

    sodium_meq_l: float
    potassium_meq_l: float
    glucose_mmol_l: float
    hct_pct: float
    hco3_meq_l: float

    heart_health: float
    lung_health: float
    kidney_health: float

    disease_name: str | None
    disease_active: bool
    disease_state: dict[str, Any] | None
```

Purpose:

- one stable read model for downstream consumers
- one place to decide whether to read from `history` or direct module attributes
- one place to normalize names and units

This is the formalized version of what `src/report_engine.get_state()` is already approximating today.

## 2. Clinical Interpreter

Suggested file:

- `src/clinical_interpreter.py`

Suggested protocol:

```python
from typing import Protocol, Sequence


class ClinicalInterpreterProtocol(Protocol):
    def snapshot(self, engine) -> ClinicalSnapshot: ...
    def active_signs(self, engine) -> Sequence[ClinicalSign]: ...
    def sign_tags(self, engine) -> list[str]: ...
    def report(self, test_type: str, engine) -> dict: ...
    def phase(self, snapshot: ClinicalSnapshot) -> str: ...
    def summary(self, snapshot: ClinicalSnapshot, elapsed_min: int) -> dict: ...
```

This interface is the key seam.

The application layer should ask the interpreter for:

- a report
- a phase
- a summary

It should not reconstruct those itself from raw engine internals.

## 3. Default Implementation

Suggested implementation composition:

- `snapshot()`:
  - wrap the shared `src/clinical_state.py` adapter
- `active_signs()` and `sign_tags()`:
  - delegate to `ClinicalSignsEngine`
- `report()`:
  - delegate to `report_engine.generate_report()`
- `phase()`:
  - move current `game.action_system.determine_phase()` logic here
- `summary()`:
  - move current `game.action_system._engine_summary()` logic here

This means phase 1 can add the seam without changing numerical formulas or report content.

## Concrete Mapping From Current Code

### Move or wrap first

`src/report_engine.get_state(creature)`

Current role:

- legacy compatibility wrapper over the shared clinical-state adapter

Target role:

- compatibility helper only; not the preferred public seam

### Keep as implementation, not public architecture center

`src/report_engine.generate_report(test_type, creature)`

Current role:

- exam report builder

Target role:

- implementation detail behind `ClinicalInterpreter.report()`

### Move out of game layer

`game.action_system.determine_phase(engine)`

Current role:

- legacy compatibility entry point

Target role:

- `ClinicalInterpreter.phase(snapshot)`

### Move out of game layer

`game.action_system._engine_summary(engine, elapsed_min)`

Current role:

- legacy compatibility entry point

Target role:

- `ClinicalInterpreter.summary(snapshot, elapsed_min)`

### Decouple from kernel lifecycle later

`src/simulation.py: attach_disease() -> ClinicalSignsEngine(...)`

Current role:

- kernel creates interpretation object during disease attachment

Preferred target:

- composition root creates or injects interpretation support

This does not have to move in phase 1, but it should be documented as temporary.

## Recommended Migration Order

### Phase 1: Add seam, keep behavior

1. add `ClinicalSnapshot`
2. add `ClinicalInterpreterProtocol`
3. add a default interpreter implementation backed by existing report/sign logic
4. change `game/action_system.py` to depend on interpreter outputs instead of direct raw reads

Result:

- no gameplay API break
- no numerical behavior change
- cleaner dependency direction

### Phase 2: Reduce kernel knowledge in application code

1. delete or shrink direct raw-state helpers in `action_system.py`
2. route report/phase/summary through interpreter everywhere
3. make tests consume interpreter seam intentionally

### Phase 3: Move interpretation lifecycle out of kernel

1. stop constructing `ClinicalSignsEngine` inside `VirtualCreature.attach_disease()`
2. initialize interpretation objects in an outer composition layer
3. keep the kernel free of report/sign-engine ownership

## What This Layer Is Not

It is not:

- a UI formatter
- a persistence serializer
- a game rule engine
- a place to rescale disease rates for pacing

If a feature changes physiology, it belongs in the kernel.

If a feature only changes how physiology is described, observed, summarized, or classified clinically, it belongs here.

If a feature changes player workflow or scenario timing, it belongs in the application layer.

## Short Design Rule

The kernel should produce truth.

The clinical interpretation layer should produce meaning.

The game layer should produce experience.
