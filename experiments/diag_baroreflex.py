"""
Diagnostic v2: trace raw_MAP, filtered_MAP, and SVR through full 60s baseline.
We need to find WHERE the divergence starts between heart_neuro and neuro_heart.
"""
import os, sys, types, numpy as np

EXPERIMENTS_DIR = 'experiments'
PROJECT_ROOT = os.path.dirname(os.path.abspath(EXPERIMENTS_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding='utf-8').read().replace('from src.', 'from ')

for _name in ['parameters', 'blood', 'fluid', 'cardiac_electrophysiology', 'noble_purkinje',
    'respiratory_rhythm', 'heart', 'lung', 'kidney', 'gut', 'liver',
    'endocrine', 'neuro', 'immune', 'coagulation', 'lymphatic',
    'lifecycle', 'toxicology', 'organ_health', 'pharmacology', 'simulation']:
    _path = os.path.join(SRC_DIR, f'{_name}.py')
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, 'exec'), _mod.__dict__)

VirtualCreature = sys.modules['simulation'].VirtualCreature

# ──────────────────────────────────────────────────────────────
# Heart-first (original)
# ──────────────────────────────────────────────────────────────
class VC_HeartFirst(VirtualCreature):
    _ordering = 'heart_neuro'

    def step(self):
        dt = self.dt
        self._step_count = getattr(self, '_step_count', 0) + 1

        self._process_events(t=self.current_time_s)
        if not self.lifecycle.is_dead():
            self.lifecycle.apply_age_factors(self)
            death = self.lifecycle.death_check()
            if death:
                self._handle_death(death)
                return

        tox = self.toxicology.compute(dt)
        self.heart.contractility_factor = tox['contractility_factor']
        svr_factor = tox['svr_factor']

        # Heart FIRST
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)

        # Then neuro
        neuro_state = self.neuro.compute(dt, heart_state, {})
        for cmd in neuro_state.get('factor_commands', []):
            self.apply_factor(cmd)

        co = heart_state['cardiac_output_ml_min']
        lung_state = self.lung.compute(dt, co)
        kidney_state = self.kidney.compute(dt, heart_state['MAP_mmHg'], 0, co)
        gut_state = self.gut.compute(dt, co)
        liver_state = self.liver.compute(dt, gut_state, co)
        endocrine_state = self.endocrine.compute(dt)
        coagulation_state = self.coagulation.compute(dt, liver_state, {})
        for cmd in coagulation_state.get('factor_commands', []):
            self.apply_factor(cmd)
        lymphatic_state = self.lymphatic.compute(dt, gut_state, {})
        for cmd in lymphatic_state.get('factor_commands', []):
            self.apply_factor(cmd)
        immune_state = self.immune.compute(dt, endocrine_state)
        self.fluid.compute(dt)
        self.current_time_s += dt

# ──────────────────────────────────────────────────────────────
# Neuro-first (reversed)
# ──────────────────────────────────────────────────────────────
class VC_NeuroFirst(VirtualCreature):
    _ordering = 'neuro_heart'

    def step(self):
        dt = self.dt
        self._step_count = getattr(self, '_step_count', 0) + 1

        self._process_events(t=self.current_time_s)
        if not self.lifecycle.is_dead():
            self.lifecycle.apply_age_factors(self)
            death = self.lifecycle.death_check()
            if death:
                self._handle_death(death)
                return

        tox = self.toxicology.compute(dt)
        self.heart.contractility_factor = tox['contractility_factor']
        svr_factor = tox['svr_factor']

        # Neuro FIRST
        neuro_state = self.neuro.compute(dt,
            {'MAP_mmHg': self.heart.mean_arterial_pressure,
             'HR': self.heart.heart_rate,
             'SVR': self.heart.SVR},
            {'PaO2_mmHg': self.blood.arterial_PO2_mmHg,
             'PaCO2_mmHg': self.blood.arterial_PCO2_mmHg,
             'pH': self.blood.arterial_pH})
        for cmd in neuro_state.get('factor_commands', []):
            self.apply_factor(cmd)

        # Then heart
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)

        co = heart_state['cardiac_output_ml_min']
        lung_state = self.lung.compute(dt, co)
        kidney_state = self.kidney.compute(dt, heart_state['MAP_mmHg'], 0, co)
        gut_state = self.gut.compute(dt, co)
        liver_state = self.liver.compute(dt, gut_state, co)
        endocrine_state = self.endocrine.compute(dt)
        coagulation_state = self.coagulation.compute(dt, liver_state, {})
        for cmd in coagulation_state.get('factor_commands', []):
            self.apply_factor(cmd)
        lymphatic_state = self.lymphatic.compute(dt, gut_state, {})
        for cmd in lymphatic_state.get('factor_commands', []):
            self.apply_factor(cmd)
        immune_state = self.immune.compute(dt, endocrine_state)
        self.fluid.compute(dt)
        self.current_time_s += dt

# ──────────────────────────────────────────────────────────────
# Run 60s, record every 5 steps (0.05s intervals)
# Track: raw_MAP, filtered_MAP, sympathetic, SVR, stroke_volume, heart_rate
# ──────────────────────────────────────────────────────────────
DT = 0.01
T_END = 60.0
N_STEPS = int(T_END / DT)
RECORD_INTERVAL = 50  # every 0.5s

print('=' * 90)
print('DIAGNOSTIC v2: 60s baseline trace, every 5s')
print('=' * 90)

for OrderingClass, name in [(VC_HeartFirst, 'heart_neuro'), (VC_NeuroFirst, 'neuro_heart')]:
    vc = OrderingClass(body_weight_kg=20.0)
    vc.dt = DT
    vc._step_count = 0

    recs = []
    for i in range(N_STEPS + 1):
        if i % RECORD_INTERVAL == 0:
            h = vc.heart
            recs.append({
                't': i * DT,
                'filtered_MAP': h.mean_arterial_pressure,
                'MAP_target': h.MAP_target,
                'sympathetic': h.sympathetic,
                'SVR': h.SVR,
                'stroke_volume': h.stroke_volume,
                'heart_rate': h.heart_rate,
            })
        vc.step()
        if vc.lifecycle.is_dead():
            break

    print(f'\n=== {name} ===')
    print(f'{"t":>5}  {"filtered_MAP":>13}  {"sympathetic":>10}  {"SVR":>8}  {"SV":>8}  {"HR":>8}')
    for r in recs:
        print(f'{r["t"]:5.1f}  {r["filtered_MAP"]:13.4f}  {r["sympathetic"]:10.6f}  '
              f'{r["SVR"]:8.4f}  {r["stroke_volume"]:8.4f}  {r["heart_rate"]:8.2f}')

print('\n' + '=' * 90)
print('QUESTION: At which time does the divergence start?')
print('If t=0 (step 0 filtered_MAP differs) -> ordering changes MAP reading at step 1')
print('If t>0 -> divergence builds gradually from identical initial conditions')
print('=' * 90)