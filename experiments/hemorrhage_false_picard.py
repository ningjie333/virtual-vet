"""
Hemorrhage False Picard: Does k>1 behave differently under blood loss?
If k=4 differs from k=1 during hemorrhage → scenario-dependent pseudo-convergence
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

class VC_HemorrhageFalsePicard(VirtualCreature):
    """Hemorrhage model with configurable k forward passes"""
    def __init__(self, k=1, **kwargs):
        super().__init__(**kwargs)
        self._step_count = 0
        self._k = k
        # Configure 400mL hemorrhage at t=5s
        self._blood_loss_config = {
            "t_onset": 5.0,
            "k": 35.0,
            "width": 6.0,
            "total_ml": 400.0,
            "duration": 300.0,
        }

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

        for _ in range(self._k):
            # heart→neuro ordering
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


DT = 0.01
T_END = 60.0
N_STEPS = int(T_END / DT)
WEIGHT_KG = 20.0

print('=' * 75)
print('HEMORRHAGE FALSE PICARD EXPERIMENT')
print('Does k>1 behave differently under 400mL blood loss at t=5s?')
print('=' * 75)

results = {}
for k in [1, 2, 4]:
    vc = VC_HemorrhageFalsePicard(body_weight_kg=WEIGHT_KG, k=k)
    vc.dt = DT
    vc._cached_inputs.clear()

    recs = []
    for i in range(N_STEPS + 1):
        if i % 500 == 0:  # every 5s
            recs.append({
                't': i * DT,
                'MAP': float(vc.heart.mean_arterial_pressure),
                'HR': float(vc.heart.heart_rate),
                'SVR': float(vc.heart.SVR),
                'BV': float(vc.heart.circulating_volume_ml),
            })
        vc.step()
        if vc.lifecycle.is_dead():
            break

    results[k] = recs

    print(f'\nk={k}:')
    print(f'  {"t":>5}  {"MAP":>8}  {"HR":>7}  {"SVR":>8}  {"BV":>8}')
    for r in recs:
        print(f'  {r["t"]:5.1f}  {r["MAP"]:8.2f}  {r["HR"]:7.2f}  '
              f'{r["SVR"]:8.4f}  {r["BV"]:8.1f}')

print('\n' + '=' * 75)
print('COMPARISON: k=1 vs k=4 at key timepoints')
print('=' * 75)
print(f'{"t":>5}  {"k=1 MAP":>10}  {"k=4 MAP":>10}  {"ΔMAP":>8}  {"k=1 HR":>8}  {"k=4 HR":>8}')

for i in range(len(results[1])):
    t = results[1][i]['t']
    m1 = results[1][i]['MAP']
    m4 = results[4][i]['MAP']
    h1 = results[1][i]['HR']
    h4 = results[4][i]['HR']
    delta = m4 - m1
    print(f'{t:5.1f}  {m1:10.2f}  {m4:10.2f}  {delta:8.3f}  {h1:8.2f}  {h4:8.2f}')

print('\n' + '=' * 75)
print('CONCLUSION:')
k1_recs = results[1]
k4_recs = results[4]
max_delta = max(abs(k4_recs[i]['MAP'] - k1_recs[i]['MAP']) for i in range(len(k1_recs)))
print(f'  Max |MAP(k=4) - MAP(k=1)| across all timepoints: {max_delta:.3f} mmHg')
if max_delta < 0.5:
    print('  → Consistent pseudo-convergence across scenarios')
    print('  → k=1 already saturates HR; k>1 does not change outcome')
else:
    print('  → k>1 DOES change outcome under hemorrhage')
    print('  → Scenario-dependent behavior — further analysis needed')
print('=' * 75)