"""
False Picard Experiment: Does k>1 forward passes accumulate or reduce error?

Hypothesis: k>1 passes without convergence criterion accumulate bias, not reduce it.
"""
import os, sys, types, numpy as np

EXPERIMENTS_DIR = 'experiments'
PROJECT_ROOT = os.path.dirname(os.path.abspath(EXPERIMENTS_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding='utf-8').read().replace('from src.', 'from ')

for _name in ['parameters', 'blood', 'fluid', 'cardiac_electrophysiology', 'noble_purkinje',
    'respiratory_rhythm', 'heart', 'lung', 'kidney', 'gut', 'liver',
    'endocrine', 'neuro', 'immune', 'coagulation', 'lymphatic',
    'lifecycle', 'toxicology', 'organ_health', 'pharmacology', 'simulation']:
    _path = os.path.join(SRC_DIR, f'{_name}.py')
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, 'exec'), _mod.__dict__)

VirtualCreature = sys.modules['simulation'].VirtualCreature

# ============================================================
# VC with configurable k forward passes per timestep
# ============================================================
class VC_FalsePicard(VirtualCreature):
    """Repeats forward chain k times per timestep WITHOUT convergence criterion"""
    def __init__(self, k=1, **kwargs):
        super().__init__(**kwargs)
        self._step_count = 0
        self._k = k

    def step(self):
        dt = self.dt
        self._step_count += 1
        t = self.current_time_s

        self._process_events(t)

        if self._blood_loss_config is not None:
            cfg = self._blood_loss_config
            t_rel = t - cfg["t_onset"]
            if t_rel >= 0:
                sigmoid_on = 1.0 / (1.0 + np.exp(-t_rel / cfg["width"]))
                t_fall = t_rel - 3 * cfg["width"]
                sigmoid_off = 1.0 / (1.0 + np.exp(-t_fall / cfg["width"]))
                rate = cfg["k"] * sigmoid_on * (1.0 - sigmoid_off)
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
        self.heart.contractility_factor = tox_state["contractility_factor"]
        svr_factor = tox_state["svr_factor"]

        if hasattr(self, 'medication_due') and self.medication_due:
            pharma_commands = self.pharmacology.compute(dt, self)
            if pharma_commands:
                for cmd in pharma_commands:
                    self.apply_factor(cmd)
            self.medication_due = False

        # ================================================
        # FALSE PICARD: repeat k times WITHOUT convergence check
        # ================================================
        for _ in range(self._k):
            # heart→neuro ordering (drained split analog)
            heart_state = self.heart.compute(dt, svr_factor=svr_factor)
            co_ml_min = heart_state["cardiac_output_ml_min"]

            neuro_state = self.neuro.compute(dt,
                {"MAP_mmHg": self.heart.mean_arterial_pressure,
                 "HR": self.heart.heart_rate,
                 "SVR": self.heart.SVR},
                {"PaO2_mmHg": self.blood.arterial_PO2_mmHg,
                 "PaCO2_mmHg": self.blood.arterial_PCO2_mmHg,
                 "pH": self.blood.arterial_pH})
            for cmd in neuro_state.get('factor_commands', []):
                self.apply_factor(cmd)

            lung_state = self.lung.compute(dt, co_ml_min)
            kidney_state = self.kidney.compute(dt, heart_state["MAP_mmHg"], 0, co_ml_min)
            gut_state = self.gut.compute(dt, co_ml_min)
            liver_state = self.liver.compute(dt, gut_state, co_ml_min)
            endocrine_state = self.endocrine.compute(dt)
            coagulation_state = self.coagulation.compute(dt, liver_state, {})
            for cmd in coagulation_state.get('factor_commands', []):
                self.apply_factor(cmd)
            lymphatic_state = self.lymphatic.compute(dt, gut_state, {})
            for cmd in lymphatic_state.get('factor_commands', []):
                self.apply_factor(cmd)
            immune_state = self.immune.compute(dt, endocrine_state)

            if self.disease:
                engine_state = {"MAP_mmHg": heart_state["MAP_mmHg"],
                               "HR": heart_state["heart_rate_bpm"],
                               "CO_L_per_min": co_ml_min / 1000.0,
                               "blood_volume_mL": self.heart.circulating_volume_ml}
                commands = self.disease.compute(dt, engine_state)
                if commands:
                    for cmd in commands:
                        self.apply_factor(cmd)

        fluid_state = self.fluid.compute(dt)
        self.current_time_s += dt


# ============================================================
# Run experiment
# ============================================================
DT = 0.01
T_END = 60.0
N_STEPS = int(T_END / DT)
WEIGHT_KG = 20.0

print('=' * 70)
print('FALSE PICARD EXPERIMENT')
print('Does k>1 forward passes accumulate or reduce bias?')
print('=' * 70)
print(f'{"k":>4}  {"MAP@60s":>12}  {"HR@60s":>8}  {"SVR@60s":>10}  {"interpretation"}')
print('-' * 70)

results = []
for k in [1, 2, 4, 8, 16]:
    vc = VC_FalsePicard(body_weight_kg=WEIGHT_KG, k=k)
    vc.dt = DT
    vc._cached_inputs.clear()

    for i in range(N_STEPS + 1):
        vc.step()
        if vc.lifecycle.is_dead():
            break

    results.append({
        'k': k,
        'MAP': float(vc.heart.mean_arterial_pressure),
        'HR': float(vc.heart.heart_rate),
        'SVR': float(vc.heart.SVR),
    })

    bias = results[-1]['MAP'] - 100.0
    if k == 1:
        baseline_MAP = results[-1]['MAP']
        print(f'{k:4d}  {results[-1]["MAP"]:12.3f}  {results[-1]["HR"]:8.2f}  '
              f'{results[-1]["SVR"]:10.4f}  baseline (k=1)')
    else:
        delta = results[-1]['MAP'] - baseline_MAP
        if delta > 0.5:
            interp = f'ERROR ACCUMULATES +{delta:.1f} mmHg'
        elif delta < -0.5:
            interp = f'error reduces -{delta:.1f} mmHg'
        else:
            interp = f'no significant change {delta:+.1f} mmHg'
        print(f'{k:4d}  {results[-1]["MAP"]:12.3f}  {results[-1]["HR"]:8.2f}  '
              f'{results[-1]["SVR"]:10.4f}  {interp}')

print('=' * 70)
print('\nCONCLUSION:')
k1_MAP = results[0]['MAP']
k16_MAP = results[4]['MAP']
if k16_MAP > k1_MAP + 1.0:
    print(f'  ✅ CONFIRMED: Error accumulates with k>1')
    print(f'     k=1: {k1_MAP:.3f} mmHg → k=16: {k16_MAP:.3f} mmHg')
    print(f'     → False Picard is NOT equivalent to true Gauss-Seidel iteration')
    print(f'     → Multiple passes without convergence criterion propagates bias')
elif k16_MAP < k1_MAP - 1.0:
    print(f'  ⚠️ Error reduces with k>1 — needs further analysis')
    print(f'     k=1: {k1_MAP:.3f} mmHg → k=16: {k16_MAP:.3f} mmHg')
else:
    print(f'  ⚠️ No significant change — error may be saturated')
    print(f'     k=1: {k1_MAP:.3f} mmHg → k=16: {k16_MAP:.3f} mmHg')
print('=' * 70)