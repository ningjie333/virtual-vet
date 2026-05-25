"""Test: Removing the raw_MAP clamp (set upper bound to 1000).

Hypothesis: The 180 clamp creates artificial positive error that drives HR unbounded.
Without the clamp, raw_MAP stays at ~72.8 (below target) → error positive → still drives HR up.
But we need to verify what happens without the clamp.
"""
import subprocess, os

src_dir = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\src'

SCRIPT = r"""
import sys, os, types, numpy as np
SRC_DIR = r"SRC_DIR_PLACEHOLDER"
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    src = open(path, encoding='utf-8').read().replace('from src.', 'from ')
    # Remove the raw_MAP clamp by replacing min(180, ...) with min(1000, ...)
    src = src.replace('raw_MAP = max(30.0, min(180.0, raw_MAP))',
                      'raw_MAP = max(30.0, min(1000.0, raw_MAP))')
    return src

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
n_steps = int(T_END / DT)

print("=== PATCHED: raw_MAP clamp = 1000 (no artificial saturation at 180) ===")
vc = VirtualCreature(body_weight_kg=20.0)
vc.dt = DT
vc.heart.HR_max = 1e6

for i in range(n_steps):
    vc.step()

hr = vc.heart.heart_rate
sv = vc.heart.stroke_volume
svr = vc.heart.SVR
co = hr * sv / 1000.0
map_base = 60.0
raw_map = map_base + co * svr
map_display = vc.heart.mean_arterial_pressure
MAP_target = 100.0

print(f"MAP_display (filtered) = {map_display:.3f}")
print(f"raw_MAP (CO*SVR) = {raw_map:.3f}")
print(f"HR = {hr:.1f} bpm")
print(f"SV = {sv:.3f} mL")
print(f"SVR = {svr:.4f}")
print(f"CO = {co:.4f} L/min")
print(f"bias = {map_display - MAP_target:.3f} mmHg")
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=180)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:500])