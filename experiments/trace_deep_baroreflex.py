"""
Deep trace: what does baroreflex compute every step, and what does neuro do?

Key insight: heart→neuro means neuro reads MAP from PREVIOUS heart.compute()
So neuro's error is ALWAYS one step behind heart's error.

But that can't explain the HR increase with negative error throughout...

Let me check: does neuro's FactorCommand actually get applied?
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

class DeepTraceVC(VirtualCreature):
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

        # === BEFORE heart.compute: compute what heart would see ===
        co_before = h.heart_rate * h.stroke_volume
        raw_map_before = 70.0 + (co_before / 60.0) * h.SVR
        error_bef = (h.MAP_target - raw_map_before) / h.MAP_target

        # === HEART COMPUTE (updates h.heart_rate, h.SVR based on error) ===
        heart_state = h.compute(dt, svr_factor=svr_factor)

        # === AFTER heart.compute: what the NEURO reads (filtered MAP) ===
        neuro_map = h.mean_arterial_pressure
        neuro_error = (h.MAP_target - neuro_map) / h.MAP_target

        # === NEURO COMPUTE ===
        neuro_state = self.neuro.compute(dt,
            {'MAP_mmHg': neuro_map,
             'HR': h.heart_rate,
             'SVR': h.SVR},
            {'PaO2_mmHg': self.blood.arterial_PO2_mmHg,
             'PaCO2_mmHg': self.blood.arterial_PCO2_mmHg,
             'pH': self.blood.arterial_pH})

        # Track FactorCommands
        factor_cmds = neuro_state.get('factor_commands', [])
        hr_factor = 1.0
        svr_factor_cmd = 1.0
        for cmd in factor_cmds:
            target = cmd.target if hasattr(cmd, 'target') else cmd['target']
            op = cmd.op if hasattr(cmd, 'op') else cmd['op']
            value = cmd.value if hasattr(cmd, 'value') else cmd['value']
            if target == 'heart_rate' and op == 'multiply':
                hr_factor *= value
            elif target == 'SVR' and op == 'multiply':
                svr_factor_cmd *= value

        # Apply FactorCommands
        for cmd in factor_cmds:
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

        # Record at key steps
        record_steps = {1, 2, 3, 4, 5, 10, 100, 500, 1000, 2000, 2495, 2496, 2497, 2498, 2499,
                        2500, 2501, 2502, 2505, 2510, 2550, 2600, 3000, 4000, 5000, 6000}
        if self._step_count in record_steps:
            self._traces.append({
                'step': self._step_count,
                't': t,
                'HR': h.heart_rate,
                'HR_before_baro': 85.0,  # will compute
                'SV': h.stroke_volume,
                'SVR': h.SVR,
                'MAP_filtered': h.mean_arterial_pressure,
                'raw_MAP_bef': raw_map_before,
                'error_bef': error_bef,
                'neuro_error': neuro_error,
                'neuro_map': neuro_map,
                'hr_factor': hr_factor,
                'svr_factor_cmd': svr_factor_cmd,
                'sympathetic': h.sympathetic,
                'parasympathetic': h.parasympathetic,
            })


vc = DeepTraceVC(body_weight_kg=20.0)
vc.dt = DT
T_END = 60.0
n_steps = int(T_END / DT)
for i in range(n_steps):
    vc.step()
    if vc.lifecycle.is_dead():
        break

print('=' * 110)
print('DEEP TRACE: baroreflex vs neuro FactorCommand')
print('error_bef = error heart.compute() uses (raw_MAP from HR at step start)')
print('neuro_error = error neuro.compute() uses (MAP_filtered from PREVIOUS step)')
print('hr_factor = neuro FactorCommand on HR (multiplicative)')
print('=' * 110)
print(f'{"Step":>5}  {"t":>5}  {"HR":>6}  {"SVR":>7}  {"MAP_filt":>8}  '
      f'{"raw_bef":>8}  {"err_bef":>8}  {"n_err":>8}  {"hr_fact":>8}  {"sym":>6}  {"para":>6}')
print('-' * 110)
for tr in vc._traces:
    print(f'{tr["step"]:5d}  {tr["t"]:5.1f}  {tr["HR"]:6.2f}  {tr["SVR"]:7.4f}  '
          f'{tr["MAP_filtered"]:8.2f}  {tr["raw_MAP_bef"]:8.2f}  {tr["error_bef"]:8.4f}  '
          f'{tr["neuro_error"]:8.4f}  {tr["hr_factor"]:8.4f}  '
          f'{tr["sympathetic"]:6.4f}  {tr["parasympathetic"]:6.4f}')

# Find where HR starts increasing
print('\n' + '=' * 110)
print('KEY: HR increase detection')
print('=' * 110)
for i in range(1, len(vc._traces)):
    prev = vc._traces[i-1]
    curr = vc._traces[i]
    if abs(curr['HR'] - prev['HR']) > 0.5:
        print(f'HR change at step {prev["step"]} → {curr["step"]}: {prev["HR"]:.2f} → {curr["HR"]:.2f}')
        print(f'  error_bef={curr["error_bef"]:.4f}, neuro_error={curr["neuro_error"]:.4f}')
        print(f'  hr_factor={curr["hr_factor"]:.4f}, svr_factor={curr["svr_factor_cmd"]:.4f}')
        print(f'  sympathetic={curr["sympathetic"]:.4f}, parasympathetic={curr["parasympathetic"]:.4f}')
print('=' * 110)