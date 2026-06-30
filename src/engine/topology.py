"""
Engine topology — parameter registry.

This module centralises the engine's "shape" data:

1. **_PARAM_PATHS** — the whitelisted parameter paths that
   `apply_factor(FactorCommand)` is allowed to write to. This is a
   **write-protocol**, not a data-flow table. Format:
   `"module.attr" -> (engine_module_name, attribute_name)`.

2. **Topology / discover_topology** — Phase 5 placeholders. When modules
   declare `INPUTS` / `OUTPUTS` class attributes, `discover_topology`
   will auto-derive the coupling graph from those declarations
   (eliminating the central-table drift problem flagged in the audit).

Phase 1: this module is a pure code-motion extraction from
`src/simulation.py` and `src/common_types.py`. Zero behavior change.
"""

from dataclasses import dataclass, field


# ── _PARAM_PATHS: whitelisted write-protocol for apply_factor() ────────────
# All paths that `apply_factor(FactorCommand)` is allowed to write to must be
# registered here. This is a SAFETY boundary (whitelist), not a data-flow table.
# Format: "module.attr" -> (engine_module_name, attribute_name)
#
# Moved from src/common_types.py:41-151 (Phase 1).

_PARAM_PATHS: dict[str, tuple[str, str]] = {
    # ── Heart ──────────────────────────────────────────────────────────────
    "heart.heart_rate":              ("heart", "heart_rate"),
    "heart.contractility_factor":    ("heart", "contractility_factor"),
    "heart.preload_factor":          ("heart", "preload_factor"),
    "heart.SVR":                     ("heart", "SVR"),
    "heart.cortisol_factor":         ("heart", "cortisol_factor"),
    "heart.MAP":                     ("heart", "mean_arterial_pressure"),
    "heart.CVP":                     ("heart", "central_venous_pressure"),
    "heart.blood_volume":            ("heart", "circulating_volume_ml"),
    "heart.stroke_volume":           ("heart", "stroke_volume"),
    "heart.cardiac_output":          ("heart", "cardiac_output"),  # organ_health factor
    # ── Lung ──────────────────────────────────────────────────────────────
    "lung.diffusion_coefficient":    ("lung", "diffusion_coefficient"),
    "lung.PaO2":                     ("lung", "alveolar_PO2"),
    "lung.PaCO2":                    ("lung", "alveolar_PCO2"),
    "lung.VQ_ratio":                 ("lung", "VQ_ratio"),
    "lung.respiratory_rate":         ("lung", "respiratory_rate"),
    # ── Kidney ────────────────────────────────────────────────────────────
    "kidney.GFR":                        ("kidney", "GFR"),
    "kidney.urine_output":               ("kidney", "urine_output"),
    "kidney.renal_blood_flow":           ("kidney", "renal_blood_flow"),
    "kidney._disease_gfr_multiplier":    ("kidney", "_disease_gfr_multiplier"),
    # ── Blood ─────────────────────────────────────────────────────────────
    "blood.sodium_mEq_L":          ("blood", "sodium_mEq_L"),
    "blood.potassium":             ("blood", "potassium_mEq_L"),
    "blood.pH":                    ("blood", "arterial_pH"),
    "blood.temperature":           ("blood", "core_temperature_C"),
    "blood.BUN":                   ("blood", "bun_mg_dL"),
    "blood.HCO3":                  ("fluid", "vascular_hco3_meq_l"),
    "blood.glucose":               ("blood", "glucose_mmol_L"),
    "blood.lactate":               ("blood", "lactate_mmol_L"),
    "blood.creatinine":            ("blood", "creatinine_mg_dL"),
    "blood.red_cell_volume_ml":    ("blood", "red_cell_volume_ml"),
    "blood.bilirubin_mg_dL":       ("blood", "bilirubin_mg_dL"),
    "blood.ketone_mmol_L":         ("blood", "ketone_mmol_L"),
    "blood.PLT":                   ("blood", "PLT"),
    # Blood — liver/gut markers
    "blood.ALT":                   ("blood", "ALT_U_L"),
    "blood.AST":                   ("blood", "AST_U_L"),
    "blood.ALP":                   ("blood", "ALP_U_L"),
    "blood.GGT":                   ("blood", "GGT_U_L"),
    "blood.albumin":               ("blood", "albumin_g_dL"),
    "blood.ammonia":               ("blood", "ammonia_umol_L"),
    "blood.bile_acids":            ("blood", "bile_acids_umol_L"),
    "blood.amino_acids":           ("blood", "amino_acids_g_L"),
    "blood.fatty_acids":           ("blood", "fatty_acids_mmol_L"),
    # Blood — coupling engine targets
    "blood.arterial_PO2_mmHg":     ("blood", "arterial_PO2_mmHg"),
    "blood.arterial_PCO2_mmHg":    ("blood", "arterial_PCO2_mmHg"),
    # Blood — coagulation aliases (coag.* 和 blood.* 指向同一属性)
    "blood.PT_sec":                ("blood", "PT_sec"),
    "blood.aPTT_sec":              ("blood", "aPTT_sec"),
    "blood.fibrinogen_mg_dL":      ("blood", "fibrinogen_mg_dL"),
    "blood.INR":                   ("blood", "INR"),
    "blood.coagulation_factor_VII": ("blood", "coagulation_factor_VII"),
    # P0 0d: factor-paths for fields previously written direct in step
    "blood.saturation":            ("blood", "arterial_saturation"),
    "blood.CRP":                   ("blood", "CRP_mg_L"),
    "blood.drug_concentration_mg_kg": ("blood", "drug_concentration_mg_kg"),
    # Blood — lymphatic aliases
    "blood.splenic_reserve_mL":    ("blood", "splenic_reserve_mL"),
    "blood.interstitial_fluid_mL": ("blood", "interstitial_fluid_mL"),
    "blood.lymph_flow_mL_min":     ("blood", "lymph_flow_mL_min"),
    # ── Gut ────────────────────────────────────────────────────────────────
    "gut.motility":                ("gut", "gut_motility"),
    "gut.gut_motility":            ("gut", "gut_motility"),
    "gut.barrier_integrity":       ("gut", "barrier_integrity"),
    "gut.microbiome_activity":     ("gut", "microbiome_activity"),
    # ── Liver ─────────────────────────────────────────────────────────────
    "liver.metabolic_activity":    ("liver", "metabolic_activity"),
    "liver.detox_capacity":        ("liver", "detox_capacity"),
    "liver.cyp450_activity":       ("liver", "cyp450_activity"),
    "liver.glycogen_fraction":     ("liver", "glycogen_fraction"),
    "liver.bilirubin_conjugation": ("liver", "bilirubin_conjugation"),
    # ── Endocrine ──────────────────────────────────────────────────────────
    "endocrine.T3_factor":         ("endocrine", "T3_factor"),
    "endocrine.T4_factor":         ("endocrine", "T4_ug_dL"),
    "endocrine.metabolic_rate":    ("endocrine", "metabolic_rate"),
    "endocrine.T3_ng_dL":          ("endocrine", "T3_ng_dL"),
    "endocrine.T4_ug_dL":          ("endocrine", "T4_ug_dL"),
    "endocrine.insulin_factor":    ("endocrine", "insulin_factor"),
    "endocrine.glucagon_factor":   ("endocrine", "glucagon_factor"),
    "endocrine.insulin_uU_mL":     ("endocrine", "insulin_uU_mL"),
    "endocrine.glucagon_pg_mL":   ("endocrine", "glucagon_pg_mL"),
    "endocrine.cortisol_factor":   ("endocrine", "cortisol_factor"),
    "endocrine.cortisol_ug_dL":    ("endocrine", "cortisol_ug_dL"),
    "endocrine.HPA_axis":          ("endocrine", "HPA_axis"),
    "endocrine.epinephrine_pg_mL": ("endocrine", "epinephrine_pg_mL"),
    "endocrine.norepinephrine_pg_mL": ("endocrine", "norepinephrine_pg_mL"),
    "endocrine.PTH_pg_mL":         ("endocrine", "PTH_pg_mL"),
    "endocrine.calcium_mg_dL":      ("endocrine", "calcium_mg_dL"),
    "endocrine.phosphate_mg_dL":   ("endocrine", "phosphate_mg_dL"),
    "endocrine.calcium_factor":    ("endocrine", "calcium_factor"),
    "endocrine.GH_ng_mL":          ("endocrine", "GH_ng_mL"),
    "endocrine.IGF1_nmol_L":       ("endocrine", "IGF1_nmol_L"),
    "endocrine.growth_factor":     ("endocrine", "growth_factor"),
    # ── Neuro ──────────────────────────────────────────────────────────────
    "neuro.sympathetic_tone":     ("neuro", "sympathetic_tone"),
    "neuro.parasympathetic_tone":  ("neuro", "parasympathetic_tone"),
    "neuro.consciousness":         ("neuro", "consciousness"),
    "neuro.seizure":               ("neuro", "seizure"),
    "neuro.pain_level":            ("neuro", "pain_level"),
    "neuro.chemoreceptor_drive":   ("neuro", "chemoreceptor_drive"),
    # ── Immune ─────────────────────────────────────────────────────────────
    "immune.cytokine_level":       ("immune", "cytokine_level"),
    "immune.wbc_count":            ("immune", "wbc_count"),
    "immune.crp_level":            ("immune", "crp_level"),
    "immune.acute_phase_response": ("immune", "acute_phase_response"),
    "immune.immune_suppression":   ("immune", "immune_suppression"),
    "immune.coagulation_state":    ("immune", "coagulation_state"),
    "immune.antibiotic_effect":    ("immune", "antibiotic_effect"),
    "immune._infection_signal":     ("immune", "_infection_signal"),
    # ── Coagulation ────────────────────────────────────────────────────────
    "coag.PT_sec":                 ("blood", "PT_sec"),
    "coag.aPTT_sec":               ("blood", "aPTT_sec"),
    "coag.fibrinogen_mg_dL":       ("blood", "fibrinogen_mg_dL"),
    "coag.factor_VII":             ("coagulation", "factor_VII"),
    "coag.coagulation_state":      ("coagulation", "coagulation_state"),
    # ── Lymphatic ──────────────────────────────────────────────────────────
    "lymph.splenic_reserve_mL":    ("blood", "splenic_reserve_mL"),
    "lymph.lymph_flow":            ("lymphatic", "lymph_flow_rate"),
    "lymph.interstitial_fluid":    ("blood", "interstitial_fluid_mL"),
}


