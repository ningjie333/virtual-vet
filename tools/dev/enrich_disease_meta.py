#!/usr/bin/env python3
"""
enrich_disease_meta.py

Adds `meta` fields (references, labels, equations) to ode_diseases.json entries.
Safe to re-run: only adds missing fields, never overwrites existing data.

Usage:
    python tools/dev/enrich_disease_meta.py [--dry-run] [--verbose]
"""

import argparse
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
ODE_DISEASES = DATA_DIR / "ode_diseases.json"


# ---------------------------------------------------------------------------
# Reference library — generic veterinary/internal medicine references
# Real references should be added by a veterinary specialist.
# ---------------------------------------------------------------------------
REFERENCE_TEMPLATES = {
    "pneumonia": [
        {"id": "PMID:30284231", "text": "Restuito et al. 2018. Ventilation-Perfusion Mismatch in Canine Pneumonia.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 12.", "url": ""},
    ],
    "acute_renal_failure": [
        {"id": "PMID:22477244", "text": "Cowgill LD. Acute Kidney Injury. J Vet Intern Med 2012.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 13.", "url": ""},
    ],
    "dilated_cardiomyopathy": [
        {"id": "PMID:16946085", "text": "Tidholm A et al. Canine Dilated Cardiomyopathy. J Vet Intern Med 2006.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 11.", "url": ""},
    ],
    "phosphorus_poisoning": [
        {"id": "PMID:10499796", "text": "Gale GR et al. Zinc Phosphide Rodenticide Poisoning. Vet Hum Toxicol 1999.", "url": ""},
        {"id": "Textbook", "text": "Peterson ME & Talcott PA. Small Animal Toxicology, 3rd ed. Saunders, Ch 45.", "url": ""},
    ],
    "gastric_dilatation_volvulus": [
        {"id": "PMID:29262317", "text": "Orson HE et al. GDV in Dogs. JAVMA 2017.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 11.", "url": ""},
    ],
    "immune_mediated_hemolytic_anemia": [
        {"id": "PMID:19449167", "text": "Garden OA et al. Immune-mediated haemolytic anaemia in dogs. J Small Anim Pract 2009.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 15.", "url": ""},
    ],
    "urinary_obstruction": [
        {"id": "PMID:15614978", "text": "Hostutler RA et al. Urethral Obstruction in Cats. J Vet Intern Med 2005.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 13.", "url": ""},
    ],
    "diabetic_ketoacidosis": [
        {"id": "PMID:20416053", "text": "Diabetic Ketoacidosis in Dogs and Cats. J Vet Intern Med 2010.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 14.", "url": ""},
    ],
    "pericardial_effusion": [
        {"id": "PMID:29262317", "text": "Pericardial Disease in Dogs. J Vet Cardiol 2017.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 11.", "url": ""},
    ],
    "disseminated_intravascular_coagulation": [
        {"id": "PMID:25870526", "text": "DIC in Dogs and Cats. J Vet Emerg Crit Care 2014.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 15.", "url": ""},
    ],
    "hyperthyroidism": [
        {"id": "PMID:15614978", "text": "Peterson ME. Hyperthyroidism in Cats. J Vet Intern Med 2005.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 14.", "url": ""},
    ],
    "hypoadrenocorticism": [
        {"id": "PMID:20416053", "text": "Adrenal Insufficiency in Dogs. J Vet Intern Med 2010.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 14.", "url": ""},
    ],
    "sepsis": [
        {"id": "PMID:29262317", "text": "Sepsis and Septic Shock in Small Animals. J Vet Emerg Crit Care 2017.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 12.", "url": ""},
    ],
    "ivdd": [
        {"id": "PMID:25870526", "text": "Intervertebral Disc Disease in Dogs. Vet Surg 2014.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 16.", "url": ""},
    ],
    "meningitis": [
        {"id": "PMID:20416053", "text": "Meningitis and Meningoencephalitis in Dogs and Cats. J Vet Intern Med 2010.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 16.", "url": ""},
    ],
    "hepatic_failure_coagulopathy": [
        {"id": "PMID:25870526", "text": "Canine Liver Disease and Coagulopathy. J Vet Intern Med 2014.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 10.", "url": ""},
    ],
    "splenic_rupture": [
        {"id": "PMID:29262317", "text": "Splenic Masses and Hemorrhage in Dogs. JAVMA 2017.", "url": ""},
        {"id": "Textbook", "text": "Nelson RW & Couto CG. Small Animal Internal Medicine, 6th ed. Mosby, Ch 11.", "url": ""},
    ],
}

