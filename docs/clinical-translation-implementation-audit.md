# Clinical Translation Implementation Audit

Current-code audit of the path from physiology kernel state to symptoms, tags,
exam findings, medical phase, and UI-facing report payloads.

Last reviewed: 2026-06-10

## Purpose

This note is narrower than the architecture sketches.

It answers two concrete questions about the code as it exists today:

1. how does a real exam request move through the implementation?
2. where are symptom/report meanings duplicated or inconsistent?

This is an implementation audit, not a target-state design note.

## Scope

Primary files:

- `gui_app.py`
- `game/action_system.py`
- `game/runtime.py`
- `src/clinical_state.py`
- `src/clinical_snapshot.py`
- `src/clinical_interpreter.py`
- `src/clinical_signs_engine.py`
- `src/report_engine.py`
- `data/symptom_definitions.json`
- `data/exam_templates.json`

## Current Exam Flow

Real request path for `POST /api/examine`:

1. `gui_app.py:api_examine()`
2. `game.action_system.process_action(..., "examine", ...)`
3. `runtime.interpreter.report(test_type, engine)`
4. `DefaultClinicalInterpreter.report()`
5. `extract_clinical_state(engine)`
6. `generate_report(test_type, creature, state=..., sign_tags=...)`
7. report is stored in `state.reports` or `state.pending_reports`
8. only after report creation, `runtime.advance_and_refresh(engine, time_cost)`
9. after advancement, `interpreter.snapshot(...) -> interpreter.phase(...) -> interpreter.summary(...)`
10. Flask route returns:
   - `report`
   - `new_reports`
   - `medical_phase`
   - `vitals`
   - `game_log`

In short:

```text
request
  -> report from pre-advance engine state
  -> advance physiology
  -> recompute medical phase and summary from post-advance engine state
  -> assemble response
```

That means the response can contain:

- a report describing the state before the exam consumed time
- a medical phase and vitals describing the state after time advanced

This is a real timing split in the current implementation, not just a conceptual
one.

## Current Read Models

There are two active clinical read models.

### 1. Dict-style clinical state

Built by `src/clinical_state.py:extract_clinical_state()`.

Characteristics:

- prefers the latest `history` values
- falls back to direct module attributes
- injects derived fields such as ECG interpretation details
- returns a mixed `dict`

Consumers:

- `DefaultClinicalInterpreter.report()`
- `ClinicalSignsEngine._get_engine_state()`
- `report_engine.get_state()`

### 2. Typed clinical snapshot

Built by `src/clinical_state.py:build_clinical_snapshot()`
into `src/clinical_snapshot.py:ClinicalSnapshot`.

Characteristics:

- wraps many of the same values into a typed dataclass
- still depends on `extract_clinical_state()` internally
- adds disease metadata and selected direct kernel values

Consumers:

- `DefaultClinicalInterpreter.phase()`
- `DefaultClinicalInterpreter.summary()`

## Layer-by-Layer Behavior

### A. Action layer

`process_action()` owns:

- exam action dispatch
- scenario time cost
- pending report queue
- engine advancement trigger
- phase/win/loss update

But for medical-facing outputs it already delegates to the interpreter.

Important implementation detail:

- `interpreter.report(...)` is called before time advancement
- `interpreter.phase(...)` and `interpreter.summary(...)` are called after time advancement

### B. Clinical interpreter layer

`DefaultClinicalInterpreter` is not one unified translator yet.

It currently does three different kinds of work:

- `snapshot()`: typed read-model construction
- `report()`: report generation via dict state + sign tags
- `phase()/summary()`: medical scoring and UI summary formatting

So this layer is a coordinator over multiple downstream read styles, not a
single coherent interpretation pipeline.

### C. Clinical signs layer

`ClinicalSignsEngine.compute()`:

- pulls a fresh dict state via `extract_clinical_state()`
- loops over every symptom rule in `symptom_definitions.json`
- evaluates threshold or multi-parameter rules
- tracks onset/offset/sustained activation
- stores active signs and clue tags

Important implementation detail:

