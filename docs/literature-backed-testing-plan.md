# Literature-Backed Testing Plan

Plan for strengthening kernel tests with external evidence where external evidence
is appropriate.

Last reviewed: 2026-06-10

## Purpose

This project should not treat all tests the same.

Some tests should be backed by external veterinary or physiological literature:

- baseline reference ranges
- disease natural history
- treatment response
- species differences
- lifecycle / aging effects

Some tests should not pretend to be literature-backed:

- API shape
- persistence
- routing
- serialization
- protocol mechanics
- engineering performance budgets

This document focuses only on the first category.

## Core Rule

Use literature when the test is making a claim about:

- physiology truth
- clinical plausibility
- disease-course plausibility
- intervention plausibility

Do not use literature as fake decoration for:

- outer-layer contracts
- architecture seams
- benchmark thresholds

## Evidence Tiers

### `Tier A`

Best anchors for regression tests.

- consensus statements
- guidelines
- large healthy reference datasets
- standard veterinary reference manuals

Good for:

- baseline windows
- disease staging windows
- intervention response bounds

### `Tier B`

Useful but less authoritative.

- cohort studies
- retrospective studies
- disease reviews

Good for:

- trend assertions
- wide tolerance bands
- stage-dependent checkpoints

### `Tier C`

Mechanistic support, not final truth.

- experimental physiology papers
- narrower model systems
- older small studies

Good for:

- directionality
- relative ordering
- qualitative timing claims

## Current External Anchors Worth Using

### Blood gas baseline references

Use for:

- `tests/test_blood.py`
- `tests/test_lung.py`
- selected baseline checks in integration tests

Suggested anchors:

- Merck Veterinary Manual blood gas reference ranges
  - https://www.merckvetmanual.com/multimedia/table/blood-gas-analysis-reference-ranges

Constraint type:

- `Tier A`

Good assertion shapes:

- canine baseline pH / pCO2 / pO2 windows
- species-specific baseline windows where supported

### Healthy canine GFR reference intervals

Use for:

- `tests/test_kidney.py`
- disease progression checkpoints that refer back to normal canine GFR

Suggested anchor:

- Bexfield et al., healthy dogs GFR reference intervals
  - PubMed PMID `18289291`
  - https://pubmed.ncbi.nlm.nih.gov/18289291/

Constraint type:

- `Tier A` to `Tier B`

Good assertion shapes:

- healthy 20 kg canine baseline GFR sits in a literature-compatible band
- disease progression pushes GFR outside baseline-normal windows on appropriate timescales

### Acute kidney injury consensus / review literature

Use for:

- `tests/test_diseases.py` ARF
- `tests/test_cross_module_coupling.py`
- `tests/test_untreated_deterioration.py`

Suggested anchors:

- IRIS best-practice consensus for AKI in dogs and cats
  - PubMed PMID `38325516`
  - https://pubmed.ncbi.nlm.nih.gov/38325516/
- recent AKI review / clinicopathologic overview in dogs
  - PubMed PMID `35103347`
  - https://pubmed.ncbi.nlm.nih.gov/35103347/
- bicarbonate deficiency / acid-base relevance in canine kidney injury
  - PubMed PMID `37235446`
  - https://pubmed.ncbi.nlm.nih.gov/37235446/

Constraint type:

- consensus: `Tier A`
- review / observational support: `Tier B`

Good assertion shapes:

- AKI natural history should reduce GFR
- azotemia should rise with sustained low GFR
- potassium and acid-base disturbance should worsen in the right direction
- thresholds should be stage-aware, not single magic numbers at all times

### Pneumonia / respiratory disease literature

Use for:

- `tests/test_diseases.py` pneumonia
- `tests/test_species_specific.py`
- `tests/test_untreated_deterioration.py`
- future intervention-response tests

Suggested anchors:

- ISCAID respiratory / bacterial pneumonia guidance for dogs and cats
  - PubMed PMID `28185306`
  - https://pubmed.ncbi.nlm.nih.gov/28185306/
- recent respiratory-disease observational work in dogs
  - PubMed PMID `38250933`
  - https://pubmed.ncbi.nlm.nih.gov/38250933/

Constraint type:

- guideline: `Tier A`
- observational respiratory association study: `Tier B`

Good assertion shapes:

- pneumonia should worsen oxygenation metrics relative to matched healthy baseline
- cross-species disease tests should use hypoxemia-related outputs rather than trivial positivity checks
- treatment-response tests should target oxygenation improvement windows

### Fluid therapy and hemodynamic response

Use for:

- future tests in `tests/test_cross_module_coupling.py`
- future tests for blood-loss recovery and bolus response

Suggested anchor:

- AAHA 2024 fluid therapy guidelines
  - https://www.aaha.org/resources/2024-aaha-fluid-therapy-guidelines-for-dogs-and-cats/section-5-fluid-therapy-in-ill-patients/

