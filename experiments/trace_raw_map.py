"""Trace the raw_MAP computation to understand why MAP_display stabilizes at 180
while HR keeps growing (dt=0.01, HR_max=1e6, T=120s)."""
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
T_END = 120.0
n_steps = int(T_END / DT)

vc = VirtualCreature(body_weight_kg=20.0)
vc.dt = DT
vc.heart.HR_max = 1e6

# Key: compute raw_MAP from CO × SVR / 60
MAP_target = 100.0

trace_steps = [1, 100, 500, 1000, 2000, 4000, 6000, 8000, 10000, 12000]

for i in range(n_steps):
    vc.step()
    if (i+1) in trace_steps:
        map_disp = vc.heart.mean_arterial_pressure
        hr = vc.heart.heart_rate
        sv = vc.heart.stroke_volume
        svr = vc.heart.SVR
        co = hr * sv / 1000.0
        raw_map = co * svr / 60.0  # This is the Frank-Starling formula
        error = (MAP_target - map_disp) / MAP_target
        error_raw = (MAP_target - raw_map) / MAP_target

        print("{:6} t={:6.2f}s MAP_disp={:7.3f} raw_MAP={:7.3f} err_disp={:+7.4f} err_raw={:+7.4f} HR={:8.2f} SV={:.3f} SVR={:.3f} CO={:.3f}".format(
            i+1, vc.current_time_s, map_disp, raw_map, error, error_raw, hr, sv, svr, co
        ), flush=True)

print()
print("=== FINAL ===")
print("MAP_display: {:.3f}".format(vc.heart.mean_arterial_pressure))
print("raw_MAP (CO*SVR/60): {:.3f}".format(vc.heart.heart_rate * vc.heart.stroke_volume / 1000.0 * vc.heart.SVR / 60.0))
print("MAP formula check: CO={:.3f} SVR={:.3f} → MAP={:.3f}".format(
    vc.heart.heart_rate * vc.heart.stroke_volume / 1000.0,
    vc.heart.SVR,
    vc.heart.heart_rate * vc.heart.stroke_volume / 1000.0 * vc.heart.SVR / 60.0
))
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=120)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:300])