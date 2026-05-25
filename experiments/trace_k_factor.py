"""
CRITICAL: Check if HH k_toxicity_factor > 1 overrides parasympathetic braking.

HR_increase despite negative error → either:
1. k_toxicity_factor > 1 (K+ rising) overriding parasympathetic effect, OR
2. Something else in baroreflex

Let me trace k_toxicity_factor every step.
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

class KTraceVC(VirtualCreature):
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

        # Capture HH state before
        k_factor_before = h.hh.k_toxicity_factor if hasattr(h, 'hh') else 1.0
        k_before = h.blood.potassium_mEq_L

        # Heart compute
        heart_state = h.compute(dt, svr_factor=svr_factor)

        # State AFTER heart.compute
        co_after = h.heart_rate * h.stroke_volume
        raw_map_after = 70.0 + (co_after / 60.0) * h.SVR
        error_aft = (h.MAP_target - raw_map_after) / h.MAP_target

        # Compute baroreflex HR_delta manually
        # From heart.py _baroreceptor_feedback:
        # HR_para = -parasymp * 15 * max(0, -error)
        # HR_symp = symp * 50 * max(0, error)
        # HR_delta = (HR_para + HR_symp) * dt
        k_factor_after = h.hh.k_toxicity_factor if hasattr(h, 'hh') else 1.0
        k_after = h.blood.potassium_mEq_L
        HR_para = -h.parasympathetic * 15.0 * max(0.0, -error_bef)
        HR_symp = h.sympathetic * 50.0 * max(0.0, error_bef)
        HR_delta_from_baro = (HR_para + HR_symp) * dt
        HR_delta_total = h.heart_rate - 85.0  # relative to initial

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

        record_steps = {1, 2, 3, 4, 5, 10, 100, 500, 1000, 2000, 2495, 2500, 2550, 2600, 3000, 4000, 5000, 6000}
        if self._step_count in record_steps:
            self._traces.append({
                'step': self._step_count,
                't': t,
                'HR': h.heart_rate,
                'SV': h.stroke_volume,
                'SVR': h.SVR,
                'MAP_filtered': h.mean_arterial_pressure,
                'raw_MAP': raw_map_before,
                'error': error_bef,
                'HR_para': HR_para,
                'HR_symp': HR_symp,
                'HR_delta_baro': HR_delta_from_baro,
                'k_factor': k_factor_after,
                'k_before': k_before,
                'k_after': k_after,
                'sympathetic': h.sympathetic,
                'parasympathetic': h.parasympathetic,
            })


vc = KTraceVC(body_weight_kg=20.0)
vc.dt = DT
T_END = 60.0
n_steps = int(T_END / DT)
for i in range(n_steps):
    vc.step()
    if vc.lifecycle.is_dead():
        break

print('=' * 115)
print('HH K+ TOXICITY FACTOR TRACE: Is k_factor > 1 overriding parasympathetic braking?')
print('=' * 115)
print(f'{"Step":>5}  {"t":>5}  {"HR":>7}  {"err":>8}  {"HR_para":>8}  {"HR_symp":>8}  '
      f'{"k_bef":>7}  {"k_aft":>7}  {"k_fact":>7}  {"sym":>6}  {"para":>6}')
print('-' * 115)
for tr in vc._traces:
    print(f'{tr["step"]:5d}  {tr["t"]:5.1f}  {tr["HR"]:7.2f}  {tr["error"]:8.4f}  '
          f'{tr["HR_para"]:8.4f}  {tr["HR_symp"]:8.4f}  '
          f'{tr["k_before"]:7.3f}  {tr["k_after"]:7.3f}  {tr["k_factor"]:7.4f}  '
          f'{tr["sympathetic"]:6.4f}  {tr["parasympathetic"]:6.4f}')

print('\n' + '=' * 115)
print('ANALYSIS:')
for i in range(1, len(vc._traces)):
    prev = vc._traces[i-1]
    curr = vc._traces[i]
    if abs(curr['HR'] - prev['HR']) > 0.5:
        print(f'\nHR change at step {prev["step"]} → {curr["step"]}: {prev["HR"]:.2f} → {curr["HR"]:.2f}')
        print(f'  error = {curr["error"]:.4f} (MAP > target → negative)')
        print(f'  HR_para = {curr["HR_para"]:.4f} (should DECREASE HR since error < 0)')
        print(f'  HR_symp = {curr["HR_symp"]:.4f} (should be 0 since error < 0)')
        print(f'  k_factor = {curr["k_factor"]:.4f} (1.0 = no K+ effect, >1 = accelerates HR)')
        print(f'  k_before = {curr["k_before"]:.3f}, k_after = {curr["k_after"]:.3f}')
        if curr['HR_para'] < 0 and curr['HR_symp'] == 0:
            net_change = curr['HR_para'] + curr['HR_symp']
            expected_hr_change = net_change * 0.01
            print(f'  Net baro = {net_change:.4f}, expected HR change/step = {expected_hr_change:.6f}')
            print(f'  BUT actual HR change = {curr["HR"] - prev["HR"]:.4f}')
            print(f'  → k_factor × HR_increase = {curr["k_factor"]:.4f} × {abs(expected_hr_change):.6f} = {curr["k_factor"] * abs(expected_hr_change):.6f}')
print('=' * 115)