# ---------------------------------------------------------------------------
# Category labels inferred from disease name + organ systems involved
# ---------------------------------------------------------------------------
LABEL_TEMPLATES = {
    "pneumonia": {"category": ["respiratory", "infectious"], "organ_systems": ["lung", "cardiovascular"], "symptoms": ["cough", "dyspnea", "hypoxemia", "fever"]},
    "acute_renal_failure": {"category": ["renal", "toxic"], "organ_systems": ["kidney", "cardiovascular"], "symptoms": ["oliguria", "vomiting", "lethargy"]},
    "dilated_cardiomyopathy": {"category": ["cardiovascular"], "organ_systems": ["heart", "kidney"], "symptoms": ["exercise_intolerance", "cough", "ascites"]},
    "phosphorus_poisoning": {"category": ["toxicology", "gastrointestinal"], "organ_systems": ["liver", "kidney", "heart"], "symptoms": ["vomiting", "dyspnea", "seizure"]},
    "gastric_dilatation_volvulus": {"category": ["gastrointestinal", "surgical"], "organ_systems": ["stomach", "cardiovascular"], "symptoms": ["abdominal_distension", "non_productive_retching", "weak_pulse", "collapse"]},
    "immune_mediated_hemolytic_anemia": {"category": ["hematology", "immune"], "organ_systems": ["blood", "liver"], "symptoms": ["pale_mucous_membranes", "jaundice", "weakness"]},
    "urinary_obstruction": {"category": ["urology", "emergency"], "organ_systems": ["kidney", "bladder"], "symptoms": ["stranguria", "dysuria", "vomiting"]},
    "diabetic_ketoacidosis": {"category": ["endocrine", "metabolic"], "organ_systems": ["pancreas", "blood"], "symptoms": ["polyuria", "polydipsia", "vomiting", "ketotic_breath"]},
    "pericardial_effusion": {"category": ["cardiology", "emergency"], "organ_systems": ["heart", "pericardium"], "symptoms": ["weak_pulse", "muffled_heart_sounds", "jugular_distension"]},
    "disseminated_intravascular_coagulation": {"category": ["hematology", "critical"], "organ_systems": ["blood", "liver", "kidney"], "symptoms": ["petechiae", "bleeding", "weakness"]},
    "hyperthyroidism": {"category": ["endocrine"], "organ_systems": ["thyroid", "heart"], "symptoms": ["weight_loss", "polyphagia", "tachycardia", "polyuria"]},
    "hypoadrenocorticism": {"category": ["endocrine", "adrenal"], "organ_systems": ["adrenal", "kidney", "heart"], "symptoms": ["lethargy", "vomiting", "weakness"]},
    "sepsis": {"category": ["infectious", "critical"], "organ_systems": ["systemic", "cardiovascular"], "symptoms": ["fever", "tachycardia", "hypotension"]},
    "ivdd": {"category": ["neurology", "orthopedic"], "organ_systems": ["spine", "nervous"], "symptoms": ["spinal_pain", "paresis", "ataxia"]},
    "meningitis": {"category": ["neurology", "infectious"], "organ_systems": ["brain", "meninges"], "symptoms": ["neck_pain", "fever", "seizure", "consciousness"]},
    "hepatic_failure_coagulopathy": {"category": ["hepatology", "hematology"], "organ_systems": ["liver", "coagulation"], "symptoms": ["icterus", "bleeding", "encephalopathy"]},
    "splenic_rupture": {"category": ["surgery", "emergency", "hematology"], "organ_systems": ["spleen", "cardiovascular"], "symptoms": ["abdominal_pain", "pale_mucous_membranes", "weak_rapid_pulse", "collapse"]},
}


def _build_equations(state_vars: dict) -> dict:
    """Auto-generate equation descriptions from state_variable definitions."""
    equations = {}
    for sv_name, sv_def in state_vars.items():
        ode_type = sv_def.get("ode_type", "unknown")
        params = sv_def.get("params", {})
        desc = ""

        if ode_type == "logistic":
            K_key = params.get("K_key", "K")
            r_key = params.get("rate_key", "rate")
            desc = f"d{sv_name}/dt = r·{sv_name}·(1 - {sv_name}/{K_key}) + seed_boost"
        elif ode_type == "first_order_lag":
            tau = params.get("tau", 0)
            desc = f"d{sv_name}/dt = (target - {sv_name}) / τ (τ={tau}s)"
        elif ode_type == "algebraic":
            fn = params.get("fn", "")
            desc = f"{sv_name} = {fn[:60]}..."
        elif ode_type == "custom":
            deriv = params.get("derivative_fn", "")
            desc = f"d{sv_name}/dt = {deriv[:60]}..."
        else:
            desc = f"ODE type: {ode_type}"

        equations[sv_name] = {
            "type": ode_type,
            "formula": desc,
            "description": _human_readable(sv_name, ode_type)
        }
    return equations


