"""
Hemorrhage 400mL: Subprocess-isolated ordering comparison.
Each ordering runs in independent Python process — no state contamination.

This is the gold-standard test for the hemorrhage scenario.
"""
import subprocess, os, json, sys

pwd = os.getcwd()
src_dir = os.path.join(pwd, 'src')
print(f'Working dir: {pwd}')
print(f'SRC_DIR: {src_dir}')
print(f'Exists: {os.path.exists(src_dir)}')

# Use __SRC_DIR__ placeholder to avoid .format() curly brace conflicts
HEART_SCRIPT = r"""
import sys, os, types, numpy as np
SRC_DIR = "__SRC_DIR__"
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding="utf-8").read().replace("from src.", "from ")

sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(SRC_DIR, "parameters.py")),
             os.path.join(SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _n in ["blood", "fluid", "cardiac_electrophysiology", "noble_purkinje",
    "respiratory_rhythm", "heart", "lung", "kidney", "gut", "liver",
    "endocrine", "neuro", "immune", "coagulation", "lymphatic",
    "lifecycle", "toxicology", "organ_health", "pharmacology", "simulation"]:
    _p = os.path.join(SRC_DIR, _n + ".py")
    _s = _read_patched(_p)
    _m = types.ModuleType(_n)
    sys.modules[_n] = _m
    exec(compile(_s, _p, "exec"), _m.__dict__)

VirtualCreature = sys.modules["simulation"].VirtualCreature

DT = 0.01
T_END = 120.0
SAVE_INT = 200

vc = VirtualCreature(body_weight_kg=20.0)
vc.dt = DT
vc._blood_loss_config = {'t_onset': 5.0, 'volume_ml': 400.0, 'k': 35.0, 'width': 6.0}

records = []
for i in range(int(T_END / DT) + 1):
    if i % SAVE_INT == 0:
        records.append({'t': i*DT,
                        'MAP': float(vc.heart.mean_arterial_pressure),
                        'HR': float(vc.heart.heart_rate),
                        'SVR': float(vc.heart.SVR),
                        'BV': float(vc.heart.circulating_volume_ml)})
    vc.step()

import json
print("DATA:" + json.dumps(records))
"""

NEURO_SCRIPT = r"""
import sys, os, types, numpy as np
SRC_DIR = "__SRC_DIR__"
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding="utf-8").read().replace("from src.", "from ")

sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(SRC_DIR, "parameters.py")),
             os.path.join(SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _n in ["blood", "fluid", "cardiac_electrophysiology", "noble_purkinje",
    "respiratory_rhythm", "heart", "lung", "kidney", "gut", "liver",
    "endocrine", "neuro", "immune", "coagulation", "lymphatic",
    "lifecycle", "toxicology", "organ_health", "pharmacology", "simulation"]:
    _p = os.path.join(SRC_DIR, _n + ".py")
    _s = _read_patched(_p)
    _m = types.ModuleType(_n)
    sys.modules[_n] = _m
    exec(compile(_s, _p, "exec"), _m.__dict__)

VirtualCreature = sys.modules["simulation"].VirtualCreature

DT = 0.01
T_END = 120.0
SAVE_INT = 200

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
        if hasattr(self, "medication_due") and self.medication_due:
            pharma_commands = self.pharmacology.compute(dt, self)
            if pharma_commands:
                for cmd in pharma_commands:
                    self.apply_factor(cmd)
            self.medication_due = False
        neuro_state = self.neuro.compute(dt,
            {"MAP_mmHg": self.heart.mean_arterial_pressure,
             "HR": self.heart.heart_rate,
             "SVR": self.heart.SVR},
            {"PaO2_mmHg": self.blood.arterial_PO2_mmHg,
             "PaCO2_mmHg": self.blood.arterial_PCO2_mmHg,
             "pH": self.blood.arterial_pH})
        for cmd in neuro_state.get("factor_commands", []):
            self.apply_factor(cmd)
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

vc = VC_NeuroFirst(body_weight_kg=20.0)
vc.dt = DT
vc._blood_loss_config = {'t_onset': 5.0, 'volume_ml': 400.0, 'k': 35.0, 'width': 6.0}

records = []
for i in range(int(T_END / DT) + 1):
    if i % SAVE_INT == 0:
        records.append({'t': i*DT,
                        'MAP': float(vc.heart.mean_arterial_pressure),
                        'HR': float(vc.heart.heart_rate),
                        'SVR': float(vc.heart.SVR),
                        'BV': float(vc.heart.circulating_volume_ml)})
    vc.step()

import json
print("DATA:" + json.dumps(records))
"""

