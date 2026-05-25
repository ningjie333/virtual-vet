"""Run Radau unified solver as reference for MAP at steady-state.

Compare: Sequential Euler dt=0.01 → MAP=144.742 vs Radau → MAP=?
"""
import subprocess, os

src_dir = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\src'

SCRIPT = r"""
import sys, os, types, numpy as np
SRC_DIR = r"SRC_DIR_PLACEHOLDER"
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding='utf-8').read().replace('from src.', 'from ')

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

print("=== Radau Unified Solver Reference (T=60s) ===")
vc = VirtualCreature(body_weight_kg=20.0)
sol = vc.run_unified_ivp(t_end=60.0, dt_save=1.0)
vc.load_state_vector(sol.y[:, -1])

map_radau = vc.heart.mean_arterial_pressure
hr_radau = vc.heart.heart_rate
sv_radau = vc.heart.stroke_volume
svr_radau = vc.heart.SVR
co_radau = hr_radau * sv_radau / 1000.0
raw_map_radau = 60.0 + co_radau * svr_radau

print(f"Radau T=60s: MAP_display={map_radau:.3f}, raw_MAP={raw_map_radau:.3f}, HR={hr_radau:.1f}, bias={map_radau-100:.3f}")

print()
print("=== Sequential Euler dt=0.01, T=60s (for comparison) ===")
vc2 = VirtualCreature(body_weight_kg=20.0)
vc2.dt = 0.01
n_steps = int(60.0 / 0.01)
for i in range(n_steps):
    vc2.step()
map_seq = vc2.heart.mean_arterial_pressure
hr_seq = vc2.heart.heart_rate
print(f"Sequential Euler: MAP_display={map_seq:.3f}, HR={hr_seq:.1f}, bias={map_seq-100:.3f}")

print()
print("=== Radau T=120s ===")
vc3 = VirtualCreature(body_weight_kg=20.0)
sol3 = vc3.run_unified_ivp(t_end=120.0, dt_save=1.0)
vc3.load_state_vector(sol3.y[:, -1])
map_radau2 = vc3.heart.mean_arterial_pressure
hr_radau2 = vc3.heart.heart_rate
svr_radau2 = vc3.heart.SVR
co_radau2 = hr_radau2 * vc3.heart.stroke_volume / 1000.0
raw_map_radau2 = 60.0 + co_radau2 * svr_radau2
print(f"Radau T=120s: MAP_display={map_radau2:.3f}, raw_MAP={raw_map_radau2:.3f}, HR={hr_radau2:.1f}, bias={map_radau2-100:.3f}")

print()
print("KEY: Is Radau MAP close to 100 (ground truth) or close to 144.7 (Euler)?")
print(f"  Radau T=120: {map_radau2:.3f} (should be ~100 if baseline is correct)")
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=300)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:500])