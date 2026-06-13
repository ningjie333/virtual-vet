# Test Evidence Registry

Registry of external evidence used, or planned to be used, for literature-backed
kernel tests.

Last reviewed: 2026-06-13

## Purpose

This file is the bookkeeping layer.

It records:

- which external sources we are using
- what kind of evidence they provide
- which tests they support
- whether the source is already encoded into assertions
- whether the current model appears aligned or discrepant

This avoids two bad outcomes:

- evidence scattered across ad hoc comments
- “literature-backed” claims that cannot be audited later

## Status Labels

### `encoded`

The source is already reflected in at least one concrete test assertion.

### `planned`

The source has been selected, but the corresponding assertion upgrade is not
yet implemented.

### `discrepancy`

The source is relevant, but current model behavior appears materially different
enough that we should not silently encode it as a passing test yet.

## Evidence Table

| Domain | Source | Type | Status | Current target files | Notes |
|---|---|---|---|---|---|
| Canine blood gas reference ranges | Merck Veterinary Manual blood gas reference ranges | Reference manual | `encoded` | `tests/test_blood.py`, `tests/test_lung.py` | Encoded for default canine arterial blood gas baselines; integrated lung baseline still needs separate review |
| Healthy canine GFR reference intervals | Bexfield et al., PMID `18289291` | Healthy reference dataset | `encoded` | `tests/test_kidney.py` | Added weight-normalized healthy-dog GFR window |
| AKI diagnosis and management in dogs/cats | IRIS consensus, PMID `38325516` | Consensus statement | `planned` | `tests/test_diseases.py`, `tests/test_cross_module_coupling.py`, `tests/test_untreated_deterioration.py` | Best anchor for AKI staging / feature expectations |
| AKI clinical context in dogs | Review, PMID `35103347` | Review | `planned` | `tests/test_diseases.py`, `tests/test_untreated_deterioration.py` | Supports GFR decline, azotemia, hyperkalemia, acid-base worsening expectations |
| Bicarbonate deficiency / kidney injury relevance | Study, PMID `37235446` | Observational clinical study | `planned` | `tests/test_diseases.py`, `tests/test_cross_module_coupling.py` | Good support for acid-base assertions in renal disease |
| Respiratory / pneumonia guidance | ISCAID guideline, PMID `28185306` | Guideline | `planned` | `tests/test_diseases.py`, `tests/test_species_specific.py`, `tests/test_untreated_deterioration.py` | Good anchor for disease relevance and clinical outcome framing |
| Respiratory disease oxygenation associations in dogs | Study, PMID `38250933` | Observational study | `planned` | `tests/test_species_specific.py`, future pneumonia checkpoints | Useful for oxygenation-centered assertions |
| Fluid therapy in ill dogs/cats | AAHA 2024 fluid therapy guidelines | Guideline | `planned` | future hemodynamic response tests | Best for bolus / hypovolemia response tests |
| Equine arterial blood gas reference anchor | Sherlock 2019 as already cited in repo lifecycle notes | Literature anchor | `discrepancy` | future equine baseline tests | Current sampled model PaCO2 appears too low |

## Source Records

> **Paper → Code traceability** (P3-2): Every source below is mapped to its
> **Hierarchy ID** (see [docs/literature-hierarchy.md](literature-hierarchy.md))
> and the **Code modules** that consume its parameters. New sources MUST
> register in `literature-hierarchy.md` first (Anti-Scatter Rule).

### 1. Merck Veterinary Manual blood gas reference ranges

- Hierarchy ID: `S-CV-1` (Nelson & Couto Small Animal Internal Medicine 5e, Ch.22)
- Code modules: `src/blood.py`, `src/lung.py`
- URL: https://www.merckvetmanual.com/multimedia/table/blood-gas-analysis-reference-ranges
- Role:
  - healthy blood gas baseline windows
  - best used for broad normal-range assertions
- Target tests:
  - `tests/test_blood.py`
  - `tests/test_lung.py`
- Current encoding:
  - `tests/test_blood.py::test_canine_default_arterial_blood_gases_match_merck_reference_ranges`
- Current caution:
  - integrated canine lung/engine stabilization still appears slightly high for
    `PaO2` relative to the Merck arterial window, so `tests/test_lung.py`
    remains a follow-up item rather than a silently widened pass
- Status:
  - `encoded`

### 2. Bexfield et al. healthy-dog GFR reference intervals

- Hierarchy ID: `S-REN-2` (Bexfield et al. 2008, healthy dog GFR)
- Code modules: `src/kidney.py`
- URL: https://pubmed.ncbi.nlm.nih.gov/18289291/
- PMID: `18289291`
- Role:
  - healthy-dog weight-normalized GFR reference interval
- Current encoding:
  - `tests/test_kidney.py::test_GFR_normal_MAP_matches_healthy_dog_reference_interval`
- Status:
  - `encoded`

### 3. IRIS AKI best-practice consensus

- Hierarchy ID: `S-REN-1` (Segev G et al. IRIS AKI Consensus 2024)
- Code modules: `src/kidney.py`, `data/ode_diseases.json::acute_renal_failure`
- URL: https://pubmed.ncbi.nlm.nih.gov/38325516/
- PMID: `38325516`
- Pub type:
  - consensus statement
- Role:
  - highest-priority external anchor for AKI feature expectations
  - useful for deciding what should be tested in AKI besides raw GFR
- Target tests:
  - `tests/test_diseases.py`
  - `tests/test_cross_module_coupling.py`
  - `tests/test_untreated_deterioration.py`