Constraint type:

- `Tier A`

Good assertion shapes:

- blood loss should reduce perfusion markers
- fluid bolus should improve MAP / perfusion or volume-linked outputs within bounded windows

## File-By-File Priorities

### `tests/test_blood.py`

Current status:

- already fairly strong

Next literature-backed upgrades:

- make explicit that default canine blood-gas windows align with a named reference
- keep tolerance bands broad enough to reflect model idealization

Priority:

- `P2`

### `tests/test_lung.py`

Current status:

- strong math tests
- baseline range claims can be better anchored

Next upgrades:

- tie healthy baseline gas windows to named references
- avoid over-claiming species-specific truth where the model clearly diverges

Priority:

- `P1`

### `tests/test_kidney.py`

Current status:

- strong internal math
- not yet clearly anchored to external canine reference ranges

Next upgrades:

- healthy baseline GFR window from healthy-dog reference data
- disease progression checkpoints from AKI consensus / review literature

Priority:

- `P1`

### `tests/test_diseases.py`

Current status:

- mixed
- several sign-only assertions

Immediate upgrades:

- exact formula checks where the comment already states a formula
- later add sparse trajectory checkpoints at clinically meaningful times

Priority:

- `P0`

### `tests/test_species_specific.py`

Current status:

- one especially weak disease assertion

Immediate upgrade:

- replace `heart_rate > 0` with deterioration in oxygenation versus matched healthy controls

Priority:

- `P0`

### `tests/test_untreated_deterioration.py`

Current status:

- expensive but low-yield

Immediate upgrade:

- add disease-specific deterioration markers

Later upgrade:

- rebuild around sparse natural-history checkpoints and endpoint windows

Priority:

- `P0`

### `tests/test_cross_module_coupling.py`

Current status:

- directionality-only

Next upgrades:

- better AKI / hyperkalemia / acidosis coupling windows
- fluid-resuscitation response tests

Priority:

- `P1`

### `tests/test_lifecycle_literature.py`

Current status:

- mixed literature integrity and engine validation

Recommended refactor:

- split into:
  - reference-data integrity
  - engine-against-reference validation

Priority:

- `P1`

## What Was Safe To Implement Immediately

The first implementation batch should prefer tests where:

- the code comment already states the intended formula
- the current assertion is obviously too weak
- the stronger assertion does not require guessing at a disputed literature number

That yields three safe wins:

1. exact disease command-value checks in `tests/test_diseases.py`
2. cross-species pneumonia effect checks in `tests/test_species_specific.py`
3. disease-specific deterioration checks in `tests/test_untreated_deterioration.py`

## What Should Wait For A Deeper Literature Pass

These need a more deliberate evidence-collection pass before tightening:

- exact feline and equine baseline respiratory / blood-gas windows
- lifecycle aging magnitudes and decline curves
- DCM long-horizon natural history
- intervention-response timing windows

## Recommended Next Pass

After the first implementation batch, the next best literature-backed work is:

1. add healthy canine baseline GFR reference-window checks using PMID `18289291`
2. create sparse AKI checkpoints for `GFR`, `BUN`, `K`, and `pH`
3. add sparse pneumonia checkpoints for `PaO2` / `SpO2`
4. split lifecycle evidence into reference-integrity and behavior-validation suites

## Current Sampled Literature Mismatches

These are not yet formal failing tests, but they are important.

They come from direct local sampling on `2026-06-10` and should guide where we
do not tighten blindly.

### Equine baseline respiratory gas mismatch

Current sampled model state after short stabilization:

- equine `PaCO2` about `29-30 mmHg`
- equine `pH` about `7.53-7.56`

Relevant reference anchor already present in repo literature notes:

- Sherlock 2019 equine arterial `PaCO2` around `42 mmHg`

Interpretation:

- the current equine baseline appears materially hypocapnic relative to the
  cited literature anchor
- this should be treated as a model discrepancy to investigate, not a place to
  silently widen tests until they pass

### Species-specific baseline tests need selective tightening

The quick sampling showed:

- canine baseline is close to the current intended blood-gas setpoint
- feline baseline is plausible enough for broad checks but still needs a proper
  source-backed pass
- equine baseline is the clearest current mismatch

So the correct next move is:

- tighten canine kidney and canine respiratory anchors first
- document equine mismatch explicitly
- avoid adding fake “literature-backed” equine window tests until the model or
  the evidence mapping is clarified

## Important Limitation

External literature should constrain the kernel, not dictate exact equality.

This engine is still a simplified model.

So literature-backed tests should usually assert:

- direction
- ordering
- broad physiological windows
- sparse checkpoint bands

They should usually not assert:

- exact equality to cohort means
- exact minute-by-minute reproduction of clinical patients
