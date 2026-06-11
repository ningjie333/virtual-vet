# Clue Trigger Plan

Plan for making clue production explicit, auditable, and compatible with a
kernel-first clinical architecture.

Last reviewed: 2026-06-11 (Q2 & Q3 resolved; Q1 superseded — see Q1 Resolution section)

## Purpose

This note defines how `clue` production should work.

It is narrower than the overall interpretation refactor.
Its job is to answer four questions:

1. what kinds of clues exist?
2. which layer is allowed to trigger each kind?
3. how should diagnosis consume clues safely?
4. how do we migrate from the current mixed system without breaking the kernel?

## Guiding Rule

The physiology kernel remains the source of truth.

`clue` logic is downstream interpretation logic.
It must read kernel truth, not reshape kernel science around UI or game needs.

The architecture rule is:

```text
kernel state
  -> observation snapshot
  -> clue derivation
  -> exam/report projection
  -> diagnosis / suggestion / explanation
```

Game flow may decide when to ask for a report.
Game flow must not decide what a clinically meaningful clue means.

## Non-Goals

This plan does not:

- rewrite disease ODEs or organ coupling
- change solver semantics
- redefine disease natural history just to make clue emission easier
- merge every clue into one file immediately

## Current Audit Snapshot

Current implementation facts from the codebase audit:

- distinct clue universe: `167`
- symptom-layer clue count: `110`
- exam-tag clue count: `47`
- `diseases.json` `clue_to_test` entries: `70`
- direct overlap between symptom clues and exam-tag clues: `7`

Direct overlaps already found:

- `anuria`
- `arrhythmia`
- `crackles`
- `dehydration`
- `icterus`
- `petechiae`
- `pulsus_paradoxus`

Current structural problems:

- symptom rules already emit global clinical clues
- exam templates also emit partly global clues
- diagnosis consumes only report `tags`
- some diagnosis clues are not owned by symptom rules at all
- many symptom clues never participate in diagnosis
- report templates therefore act as a second clue engine

This is the core inconsistency:

```text
kernel
  -> signs engine emits clues
  -> report templates emit clues again
  -> diagnosis trusts report tags only
```

## Why This Matters

Without an explicit clue-trigger policy, the system drifts in three ways:

1. the same clinical concept gains multiple trigger definitions
2. diagnosis quality depends on which exam happened to emit a tag
3. report wording, clue semantics, and suggested-test logic become coupled

For a kernel-first project, this is backwards.
The clinically meaningful signal should exist before report formatting.

## Core Design Principles

### 1. One clue, one primary owner

Every clue ID must have one primary trigger owner.

Other layers may:

- display it
- suppress it from a given report
- route it into diagnosis
- alias it during migration

Other layers may not silently redefine its trigger condition.

### 2. Tags are transport, clues are semantics

`report.tags` should be treated as a transport surface for already-defined clue
semantics.

A report may package clues.
A report should not invent globally meaningful clues ad hoc.

### 3. Observation first, interpretation second

Clues should derive from explicit observation surfaces:

- normalized vitals
- normalized lab values
- explicit disease-marker view where latent disease state is still needed

They should not be open-ended reads from arbitrary `creature.*` or
`disease.*` paths inside many consumers.

### 4. Exam-local findings are allowed, but must stay local

Some findings are exam-specific evidence, not global bedside signs.

Examples:

- `lung_exudate_xray`
- `lung_exudate_ct`
- `cardiomegaly_us`
- `t_wave_tall`

These are legitimate clues, but they are owned by the corresponding exam
finding layer, not by the symptom engine.

### 5. No scattered hardcoding

The target is not a larger pile of `if clue_id == ...`.

The target is an explicit clue registry with machine-checkable metadata.

## Proposed Clue Taxonomy

Each clue should belong to exactly one of these categories.

## A. Bedside observational clues

Definition:
Clinically observable signs or symptoms that can be derived from the shared
clinical observation snapshot.

Examples:

- `crackles`
- `arrhythmia`
- `pulsus_paradoxus`
- `icterus`
- `petechiae`
- `dehydration`
- `anuria`

Primary owner:

- signs / symptom engine

Allowed trigger inputs:

- observation snapshot
- explicitly exposed disease markers only when the sign truly depends on a
  latent variable that is not otherwise observable

Not allowed:

- duplicate trigger rules in exam templates

## B. Quantitative abnormality clues

Definition:
Thresholded abnormalities from measured values.

Examples:

- `hr_high`
- `hr_low`
- `rr_high`
- `map_low`
- `PaO2_low`
- `PaCO2_high`
- `wbc_high`
- `plt_low`
- `cr_high`
- `bun_high`

Primary owner:

- normalized measurement-to-clue translators

Recommended ownership split:

- bedside vitals abnormality clues from shared vital-range config
- lab abnormality clues from assay-specific range config
- blood-gas abnormality clues from blood-gas range config

Not allowed:

- each exam template inventing its own threshold definition for the same global
  abnormality

## C. Exam-evidence clues

Definition:
Findings that only exist because a specific exam modality was performed.

Examples:

- `lung_exudate_xray`
- `lung_exudate_ct`
- `lung_exudate_us`
- `cardiomegaly_xray`
- `cardiomegaly_us`
- `t_wave_tall`
- `qrs_wide`
- `p_wave_absent`
- `usg_low`
- `upcr_high`

Primary owner:

- exam-specific finding translators

Allowed location of logic:

- exam template rules
- or dedicated exam adapters that templates call

Rule:

These clues are permitted to remain exam-owned because the modality itself is
part of the meaning.

## D. Derived diagnostic synthesis clues

Definition:
Higher-level abstractions inferred from multiple lower-level observations or
findings.

Examples:

- a future generic `respiratory_failure_pattern`
- a future generic `coagulopathy_pattern`

Primary owner:

- dedicated synthesis layer only

Rule:

This category should remain small.
If a clue can be expressed directly as an observed sign or measured
abnormality, prefer that simpler ownership.

## E. Deprecated aliases

Definition:
Compatibility IDs kept only to avoid a big-bang break.

Rule:

- must map to a canonical clue ID
- must have an expiry plan
- must not accumulate indefinitely

## Ownership Matrix

| Clue category | Primary owner | May appear in report tags | May drive diagnosis | Notes |
| --- | --- | --- | --- | --- |
| Bedside observational | signs engine | yes | yes | globally meaningful clinical findings |
| Quantitative abnormality | measurement translators | yes | yes | thresholds should be defined once |
| Exam-evidence | exam-specific translators | yes | yes | modality-specific evidence |
| Derived synthesis | synthesis layer | yes | yes, cautiously | keep small and explicit |
| Deprecated alias | alias registry | optionally | only through canonical mapping | migration-only |

## Proposed Registry Model

To avoid hardcoded clue semantics being scattered across files, introduce one
catalog of clue metadata.

Suggested shape:

```json
{
  "crackles": {
    "category": "bedside_observational",
    "owner": "symptom_engine",
    "diagnosis_allowed": true,
    "projection_allowed_in_reports": true,
    "suggested_test_owner": "auscultation",
    "canonical": "crackles"
  },
  "PaO2_low": {
    "category": "quantitative_abnormality",
    "owner": "blood_gas_ranges",
    "diagnosis_allowed": true,
    "projection_allowed_in_reports": true,
    "suggested_test_owner": "blood_gas",
    "canonical": "PaO2_low"
  }
}
```

Minimum fields the registry should own:

- clue ID
- category
- primary owner
- canonical ID
- diagnosis eligibility
- suggested-test source
- alias-of, if deprecated

This can be stored as `data/clue_catalog.json` later.
The important design point is that ownership becomes declarative and testable.

## Trigger Policy

## Rule 1. Every emitted clue must resolve through the registry

Any layer emitting a clue should be able to answer:

- is this clue registered?
- what category is it?
- who owns its trigger semantics?

Unregistered clue emission should fail validation.

## Rule 2. Reports may project, but not redefine, globally owned clues

If `crackles` is owned by the signs engine:

- auscultation reports may include `crackles`
- diagnosis may consume `crackles`
- auscultation template must not define a second independent `crackles`
  condition

If the report wants modality-specific evidence, it should use a distinct
exam-evidence clue, not redefine the global bedside clue.

## Rule 3. Measured abnormality clues should come from range translators

