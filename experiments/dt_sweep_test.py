"""Subprocess isolation test: dt sweep fine-grained without FactorCommand"""
import subprocess, os

pwd = os.getcwd()
src_dir = os.path.join(pwd, 'src')
print(f'Working dir: {pwd}')
print(f'SRC_DIR: {src_dir}')

SCRIPT_TEMPLATE = r"""
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

DT = DT_PLACEHOLDER
T_END = 60.0
n_steps = int(T_END / DT)

vc = VirtualCreature(body_weight_kg=20.0)
vc.dt = DT
for i in range(n_steps):
    vc.step()
map_val = vc.heart.mean_arterial_pressure
hr_val = vc.heart.heart_rate
print("dt=" + "DT_PLACEHOLDER" + " MAP={:.3f} HR={:.2f}".format(map_val, hr_val), flush=True)
"""

print('\n=== DT SWEEP (no FactorCommand, fine-grained) ===\n')
results = []
for dt in [0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.001]:
    script = SCRIPT_TEMPLATE.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('DT_PLACEHOLDER', str(dt))
    r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=600)
    out = r.stdout.strip()
    err = r.stderr.strip() if r.stderr else ''
    results.append((dt, out, err))
    print('dt={}: {}'.format(dt, out))
    if err and 'WARNING' not in err and 'Deprecation' not in err:
        print('  stderr:', err[:300])
    print()

print('\n=== SUMMARY ===')
print('Radau reference MAP = 100.000')
for dt, out, err in results:
    for line in out.strip().split('\n'):
        if 'MAP=' in line:
            try:
                map_val = float(line.split('MAP=')[1].split()[0])
                bias = map_val - 100.0
                print('dt={}: MAP={:.3f}  (bias={:+.3f} mmHg)  HR={:.2f}'.format(
                    dt, map_val, bias,
                    float(line.split('HR=')[1].split()[0]) if 'HR=' in line else 0))
            except:
                pass