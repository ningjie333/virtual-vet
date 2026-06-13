# Disease Diagnostic References — Quick Ref

> Quick reference index of per-disease literature.
> **Single source of truth**: [data/disease_references.json](../data/disease_references.json) (structured data).
> **Citation key**: [docs/literature-hierarchy.md](literature-hierarchy.md) (CORE / SUBSIDIARY / PER-DISEASE tiers).
> **Last synced**: 2026-06-13 (consolidated from prior 395-line version).

## How to use

1. **Find a paper's full citation**: look up the ID in [literature-hierarchy.md](literature-hierarchy.md).
2. **Find a disease's diagnostic criteria + thresholds**: query `data/disease_references.json` (the .md never re-states them).
3. **Add a new paper**: register it in `literature-hierarchy.md` first, then reference it from `disease_references.json` by ID.

**Anti-Scatter Rule**: This file MUST NOT add new citations not present in
`literature-hierarchy.md`. Only quick-ref pointers are allowed.

---

## Disease → Citation Index

| # | Disease | Per-Disease IDs (see literature-hierarchy.md) | Structured data |
|---|---------|-----------------------------------------------|-----------------|
| 1 | Pneumonia (肺炎) | D-PNA-1, D-PNA-2 | `disease_references.json::pneumonia` |
| 2 | Acute Renal Failure (急性肾衰竭) | D-ARF-1, D-ARF-2 | `disease_references.json::acute_renal_failure` |
| 3 | Dilated Cardiomyopathy (扩张型心肌病) | D-DCM-1, D-DCM-2 | `disease_references.json::dilated_cardiomyopathy` |
| 4 | Phosphorus Poisoning (磷化锌中毒) | D-PHOS-1 (TBD) | `disease_references.json::phosphorus_poisoning` |
| 5 | Gastric Dilatation-Volvulus (GDV) | D-GDV-1 (TBD) | `disease_references.json::gdv` |
| 6 | Immune-Mediated Hemolytic Anemia | D-IMHA-1 (TBD) | `disease_references.json::imha` |
| 7 | Urinary Obstruction (尿道梗阻) | D-UR-1 (TBD) | `disease_references.json::urinary_obstruction` |
| 8 | Diabetic Ketoacidosis (DKA) | D-DKA-1 (TBD) | `disease_references.json::dka` |
| 9 | Pericardial Effusion (心包积液) | D-PE-1 (TBD) | `disease_references.json::pericardial_effusion` |
| 10 | Disseminated Intravascular Coagulation (DIC) | S-ENDO-2, D-DIC-1 (TBD) | `disease_references.json::dic` |
| 11 | Hepatic Failure Coagulopathy | S-ENDO-2, D-HF-1 (TBD) | `disease_references.json::hepatic_failure` |
| 12 | Splenic Rupture (脾脏破裂) | D-SR-1 (TBD) | `disease_references.json::splenic_rupture` |

**TODO**: Convert all `(TBD)` IDs to actual registered entries in
`literature-hierarchy.md` TIER 3 PER-DISEASE section. Until converted,
those citations live in `disease_references.json` but cannot be tracked
through the hierarchy.

---

## Common diagnostic thresholds (cross-disease)

For quick lookup. Full details in `disease_references.json`.

| Threshold | Value | Used by | Source |
|-----------|-------|---------|--------|
| PaO2 < 80 mmHg | hypoxemia | Pneumonia | Dear 2020 |
| PaCO2 > 50 mmHg | respiratory failure | Pneumonia | Dear 2020 |
| WBC elevated (66%) | inflammation | Pneumonia | Dear 2020 |
| BAL cells > 500/μL | alveolar inflammation | Pneumonia | Dear 2020 |
| AKI staging (creatinine 1.4/2.8/5.0) | renal severity | ARF | IRIS 2024 |
| Hyperkalemia ECG (5.5/6.5/8.0) | cardiac risk | ARF | Iimori 2026 |
| EF/FS < 40%/25% | DCM diagnosis | DCM | ACVIM 2020 |
| Lactate > 6 mmol/L | GDV outcome | GDV | Mooney 2014 |

---

## Removed from this file (now in disease_references.json)

The 13 KB of per-disease narrative previously here has been consolidated
into `data/disease_references.json`. That file is the canonical source for:

- Citation metadata (authors, year, title, journal, DOI/PMID, type)
- Diagnostic criteria (threshold, source, mechanism)
- Treatment protocols (drug, dose, route, frequency)
- Population studies (sample size, outcome)

To query: `jq '.pneumonia' data/disease_references.json`

---

*Created: 2026-05-28*
*Pruned: 2026-06-13 — quick-ref only; details migrated to disease_references.json*