# ── Phase 5 placeholders ───────────────────────────────────────────────────
# These will become real in Phase 5 (per-module INPUTS/OUTPUTS migration).
# For now they are pure placeholders so the public API is fixed.

@dataclass(frozen=True)
class Topology:
    """The engine's module coupling graph (Phase 5+).

    Phase 1: placeholder dataclass so the import surface is stable.
    Phase 5: populated by `discover_topology(modules)` from each module's
    `INPUTS`/`OUTPUTS` declarations.
    """
    adjacency: dict[str, list[str]] = field(default_factory=dict)
    inputs_of: dict[str, tuple[str, ...]] = field(default_factory=dict)
    outputs_of: dict[str, tuple[str, ...]] = field(default_factory=dict)
    blood_writers_of: dict[str, tuple[str, ...]] = field(default_factory=dict)


def discover_topology(modules: list) -> Topology:
    """Auto-discover module coupling graph (Phase 5 placeholder).

    Phase 1: returns an empty Topology (no introspection yet — modules
    still don't declare INPUTS/OUTPUTS class attributes).
    Phase 5: will introspect `module.INPUTS` and `module.OUTPUTS` class
    attributes and build the adjacency. At that point, the coupling graph
    becomes derived from this Topology rather than hand-maintained.
    """
    return Topology()
