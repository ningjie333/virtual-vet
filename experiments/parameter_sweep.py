"""
Parameter sweep: quantify bias sensitivity to three key parameters.
Sweeps baroreflex sympathetic gain, neuro SVR multiplier, and body weight.
For each combination: runs original (heart→neuro) and reversed (neuro→heart),
records MAP at t=60s, computes bias = MAP_original - 100.

Usage: python experiments/parameter_sweep.py
"""
import os, sys, types, numpy as np, json, itertools
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

DT = 0.01
T_END = 60.0
N_STEPS = int(T_END / DT)
RECORD_INTERVAL = 500  # every 0.5s

# ============================================================
# VC with REVERSED order: neuro BEFORE heart
# ============================================================
class VC_NeuroFirst(VirtualCreature):
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

        # REVERSED ORDER
        neuro_state = self.neuro.compute(dt,
            {"MAP_mmHg": self.heart.mean_arterial_pressure,
             "HR": self.heart.heart_rate,
             "SVR": self.heart.SVR},
            {"PaO2_mmHg": self.blood.arterial_PO2_mmHg,
             "PaCO2_mmHg": self.blood.arterial_PCO2_mmHg,
             "pH": self.blood.arterial_pH})

        heart_state = self.heart.compute(dt, svr_factor=svr_factor)

        co_ml_min = heart_state["cardiac_output_ml_min"]
        lung_state = self.lung.compute(dt, co_ml_min)
        kidney_state = self.kidney.compute(dt, heart_state["MAP_mmHg"], 0, co_ml_min)
        gut_state = self.gut.compute(dt, co_ml_min)
        liver_state = self.liver.compute(dt, gut_state, co_ml_min)
        endocrine_state = self.endocrine.compute(dt)
        coagulation_state = self.coagulation.compute(dt, liver_state, {})
        lymphatic_state = self.lymphatic.compute(dt, gut_state, {})
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


def run_simulation(vc_class, weight_kg, gain_svr_mult, seizure_mult, record=False):
    """Run simulation with modified gain and seizure mult."""
    vc = vc_class(body_weight_kg=weight_kg)
    vc.dt = DT
    vc._cached_inputs.clear()

    # Override SVR multiplier in neuro
    if gain_svr_mult is not None:
        vc.neuro._svr_mult_override = gain_svr_mult
    if seizure_mult is not None:
        vc.neuro._seizure_mult_override = seizure_mult

    recs = []
    for i in range(N_STEPS + 1):
        if record and i % RECORD_INTERVAL == 0:
            recs.append({'t': i*DT, 'MAP': float(vc.heart.mean_arterial_pressure)})
        vc.step()
        if vc.lifecycle.is_dead():
            break

    final_map = float(vc.heart.mean_arterial_pressure)
    if record:
        return final_map, recs
    return final_map, None


# ============================================================
# Experiment 1: Baroreflex gain sweep
# ============================================================
print('=== Experiment 1: Baroreflex SVR gain sweep ===')
print(f'{"gain":>8}  {"MAP_orig":>10}  {"MAP_rev":>10}  {"bias":>8}')
print('-' * 42)

gain_values = [0.5, 1.0, 2.0, 4.0, 8.0]
gain_results = []
for gain in gain_values:
    # SVR_increase = 1.0 + gain * sympathetic * max(0, error)
    # gain here refers to the 2.0 coefficient in heart.py line 183
    map_orig, _ = run_simulation(VirtualCreature, 20.0, gain, None)
    map_rev, _ = run_simulation(VC_NeuroFirst, 20.0, gain, None)
    bias_orig = map_orig - 100.0
    print(f'{gain:8.1f}  {map_orig:10.3f}  {map_rev:10.3f}  {bias_orig:8.3f}')
    gain_results.append({'gain': gain, 'map_orig': map_orig, 'map_rev': map_rev, 'bias': bias_orig})

# ============================================================
# Experiment 2: Seizure SVR multiplier sweep
# ============================================================
print('\n=== Experiment 2: Seizure SVR multiplier sweep ===')
print(f'{"seiz_mult":>10}  {"MAP_orig":>10}  {"MAP_rev":>10}  {"bias":>8}')
print('-' * 45)

seizure_values = [0.0, 0.1, 0.3, 0.5, 0.7]
seizure_results = []
for seiz in seizure_values:
    # seizure_effect * 0.3 controls net_SVR_mult magnitude
    # 0.0 = loop B has no SVR effect, should reduce bias
    map_orig, _ = run_simulation(VirtualCreature, 20.0, None, seiz)
    map_rev, _ = run_simulation(VC_NeuroFirst, 20.0, None, seiz)
    bias_orig = map_orig - 100.0
    print(f'{seiz:10.1f}  {map_orig:10.3f}  {map_rev:10.3f}  {bias_orig:8.3f}')
    seizure_results.append({'seizure_mult': seiz, 'map_orig': map_orig, 'map_rev': map_rev, 'bias': bias_orig})

# ============================================================
# Experiment 3: Body weight sweep
# ============================================================
print('\n=== Experiment 3: Body weight sweep ===')
print(f'{"weight_kg":>10}  {"MAP_orig":>10}  {"MAP_rev":>10}  {"bias":>8}')
print('-' * 45)

weight_values = [10.0, 20.0, 30.0, 40.0]
weight_results = []
for wt in weight_values:
    map_orig, _ = run_simulation(VirtualCreature, wt, None, None)
    map_rev, _ = run_simulation(VC_NeuroFirst, wt, None, None)
    bias_orig = map_orig - 100.0
    print(f'{wt:10.1f}  {map_orig:10.3f}  {map_rev:10.3f}  {bias_orig:8.3f}')
    weight_results.append({'weight_kg': wt, 'map_orig': map_orig, 'map_rev': map_rev, 'bias': bias_orig})

# ============================================================
# Save results
# ============================================================
out = {
    'gain_sweep': gain_results,
    'seizure_sweep': seizure_results,
    'weight_sweep': weight_results
}
out_path = os.path.join(EXPERIMENTS_DIR, 'parameter_sweep_results.json')
with open(out_path, 'w') as f:
    json.dump(out, f, indent=2)
print(f'\nResults saved to {out_path}')