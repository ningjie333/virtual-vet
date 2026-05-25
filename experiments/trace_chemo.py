"""
The +0.1/step HR increase comes from neuro's chemoreceptor_drive.
neuro.compute() issues FactorCommand "heart.heart_rate" "add" +0.1 every step.
This is the "Loop B" coupling that the paper discusses.

Let me confirm: the chemoreceptor_drive starts at 0, but at step 2491 it turns on.
Why does it turn on at step 2491?
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

class ChemoTraceVC(VirtualCreature):
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
        co_ml_min = h.heart_rate * h.stroke_volume

        # Heart compute
        heart_state = h.compute(dt, svr_factor=svr_factor)

        # Neuro compute - capture what it returns
        neuro_state = self.neuro.compute(dt,
            {'MAP_mmHg': h.mean_arterial_pressure,
             'HR': h.heart_rate,
             'SVR': h.SVR},
            {'PaO2_mmHg': self.blood.arterial_PO2_mmHg,
             'PaCO2_mmHg': self.blood.arterial_PCO2_mmHg,
             'pH': self.blood.arterial_pH})

        # Extract the net_HR_add from neuro_state
        net_HR_add = neuro_state.get('net_HR_add', 0)
        chemoreceptor_drive = neuro_state.get('chemoreceptor_drive', 0)
        seizure = neuro_state.get('seizure', 0)
        pain_level = neuro_state.get('pain_level', 0)

        # Apply FactorCommands
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

        record_steps = {1, 2, 3, 4, 5, 10, 100, 500, 1000, 2000, 2485, 2486, 2487, 2488, 2489, 2490,
                        2491, 2492, 2493, 2494, 2495, 2496, 2500, 2550, 2600, 3000}
        if self._step_count in record_steps:
            self._traces.append({
                'step': self._step_count,
                't': t,
                'HR': h.heart_rate,
                'MAP_filtered': h.mean_arterial_pressure,
                'PaO2': self.blood.arterial_PO2_mmHg,
                'PaCO2': self.blood.arterial_PCO2_mmHg,
                'pH': self.blood.arterial_pH,
                'chemo_drive': chemoreceptor_drive,
                'net_HR_add': net_HR_add,
                'seizure': seizure,
                'pain_level': pain_level,
            })


vc = ChemoTraceVC(body_weight_kg=20.0)
vc.dt = DT
T_END = 60.0
n_steps = int(T_END / DT)
for i in range(n_steps):
    vc.step()
    if vc.lifecycle.is_dead():
        break

print('=' * 105)
print('NEURO CHEMORECEPTOR TRACE: What triggers the +0.1/step HR increase?')
print('=' * 105)
print(f'{"Step":>5}  {"t":>5}  {"HR":>7}  {"MAP":>7}  {"PaO2":>6}  {"PaCO2":>6}  {"pH":>6}  '
      f'{"chemo":>6}  {"net_HR":>7}  {"seizure":>7}  {"pain":>6}')
print('-' * 105)
for tr in vc._traces:
    print(f'{tr["step"]:5d}  {tr["t"]:5.1f}  {tr["HR"]:7.4f}  {tr["MAP_filtered"]:7.2f}  '
          f'{tr["PaO2"]:6.1f}  {tr["PaCO2"]:6.1f}  {tr["pH"]:6.3f}  '
          f'{tr["chemo_drive"]:6.3f}  {tr["net_HR_add"]:7.2f}  '
          f'{tr["seizure"]:7.3f}  {tr["pain_level"]:6.1f}')

print('\n' + '=' * 105)
print('KEY FINDING:')
print('=' * 105)
for i in range(1, len(vc._traces)):
    prev = vc._traces[i-1]
    curr = vc._traces[i]
    hr_delta = curr['HR'] - prev['HR']
    net_hr_add = curr['net_HR_add']
    if abs(hr_delta) > 0.01:
        print(f'Step {prev["step"]}→{curr["step"]}: HR Δ={hr_delta:.4f}, net_HR_add={net_hr_add:.2f}, '
              f'chemo_drive={curr["chemo_drive"]:.3f}, PaO2={curr["PaO2"]:.1f}, PaCO2={curr["PaCO2"]:.1f}')
print('=' * 105)