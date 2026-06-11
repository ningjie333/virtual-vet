# Clinical Translation Convergence Plan

Minimal-change plan for tightening the current kernel -> symptom -> report
translation path into one cleaner clinical interpretation layer.

Last reviewed: 2026-06-10

## Purpose

This note follows
[clinical-translation-implementation-audit.md](clinical-translation-implementation-audit.md).

The audit answered:

- how the current code really works
- where meaning is duplicated or inconsistent

This note answers the next question:

- what is the safest order to tighten the boundary without rewriting kernel science?

## Guiding Rule

Do not rewrite physiology to fix interpretation architecture.

The kernel remains the source of physiological truth.
This plan only changes:

- how truth is read
- how signs are derived
- how reports consume derived meaning

It does not change:

- disease rate constants
- solver semantics
- organ coupling math
- core disease-state evolution rules

## Desired End State

The target is not "more abstractions".
The target is one authoritative translation path:

```text
Kernel state
  -> clinical observation snapshot
  -> sign / clue derivation
  -> exam-specific report composition
  -> medical phase / clinician summary
```

The main architectural rule is:

- one clinical concept should have one primary owner

Examples:

- `crackles`
- `petechiae`
- `icterus`
- `pulsus_paradoxus`

should not each have multiple unrelated trigger definitions spread across
symptom rules and exam templates.

## Design Rules For The Refactor

### 1. One stable input model

Downstream interpretation code should not mix:

- `history`
- direct organ reads
- arbitrary `creature.*`
- arbitrary `disease.*`

inside every consumer.

Those decisions should be centralized once.

### 2. One owner per clue

For any globally meaningful clue ID:

- one layer owns the trigger definition
- other layers may display or route it
- other layers should not silently redefine it

### 3. Report composition is not sign derivation

Report templates may decide:

- wording
- grouping
- exam-specific visibility
- quantitative result formatting

They should not become a second global symptom engine.

### 4. Compatibility wrappers are allowed

We do not need a big-bang cutover.

Old entry points may survive temporarily if they become thin wrappers over the
new internal path.

## Minimal-Cut Strategy

The safest sequence is:

1. unify interpretation inputs
2. cut report-engine direct access to raw kernel objects
3. define clue ownership explicitly
4. then decide whether to consolidate more logic into the signs layer

This order matters.

If we start by merging rules first, we will be doing semantic cleanup while the
data path itself is still unstable.

## Phase 1: Freeze Inputs Behind Explicit Read Models

## Goal

Make every downstream interpreter consumer read through explicit, inspectable
objects instead of open-ended kernel references.

## Recommended move

Keep `ClinicalSnapshot`, but expand the interpretation-facing model set into two
explicit artifacts:

### A. Observation snapshot

Authoritative clinically observable values, normalized once.

Suggested shape:

```python
@dataclass(frozen=True)
class ClinicalObservation:
    time_s: float
    species: str
    weight_kg: float

    hr_bpm: float
    map_mmhg: float
    rr_bpm: float
    spo2_pct: float
    pao2_mmhg: float
    paco2_mmhg: float
    ph: float
    temperature_c: float

    gfr_ml_min: float
    urine_ml_min: float
    bun_mg_dl: float
    creatinine_mg_dl: float
    bilirubin_mg_dl: float
    lactate_mmol_l: float
    ketone_mmol_l: float

    sodium_meq_l: float
    potassium_meq_l: float
    glucose_mmol_l: float
    hct_pct: float
    plt_k_ul: float | None
    wbc_k_ul: float | None
    pt_s: float | None
    aptt_s: float | None
    fibrinogen_mg_dl: float | None

    co_ml_min: float
    cvp_mmhg: float
    blood_volume_ml: float
    bv_ratio: float
    contractility_factor: float
    diffusion_coefficient: float
```

This can be implemented as:

- a new dataclass
- or a broadened `ClinicalSnapshot`

The important part is not the class name.
It is the rule that report/sign/summary consumers all read the same canonical
observation surface.

### B. Disease marker view

Not all clinically relevant downstream meaning comes from direct observations.
Some current rules rely on disease-latent variables such as:

- `arrhythmia_severity`
- `tamponade_severity`
- `alveolar_exudate`
- `hemorrhage_risk`

Those should not remain open-ended `disease.*` reads inside report templates.

Instead, expose a deliberate marker view:

```python
@dataclass(frozen=True)
class DiseaseMarkerView:
    values: dict[str, float | bool | None]
```

This is not idealized physiology.
It is an explicit compatibility boundary around existing disease-latent state.

## Why this phase comes first

Because later clue cleanup will be unmanageable if:

- signs read one thing
- reports read another
- summaries read a third

## Recommended implementation style

Do not break callers yet.

Instead:

1. create the new read model builder
2. make `ClinicalInterpreter.report()` build it internally
3. make `ClinicalSignsEngine` consume it internally
4. keep old wrappers until tests move over

## Phase 2: Make Report Engine Consume Explicit Inputs Only

## Goal

Stop allowing report templates to reach directly into:

- `creature.*`
- arbitrary `disease.*`
- legacy `clinical_signs_engine`

## Recommended move

