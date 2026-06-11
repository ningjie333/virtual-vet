#!/usr/bin/env python3
"""Quick warmup check — 5min window only to get fast signal."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import json
from src.simulation import VirtualCreature
from src.diseases import create_disease
from src.clinical_signs_engine import ClinicalSignsEngine

with open('data/cases.json') as f:
    cases = json.load(f)['cases']

with open('data/symptom_definitions.json') as f:
    symptom_defs = json.load(f)['symptoms']

results = []
for case in cases:
    disease_name = case['disease']
    warmup_min = case['warmup_minutes']
    title = case['title']
    species = case['animal']['species'].lower()
    weight = case['animal']['weight_kg']

    vc = VirtualCreature(species=species, body_weight_kg=weight)
    disease = create_disease(disease_name, severity='moderate')
    vc.attach_disease(disease)
    vc.simulate(warmup_min)

    # Use vc.clinical_signs_engine (populated during simulate, not a new instance!)
    engine = vc.clinical_signs_engine
    engine.compute(vc.current_time_s)
    signs_after_warmup = set(engine.get_sign_tags())

    # Run 5 more minutes
    vc.simulate(5)
    engine.compute(vc.current_time_s)
    signs_after_5 = set(engine.get_sign_tags())

    results.append({
        'case': case['id'],
        'disease': disease_name,
        'warmup_min': warmup_min,
        'signs_at_warmup_end': sorted(signs_after_warmup),
        'signs_after_5min': sorted(signs_after_5),
        'signs_before_warmup': sorted(signs_after_5 - signs_after_warmup),
    })
    print(f"{case['id']} {disease_name:<35} warmup={warmup_min}min signs@warmup={signs_after_warmup} new_in_5min={sorted(signs_after_5 - signs_after_warmup)}")

print("\n--- Summary ---")
for r in results:
    if not r['signs_after_5min']:
        print(f"MISSING SIGNS: {r['case']} ({r['disease']})")
    elif r['signs_at_warmup_end']:
        print(f"TRIGGERS EARLY: {r['case']} ({r['disease']}) warmup={r['warmup_min']}min {r['signs_at_warmup_end']}")