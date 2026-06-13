# Literature Hierarchy

> Provenance for every physiological model decision in VirtualVet.
> Last reviewed: 2026-06-13

## Purpose

This file is the **single source of truth** for which literature justifies which
part of the engine. It has three tiers:

| Tier | Count | Role |
|------|-------|------|
| **CORE** | ≤5 | Underpin all engine design decisions |
| **SUBSIDIARY** | 1–3 per organ subsystem | Anchor specific parameter ranges or coupling coefficients |
| **PER-DISEASE** | 1–3 per disease | Justify disease ODE parameters and severity presets |

**Rule**: A paper must appear in this file before it can be added to
`parameter_references.json` or `test-evidence-registry.md`.

---

## TIER 1 — CORE PAPERS

≤5 canonical references. Every engine module traces back to at least one.
No more than 5 — if a new paper does not fit under an existing CORE, raise a
design decision before adding it.

### C1 — Baroreflex and Cardiovascular Coupling

| Field | Value |
|-------|-------|
| **Full citation** | Ursino M. *Mechanisms of blood pressure regulation.* Med Biol Eng Comput. 1998;36(5):556-567. |
| **PMID** | 10397889 |
| **Type** | Quantitative physiology model |
| **Justifies** | `heart.heart_rate` baroreflex gain, `heart.SVR` baroreflex-mediated changes, `neuro` HR → SVR coupling latency |
| **Code modules** | `src/heart.py`, `src/neuro.py`, `src/endocrine.py` (renin) |
| **Key equations** | `HR_para = -40 × para × max(0, -error)`, `HR_symp = +15 × sym × max(0, error)` (Ursino 1998 Eq. 3–4) |

### C2 — Cardiac Output and Tissue Perfusion

| Field | Value |
|-------|-------|
| **Full citation** | Guyton AC, Hall JE. *Textbook of Medical Physiology.* 14th ed. Elsevier; 2020. Ch. 14, 19, 22, 26. |
| **Type** | Textbook (anchor) |
| **Justifies** | `heart.cardiac_output` baseline (CO = SV × HR), `heart.SVR` relationship MAP = CO × SVR, `heart.preload_volume` Starling mechanism, `fluid.V_vascular_mL` 3-compartment distribution |
| **Code modules** | `src/heart.py`, `src/fluid.py`, `src/engine/topology.py` CONNECTIONS |

### C3 — Respiratory Gas Exchange and V/Q Mismatch

| Field | Value |
|-------|-------|
| **Full citation** | West JB. *Respiratory Physiology: The Essentials.* 9th ed. Lippincott Williams & Wilkins; 2012. |
| **Type** | Textbook |
| **Justifies** | `lung.alveolar_PO2` alveolar gas equation, `lung.arterial_PO2` A-a gradient model, `lung.V_Q_ratio` V/Q mismatch effects on PaO2/PaCO2 |
| **Code modules** | `src/lung.py` |
| **Key equation** | `PAO2 = FiO2 × (Patm - PH2O) - PACO2/R` (West 2012 Eq. 5–7) |

### C4 — Acid-Base Chemistry

| Field | Value |
|-------|-------|
| **Full citation** | Henderson LJ. *The theory of neutrality regulation in the animal organism.* Am J Physiol. 1908;21:427-432. + Hasselbalch KA. *Die Berechnung der Wasserstoffzahl des Blutes.* Biochem Z. 1916;78:112-144. |
| **Type** | Foundational chemistry (no single PMID — historical papers) |
| **Justifies** | `blood.arterial_pH` Henderson-Hasselbalch equation, `blood.HCO3_mEq_L` bicarbonate buffer system, `blood.PCO2_mmHg` respiratory acid-base role |
| **Code modules** | `src/blood.py`, `src/fluid.py` (pH buffering) |
| **Key equation** | `pH = 6.1 + log10(HCO3 / (0.03 × PCO2))` (Henderson-Hasselbalch) |