Introduce an internal report input object:

```python
@dataclass(frozen=True)
class ExamInterpretationInput:
    observation: ClinicalObservation
    disease_markers: DiseaseMarkerView
    clue_tags: list[str]
    active_signs: list[str]
```

Then move report generation toward:

```python
generate_report(test_type, exam_input)
```

not:

```python
generate_report(test_type, creature, state=..., sign_tags=...)
```

## Compatibility cut

Keep the public function name if desired, but invert ownership internally:

```python
def generate_report(test_type, creature, state=None, sign_tags=None):
    exam_input = _build_exam_input(creature, state=state, sign_tags=sign_tags)
    return generate_report_from_input(test_type, exam_input)
```

That keeps external behavior stable while tightening the real dependency graph.

## What to forbid after this phase

Within new report logic:

- no direct `creature.blood.*`
- no direct `creature.heart.*`
- no direct `disease.foo`
- no fallback read from `creature.clinical_signs_engine`

Everything should arrive through `ExamInterpretationInput`.

## Why this is the highest-value cut

Because today the report layer is the biggest boundary leak.

It currently does all of these:

- consumes observations
- re-derives clues
- reads raw kernel objects
- reads disease-latent state directly
- formats the final report

This phase does not yet decide which clue owner is correct.
It simply forces all report decisions to use explicit upstream inputs.

## Phase 3: Split Global Clues From Exam-Local Findings

## Goal

Separate:

- globally meaningful clinical clues
- exam-local rendering and narrative details

## Rule

Global clue IDs belong to the sign/clue derivation layer.

Exam templates may still define:

- exam-specific narrative branches
- imaging-specific pattern labels
- quantitative result flags

But they should not silently redefine global clue triggers.

## Recommended classification

### A. Global clinical clues

Examples:

- `crackles`
- `arrhythmia`
- `icterus`
- `petechiae`
- `pulsus_paradoxus`
- `dehydration`

These should have one primary derivation rule.

### B. Exam-local findings

Examples:

- `lung_exudate_xray`
- `cardiomegaly_us`
- `PaO2_low`
- `hr_high`

These may remain report-local if they are clearly treated as exam output labels
rather than global bedside signs.

## Concrete cleanup rule

For every overlapping clue ID:

1. choose primary owner
2. convert the other layer to consume or display it
3. delete duplicated trigger logic

## Suggested first cleanup batch

Highest-value first batch from the audit:

1. `crackles`
2. `pulsus_paradoxus`
3. `petechiae`
4. `icterus`

Reason:

- these currently drift across different proxy variables
- the semantic mismatch is larger than for `arrhythmia`

## Phase 4: Make Exam Timing Semantics Explicit

## Goal

Resolve the current split where:

- report describes pre-advance state
- phase/vitals describe post-advance state

## Minimal safe fix

Do not change exam timing semantics immediately.

First make them explicit in payloads and code.

Recommended additions:

- `observed_at_s`
- `reported_at_s`
- `report_basis`: `"pre_advance"` or `"post_advance"`

This keeps behavior stable while making the temporal model inspectable.

## Then decide policy deliberately

After timing is explicit, choose one of these models by exam type:

### Model A. Immediate bedside observation

For:

- physical
- inspection
- auscultation
- blood pressure

Policy:

- report should describe near-current state at exam completion

### Model B. Sample collected now, result available later

For:

- blood routine
- chemistry
- coagulation
- cytology

Policy:

- sampled-at state and available-at time are distinct

The main point is not which model wins today.
The point is to stop pretending the current mixed payload is one atomic clinical
observation.

## Phase 5: Tighten Tests Around Ownership And Drift

## Goal

Make future drift hard to reintroduce.

## Recommended test types

### 1. Overlap ownership tests

For every globally owned clue:

- assert exactly one primary rule source
- assert report layer only displays/forwards it

### 2. Input-boundary tests

Assert report generation no longer requires:

- `creature`
- `disease`
- engine-owned signs objects

when given explicit interpretation input.

### 3. Timing-basis tests

Assert report payloads explicitly identify:

- observation time
- release time
- basis semantics

### 4. Drift audits

Keep a small scriptable audit that reports:

- clue IDs appearing in both symptom definitions and exam tag rules
- differences in threshold source or variable source

The audit that produced the current overlap table can become a maintained guard.

## What Not To Do First

Do not start with:

- deleting `ClinicalSignsEngine`
- rewriting all symptom formulas
- removing all disease-latent variables from interpretation in one step
- moving every report rule into the sign layer immediately

Those are larger semantic changes.

The current problem is first a boundary problem, then a rule-unification
problem.

## Recommended Execution Order

If we continue from here, the cleanest order is:

1. add explicit observation + disease-marker read models
2. refit report engine to consume explicit inputs
3. define global clue ownership
4. clean high-risk overlapping clues
5. make timing basis explicit
6. only then consider deeper consolidation

## Bottom Line

The safest next move is not "rewrite symptom logic".

The safest next move is:

- stabilize the clinical translation inputs
- make report composition downstream-only
- then remove duplicated clue ownership case by case

That sequence preserves kernel credibility while making the interpretation layer
architecturally honest.
