"""Arm B Experiment: Reverse module order → test if bias magnitude/sign changes.

If H2 (sequential iteration amplification) is true: reversing order should flip sign or change magnitude.
If H2 is false: bias is same regardless of order.

The experiment: patch simulation.step() to reverse the module evaluation order.
Compare: Forward order (default) vs Reverse order.

dt values: 0.01, 0.05, 0.1
"""
import subprocess, os

src_dir = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\src'

SCRIPT = r"""
import sys, os, types, numpy as np
SRC_DIR = r"SRC_DIR_PLACEHOLDER"
sys.path.insert(0, SRC_DIR)

def _read_patched(path, reverse=False):
    src = open(path, encoding='utf-8').read().replace('from src.', 'from ')
    if reverse:
        # Patch the _organ_modules property to reverse order
        src = src.replace(
            '@property\n    def _organ_modules(self):',
            '_organ_modules_original = '
        )
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

print("=" * 80)
print("ARM B: REVERSE MODULE ORDER TEST")
print("=" * 80)

# The key insight from the simulation: module order can be reversed by
# modifying the _organ_modules list before step()

for dt_val in [0.01, 0.05, 0.1]:
    n_steps = int(T_END / dt_val)

    print(f"\ndt = {dt_val}:")

    # Forward order
    vc_fwd = VirtualCreature(body_weight_kg=20.0)
    vc_fwd.dt = dt_val
    # Keep HR_max=180 to stay in comparable saturation regime
    for i in range(n_steps):
        vc_fwd.step()

    hr_f = vc_fwd.heart.heart_rate
    sv_f = vc_fwd.heart.stroke_volume
    svr_f = vc_fwd.heart.SVR
    co_f = hr_f * sv_f / 1000.0
    raw_map_f = 60.0 + co_f * svr_f
    map_f = vc_fwd.heart.mean_arterial_pressure
    bias_f = map_f - 100

    print(f"  Forward:  MAP={map_f:.3f}, raw_MAP={raw_map_f:.3f}, HR={hr_f:.1f}, bias={bias_f:.3f}")

    # Reverse order - get the list and reverse it
    vc_rev = VirtualCreature(body_weight_kg=20.0)
    vc_rev.dt = dt_val

    # Access the modules list and reverse it
    if hasattr(vc_rev, '_organ_modules'):
        original_list = list(vc_rev._organ_modules)
        vc_rev._organ_modules = list(reversed(original_list))

    for i in range(n_steps):
        vc_rev.step()

    hr_r = vc_rev.heart.heart_rate
    sv_r = vc_rev.heart.stroke_volume
    svr_r = vc_rev.heart.SVR
    co_r = hr_r * sv_r / 1000.0
    raw_map_r = 60.0 + co_r * svr_r
    map_r = vc_rev.heart.mean_arterial_pressure
    bias_r = map_r - 100

    print(f"  Reverse:  MAP={map_r:.3f}, raw_MAP={raw_map_r:.3f}, HR={hr_r:.1f}, bias={bias_r:.3f}")
    print(f"  Δbias = {bias_r - bias_f:.3f} (forward - reverse)")

print()
print("=" * 80)
print("INTERPRETATION:")
print("  If |bias_forward| ≈ |bias_reverse|: H2 falsified (sequential iteration NOT the cause)")
print("  If bias flips sign or differs substantially: H2 corroborated")
print("=" * 80)
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=180)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:500])