Clues such as:

- `hr_high`
- `map_low`
- `PaO2_low`
- `wbc_high`
- `cr_high`

should not be duplicated across many exam templates.

The exam decides whether that value is visible.
The threshold definition itself should live in the measurement translator.

## Rule 4. Exam templates may own modality-specific evidence only

`exam_templates.json` should gradually move toward:

- wording
- visibility
- grouping
- quantitative result display
- modality-specific findings

It should move away from owning global sign semantics.

## Rule 5. Diagnosis may consume only approved clue surfaces

`diseases.json` should reference only:

- registered bedside clues
- registered quantitative abnormality clues
- registered exam-evidence clues
- explicitly approved synthesis clues

Diagnosis should not depend on ad hoc report-only wording artifacts.

## Current Problems By Category

## A. Highest-risk duplicates

These clues already exist in both symptom definitions and exam tag rules:

- `crackles`
- `arrhythmia`
- `pulsus_paradoxus`
- `icterus`
- `petechiae`
- `dehydration`
- `anuria`

These should be resolved first because they create direct semantic conflict.

## B. Diagnosis-only but not symptom-owned clues

Examples:

- `PaCO2_high`
- `PaO2_low`
- `SpO2_low`
- `hr_high`
- `hr_low`
- `rr_high`
- `map_high`
- `map_low`
- `wbc_high`
- `plt_low`
- `cr_high`
- `bun_high`
- `gfr_low`

These are not necessarily wrong.
They are just currently owned in a fragmented way.
They should be normalized under quantitative translators.

## C. Exam-evidence clues currently mixed with general clues

Examples:

- `lung_exudate_xray`
- `lung_exudate_ct`
- `lung_exudate_us`
- `cardiomegaly_xray`
- `cardiomegaly_us`

These are legitimate modality-bound clues.
They should remain available to diagnosis, but their ownership must be explicit.

## D. Symptom-only clues with no diagnosis use

Examples:

- `cyanosis`
- `dyspnea`
- `cough`
- `orthopnea`
- `heart_murmur`
- `shock`

These are not useless.
They may still be valuable for:

- clinical narrative
- scenario presentation
- future differential logic
- severity summarization

But they should be classified intentionally instead of just existing by
accident.

## Migration Plan

## Wave 0. Freeze and classify the clue universe

Goal:

- build the first clue catalog
- assign every existing clue a category and primary owner
- mark aliases and unresolved ownership conflicts

Deliverables:

- `data/clue_catalog.json`
- validation script or test proving every emitted clue is cataloged

No semantic rewrites yet.
This wave makes the system inspectable.

## Wave 1. Eliminate direct duplicate owners

Target set:

- `crackles`
- `arrhythmia`
- `pulsus_paradoxus`
- `icterus`
- `petechiae`
- `dehydration`
- `anuria`

Policy:

- keep the global clue on the symptom/sign side
- let reports project the clue if visible in that exam
- remove duplicate global trigger rules from exam templates

If a modality-specific interpretation is needed, mint a distinct
exam-evidence clue rather than reusing the same global clue ID.

## Wave 2. Normalize quantitative abnormalities

Target set:

- vitals abnormalities
- blood-gas abnormalities
- CBC/chemistry/coag abnormalities

Policy:

- centralize threshold ownership in range translators
- let each exam decide visibility, not semantics
- keep report payload shape stable during migration if possible

This wave removes a large amount of hidden duplication from
`exam_templates.json`.

## Wave 3. Separate exam evidence from report narration

Target set:

- imaging clues
- ECG morphology clues
- urinalysis-specific clues

Policy:

- define modality-specific finding emitters explicitly
- let templates consume emitted findings for wording
- avoid mixing display formulas and clue trigger semantics in the same rule set

## Wave 4. Tighten diagnosis inputs

Policy:

- require all disease clues to exist in the clue catalog
- require diagnosis eligibility to be explicit
- move `clue_to_test` ownership into the same registry or a linked registry

This wave turns diagnosis from a loosely coupled consumer into a validated one.

## Wave 5. Reassess symptom-only clues

For the large set of symptom clues not currently used by diagnosis, choose one
of four outcomes:

