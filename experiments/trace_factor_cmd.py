"""
CRITICAL: At step 2491, baroreflex sets HR=85.000000 but final HR=85.100178.
Delta = +0.1 → something is adding to HR after baroreflex.

This +0.1 is coming from neuro's FactorCommand "heart.heart_rate" "add".

Let me trace the FactorCommand application to see what's happening.
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

# Patch apply_factor to trace heart_rate changes
_apply_factor = VirtualCreature.apply_factor

def _patched_apply_factor(self, cmd):
    if hasattr(cmd, 'target') and cmd.target == 'heart.heart_rate' and cmd.op == 'add':
        hr_before = self.heart.heart_rate
        _apply_factor(self, cmd)
        hr_after = self.heart.heart_rate
        print(f'  apply_factor({cmd.target}, {cmd.op}, {cmd.value:.4f}): HR {hr_before:.6f} → {hr_after:.6f} (Δ={hr_after-hr_before:.6f})')
    else:
        _apply_factor(self, cmd)

VirtualCreature.apply_factor = _patched_apply_factor

class FCTraceVC(VirtualCreature):
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

        h = self.heart
        print(f'\nStep {self._step_count} (t={t:.2f}s): BEFORE heart.compute HR={h.heart_rate:.6f}')

        # Heart compute
        heart_state = h.compute(dt, svr_factor=svr_factor)
        print(f'  AFTER heart.compute HR={h.heart_rate:.6f}')

        # Neuro compute
        neuro_state = self.neuro.compute(dt,
            {'MAP_mmHg': h.mean_arterial_pressure,
             'HR': h.heart_rate,
             'SVR': h.SVR},
            {'PaO2_mmHg': self.blood.arterial_PO2_mmHg,
             'PaCO2_mmHg': self.blood.arterial_PCO2_mmHg,
             'pH': self.blood.arterial_pH})

        fcs = neuro_state.get('factor_commands', [])
        if fcs:
            print(f'  Neuro FactorCommands:')
            for fc in fcs:
                print(f'    {fc}')
        else:
            print(f'  Neuro FactorCommands: (none)')

        print(f'  BEFORE apply_factor HR={h.heart_rate:.6f}')
        for cmd in fcs:
            self.apply_factor(cmd)
        print(f'  AFTER apply_factor HR={h.heart_rate:.6f}')

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
        print(f'  FINAL HR at end of step {self._step_count}: {h.heart_rate:.6f}')


vc = FCTraceVC(body_weight_kg=20.0)
vc.dt = DT
# Only run steps 2489-2495
for i in range(2495):
    vc.step()
    if vc.lifecycle.is_dead():
        break
    if i < 2488:
        # Skip output for early steps
        continue
    if i > 2495:
        break

print('\n' + '='*80)
print('ANALYSIS: At step 2491, baroreflex decreases HR but final HR increases by 0.1')
print('The +0.1 must come from a FactorCommand with op="add"')
print('='*80)