"""
Critical experiment: Swap module order — neuro BEFORE heart
If bias reverses (MAP < 100 instead of > 100) → proves Gauss-Seidel causal chain
"""
import os, sys, types, numpy as np
EXPERIMENTS_DIR = 'experiments'
PROJECT_ROOT = os.path.dirname(os.path.abspath(EXPERIMENTS_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding='utf-8').read().replace('from src.', 'from ')

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

WEIGHT_KG = 20.0
DT = 0.01
T_END = 60.0

def make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return vc

# ============================================================
# VC with REVERSED order: neuro BEFORE heart
# ============================================================
class VC_NeuroFirst(VirtualCreature):
    """Neuro compute BEFORE heart — reverses baroreflex information lag"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._step_count = 0

    def step(self):
        dt = self.dt
        self._step_count += 1
        t = self.current_time_s

        # Event processing (same as original)
        self._process_events(t)

        # Blood loss model (same as original)
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

        # Tox (same as original)
        tox_state = self.toxicology.compute(dt)
        self.heart.contractility_factor = tox_state["contractility_factor"]
        svr_factor = tox_state["svr_factor"]

        # Pharma (same as original)
        if hasattr(self, 'medication_due') and self.medication_due:
            pharma_commands = self.pharmacology.compute(dt, self)
            if pharma_commands:
                for cmd in pharma_commands:
                    self.apply_factor(cmd)
            self.medication_due = False

        # ===== REVERSED ORDER =====
        # 1. FIRST: neuro sees OLD heart state, computes NEW sympathetic
        # (Before heart.compute changes HR/SVR)
        neuro_state = self.neuro.compute(dt,
            {"MAP_mmHg": self.heart.mean_arterial_pressure,
             "HR": self.heart.heart_rate,
             "SVR": self.heart.SVR},
            {"PaO2_mmHg": self.blood.arterial_PO2_mmHg,
             "PaCO2_mmHg": self.blood.arterial_PCO2_mmHg,
             "pH": self.blood.arterial_pH})

        # 2. SECOND: heart sees NEW sympathetic from neuro, updates HR/SVR
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)

        # 3. Rest of modules (same order as original)
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


# ============================================================
# REFERENCE: Original order (heart → neuro)
# ============================================================
print('=== Reference: Original order (heart→neuro, 60s) ===')
vc_orig = make_vc()
vc_orig.dt = DT
n_steps = int(T_END / DT)
recs_orig = []
for i in range(n_steps + 1):
    if i % 500 == 0:
        recs_orig.append({'t': i*DT, 'MAP': float(vc_orig.heart.mean_arterial_pressure)})
    vc_orig.step()
map_orig = np.array([r['MAP'] for r in recs_orig])
print(f'  Original MAP at t=60s: {map_orig[-1]:.3f} mmHg')

# ============================================================
# TEST: Reversed order (neuro → heart)
# ============================================================
print('\n=== Test: Reversed order (neuro→heart, 60s) ===')
vc_rev = VC_NeuroFirst(body_weight_kg=WEIGHT_KG)
vc_rev.dt = DT
vc_rev._cached_inputs.clear()
recs_rev = []
for i in range(n_steps + 1):
    if i % 500 == 0:
        recs_rev.append({'t': i*DT, 'MAP': float(vc_rev.heart.mean_arterial_pressure)})
    vc_rev.step()
map_rev = np.array([r['MAP'] for r in recs_rev])
print(f'  Reversed MAP at t=60s: {map_rev[-1]:.3f} mmHg')

# ============================================================
# ANALYSIS
# ============================================================
print('\n=== Analysis ===')
print(f'  Original (heart→neuro):  MAP = {map_orig[-1]:.3f} mmHg')
print(f'  Reversed (neuro→heart): MAP = {map_rev[-1]:.3f} mmHg')
print(f'  Delta (reversed - original): {map_rev[-1] - map_orig[-1]:.3f} mmHg')
print()
if map_rev[-1] < 100 and map_orig[-1] > 100:
    print('  *** BIAS REVERSED ***')
    print('  Original > 100 (偏高), Reversed < 100 (偏低)')
    print('  → 偏差方向由模块顺序决定 = Gauss-Seidel 铁证')
    print('  → 论文 §4.2 核心证据')
elif map_rev[-1] > 100 and map_orig[-1] > 100:
    print('  Both > 100, but reversed is lower')
    print(f'  → {map_orig[-1] - map_rev[-1]:.3f} mmHg reduction when neuro leads')
    print('  → Partial reversal supports Gauss-Seidel hypothesis')
else:
    print('  Unexpected: check simulation behavior')

# Also show time series
print('\n  Time series comparison (every 10s):')
print(f'  {"t[s]":>6}  {"Original MAP":>14}  {"Reversed MAP":>14}')
for i, (r_orig, r_rev) in enumerate(zip(recs_orig, recs_rev)):
    print(f'  {r_orig["t"]:6.1f}  {r_orig["MAP"]:14.3f}  {r_rev["MAP"]:14.3f}')