"""Debug: Why does HR=276.44 stabilize when HR_max=1e6 and error>0 (MAP=180 > MAP_target=100)?

Goal: trace the baroreflex error and sympathetic/parasympathetic signals to understand
why HR stabilizes at 276.44 instead of growing without bound.
"""
import subprocess, os

src_dir = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\src'

# This script runs for T=60s and prints final state + a short trace of error/HR
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
vc.heart.HR_max = 1e6  # Remove HR cap

# Trace: collect error, sympathetic, HR, MAP at selected steps
trace_steps = [1, 2, 3, 10, 50, 100, 500, 1000, 3000, 6000]
trace = []

for i in range(n_steps):
    vc.step()
    if (i+1) in trace_steps:
        map_val = vc.heart.mean_arterial_pressure
        raw_map = map_val  # mean_arterial_pressure is what's displayed
        hr = vc.heart.heart_rate
        symp = vc.heart.sympathetic
        parasymp = vc.heart.parasympathetic

        # Manually compute error as in _baroreceptor_feedback
        # MAP_target is a module-level or class constant
        MAP_target = 100.0
        error = (MAP_target - raw_map) / MAP_target
        svr_inc = 1.0 + 2.0 * symp * max(0.0, error)
        svr = vc.heart.SVR

        trace.append((i+1, vc.current_time_s, map_val, raw_map, error, symp, parasymp, hr, svr, svr_inc))

print("Step | t(s)  | MAP_display | error   | sympathetic | parasymp | HR       | SVR      | svr_inc", flush=True)
print("-" * 100, flush=True)
for entry in trace:
    step, t, map_d, raw, err, sym, para, hr_val, svr, svr_inc = entry
    print("{:5} | {:5.2f} | {:11.3f} | {:7.4f} | {:11.6f} | {:9.6f} | {:9.2f} | {:9.3f} | {:7.4f}".format(
        step, t, map_d, err, sym, para, hr_val, svr, svr_inc), flush=True)

print()
print("FINAL: MAP={:.3f} HR={:.2f} SVR={:.3f} HR_max={:.0f}".format(
    vc.heart.mean_arterial_pressure, vc.heart.heart_rate,
    vc.heart.SVR, vc.heart.HR_max), flush=True)
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=120)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:300])