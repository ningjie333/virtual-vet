"""Test: Removing the raw_MAP clamp (max(30, min(180, raw_MAP))) should eliminate the bias.

The hypothesis: The clamp at 180 creates artificial positive error signal.
Without the clamp, raw_MAP = 72.81 → MAP_display would track raw_MAP ≈ 72.81
→ error = (100-72.81)/100 = +0.27 → still drives HR up...

WAIT. That doesn't help either. If we remove the clamp:
- raw_MAP = 72.81 (below target)
- error = +0.27 → baroreflex STILL drives HR up

The REAL question is: can the system ever achieve MAP=100 with current parameters?

At steady-state: MAP = 60 + (HR*SV/1000)*1.41
For MAP=100: (HR*SV) = 100-60 / 1.41 * 1000 = 40/1.41 * 1000 = 28369 mL
With HR=85: SV = 334 mL ← impossible
With SV=20: HR = 1418 bpm ← impossible
With SV=10: HR = 2837 bpm ← impossible

The setpoint IS UNACHIEVABLE with current SVR and SV.

This means the bias is a FUNDAMENTAL MODEL BUG, not a numerical artifact!

Let's verify: if we set MAP_target=72 (the achievable steady-state MAP), bias should be ~0.
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

# Test 1: Patch out the raw_MAP clamp (set upper bound to 1000)
SCRIPT_PATCHED = r"""
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
error = (MAP_target - raw_map) / MAP_target

print(f"MAP_display (filtered) = {map_display:.3f}")
print(f"raw_MAP (CO*SVR) = {raw_map:.3f}")
print(f"error = {error:.6f}")
print(f"HR = {hr:.1f} bpm")
print(f"SV = {sv:.3f} mL")
print(f"SVR = {svr:.4f}")
print(f"CO = {co:.4f} L/min")
print(f"bias = {map_display - MAP_target:.3f} mmHg")
"""

script = SCRIPT_PATCHED.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=180)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:500])

print()

# Test 2: What MAP_target would make bias=0?
# At steady-state: raw_MAP = 60 + (HR*SV/1000)*1.41
# The system converges to HR=180, SV=20, SVR=1.41 → raw_MAP=144.6
# If MAP_target=144.6, bias should be 0

SCRIPT_TARGET_TEST = r"""
import sys, os, types, numpy as np
SRC_DIR = r"SRC_DIR_PLACEHOLDER"
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    src = open(path, encoding='utf-8').read().replace('from src.', 'from ')
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

print("=== INVESTIGATE: What steady-state raw_MAP does the system converge to? ===")
print()

for target in [100, 120, 140, 144.7, 150, 160]:
    vc = VirtualCreature(body_weight_kg=20.0)
    vc.dt = DT
    vc.heart.HR_max = 1e6
    vc.heart.MAP_target = target  # Try different targets

    for i in range(n_steps):
        vc.step()

    hr = vc.heart.heart_rate
    sv = vc.heart.stroke_volume
    svr = vc.heart.SVR
    co = hr * sv / 1000.0
    map_base = 60.0
    raw_map = map_base + co * svr
    map_display = vc.heart.mean_arterial_pressure

    print(f"MAP_target={target:6.1f} → raw_MAP={raw_map:.3f}, MAP_display={map_display:.3f}, HR={hr:.1f}")
"""

script2 = SCRIPT_TARGET_TEST.replace('SRC_DIR_PLACEHOLDER', src_dir)
r2 = subprocess.run(['python', '-c', script2], capture_output=True, text=True, timeout=300)
print(r2.stdout.strip())
if r2.stderr and 'WARNING' not in r2.stderr and 'Deprecation' not in r2.stderr:
    print('ERR:', r2.stderr[:500])