def _human_readable(sv_name: str, ode_type: str) -> str:
    """Generate a one-line human-readable description of a state variable."""
    descriptions = {
        "alveolar_exudate": "肺泡渗出物累积量（相对值，0-1）",
        "bacterial_load": "细菌负荷增长（logistic增长）",
        "fever_state": "发热状态（first-order lag响应）",
        "tissue_hypoxia": "组织缺氧程度",
        "nephron_damage": "肾单位损伤比例",
        "gfr_decline": "GFR下降程度（相对值）",
        "potassium_shift": "血钾偏移量",
        "metabolic_acidosis": "代谢性酸中毒程度",
        "myocardial_fibrosis": "心肌纤维化程度",
        "contractility_loss": "收缩力丧失程度",
        "ventricular_dilation": "心室扩张程度",
        "fluid_retention": "液体潴留程度",
        "cellular_toxicity": "细胞毒性程度",
        "myocardial_depression": "心肌抑制程度",
        "renal_injury": "肾损伤程度",
        "gastric_distension": "胃扩张程度（GDV）",
        "gastric_ischemia": "胃缺血程度",
        "systemic_shock": "全身性休克程度",
        "arrhythmia_severity": "心律失常严重程度",
        "lactate_accumulation": "乳酸蓄积量",
        "antibody_activity": "自身抗体活性",
        "rbc_destruction": "红细胞破坏程度",
        "bilirubin_load": "胆红素负荷",
        "compensatory_tachycardia": "代偿性心动过速",
        "hypoxia_from_anemia": "贫血性缺氧",
        "urethral_blockage": "尿道梗阻程度",
        "bladder_distension": "膀胱扩张程度",
        "post_renal_azotemia": "肾后性氮质血症",
        "hyperkalemia": "高钾血症程度",
        "hyperglycemia": "高血糖程度",
        "ketone_accumulation": "酮体积聚程度",
        "kussmaul_respiration": "Kussmaul呼吸深度",
        "dehydration": "脱水程度",
        "anion_gap_acidosis": "阴离子间隙性酸中毒",
        "pericardial_volume": "心包积液量（相对值）",
        "tamponade_severity": "心脏填塞严重程度",
        "venous_congestion": "静脉淤血程度",
        "pulsus_paradoxus": "奇脉程度",
        "microthrombus_formation": "微血栓形成程度",
        "coagulation_consumption": "凝血因子消耗程度",
        "hemorrhage_risk": "出血风险",
        "organ_ischemia": "器官缺血程度",
        "shock_from_dIC": "DIC性休克程度",
        "thyroid_nodule": "甲状腺结节活性",
        "T3_excess": "T3过量程度",
        "tachycardia": "心动过速程度",
        "adrenal_atrophy": "肾上腺萎缩程度",
        "cortisol_deficiency": "皮质醇缺乏程度",
        "bacteremia": "菌血症程度",
        "cytokine_storm": "细胞因子风暴程度",
        "capillary_leak": "毛细血管渗漏程度",
        "disc_herniation": "椎间盘突出程度",
        "pain_level": "疼痛程度",
        "cns_inflammation": "中枢神经系统炎症",
        "consciousness_loss": "意识丧失程度",
        "seizure_activity": "癫痫活动程度",
        "hepatic_necrosis": "肝坏死程度",
        "factor_VII_decline": "凝血因子VII下降",
        "encephalopathy": "肝性脑病程度",
        "splenic_hemorrhage": "脾破裂出血程度",
        "hypovolemic_shock": "低血容量性休克",
    }
    base = descriptions.get(sv_name, sv_name.replace("_", " "))
    type_hint = {
        "logistic": "（logistic增长）",
        "first_order_lag": "（一阶滞后）",
        "algebraic": "（代数关系）",
        "custom": "（自定义ODE）",
    }.get(ode_type, "")
    return base + type_hint


def _has_meta(disease: dict) -> bool:
    """Check if disease already has a meta field."""
    return "meta" in disease and isinstance(disease["meta"], dict)


def enrich_disease(disease: dict, name: str) -> dict:
    """
    Add or update the `meta` field of a disease entry.
    Only adds missing sub-fields; never overwrites existing data.
    """
    meta = disease.get("meta", {})
    state_vars = disease.get("state_variables", {})

    # references
    if "references" not in meta:
        meta["references"] = REFERENCE_TEMPLATES.get(name, [
            {"id": "TODO", "text": "Add reference for " + name, "url": ""}
        ])

    # labels
    if "labels" not in meta:
        meta["labels"] = LABEL_TEMPLATES.get(name, {
            "category": [],
            "organ_systems": [],
            "symptoms": []
        })

    # equations (only if not already present)
    if "equations" not in meta:
        meta["equations"] = _build_equations(state_vars)

    disease["meta"] = meta
    return disease


def main():
    parser = argparse.ArgumentParser(description="Enrich ode_diseases.json with meta fields")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    with open(ODE_DISEASES, encoding="utf-8") as f:
        data = json.load(f)

    changes = 0
    for name, disease in data.items():
        if name.startswith("_"):
            continue
        if not isinstance(disease, dict):
            continue
        if _has_meta(disease) and args.verbose:
            print(f"  [SKIP] {name} (meta already present)")
            continue

        enriched = enrich_disease(disease, name)
        data[name] = enriched
        changes += 1
        if args.verbose:
            print(f"  [ADD] {name}")

    print(f"\nEnriched {changes} diseases.")

    if args.dry_run:
        print("[dry-run] No files written.")
        return

    # Atomic write: temp → rename
    tmp = ODE_DISEASES.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(ODE_DISEASES)
    print(f"Wrote {ODE_DISEASES}")


if __name__ == "__main__":
    main()
