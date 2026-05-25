"""
Run neuro→heart ordering to see if chemoreceptor_drive also activates.

If neuro→heart also has net_HR_add=0.1 starting at step 2000,
then why does MAP stay at 100? The answer to the T2 paradox must be:
the chemoreceptor triggers in BOTH orderings at step ~2000,
but in heart→neuro the elevated HR causes MAP to rise above target,
creating the feedback loop that leads to 144.7.
In neuro→heart, MAP_filtered stays at 100, so the baroreflex sees error=0,
and the system reaches a different steady state.
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

class NeuroFirstVC(VirtualCreature):
    """neuro→heart ordering"""
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

        # === NEURO FIRST (reads MAP from previous step) ===
        neuro_state = self.neuro.compute(dt,
            {'MAP_mmHg': h.mean_arterial_pressure,  # STALE MAP (initialized to 100)
             'HR': h.heart_rate,
             'SVR': h.SVR},
            {'PaO2_mmHg': self.blood.arterial_PO2_mmHg,
             'PaCO2_mmHg': self.blood.arterial_PCO2_mmHg,
             'pH': self.blood.arterial_pH})

        net_HR_add = neuro_state.get('net_HR_add', 0)
        chemoreceptor_drive = neuro_state.get('chemoreceptor_drive', 0)
        MAP_error_read_by_neuro = (h.MAP_target - h.mean_arterial_pressure) / h.MAP_target

        # Apply FactorCommands
        for cmd in neuro_state.get('factor_commands', []):
            self.apply_factor(cmd)

        # === HEART SECOND ===
        heart_state = h.compute(dt, svr_factor=svr_factor)

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

        record_steps = {1, 2, 3, 4, 5, 10, 100, 500, 1000, 2000, 2490, 2491, 2495, 2500, 2550, 2600, 3000, 4000, 5000, 6000}
        if self._step_count in record_steps:
            self._traces.append({
                'step': self._step_count,
                't': t,
                'HR': h.heart_rate,
                'MAP_filtered': h.mean_arterial_pressure,
                'MAP_target': h.MAP_target,
                'MAP_error_read_by_neuro': MAP_error_read_by_neuro,
                'net_HR_add': net_HR_add,
                'chemoreceptor_drive': chemoreceptor_drive,
                'sympathetic': h.sympathetic,
                'parasympathetic': h.parasympathetic,
            })


vc = NeuroFirstVC(body_weight_kg=20.0)
vc.dt = DT
T_END = 60.0
n_steps = int(T_END / DT)
for i in range(n_steps):
    vc.step()
    if vc.lifecycle.is_dead():
        break

print('=' * 100)
print('NEURO→HEART ORDERING: Full trace')
print('=' * 100)
print(f'{"Step":>5}  {"t":>5}  {"HR":>7}  {"MAP":>7}  {"err_neuro":>10}  {"net_HR":>7}  '
      f'{"chemo":>6}  {"sym":>6}  {"para":>6}')
print('-' * 100)
for tr in vc._traces:
    print(f'{tr["step"]:5d}  {tr["t"]:5.1f}  {tr["HR"]:7.2f}  {tr["MAP_filtered"]:7.2f}  '
          f'{tr["MAP_error_read_by_neuro"]:10.4f}  {tr["net_HR_add"]:7.2f}  '
          f'{tr["chemoreceptor_drive"]:6.3f}  '
          f'{tr["sympathetic"]:6.4f}  {tr["parasympathetic"]:6.4f}')

if vc._traces:
    final = vc._traces[-1]
    print(f'\nNEURO→HEART FINAL STATE: HR={final["HR"]:.2f}, MAP={final["MAP_filtered"]:.2f} mmHg')
    print(f'  Compared to heart→neuro: HR≈180, MAP≈144.77 mmHg')
    print(f'  Bias = {144.77 - final["MAP_filtered"]:.2f} mmHg')
print('=' * 100)