1. keep as presentation-only clues
2. promote into diagnosis candidates
3. collapse into a broader canonical clue
4. deprecate

This should be evidence-driven, not aesthetic cleanup.

## Validation Rules

The following tests should eventually exist.

## Registry completeness

- every clue emitted by symptom rules exists in the clue catalog
- every clue emitted by exam rules exists in the clue catalog
- every clue referenced by `diseases.json` exists in the clue catalog

## Ownership integrity

- every canonical clue has exactly one primary owner
- duplicate owners are rejected unless explicitly marked as alias/projection
- symptom-owned clues cannot be redefined in exam templates

## Category integrity

- bedside observational clues may only be owned by the signs engine
- quantitative abnormality clues may only be owned by measurement translators
- exam-evidence clues may only be owned by approved exam finding translators

## Diagnosis integrity

- every disease clue has `diagnosis_allowed = true`
- every `clue_to_test` mapping references a registered clue
- deprecated aliases cannot be added to new disease definitions

## Projection integrity

- report templates may display registered clues
- report templates may not emit unregistered global clues
- report templates may only own clues whose registry category allows exam
  ownership

## Recommended Implementation Order In Code

1. add the clue catalog without changing behavior
2. add validation tests that classify current conflicts instead of failing on
   everything at once
3. fix the seven direct duplicate clues first
4. move quantitative abnormality ownership out of exam templates
5. then tighten diagnosis consumption rules

This order keeps the migration observable and low-risk.

## Immediate Decisions Already Recommended

Unless later evidence contradicts it, the default ownership should be:

- symptom engine owns global bedside clues
- measurement translators own global quantitative abnormality clues
- exam-specific translators own modality-bound findings
- diagnosis consumes only registered canonical clues

That gives the project a clean clinical boundary without forcing a kernel
rewrite.

## Open Questions

These do not block the plan, but they do affect later implementation detail:

1. ~~should some current symptom clues become presentation-only instead of
   diagnosis-facing?~~  **SUPERSEDED 2026-06-11** — see below
2. ~~should generic cross-modality abstractions such as "pulmonary infiltrate"
   exist, or should modality-specific evidence stay separate?~~  **RESOLVED 2026-06-11**
3. ~~should suggested-test routing stay in `diseases.json`, or move into the clue
   catalog as clue metadata?~~  **RESOLVED 2026-06-11**

### Q1 Resolution (2026-06-11)

**Decision**: Do NOT execute. The original Q1 framing assumed a distinction
between "diagnosis-facing" vs "presentation-only" symptom clues that does not
actually exist in the runtime. See `memory/2026-06-11-wave5-q1-superseded.md`
for the full evidence trail.

Concretely:

- The actual diagnosis matching path is
  `sign_tags → report.tags → match_diseases() → _DISEASE_CLUES (= diseases.json::clues)`.
- `diseases.json::clue_to_test` (the Q3-mapped field) does NOT participate
  in matching; it only recommends next-exam.
- Of the 110 symptom clues produced by the symptom engine, only **13** are
  referenced by any disease's `clues` list. The remaining **97** are already
  effectively presentation-only — they enter `report.tags` but never drive a
  match.
- Catalog-side `diagnosis_allowed` flags do not change runtime behavior;
  flipping them would be cosmetic.

**Implication**: Wave 5 of the migration plan is replaced by a deferred note.
The real contract work (diseases.json::clues integrity, naming-drift detection)
belongs to a future game-runtime refactor, not this plan.

### Q2 Resolution (2026-06-11)

**Decision**: Keep modality-specific evidence separate. Do NOT introduce
generic cross-modality abstractions.

Concretely:

- `lung_exudate_xray` / `lung_exudate_ct` / `lung_exudate_us` remain three
  distinct Category C clues, each owned by its respective exam finding
  translator.
- Diagnosis matches each one separately; no implicit `any_of` collapsing at
  the clue layer.
- If clinical logic needs "any imaging modality showing infiltrate → trigger X",
  aggregate in the disease config (`diseases.json`) using `any_of: [...]`,
  not at the clue layer.
- New Category C clues must carry a modality suffix (`*_xray` / `*_ct` / `*_us` /
  `*_ecg` / `*_usg`); bare IDs are not allowed in Category C.

Rationale:

- Modality is part of the semantic meaning (X-ray vs CT infiltrate carries
  different diagnostic weight).
- A new abstraction layer would introduce hidden `any_of` behavior and make
  diagnosis matching opaque.
- Wave 0–4 must not add new abstraction layers; clean existing owners first.

### Q3 Resolution (2026-06-11)

**Decision**: Move `clue_to_test` ownership entirely into
`data/clue_catalog.json`. Do NOT keep overrides in `diseases.json`.

Concretely:

- `data/clue_catalog.json` gains a `suggested_tests` field on every Category
  A/B/C entry. Empty array `[]` is allowed and means "no specific next exam".
- `diseases.json` drops the `clue_to_test` field entirely. Only `clues`
  remains (the diagnosis match list).
- The diagnosis / "suggest next exam" code reads `suggested_tests` from the
  catalog, not from the disease config.
- No override mechanism (`clue_to_test_override` is forbidden) — YAGNI.

Fallback rule when `suggested_tests` is empty: the report / suggestion code
falls back to a generic baseline exam set defined at the code layer, not the
data layer.

Rationale:

- "Seeing crackles → auscultate" is the semantics of `crackles`, not of any
  particular disease. The recommendation belongs to the clue's owner.
- The override case (clue X suggests different exams in different diseases)
  is rare in clinical practice; if it ever appears, it is a NEW clue
  (e.g. `crackles_with_edema`), not a config override.
- Aligns with Q2: a clean one-owner-per-clue boundary is easier to enforce
  when the owner's recommendation responsibility also lives in one place.

Wave 4 validation rules following this decision:

- every Category A/B/C entry in the catalog must declare `suggested_tests`
  (may be `[]`)
- `diseases.json` schema rejects `clue_to_test` field
- `diseases.json` schema rejects any `clue_to_test_override` field

The safest default is:

- do not add new abstraction layers until the current clue owners are clean
- keep modality-specific evidence separate for now  ← confirmed by Q2 decision
- treat the clue catalog as the future home of ownership metadata  ← confirmed by Q3 decision

## Residual Ambiguities

After the high-confidence alias and category cleanup, a small set of
diagnosis-facing clue IDs still remain intentionally unresolved.

These are not being force-migrated yet because the current codebase does not
contain a sufficiently precise one-to-one canonical replacement.

### Reviewed 2026-06-11

| clue ID | Current state | Why not force-convert yet | Recommended next move |
| --- | --- | --- | --- |
| `hemorrhage` | diagnosis-only placeholder | Too broad. Current symptom layer has specific manifestations such as `hemoptysis`, `melena`, `hematemesis`, `petechiae`, `ecchymosis`, `bleeding_gums`, but no single canonical clue equal to generic "hemorrhage". | Either introduce a deliberate synthesis clue with explicit semantics, or replace disease clue usage with a disease-appropriate set of specific bleeding findings. |
| `pain_mobility` | diagnosis-only placeholder | No exact canonical symptom exists. `pain`, `weakness`, `neck_pain`, `thoracolumbar_pain`, and `limb_pain` overlap, but none is a guaranteed synonym of "pain causing reduced mobility". | Keep temporarily. Later decide whether this should become a new canonical bedside clue or be rewritten into existing symptom combinations. |
| `perfusion_poor` | diagnosis-only placeholder | Overlaps with `crt`, `cold_extremities`, `hypotension`, and `shock`, but not cleanly enough to alias without changing meaning. | Keep temporarily. Later either define a canonical perfusion clue explicitly or rewrite disease clue lists to use existing lower-level findings. |
| `splenic_mass` | diagnosis-only placeholder with ultrasound recommendation | Semantically this looks exam-evidence-like, probably future `splenic_mass_us`, but no current exam template emits such a clue. Reclassifying it now would create a modality-bound clue with no producer. | Keep temporarily. The right long-term fix is to add an emitting ultrasound finding clue, then alias or migrate `splenic_mass` to that canonical ID. |

### Rule

For these residual items:

- do not auto-convert them just to reduce the unresolved count
- do not invent new canonical IDs unless a real producer exists
- prefer explicit disease-clue rewrites over vague aliases

This is a deliberate pause, not unfinished bookkeeping.