### C5 — Veterinary Kidney Physiology

| Field | Value |
|-------|-------|
| **Full citation** | Hall JE, Guyton AC. *Textbook of Medical Physiology.* 14th ed. Elsevier; 2020. Ch. 26, 27, 30. + Nelson RW, Couto CG. *Small Animal Internal Medicine.* 5th ed. Mosby; 2013. Ch. 22. |
| **Type** | Textbook |
| **Justifies** | `kidney.GFR` baseline, `kidney.ADH_level` concentration mechanism, `kidney.renin_level` RAAS cascade, `kidney.urine_output_mL_min` Starling filtration |
| **Code modules** | `src/kidney.py` |
| **Key equation** | `GFR = Kf × (PGC - PBS - πGC + πBS)` with `PGC = 0.6 × MAP` (Hall 2016 Ch. 26) |

---

## TIER 2 — SUBSIDIARY PAPERS

Organ-subsystem references. Format: **S-{system}-{number}**.

### Cardiovascular

| ID | Citation | PMID | Justifies | Code |
|----|----------|------|-----------|------|
| S-CV-1 | Nelson & Couto, *Small Animal Internal Medicine* 5e, Ch.22 | — | Canine clinical HR range 60–140 bpm, MAP normal 80–120 mmHg | `heart.heart_rate`, `heart.MAP` |
| S-CV-2 | Chien S. *Vasoregulation in acute hemorrhage.* Am J Physiol. 1968 | 5639281 | SVR compensation in hypovolemia (4–5× baseline) | `heart.SVR` hypovolemia coupling |
| S-CV-3 | Fuentes VL et al. ACVIM DCM Consensus. *JVIM.* 2020 | 32314222 | DCM EF/FS thresholds for game diagnosis | `tests/test_diseases.py` |

### Respiratory

| ID | Citation | PMID | Justifies | Code |
|----|----------|------|-----------|------|
| S-RESP-1 | Lappin MR et al. ISCAID Antimicrobial Guidelines. *JVIM.* 2017 | 28185306 | Pneumonia clinical framing, antibiotic triggers | `tests/test_diseases.py` |
| S-RESP-2 | McCaffree DR et al. *A-a gradient in disease.* Am Rev Respir Dis. 1978 | 637876 | A-a gradient quantitative model | `lung.arterial_PO2` |
| S-RESP-3 | Dear JD. Bacterial Pneumonia in Dogs and Cats. *JVIM.* 2020 | PMC7114575 | PaO2 <80 mmHg, BAL >500 cells/μL | `tests/test_diseases.py` |

### Renal

| ID | Citation | PMID | Justifies | Code |
|----|----------|------|-----------|------|
| S-REN-1 | Segev G et al. IRIS AKI Consensus. *Vet J.* 2024 | 38325516 | AKI staging, creatinine thresholds, hyperkalemia ECG | `kidney.GFR`, `tests/test_diseases.py` |
| S-REN-2 | Bexfield et al. Healthy dog GFR reference intervals. *JSAP.* 2008 | 18289291 | Weight-normalized GFR healthy window | `kidney.GFR` baseline |
| S-REN-3 | Iimori Y et al. Hyperkalemia ECG progression. *Can Vet J.* 2026 | 41929733 | K+ 5.5/6.5/8.0 mEq/L ECG thresholds | `src/blood.py` (K+ effects on cardiac conduction) |

### Fluid / Hemodynamics

| ID | Citation | PMID | Justifies | Code |
|----|----------|------|-----------|------|
| S-FLUID-1 | AAHA 2024 Fluid Therapy Guidelines. *JAAHA.* 2024 | — | Crystalloid bolus volumes, maintenance rates | `tests/test_diseases.py` (future fluid-bolus tests) |
| S-FLUID-2 | Mooney E et al. Lactate in GDV. *Top Comp Anim Med.* 2014 | — | Lactate as outcome predictor for hemorrhage/shock | `src/blood.py` lactate production |

