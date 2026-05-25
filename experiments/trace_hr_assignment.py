"""
CRITICAL: Use descriptor protocol to track EVERY assignment to heart.heart_rate

If heart_rate increases by 0.1 at step 2491, something must be assigning it.
Let's catch every assignment with a trace.
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

# Replace HeartModule with instrumented version
_heart_mod = sys.modules['heart']

class InstrumentedHeartModule(_heart_mod.HeartModule):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._hr_assignments = []
        self._hr_tracking_enabled = True

    def __setattr__(self, name, value):
        if name == 'heart_rate' and hasattr(self, '_hr_tracking_enabled') and self._hr_tracking_enabled:
            # Capture stack trace
            import traceback
            stack = ''.join(traceback.format_stack()[-5:-1])
            self._hr_assignments.append({
                'value': value,
                'stack': stack
            })
        super().__setattr__(name, value)

# Monkey-patch the module
setattr(_heart_mod, 'HeartModule', InstrumentedHeartModule)

# Also need to make sure VirtualCreature uses our patched heart
# We need to re-import simulation after heart is patched
del sys.modules['simulation']
del sys.modules['heart']
sys.modules['heart'] = _heart_mod

# Re-load simulation with patched heart
_src = _read_patched(os.path.join(SRC_DIR, 'simulation.py'))
_mod = types.ModuleType('simulation')
sys.modules['simulation'] = _mod
exec(compile(_src, os.path.join(SRC_DIR, 'simulation.py'), 'exec'), _mod.__dict__)
VirtualCreature = sys.modules['simulation'].VirtualCreature

DT = 0.01

class TraceVC(VirtualCreature):
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
        # Clear HR assignments from previous step
        h._hr_assignments.clear()

        # Heart compute
        heart_state = h.compute(dt, svr_factor=svr_factor)

        # Capture HR assignments this step
        hr_assignments = list(h._hr_assignments)
        h._hr_assignments.clear()

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

        record_steps = {1, 2, 3, 4, 5, 10, 100, 500, 1000, 2000, 2489, 2490, 2491, 2492, 2493, 2494, 2495, 2496, 2497, 2498, 2499, 2500, 2550, 2600, 3000}
        if self._step_count in record_steps:
            self._traces.append({
                'step': self._step_count,
                't': t,
                'HR': h.heart_rate,
                'hr_assignments': hr_assignments,
            })


vc = TraceVC(body_weight_kg=20.0)
vc.dt = DT
T_END = 60.0
n_steps = int(T_END / DT)
for i in range(n_steps):
    vc.step()
    if vc.lifecycle.is_dead():
        break

print('=' * 90)
print('HEART_RATE ASSIGNMENT TRACE: Every assignment to heart.heart_rate')
print('=' * 90)
for tr in vc._traces:
    print(f'\nStep {tr["step"]} (t={tr["t"]:.2f}s): HR={tr["HR"]:.6f}')
    if tr['hr_assignments']:
        for a in tr['hr_assignments']:
            print(f'  → Set to {a["value"]:.6f}')
            # Print abbreviated stack
            for line in a['stack'].split('\n')[1:4]:
                if line.strip():
                    print(f'    {line.strip()[:80]}')
    else:
        print('  (no assignments recorded)')
print('=' * 90)