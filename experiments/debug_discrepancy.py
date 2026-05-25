"""Direct comparison: two scripts that should be identical but give different results."""
import subprocess, os

src_dir = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\src'

SCRIPT_V1 = r"""
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

for i in range(n_steps):
    vc.step()

print("V1: MAP={:.3f} HR={:.2f} SVR={:.3f} SV={:.2f} HR_max={:.0f}".format(
    vc.heart.mean_arterial_pressure,
    vc.heart.heart_rate,
    vc.heart.SVR,
    vc.heart.stroke_volume,
    vc.heart.HR_max
), flush=True)
"""

SCRIPT_V2 = r"""
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

for i in range(n_steps):
    vc.step()

map_val = vc.heart.mean_arterial_pressure
hr_val = vc.heart.heart_rate
svr_val = vc.heart.SVR
co_val = vc.heart.heart_rate * vc.heart.stroke_volume / 1000.0

print("V2: MAP={:.3f} HR={:.2f} SVR={:.3f} CO={:.3f}".format(
    map_val, hr_val, svr_val, co_val), flush=True)
"""

print('=== DIRECT COMPARISON: Two supposedly identical scripts ===\n')

v1_script = SCRIPT_V1.replace('SRC_DIR_PLACEHOLDER', src_dir)
v2_script = SCRIPT_V2.replace('SRC_DIR_PLACEHOLDER', src_dir)

r1 = subprocess.run(['python', '-c', v1_script], capture_output=True, text=True, timeout=120)
r2 = subprocess.run(['python', '-c', v2_script], capture_output=True, text=True, timeout=120)

print(f'V1: {r1.stdout.strip()}')
if r1.stderr and 'WARNING' not in r1.stderr and 'Deprecation' not in r1.stderr:
    print(f'  V1 stderr: {r1.stderr[:300]}')
print(f'V2: {r2.stdout.strip()}')
if r2.stderr and 'WARNING' not in r2.stderr and 'Deprecation' not in r2.stderr:
    print(f'  V2 stderr: {r2.stderr[:300]}')
print()

# Run V1 and V2 multiple times to check reproducibility
print('=== REPRODUCIBILITY CHECK (3 runs each) ===\n')
for label, script_template in [('V1', SCRIPT_V1), ('V2', SCRIPT_V2)]:
    script = script_template.replace('SRC_DIR_PLACEHOLDER', src_dir)
    for run in range(3):
        r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=120)
        print(f'{label} run {run+1}: {r.stdout.strip()}')
    print()

# Also check: what HR_max does VirtualCreature set at initialization?
SCRIPT_CHECK_HR_MAX = r"""
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
vc = VirtualCreature(body_weight_kg=20.0)
print("Default HR_max at init: {}".format(vc.heart.HR_max))
print("heart_rate at init: {}".format(vc.heart.heart_rate))
print("heart_rate_min: {}".format(getattr(vc.heart, 'heart_rate_min', 'N/A')))
"""

check_script = SCRIPT_CHECK_HR_MAX.replace('SRC_DIR_PLACEHOLDER', src_dir)
r_check = subprocess.run(['python', '-c', check_script], capture_output=True, text=True, timeout=120)
print(f'Initialization check: {r_check.stdout.strip()}')