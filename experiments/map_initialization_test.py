"""Definitive experiment: MAP initialization vs steady-state bias.

Two hypotheses from the background agents:
H1: MAP initialization causes the bias (starts at 100, raw_MAP=62 → error=+0.376 → HR climbs)
H2: Sequential coupling creates persistent error that is NOT from initialization

Test: Run two interventions:
1. Initialize mean_arterial_pressure to 62 (close to raw_MAP at t=0)
2. Initialize mean_arterial_pressure to 100 (default)

If bias disappears (MAP→100) in case 1 but persists in case 2 → H1 confirmed
If bias persists in both → H2 confirmed, initialization is not the primary cause

Also test with dt=0.1 and dt=0.01 to see dt-dependence.
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

DT = 0.01
T_END = 120.0
n_steps = int(T_END / DT)

print("=" * 80)
print("MAP INITIALIZATION EXPERIMENT")
print("=" * 80)

for init_map, label in [(100.0, "DEFAULT (100)"), (62.0, "RAW_MAP (62)")]:
    print(f"\n=== Initialization: {label} ===")
    vc = VirtualCreature(body_weight_kg=20.0)
    vc.dt = DT
    vc.heart.HR_max = 1e6

    # Override initialization
    vc.heart.mean_arterial_pressure = init_map

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
    error = (MAP_target - raw_map) / MAP_target

    print(f"  MAP_display (filtered) = {map_display:.3f}")
    print(f"  raw_MAP (CO*SVR) = {raw_map:.3f}")
    print(f"  error = {error:.6f}")
    print(f"  HR = {hr:.1f} bpm")
    print(f"  SV = {sv:.3f} mL")
    print(f"  SVR = {svr:.4f}")
    print(f"  CO = {co:.4f} L/min")
    print(f"  bias = {map_display - MAP_target:.3f} mmHg")

print()
print("=" * 80)
print("DT=0.1 TEST (larger step, less iteration per unit time)")
print("=" * 80)

for init_map, label in [(100.0, "DEFAULT (100)"), (62.0, "RAW_MAP (62)")]:
    print(f"\n=== dt=0.1, Initialization: {label} ===")
    vc = VirtualCreature(body_weight_kg=20.0)
    vc.dt = 0.1
    vc.heart.HR_max = 1e6

    # Override initialization
    vc.heart.mean_arterial_pressure = init_map

    n_steps_dt01 = int(T_END / 0.1)
    for i in range(n_steps_dt01):
        vc.step()

    hr = vc.heart.heart_rate
    sv = vc.heart.stroke_volume
    svr = vc.heart.SVR
    co = hr * sv / 1000.0
    map_base = 60.0
    raw_map = map_base + co * svr
    map_display = vc.heart.mean_arterial_pressure

    print(f"  MAP_display (filtered) = {map_display:.3f}")
    print(f"  raw_MAP (CO*SVR) = {raw_map:.3f}")
    print(f"  HR = {hr:.1f} bpm")
    print(f"  bias = {map_display - 100:.3f} mmHg")

print()
print("KEY ANALYSIS:")
print("  If MAP_init=100 and MAP_init=62 give SAME final MAP → initialization NOT the cause")
print("  If MAP_init=62 gives lower final MAP → initialization PARTIALLY responsible")
print("  If bias persists regardless → sequential coupling or structural bias confirmed")
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=180)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:500])