parameter resolution is not limited to one stable snapshot.
It can read from:

- `state[...]`
- `blood.*`
- `heart.*`
- `lung.*`
- `kidney.*`
- `disease.*`
- `disease._state_vars`

So the signs layer is still directly coupled to kernel object structure.

### D. Report layer

`report_engine.generate_report()`:

- loads an exam template from `exam_templates.json`
- builds a context containing:
  - `state`
  - `thresholds`
  - `disease`
  - `creature`
  - `sign_tags`
- evaluates:
  - `tag_rules`
  - `findings_rules`
  - `extra_params`
  - formula strings

Important implementation details:

- report rules can read `creature.*` directly
- report rules can read `disease.*` directly
- report rules append `sign_tags`, but also define local tag conditions again
- report findings are not just formatting; they are another interpretation layer

## Current Data-Flow Diagram

```text
VirtualCreature
  -> extract_clinical_state() ----------------------------+
  -> build_clinical_snapshot() -> ClinicalSnapshot        |
                                                         |
ClinicalSignsEngine.compute()                            |
  reads dict state + module attrs + disease attrs        |
  -> active signs / sign_tags                            |
                                                         |
DefaultClinicalInterpreter.report()                      |
  -> extract_clinical_state()                            |
  -> sign_tags()                                         |
  -> report_engine.generate_report()                     |
       -> exam template tag_rules/findings_rules         |
       -> direct creature/disease reads still allowed    |
       -> structured report                              |
                                                         |
DefaultClinicalInterpreter.phase()/summary()             |
  -> ClinicalSnapshot                                    |
  -> medical phase / UI summary                          |
```

The practical consequence is:

- signs are one interpretation path
- report templates are a second interpretation path
- phase/summary are a third interpretation path

They share some source values, but they do not share one authoritative clinical
meaning model.

## Inconsistency Audit

## 1. Report timing and phase timing are split

Current sequence:

- exam report: pre-advance state
- vitals/medical phase/summary: post-advance state

Why this matters:

- a slow exam can show a report from one moment and a severity summary from a
  later moment
- the response payload looks atomic, but medically it is not one single-time
  observation

Severity:

- medium architectural inconsistency
- potentially high for longer-latency or faster-deteriorating cases

## 2. One clinical concept can be defined twice

A script-level audit found:

- 110 symptom `clue_id`s in `symptom_definitions.json`
- 47 exam `tag_rules` `clue_id`s in `exam_templates.json`
- only 7 direct overlaps

The overlap count is small, but the overlapping cases are exactly where drift
is most dangerous.

### Overlap table

| clue_id | symptom layer rule | exam/report layer rule | audit note |
| --- | --- | --- | --- |
| `arrhythmia` | `disease.arrhythmia_severity > 0.5` | `disease.arrhythmia_severity > thresholds.arrhythmia_severe` in `auscultation` | Mostly aligned. Low risk. |
| `anuria` | `disease.urine_output < 0.05` | `state.Urine < thresholds.urine_anuria` in `ultrasound` | Same domain, different source path and threshold surface. Medium risk. |
| `dehydration` | sustained `bv_ratio < 0.95` | `bv_ratio < thresholds.bv_dehydration_moderate` in `inspection` | Same concept, but symptom side is time-windowed and exam side is instantaneous. Medium risk. |
| `icterus` | `blood.bilirubin_mg_dL > 2.0 OR disease.bilirubin_load > 0.02 OR disease.hemolysis > 0.05` | `disease.bilirubin_load > thresholds.icterus_mild` in `inspection` | Symptom rule is multi-causal; exam rule is a narrower disease-latent proxy. High risk. |
| `petechiae` | `PLT < 50000 OR (PT > 18 AND Fibrinogen < 100)` | `disease.hemorrhage_risk > thresholds.dic_hemorrhage_mild` in `inspection` | Symptom rule is lab-facing; exam rule uses one latent disease proxy. High risk. |
| `pulsus_paradoxus` | sustained `disease.tamponade_severity > 0.18` | `disease.pulsus_paradoxus > thresholds.pulsus_paradoxus_severe` in `blood_pressure` | Different variable and symptom side requires duration. High risk. |
| `crackles` | `disease.pulmonary_edema > 0.3` | `state.PaO2 < thresholds.pao2_crackles_mild` in `auscultation`; `disease.alveolar_exudate > thresholds.exudate_significant` in `endoscopy` | Same clue is triggered by different physiological proxies in different places. High risk. |