# Use .replace() to inject src_dir (avoids .format() curly brace conflicts)
# Use forward slashes to avoid Windows backslash escape issues in subprocess
src_dir_posix = src_dir.replace('\\', '/')
heart_script = HEART_SCRIPT.replace('__SRC_DIR__', src_dir_posix)
neuro_script = NEURO_SCRIPT.replace('__SRC_DIR__', src_dir_posix)

print('\n=== Hemorrhage Subprocess Isolation Test ===\n')

# Run heart→neuro
print('Running heart→neuro (original order)...')
sys.stdout.flush()
r1 = subprocess.run([sys.executable, '-c', heart_script],
                    capture_output=True, text=True, timeout=300)
if r1.returncode != 0:
    print(f'  ERROR (returncode={r1.returncode})')
    if r1.stderr: print('  stderr:', r1.stderr[:1000])
    sys.exit(1)
raw1 = r1.stdout
data_start1 = raw1.find('DATA:')
if data_start1 < 0:
    print('  ERROR: no DATA marker. stdout:', raw1[:500])
    sys.exit(1)
records1 = json.loads(raw1[data_start1 + 5:])
print(f'  Done. Final MAP = {records1[-1]["MAP"]:.3f} mmHg')

# Run neuro→heart
print('Running neuro→heart (reversed order)...')
sys.stdout.flush()
r2 = subprocess.run([sys.executable, '-c', neuro_script],
                    capture_output=True, text=True, timeout=300)
if r2.returncode != 0:
    print(f'  ERROR (returncode={r2.returncode})')
    if r2.stderr: print('  stderr:', r2.stderr[:1000])
    sys.exit(1)
raw2 = r2.stdout
data_start2 = raw2.find('DATA:')
if data_start2 < 0:
    print('  ERROR: no DATA marker. stdout:', raw2[:500])
    sys.exit(1)
records2 = json.loads(raw2[data_start2 + 5:])
print(f'  Done. Final MAP = {records2[-1]["MAP"]:.3f} mmHg')

# Compare
print(f'\n{"t[s]":>6} {"Orig MAP":>9} {"Rev MAP":>9} {"Δ MAP":>9} '
      f'{"Orig HR":>8} {"Rev HR":>8} {"Orig BV":>9} {"Rev BV":>9}')
max_delta = 0.0
max_delta_t = 0
for r1p, r2p in zip(records1, records2):
    delta = r2p['MAP'] - r1p['MAP']
    if abs(delta) > abs(max_delta):
        max_delta = delta
        max_delta_t = r1p['t']
    print(f'{r1p["t"]:6.0f} {r1p["MAP"]:9.3f} {r2p["MAP"]:9.3f} {delta:+9.3f} '
          f'{r1p["HR"]:8.2f} {r2p["HR"]:8.2f} {r1p["BV"]:9.1f} {r2p["BV"]:9.1f}')

print(f'\n=== Summary ===')
print(f'  heart→neuro final MAP: {records1[-1]["MAP"]:.3f} mmHg')
print(f'  neuro→heart final MAP: {records2[-1]["MAP"]:.3f} mmHg')
print(f'  Δ final: {records2[-1]["MAP"] - records1[-1]["MAP"]:+.3f} mmHg')
print(f'  Max |Δ|: {max_delta:+.3f} mmHg at t={max_delta_t:.0f}s')

# Save data
out = {
    'heart_to_neuro': records1,
    'neuro_to_heart': records2,
    'max_delta_mmHg': round(max_delta, 3),
    'max_delta_t_s': max_delta_t,
    'final_delta_mmHg': round(records2[-1]['MAP'] - records1[-1]['MAP'], 3),
}
out_path = os.path.join(os.path.dirname(__file__), 'hemorrhage_subprocess_data.json')
with open(out_path, 'w') as f:
    json.dump(out, f, indent=2)
print(f'\nData saved to: {out_path}')

if abs(max_delta) > 2.0:
    print('\n▲ 出血场景下两种顺序存在真实差异（>2 mmHg）')
    print('  → 顺序敏感性是场景依赖的：基线饱和掩盖了差异，出血瞬态暴露了差异')
elif abs(max_delta) < 0.5:
    print('\n✓ 出血场景下两种顺序无显著差异')
    print('  → 加上之前的基线结果，顺序无关性是普适的')
else:
    print(f'\n 出血场景下差异边界 ({abs(max_delta):.1f} mmHg)，需进一步确认')
