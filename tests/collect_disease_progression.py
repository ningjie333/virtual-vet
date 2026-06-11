#!/usr/bin/env python3
"""
Fast disease progression data collector - samples only at key timepoints.
Uses large simulate() chunks to skip empty time.
Samples: warmup_end, t+5min, t+15min, t+30min (4 points per disease).
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from src.simulation import VirtualCreature
from src.diseases import create_disease
from src.report_engine import get_state
import copy

with open('data/cases.json') as f:
    cases = json.load(f)['cases']

with open('data/symptom_definitions.json') as f:
    symptom_defs = json.load(f)['symptoms']

def sample_vc(vc):
    state = get_state(vc)
    disease = getattr(vc, 'disease', None)
    disease_vars = copy.deepcopy(disease._state_vars) if disease else {}
    engine = vc.clinical_signs_engine
    engine.compute(vc.current_time_s)
    signs = sorted(engine.get_sign_tags())
    return {
        'time_s': round(vc.current_time_s, 1),
        'HR': round(state.get('HR', 0) or 0, 1),
        'MAP': round(state.get('MAP', 0) or 0, 1),
        'RR': round(state.get('RR', 0) or 0, 1),
        'SpO2': round(state.get('SpO2', 0) or 0, 1),
        'pH': round(state.get('pH', 0) or 0, 3),
        'BUN': round(state.get('BUN', 0) or 0, 1),
        'K': round(state.get('K', 0) or 0, 2),
        'Glu': round(state.get('Glu', 0) or 0, 2),
        'Temp': round(state.get('Temp', 0) or 0, 2),
        'HCT': round(state.get('HCT', 0) or 0, 1),
        'disease_vars': {k: round(v, 4) for k, v in disease_vars.items()},
        'active_signs': signs,
    }

results = {}
for case in cases:
    disease_name = case['disease']
    title = case['title']
    warmup_min = case['warmup_minutes']
    species = case['animal']['species'].lower()
    weight = case['animal']['weight_kg']

    print(f"Processing {case['id']} {disease_name}...", flush=True)

    vc = VirtualCreature(species=species, body_weight_kg=weight)
    disease = create_disease(disease_name, severity='moderate')
    vc.attach_disease(disease)

    # Warmup
    vc.simulate(warmup_min)

    samples = []
    # Sample at warmup end
    samples.append(sample_vc(vc))

    # Jump in 5min chunks, sample at each
    for chunk_min in [5, 10, 15, 30]:
        vc.simulate(chunk_min)
        samples.append(sample_vc(vc))

    results[case['id']] = {
        'case': case['id'],
        'title': title,
        'disease': disease_name,
        'warmup_min': warmup_min,
        'history_text': case.get('history', ''),
        'samples': samples,
    }
    last = samples[-1]
    print(f"  -> {len(samples)} samples, t={last['time_s']}s, signs={last['active_signs']}")

os.makedirs('paper_rewriting_output', exist_ok=True)
with open('paper_rewriting_output/disease_progression_data.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nDone. Saved to paper_rewriting_output/disease_progression_data.json")

# Summary
print("\n=== SUMMARY ===")
for rid, r in results.items():
    all_signs = list(dict.fromkeys(s for s in r['samples'] for s_ in s.get('active_signs', [])))
    first_sign = next((s['time_s'] for s in r['samples'] if s.get('active_signs')), None)
    last = r['samples'][-1]
    print(f"{rid} {r['disease']:<35} warmup={r['warmup_min']}min "
          f"samples={len(r['samples'])} first_sign_t={first_sign}s "
          f"total_signs={len(all_signs)} last_signs={last.get('active_signs',[])}")