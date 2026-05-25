"""Subprocess isolation test: dt=0.2 extended time verification
Tests if MAP at dt=0.2 reaches 144.7 after 400s (2000 steps).
If YES → saturation-trapped instability confirmed (step-count driven)
If NO → different mechanism
"""
import subprocess, os

src_dir = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\src'

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
T_END = T_END_PLACEHOLDER
n_steps = int(T_END / DT)

vc = VirtualCreature(body_weight_kg=20.0)
vc.dt = DT
for i in range(n_steps):
    vc.step()

map_val = vc.heart.mean_arterial_pressure
hr_val = vc.heart.heart_rate
t_end = vc.current_time_s
print("dt=" + "DT_PLACEHOLDER" + " T_END=" + "T_END_PLACEHOLDER" + " MAP={:.3f} HR={:.2f} t={:.1f}s steps={}".format(
    map_val, hr_val, t_end, n_steps), flush=True)
"""

print('=== SATURATION-TRAPPED INSTABILITY VERIFICATION ===\n')

# Test 1: dt=0.2, T=60s (original observation - should give ~105.7)
print('Test 1: dt=0.2, T=60s (300 steps) — original observation')
script1 = SCRIPT_TEMPLATE.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('DT_PLACEHOLDER', '0.2').replace('T_END_PLACEHOLDER', '60')
r1 = subprocess.run(['python', '-c', script1], capture_output=True, text=True, timeout=120)
print(' ', r1.stdout.strip())
if r1.stderr and 'WARNING' not in r1.stderr and 'Deprecation' not in r1.stderr:
    print('  ERR:', r1.stderr[:200])
print()

# Test 2: dt=0.2, T=400s (2000 steps) — key prediction
print('Test 2: dt=0.2, T=400s (2000 steps) — saturation-trapped prediction')
script2 = SCRIPT_TEMPLATE.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('DT_PLACEHOLDER', '0.2').replace('T_END_PLACEHOLDER', '400')
r2 = subprocess.run(['python', '-c', script2], capture_output=True, text=True, timeout=300)
print(' ', r2.stdout.strip())
if r2.stderr and 'WARNING' not in r2.stderr and 'Deprecation' not in r2.stderr:
    print('  ERR:', r2.stderr[:200])
print()

# Test 3: dt=0.1, T=600s (6000 steps) — should saturate like dt=0.01
print('Test 3: dt=0.1, T=600s (6000 steps) — should saturate if step-count driven')
script3 = SCRIPT_TEMPLATE.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('DT_PLACEHOLDER', '0.1').replace('T_END_PLACEHOLDER', '600')
r3 = subprocess.run(['python', '-c', script3], capture_output=True, text=True, timeout=300)
print(' ', r3.stdout.strip())
if r3.stderr and 'WARNING' not in r3.stderr and 'Deprecation' not in r3.stderr:
    print('  ERR:', r3.stderr[:200])
print()

# Test 4: dt=0.01, T=60s (6000 steps) — reference saturated case
print('Test 4: dt=0.01, T=60s (6000 steps) — saturated reference: MAP≈144.7')
script4 = SCRIPT_TEMPLATE.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('DT_PLACEHOLDER', '0.01').replace('T_END_PLACEHOLDER', '60')
r4 = subprocess.run(['python', '-c', script4], capture_output=True, text=True, timeout=120)
print(' ', r4.stdout.strip())
if r4.stderr and 'WARNING' not in r4.stderr and 'Deprecation' not in r4.stderr:
    print('  ERR:', r4.stderr[:200])
print()

print('\n=== INTERPRETATION ===')
def parse(out):
    for line in out.strip().split('\n'):
        if 'MAP=' in line:
            try:
                map_val = float(line.split('MAP=')[1].split()[0])
                hr_val = float(line.split('HR=')[1].split()[0])
                steps = int(line.split('steps=')[1].split(')')[0])
                return map_val, hr_val, steps
            except: pass
    return None, None, None

m1, h1, s1 = parse(r1.stdout)
m2, h2, s2 = parse(r2.stdout)
m3, h3, s3 = parse(r3.stdout)
m4, h4, s4 = parse(r4.stdout)

if m2 and m4:
    print(f'dt=0.2 T=60s (300 steps):    MAP={m1:.3f} HR={h1:.2f}')
    print(f'dt=0.2 T=400s (2000 steps):  MAP={m2:.3f} HR={h2:.2f}')
    print(f'dt=0.1 T=600s (6000 steps):  MAP={m3:.3f} HR={h3:.2f}')
    print(f'dt=0.01 T=60s (6000 steps):  MAP={m4:.3f} HR={h4:.2f}')
    print()
    if abs(m2 - m4) < 5:
        print('→ SATURATION-TRAPPED INSTABILITY CONFIRMED:')
        print(f'  dt=0.2 needs ~2000 steps to reach same MAP as dt=0.01 at 6000 steps')
        print('  → Bias is step-count driven, not dt-invariant')
        print('  → Sequential Euler pushes system away from true fixed point')
        print('  → HR=180 saturation constraint truncates divergence = pseudo-convergence')
    elif m2 < 110:
        print('→ dt=0.2 does NOT reach 144.7 even at 2000 steps')
        print('  → Need even longer simulation or different interpretation')
    else:
        print(f'→ Partial drift: MAP={m2:.1f} but not fully saturated')
        print('  → Mixed regime, needs further investigation')