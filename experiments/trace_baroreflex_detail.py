"""
DIAGNOSIS: What does baroreflex see vs what we record?

The trace shows raw_MAP_bef=110 (error=-0.10) every step.
But heart.compute() uses raw_MAP which is computed FROM the NEW HR after baroreflex updates.

So the key question: does raw_MAP AFTER heart.compute() drop below 100?

If error becomes positive at some step, HR starts climbing → MAP climbs → HR climbs further...

This is a POSITIVE FEEDBACK LOOP: HR↑ → CO↑ → raw_MAP↑ → but wait that should make error MORE negative...

Wait - let me re-think. CO = HR × SV. If HR↑ and SV fixed → CO↑ → MAP↑ → error becomes MORE negative → parasymp dominates → HR↓

That's NEGATIVE feedback. But we see HR climbing. Something else must be happening.
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

class TracingVC(VirtualCreature):
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
        # State BEFORE heart.compute()
        co_before = h.heart_rate * h.stroke_volume
        raw_map_before = 70.0 + (co_before / 60.0) * h.SVR
        error_before = (h.MAP_target - raw_map_before) / h.MAP_target

        # Heart FIRST (this updates HR and SVR based on raw_map_before)
        heart_state = h.compute(dt, svr_factor=svr_factor)

        # State AFTER heart.compute() - this is what NEURO reads next step
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

        # Record at key steps around the transition
        record_steps = {1, 2, 3, 4, 5, 10, 50, 100, 500,
                        1500, 1800, 1900, 1950, 1980, 1990, 1995, 1996, 1997, 1998, 1999,
                        2000, 2001, 2002, 2005, 2010, 2050, 2100,
                        2500, 3000, 4000, 5000, 6000}
        if self._step_count in record_steps:
            self._traces.append({
                'step': self._step_count,
                't': t,
                'HR': h.heart_rate,
                'SV': h.stroke_volume,
                'SVR': h.SVR,
                'MAP_filtered': h.mean_arterial_pressure,
                'raw_MAP_bef': raw_map_before,
                'raw_MAP_aft': raw_map_after,
                'error_bef': error_before,
                'error_aft': error_after,
                'sympathetic': h.sympathetic,
                'parasympathetic': h.parasympathetic,
                'CO': co_ml_min,
            })


vc = TracingVC(body_weight_kg=20.0)
vc.dt = DT
T_END = 60.0
n_steps = int(T_END / DT)
for i in range(n_steps):
    vc.step()
    if vc.lifecycle.is_dead():
        break

print('=' * 95)
print('DIAGNOSIS: What does baroreflex see? error_bef=uses raw_MAP_bef (HR at step start)')
print('           error_aft=uses raw_MAP_aft (HR at step end, after baroreflex updates HR)')
print('=' * 95)
print(f'{"Step":>5}  {"t":>5}  {"HR":>7}  {"SVR":>7}  {"MAP_filt":>8}  '
      f'{"raw_bef":>8}  {"err_bef":>8}  {"raw_aft":>8}  {"err_aft":>8}  {"sym":>6}  {"para":>6}')
print('-' * 95)
for tr in vc._traces:
    print(f'{tr["step"]:5d}  {tr["t"]:5.1f}  {tr["HR"]:7.2f}  {tr["SVR"]:7.4f}  '
          f'{tr["MAP_filtered"]:8.2f}  {tr["raw_MAP_bef"]:8.2f}  {tr["error_bef"]:8.4f}  '
          f'{tr["raw_MAP_aft"]:8.2f}  {tr["error_aft"]:8.4f}  '
          f'{tr["sympathetic"]:6.4f}  {tr["parasympathetic"]:6.4f}')

print('\n' + '=' * 95)
# Find transition point
for i in range(1, len(vc._traces)):
    prev = vc._traces[i-1]
    curr = vc._traces[i]
    if abs(curr['HR'] - prev['HR']) > 1.0:
        print(f'TRANSITION: step {prev["step"]} → {curr["step"]}, HR {prev["HR"]:.2f} → {curr["HR"]:.2f}')
        print(f'  At step {curr["step"]}: error_bef={curr["error_bef"]:.4f}, error_aft={curr["error_aft"]:.4f}')
        print(f'  raw_MAP_bef={curr["raw_MAP_bef"]:.2f}, raw_MAP_aft={curr["raw_MAP_aft"]:.2f}')
        print(f'  MAP_filtered={curr["MAP_filtered"]:.2f}')
        break
print('=' * 95)