- Status:
  - `planned`

### 4. Canine AKI review / clinicopathologic context

- Hierarchy ID: `S-REN-1` (IRIS-aligned; same source pool as record 3)
- Code modules: `src/kidney.py`
- URL: https://pubmed.ncbi.nlm.nih.gov/35103347/
- PMID: `35103347`
- Role:
  - reinforces expected AKI-associated deterioration patterns
- Target tests:
  - `tests/test_diseases.py`
  - `tests/test_untreated_deterioration.py`
- Status:
  - `planned`

### 5. Bicarbonate deficiency / kidney injury relevance

- Hierarchy ID: `C4` (Henderson-Hasselbalch) for HCO3 chemistry; `S-REN-1` for clinical context
- Code modules: `src/blood.py`, `src/fluid.py`
- URL: https://pubmed.ncbi.nlm.nih.gov/37235446/
- PMID: `37235446`
- Role:
  - supports acid-base deterioration checks in kidney disease
- Target tests:
  - `tests/test_diseases.py`
  - `tests/test_cross_module_coupling.py`
- Status:
  - `planned`

### 6. ISCAID respiratory guideline

- Hierarchy ID: `S-RESP-1` (Lappin MR et al. ISCAID 2017)
- Code modules: `src/lung.py`, `data/ode_diseases.json::pneumonia`
- URL: https://pubmed.ncbi.nlm.nih.gov/28185306/
- PMID: `28185306`
- Role:
  - clinical framing for respiratory disease / pneumonia expectations
- Target tests:
  - `tests/test_diseases.py`
  - `tests/test_species_specific.py`
  - `tests/test_untreated_deterioration.py`
- Status:
  - `planned`

### 7. Respiratory disease oxygenation study in dogs

- Hierarchy ID: `S-RESP-3` (Dear JD 2020 pneumonia oxygenation)
- Code modules: `src/lung.py`
- URL: https://pubmed.ncbi.nlm.nih.gov/38250933/
- PMID: `38250933`
- Role:
  - supports oxygenation-centered respiratory assertions
- Target tests:
  - `tests/test_species_specific.py`
  - future pneumonia sparse-checkpoint tests
- Status:
  - `planned`

### 8. AAHA 2024 fluid therapy guidelines

- Hierarchy ID: `S-FLUID-1` (AAHA 2024)
- Code modules: `src/fluid.py`
- URL: https://www.aaha.org/resources/2024-aaha-fluid-therapy-guidelines-for-dogs-and-cats/section-5-fluid-therapy-in-ill-patients/
- Role:
  - future hemodynamic and resuscitation response tests
- Target tests:
  - future blood-loss / fluid-bolus tests
- Status:
  - `planned`

### 9. Equine blood gas anchor from existing repo literature notes

- Hierarchy ID: `(unregistered)` — TODO add to `literature-hierarchy.md` Tier 2 as `S-EQUINE-1`
- Code modules: `src/lung.py`, `src/parameters.py`

- Source in repo:
  - `tests/test_lifecycle_literature.py`
  - Sherlock 2019 reference already cited there
- Current local sampling on `2026-06-10`:
  - equine `PaCO2` after stabilization about `29-30 mmHg`
  - equine `pH` about `7.53-7.56`
- Why not encoded yet:
  - this currently looks discrepant enough that forcing a passing “literature
    window” test would either fail immediately or require dishonest widening
- Status:
  - `discrepancy`

## Current Implemented Literature-Backed Assertions

### Already implemented

- `tests/test_kidney.py`
  - healthy-dog normalized GFR reference interval using PMID `18289291`

### Literature-informed but not yet tightly source-windowed

- `tests/test_species_specific.py`
  - pneumonia now degrades oxygenation versus healthy matched controls
- `tests/test_untreated_deterioration.py`
  - ARF now worsens `GFR`, `K`, and `pH`
- `tests/test_diseases.py`
  - ARF integration now worsens `GFR`, `BUN`, `K`, and `pH`

These are clinically informed and source-aligned in direction, but they are not
yet strict literature-window assertions.

## Open Technical Risks Discovered While Sampling

### Coupling-rule wiring gap traced and contained

During long ARF sampling on `2026-06-10`, repeated warnings were observed:

- `apply_factor: unknown target 'fluid.vascular_volume_ml'`

Root cause traced:

- the aldosterone retention rule in `data/coupling_rules.json` targeted an
  unregistered FactorCommand path
- independently, the MAP→GFR rule used `mean_arterial_pressure` while the
  engine actually publishes the heart signal as `MAP`, so that rule could
  silently skip evaluation
- enabled GFR-coupled expressions also used `gfr` instead of runtime-published
  `GFR`, allowing additional silent no-op behavior

Containment applied:

- `validate_coupling_rules()` now rejects unknown coupling targets
- `validate_coupling_rules()` now also rejects unknown runtime source signals
  and unknown expression identifiers
- the aldosterone rule was disabled pending a proper retained-volume-rate
  design, rather than being silently allowed through an invalid write path
- the MAP→GFR rule now uses the published `MAP` signal name
- GFR-coupled rules now use the runtime-published `GFR` identifier

Remaining modeling gap:

- chronic sodium/water retention should ultimately be implemented through a
  rate or integral channel, not repeated per-step multiplication of a stateful
  volume variable

## Maintenance Rule

Whenever a new external source is used to justify a test constraint:

1. add it here
2. mark it `encoded`, `planned`, or `discrepancy`
3. note which test files it supports
4. avoid citing the source in code comments alone without registering it here
