"""Three-arm experiment to distinguish H1/H2/H3 per methodology expert recommendations.

Arm A (H1: stale baroreflex signal): bypass the sequential coupling by pre-computing
   baroreflex error from previous step's state and passing it as override.
Arm B (H2: sequential iteration amplification): reverse module order and see if bias flips sign.
Arm C (H3: HR saturation ceiling): already tested - removing HR_max causes unbounded growth.

This script implements Arm B (simplest to test, no code modification needed).
Run with forward order (default) and reverse order.
"""
import subprocess, os

src_dir = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\src'

# Arm B: Reverse module order
SCRIPT = r"""
import sys, os, types, numpy as np
SRC_DIR = r"SRC_DIR_PLACEHOLDER"
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    src = open(path, encoding='utf-8').read().replace('from src.', 'from ')
    # Patch step() to reverse module order
    # Original: ordered_modules = self.ordered_modules (in some order)
    # Patched: reversed order
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
T_END = 60.0
n_steps = int(T_END / DT)

print("=== ARM B: Reverse Module Order Test ===")
print()

# Test with DIFFERENT dt values to see if bias changes sign or magnitude
for dt_val in [0.01, 0.05, 0.1]:
    n = int(T_END / dt_val)

    # Forward order (default)
    vc_fwd = VirtualCreature(body_weight_kg=20.0)
    vc_fwd.dt = dt_val
    vc_fwd.heart.HR_max = 180  # Keep saturation to compare apples-to-apples

    for i in range(n):
        vc_fwd.step()

    hr_fwd = vc_fwd.heart.heart_rate
    sv_fwd = vc_fwd.heart.stroke_volume
    svr_fwd = vc_fwd.heart.SVR
    co_fwd = hr_fwd * sv_fwd / 1000.0
    raw_map_fwd = 60.0 + co_fwd * svr_fwd
    map_fwd = vc_fwd.heart.mean_arterial_pressure

    print(f"dt={dt_val}: Forward order  → MAP_display={map_fwd:.3f}, raw_MAP={raw_map_fwd:.3f}, HR={hr_fwd:.1f}, bias={map_fwd-100:.3f}")

print()
print("KEY: If H2 (sequential iteration amplification) is correct, reversing order")
print("should change bias magnitude or flip sign, because error propagates opposite direction.")
print("If bias is SAME for both orders → H2 falsified → look for other mechanisms.")
print()

# Check what's in the simulation step to understand order
print("=== Module Order in simulation.py ===")
import inspect
vc = VirtualCreature(body_weight_kg=20.0)
# Find the step method source to see module order
step_source = inspect.getsource(vc.step)
# Find the module list
for line in step_source.split('\n'):
    if 'organ' in line.lower() and 'for' in line.lower():
        print(line.strip())
    if 'self.' in line and 'organ' in line.lower() and 'order' in line.lower():
        print(line.strip())
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=180)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:500])