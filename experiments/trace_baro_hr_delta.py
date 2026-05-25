"""
Direct trace of HR inside heart.compute() _baroreceptor_feedback.

The key question: HR stays at 85 despite HR_para being negative every step.
Let me trace exactly what HR value is returned at each step from inside compute().

Actually, the simplest approach: patch heart._baroreceptor_feedback to print
HR before and after the HR update.
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

# Monkey-patch _baroreceptor_feedback to trace HR delta
_heart_mod = sys.modules['heart']
_original_baro = _heart_mod.HeartModule._baroreceptor_feedback

def _patched_baro(self, MAP, dt):
    hr_before = self.heart_rate
    result = _original_baro(self, MAP, dt)
    hr_after = self.heart_rate
    self._baro_hr_delta = hr_after - hr_before
    return result

_heart_mod.HeartModule._baroreceptor_feedback = _patched_baro

DT = 0.01

class PatchTraceVC(VirtualCreature):
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

        h = self.heart

        # State BEFORE heart.compute
        co_before = h.heart_rate * h.stroke_volume
        raw_map_before = 70.0 + (co_before / 60.0) * h.SVR
        error_bef = (h.MAP_target - raw_map_before) / h.MAP_target

        # Heart compute (this calls _baroreceptor_feedback internally)
        heart_state = h.compute(dt, svr_factor=svr_factor)

        # Capture HR delta from baroreflex
        baro_hr_delta = getattr(h, '_baro_hr_delta', 0.0)

        # State AFTER
        co_after = h.heart_rate * h.stroke_volume
        raw_map_after = 70.0 + (co_after / 60.0) * h.SVR

        # Neuro
        neuro_state = self.neuro.compute(dt,
            {'MAP_mmHg': h.mean_arterial_pressure,
             'HR': h.heart_rate,
             'SVR': h.SVR},
            {'PaO2_mmHg': self.blood.arterial_PO2_mmHg,
             'PaCO2_mmHg': self.blood.arterial_PCO2_mmHg,
             'pH': self.blood.arterial_pH})
        for cmd in neuro_state.get('factor_commands', []):
            self.apply_factor(cmd)

        co_ml_min = h.heart_rate * h.stroke_volume
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

        record_steps = {1, 2, 3, 4, 5, 10, 50, 100, 500, 1000, 1500, 2000,
                        2490, 2491, 2492, 2493, 2494, 2495, 2496, 2497, 2498, 2499,
                        2500, 2501, 2505, 2510, 2550, 2600, 3000, 4000, 5000, 6000}
        if self._step_count in record_steps:
            self._traces.append({
                'step': self._step_count,
                't': t,
                'HR': h.heart_rate,
                'baro_hr_delta': baro_hr_delta,
                'SV': h.stroke_volume,
                'SVR': h.SVR,
                'MAP_filtered': h.mean_arterial_pressure,
                'raw_MAP': raw_map_before,
                'error': error_bef,
                'sympathetic': h.sympathetic,
                'parasympathetic': h.parasympathetic,
            })


vc = PatchTraceVC(body_weight_kg=20.0)
vc.dt = DT
T_END = 60.0
n_steps = int(T_END / DT)
for i in range(n_steps):
    vc.step()
    if vc.lifecycle.is_dead():
        break

print('=' * 105)
print('DIRECT BAROREFLEX HR DELTA TRACE')
print('baro_hr_delta = actual HR change inside _baroreceptor_feedback per step')
print('=' * 105)
print(f'{"Step":>5}  {"t":>5}  {"HR":>7}  {"baro_d":>9}  {"SVR":>7}  {"MAP":>7}  '
      f'{"raw_MAP":>8}  {"error":>8}  {"sym":>6}  {"para":>6}')
print('-' * 105)
for tr in vc._traces:
    print(f'{tr["step"]:5d}  {tr["t"]:5.1f}  {tr["HR"]:7.4f}  {tr["baro_hr_delta"]:9.5f}  '
          f'{tr["SVR"]:7.4f}  {tr["MAP_filtered"]:7.2f}  '
          f'{tr["raw_MAP"]:8.2f}  {tr["error"]:8.4f}  '
          f'{tr["sympathetic"]:6.4f}  {tr["parasympathetic"]:6.4f}')

print('\n' + '=' * 105)
print('KEY: Does baro_hr_delta match expected HR change?')
print('=' * 105)
for i in range(1, min(20, len(vc._traces))):
    prev = vc._traces[i-1]
    curr = vc._traces[i]
    actual_delta = curr['HR'] - prev['HR']
    print(f'Step {prev["step"]}→{curr["step"]}: HR {prev["HR"]:.4f}→{curr["HR"]:.4f}, '
          f'actualΔ={actual_delta:.6f}, baro_d={curr["baro_hr_delta"]:.6f}, '
          f'error={curr["error"]:.4f}, para={curr["parasympathetic"]:.4f}')
print('=' * 105)