### Why `crackles` is the clearest example

The same clinical concept is implemented via:

- pulmonary edema severity in symptom definitions
- low arterial oxygen in auscultation tagging
- alveolar exudate in endoscopy tagging

These are related, but they are not the same thing.
One concept is being approximated three different ways.

## 3. Signs and report tags are additive, not hierarchical

`_apply_tag_rules()` in `report_engine.py`:

- first evaluates local `tag_rules`
- then appends `sign_tags`

This means:

- the report layer does not consume sign output as the source of truth
- it emits its own tags and then merges symptom-layer tags afterward

So even when the sign layer already knows a clue is active, the report layer may
arrive at the same clue by a different condition.

This is not just duplication.
It means the system currently has two independent paths to the same clue ID.

Severity:

- high boundary problem

## 4. Rule engines differ in semantics

### Clinical signs engine

Supports:

- `threshold`
- `multi_parameter`
- sustained activation windows
- onset and offset delays
- nested boolean parsing with explicit parenthesis handling

### Report engine

Supports:

- flat `and` / `or` splitting in `_eval_condition()`
- direct comparison parsing
- no sign-style onset/offset tracking
- no sustained activation model in report tags/findings

Practical consequence:

the same textual condition can have different operational meaning depending on
which layer owns it.

Severity:

- medium now
- high if more report-side rules continue to encode clinical logic

## 5. Report layer still bypasses the signs layer

Many report-side clues are not defined in the symptom system at all.

Examples include:

- `hr_high`
- `hr_low`
- `map_low`
- `PaO2_low`
- `lung_exudate_xray`
- `cardiomegaly_us`

That is not automatically wrong.
Some are exam-specific findings rather than global symptoms.

But today there is no explicit rule separating:

- globally meaningful clinical signs
- exam-local interpretation artifacts
- pure report formatting convenience tags

So the distinction exists only implicitly in the data files.

## 6. Report layer reads raw kernel objects directly

Current report formulas can still reference:

- `creature.blood.creatinine_mg_dL`
- `creature.blood.bilirubin_mg_dL`
- `creature.blood.ketone_mmol_L`
- arbitrary `disease.*`
- arbitrary `creature.*`

This matters because the report layer is not constrained to a stable observation
model.

Even if `ClinicalSnapshot` becomes cleaner, report templates can currently
bypass it.

Severity:

- high architectural leakage

## 7. `extract_clinical_state()` already mixes observation and interpretation

It does not only expose raw clinically relevant values.
It also injects interpretation-like ECG fields such as:

- `T波`
- `QRS宽度`
- `P波`
- `K_toxicity_stage`
- `AV传导`

So the state adapter is already partly an interpretation layer.

That makes it harder to keep downstream layers clean, because the shared input
is already semantically mixed.

## Bottom Line

The current code does not implement one single translation pipeline.

It implements three partially overlapping meaning systems:

1. symptom derivation from `symptom_definitions.json`
2. exam/report interpretation from `exam_templates.json`
3. phase/summary scoring from `ClinicalSnapshot`

They are close enough to work for many cases.
They are not yet clean enough to count as one authoritative clinical
translation layer.

## What This Means For Refactor Priorities

If the goal is a kernel-first, clinically credible core, the highest-value next
boundary tightening is:

1. stop letting report templates read `creature` and arbitrary `disease` state directly
2. define which clues belong to the sign layer versus exam-local report logic
3. ensure one concept has one primary trigger definition
4. decide whether exam reports should describe pre-advance or post-advance state, then make the response internally consistent

This audit does not choose the final target design.
It only records where the current implementation is semantically split.
