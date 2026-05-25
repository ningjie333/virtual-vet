"""
Full 10-step trace with detailed state to diagnose T2 paradox.
At step 1: raw_MAP=110.0, error=-0.10
But final MAP=144.7 despite consistent negative error.
Need to see how HR transitions from 85 to 180.
"""
import os, sys, types, numpy as np

EXPERIMENTS_DIR = 'experiments'
PROJECT_ROOT = os.path.dirname(os.path.abspath(EXPERIMENTS_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    src = open(path, encoding='utf-8').read()
    src = src.replace('from src.', 'from ')
    src = src.replace('import src.', 'import ')
    return src

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

DT = 0.01
T_END = 60.0

def make_vc():
    vc = VirtualCreature(body_weight_kg=20.0)
    vc._cached_inputs.clear()
    return vc


class TracingVC(VirtualCreature):
    """Heart-first with step-by-step tracing"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._step_count = 0
        self._traces = []

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

        # === Capture state BEFORE heart.compute() ===
        h = self.heart
        co_before = h.heart_rate * h.stroke_volume
        raw_map_before = 70.0 + (co_before / 60.0) * h.SVR
        error_before = (h.MAP_target - raw_map_before) / h.MAP_target
        sym_before = h.sympathetic
        para_before = h.parasympathetic

        # Heart FIRST
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)

        # === Capture state AFTER heart.compute() ===
        co_after = h.heart_rate * h.stroke_volume
        raw_map_after = 70.0 + (co_after / 60.0) * h.SVR
        error_after = (h.MAP_target - raw_map_after) / h.MAP_target

        # Neuro SECOND
        neuro_state = self.neuro.compute(dt,
            {'MAP_mmHg': self.heart.mean_arterial_pressure,
             'HR': self.heart.heart_rate,
             'SVR': self.heart.SVR},
            {'PaO2_mmHg': self.blood.arterial_PO2_mmHg,
             'PaCO2_mmHg': self.blood.arterial_PCO2_mmHg,
             'pH': self.blood.arterial_pH})
        for cmd in neuro_state.get('factor_commands', []):
            self.apply_factor(cmd)

        lung_state = self.lung.compute(dt, co_after)
        kidney_state = self.kidney.compute(dt, heart_state['MAP_mmHg'], 0, co_after)
        gut_state = self.gut.compute(dt, co_after)
        liver_state = self.liver.compute(dt, gut_state, co_after)
        endocrine_state = self.endocrine.compute(dt)
        coagulation_state = self.coagulation.compute(dt, liver_state, {})
        lymphatic_state = self.lymphatic.compute(dt, gut_state, {})
        immune_state = self.immune.compute(dt, endocrine_state)

        if self.disease:
            engine_state = {'MAP_mmHg': heart_state['MAP_mmHg'],
                           'HR': heart_state['heart_rate_bpm'],
                           'CO_L_per_min': co_after / 1000.0,
                           'blood_volume_mL': self.heart.circulating_volume_ml}
            commands = self.disease.compute(dt, engine_state)
            if commands:
                for cmd in commands:
                    self.apply_factor(cmd)

        fluid_state = self.fluid.compute(dt)
        self.current_time_s += dt

        # Record trace at steps 1-5, 10, 50, 100, 500, 1000, 2000, 3000, 4000, 5000, 6000
        record_steps = {1, 2, 3, 4, 5, 10, 50, 100, 500, 1000, 2000, 3000, 4000, 5000, 6000}
        if self._step_count in record_steps:
            self._traces.append({
                'step': self._step_count,
                't': t,
                'HR': h.heart_rate,
                'SV': h.stroke_volume,
                'SVR': h.SVR,
                'MAP_filtered': h.mean_arterial_pressure,
                'raw_MAP_before': raw_map_before,
                'raw_MAP_after': raw_map_after,
                'error_before': error_before,
                'error_after': error_after,
                'sympathetic': sym_before,
                'parasympathetic': para_before,
                'CO': co_after,
            })


vc = TracingVC(body_weight_kg=20.0)
vc.dt = DT
n_steps = int(T_END / DT)
for i in range(n_steps):
    vc.step()
    if vc.lifecycle.is_dead():
        break
    if vc._traces and vc._step_count >= 6000:
        break

print('=' * 80)
print('FULL SIMULATION TRACE: heart→neuro ordering')
print('=' * 80)
print(f'{"Step":>5}  {"t":>6}  {"HR":>7}  {"SV":>7}  {"SVR":>7}  {"MAP":>7}  {"raw_MAP_bef":>11}  {"error_bef":>10}  {"sym":>6}  {"para":>6}')
print('-' * 80)
for tr in vc._traces:
    print(f'{tr["step"]:5d}  {tr["t"]:6.2f}  {tr["HR"]:7.2f}  {tr["SV"]:7.4f}  {tr["SVR"]:7.4f}  '
          f'{tr["MAP_filtered"]:7.2f}  {tr["raw_MAP_before"]:11.2f}  {tr["error_before"]:10.4f}  '
          f'{tr["sympathetic"]:6.4f}  {tr["parasympathetic"]:6.4f}')

print('\n' + '=' * 80)
print('KEY OBSERVATIONS:')
print('=' * 80)
# Find first step where HR > 85
hr_85_count = sum(1 for tr in vc._traces if abs(tr['HR'] - 85.0) < 0.5)
hr_180_count = sum(1 for tr in vc._traces if tr['HR'] > 170)
print(f'  Steps with HR ≈ 85: {hr_85_count}')
print(f'  Steps with HR > 170: {hr_180_count}')
if vc._traces:
    first_high_hr = next((tr for tr in vc._traces if tr['HR'] > 100), None)
    if first_high_hr:
        print(f'  First step with HR > 100: step {first_high_hr["step"]} at t={first_high_hr["t"]:.2f}s')
    last_tr = vc._traces[-1]
    print(f'  Final state: step {last_tr["step"]}, HR={last_tr["HR"]:.2f}, MAP={last_tr["MAP_filtered"]:.2f}, SVR={last_tr["SVR"]:.4f}')
print('=' * 80)