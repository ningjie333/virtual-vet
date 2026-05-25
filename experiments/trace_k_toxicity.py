"""Trace k_toxicity and raw_MAP to understand HR stabilization at 276.44."""
import subprocess, os

src_dir = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\src'

SCRIPT = r"""
import sys, os, types, numpy as np
SRC_DIR = r"SRC_DIR_PLACEHOLDER"
sys.path.insert(0, SRC_DIR)

def _read_patched(path, remove_factor=False):
    src = open(path, encoding='utf-8').read().replace('from src.', 'from ')
    if remove_factor:
        src = src.replace('self.issue_factor_command(', '# ISSUE_FACTOR_COMMAND_REMOVED: self.issue_factor_command(')
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
    _s = _read_patched(_p, remove_factor=True)
    _m = types.ModuleType(_n)
    sys.modules[_n] = _m
    exec(compile(_s, _p, "exec"), _m.__dict__)

VirtualCreature = sys.modules["simulation"].VirtualCreature

DT = 0.01
T_END = 60.0
n_steps = int(T_END / DT)

vc = VirtualCreature(body_weight_kg=20.0)
vc.dt = DT
vc.heart.HR_max = 1e6

trace_steps = [1, 100, 500, 1000, 2000, 3000, 4000, 5000, 5500, 6000]

for i in range(n_steps):
    vc.step()
    if (i+1) in trace_steps:
        # Read internal k_toxicity_factor
        k_tox = vc.heart.hh.k_toxicity_factor
        k_plus = vc.heart.blood.potassium_mEq_L
        map_disp = vc.heart.mean_arterial_pressure

        # Read stroke_volume and compute raw_MAP formula
        sv = vc.heart.stroke_volume
        co = vc.heart.heart_rate * sv / 1000.0
        svr = vc.heart.SVR

        MAP_target = 100.0
        error = (MAP_target - map_disp) / MAP_target
        hr_delta = (vc.heart.parasympathetic * 15.0 * max(0, -error) +
                    vc.heart.sympathetic * 50.0 * max(0, error)) * DT

        print("{:5} t={:5.2f}s MAP_display={:7.3f} raw_HR={:7.2f} HR_delta={:+8.4f} k_tox={:.4f} K+={:.2f} SV={:.2f} CO={:.3f} symp={:.6f} parasymp={:.6f}".format(
            i+1, vc.current_time_s, map_disp, vc.heart.heart_rate, hr_delta,
            k_tox, k_plus, sv, co, vc.heart.sympathetic, vc.heart.parasympathetic
        ), flush=True)

print()
print("=== FINAL STATE ===")
print("MAP_display={:.3f}".format(vc.heart.mean_arterial_pressure))
print("HR={:.2f}".format(vc.heart.heart_rate))
print("k_toxicity={:.4f}".format(vc.heart.hh.k_toxicity_factor))
print("K+={:.3f}".format(vc.heart.blood.potassium_mEq_L))
print("SV={:.3f}".format(vc.heart.stroke_volume))
print("SVR={:.3f}".format(vc.heart.SVR))
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=120)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:300])