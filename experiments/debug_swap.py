"""Debug: print HR at key steps for both orderings in check_order_swap.py pattern"""
import os, sys, types, numpy as np
EXPERIMENTS_DIR = 'experiments'
PROJECT_ROOT = os.path.dirname(os.path.abspath(EXPERIMENTS_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding='utf-8').read().replace('from src.', 'from ')

sys.modules['parameters'] = types.ModuleType('parameters')
exec(compile(_read_patched(os.path.join(SRC_DIR, 'parameters.py')),
             os.path.join(SRC_DIR, 'parameters.py'), 'exec'),
     sys.modules['parameters'].__dict__)

for _name in ['blood', 'fluid', 'cardiac_electrophysiology', 'noble_purkinje',
    'respiratory_rhythm', 'heart', 'lung', 'kidney', 'gut', 'liver',
    'endocrine', 'neuro', 'immune', 'coagulation', 'lymphatic',
    'lifecycle', 'toxicology', 'organ_health', 'pharmacology', 'simulation']:
    _path = os.path.join(SRC_DIR, f'{_name}.py')
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, 'exec'), _mod.__dict__)

VirtualCreature = sys.modules['simulation'].VirtualCreature

WEIGHT_KG = 20.0
DT = 0.01
T_END = 60.0
n_steps = int(T_END / DT)

def make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return vc

class VC_NeuroFirst(VirtualCreature):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._step_count = 0
    def step(self):
        dt = self.dt
        self._step_count += 1
        t = self.current_time_s
        self._process_events(t)
        if self._blood_loss_config is not None:
            cfg = self._blood_loss_config
            t_rel = t - cfg['t_onset']
            if t_rel >= 0:
                sigmoid_on = 1.0 / (1.0 + np.exp(-t_rel / cfg['width']))
                t_fall = t_rel - 3 * cfg['width']
                sigmoid_off = 1.0 / (1.0 + np.exp(-t_fall / cfg['width']))
                rate = cfg['k'] * sigmoid_on * (1.0 - sigmoid_off)
                self.heart.circulating_volume_ml -= rate * dt
                if self.heart.circulating_volume_ml < 0:
                    self.heart.circulating_volume_ml = 0
        if not self.lifecycle.is_dead():
            self.lifecycle.apply_age_factors(self)
            death_cause = self.lifecycle.death_check()
            if death_cause:
                self._handle_death(death_cause)
                return
        tox_state = self.toxicology.compute(dt)
        self.heart.contractility_factor = tox_state['contractility_factor']
        svr_factor = tox_state['svr_factor']
        if hasattr(self, 'medication_due') and self.medication_due:
            pharma_commands = self.pharmacology.compute(dt, self)
            if pharma_commands:
                for cmd in pharma_commands:
                    self.apply_factor(cmd)
            self.medication_due = False
        neuro_state = self.neuro.compute(dt,
            {'MAP_mmHg': self.heart.mean_arterial_pressure,
             'HR': self.heart.heart_rate,
             'SVR': self.heart.SVR},
            {'PaO2_mmHg': self.blood.arterial_PO2_mmHg,
             'PaCO2_mmHg': self.blood.arterial_PCO2_mmHg,
             'pH': self.blood.arterial_pH})
        for cmd in neuro_state.get('factor_commands', []):
            self.apply_factor(cmd)
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)
        co_ml_min = heart_state['cardiac_output_ml_min']
        lung_state = self.lung.compute(dt, co_ml_min)
        kidney_state = self.kidney.compute(dt, heart_state['MAP_mmHg'], 0, co_ml_min)
        gut_state = self.gut.compute(dt, co_ml_min)
        liver_state = self.liver.compute(dt, gut_state, co_ml_min)
        endocrine_state = self.endocrine.compute(dt)
        coagulation_state = self.coagulation.compute(dt, liver_state, {})
        lymphatic_state = self.lymphatic.compute(dt, gut_state, {})
        immune_state = self.immune.compute(dt, endocrine_state)
        if self.disease:
            engine_state = {'MAP_mmHg': heart_state['MAP_mmHg'],
                           'HR': heart_state['heart_rate_bpm'],
                           'CO_L_per_min': co_ml_min / 1000.0,
                           'blood_volume_mL': self.heart.circulating_volume_ml}
            commands = self.disease.compute(dt, engine_state)
            if commands:
                for cmd in commands:
                    self.apply_factor(cmd)
        fluid_state = self.fluid.compute(dt)
        self.current_time_s += dt

# Reference: heart-first
print('Heart-first:')
vc1 = make_vc()
vc1.dt = DT
for i in range(n_steps + 1):
    if i % 1000 == 0:
        print(f'  t={i*DT:.0f}s: HR={vc1.heart.heart_rate:.2f}, MAP={vc1.heart.mean_arterial_pressure:.3f}')
    vc1.step()

print(f'\nNeuro-first:')
vc2 = VC_NeuroFirst(body_weight_kg=WEIGHT_KG)
vc2.dt = DT
vc2._cached_inputs.clear()
for i in range(n_steps + 1):
    if i % 1000 == 0:
        print(f'  t={i*DT:.0f}s: HR={vc2.heart.heart_rate:.2f}, MAP={vc2.heart.mean_arterial_pressure:.3f}')
    vc2.step()

print(f'\nHeart-first final: HR={vc1.heart.heart_rate:.2f}, MAP={vc1.heart.mean_arterial_pressure:.3f}')
print(f'Neuro-first final: HR={vc2.heart.heart_rate:.2f}, MAP={vc2.heart.mean_arterial_pressure:.3f}')