### Endocrine / Immune

| ID | Citation | PMID | Justifies | Code |
|----|----------|------|-----------|------|
| S-ENDO-1 | Hall JE. *Textbook of Medical Physiology* 14e, Ch.76–78 | — | Cortisol, insulin, glucagon baseline ranges | `src/endocrine.py` |
| S-ENDO-2 | Taylor FB et al. ISTH DIC Scoring. *Thromb Haemost.* 2001 | 11816725 | DIC scoring system, PT/aPTT/PLT thresholds | `src/blood.py` (coagulation cascade) |

---

## TIER 3 — PER-DISEASE PAPERS

Disease-specific references. Format: **D-{disease-abbrev}-{number}**.
Each disease in `data/ode_diseases.json` should have a `literature_refs` array
pointing here.

### D-PNA-1, D-PNA-2 — Pneumonia
- **D-PNA-1**: Dear JD. 2020 (PMC7114575) — PaO2 <80, BAL >500 cells/μL
- **D-PNA-2**: Whittle KL et al. Aspiration Pneumonia. *JVIM.* 2022 (PMC8692172) — neutrophil criteria

### D-ARF-1, D-ARF-2 — Acute Renal Failure
- **D-ARF-1**: Segev G et al. IRIS 2024 (PMID 38325516) — AKI staging
- **D-ARF-2**: Segev G et al. AKI Outcomes 249 dogs. *JVIM.* 2022 (PMC8965273) — clinical outcomes

### D-DCM-1, D-DCM-2 — Dilated Cardiomyopathy
- **D-DCM-1**: Fuentes VL et al. ACVIM DCM Consensus 2020 (PMID 32314222) — echo criteria
- **D-DCM-2**: Haggstrom J et al. QUEST Study. *JVIM.* 2008 — pimobendan dose

### D-SEP-1, D-SEP-2 — Sepsis
- **D-SEP-1**: Chien S. 1968 (PMID 5639281) — SVR compensation in sepsis
- **D-SEP-2**: ISCAID 2017 (PMID 28185306) — cytokine storm clinical picture

### D-HEM-1, D-HEM-2 — Hemorrhage
- **D-HEM-1**: Chien S. 1968 (PMID 5639281) — hemorrhage compensation
- **D-HEM-2**: Guyton 14e Ch.26 — blood volume distribution

*(Add remaining diseases using the same pattern.)*

---

## Citation Key

All literature IDs in `parameter_references.json`, `ode_diseases.json`, and
`test-evidence-registry.md` must use the ID format defined above:

| Format | Example | Used in |
|--------|---------|---------|
| `C{n}` | `C1`, `C2` | `parameter_references.json` (core papers) |
| `S-{system}-{n}` | `S-CV-2`, `S-REN-1` | `parameter_references.json` (subsidiary) |
| `D-{disease}-{n}` | `D-PNA-1`, `D-ARF-2` | `ode_diseases.json` `literature_refs` |
| `PMID:{nnnnnnn}` | `PMID:38325516` | `test-evidence-registry.md` (raw lookup) |
| `textbook:{name}` | `textbook:guyton` | `parameter_references.json` (textbooks) |

---

## Maintenance Rules

1. **Before adding any citation to code or data files**, it must first appear in
   this file with a tier and ID.
2. `report_unverified()` from `src/parameter_refs.py` should be run quarterly to
   flag `_PARAM_PATHS` entries without literature refs.
3. When a CORE paper is superseded (e.g., a better model paper emerges), do not
   delete the old ID — mark it `superseded` and note which paper replaces it.
4. PER-DISEASE papers are added when a disease's ODE parameters are calibrated
   to clinical data for the first time.
5. **No new citations in `disease_references.md`** — it must reference hierarchy IDs only.

---

## Anti-Scatter Rule

> **No new citations anywhere in the repo** unless they first appear in this file
> with a tier ID. Exceptions require a design decision note.