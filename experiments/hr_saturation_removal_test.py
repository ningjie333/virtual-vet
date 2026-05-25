"""Remove HR saturation properly and observe if bias diverges with dt refinement."""
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

# CORRECTLY remove HR saturation by setting HR_max
vc.heart.HR_max = 1e6

for i in range(n_steps):
    vc.step()

map_val = vc.heart.mean_arterial_pressure
hr_val = vc.heart.heart_rate
t_end = vc.current_time_s
print("NO_SAT dt=" + "DT_PLACEHOLDER" + " T=" + "T_END_PLACEHOLDER" + " MAP={:.3f} HR={:.2f} t={:.1f}s steps={}".format(
    map_val, hr_val, t_end, n_steps), flush=True)
"""

print('=== HR SATURATION REMOVAL (CORRECTED) ===\n')
print('Reference (with saturation, dt=0.01 T=60s):')
ref_script = SCRIPT_TEMPLATE.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('DT_PLACEHOLDER', '0.01').replace('T_END_PLACEHOLDER', '60')
ref_script = ref_script.replace("vc.heart.HR_max = 1e6", "# vc.heart.HR_max = 1e6")
r_ref = subprocess.run(['python', '-c', ref_script], capture_output=True, text=True, timeout=120)
print(' ', r_ref.stdout.strip())
print()

results = []
# Test progressively smaller dt, same observation time T=60s
for dt in [0.2, 0.1, 0.05, 0.02, 0.01]:
    script = SCRIPT_TEMPLATE.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('DT_PLACEHOLDER', str(dt)).replace('T_END_PLACEHOLDER', '60')
    r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=600)
    out = r.stdout.strip()
    results.append((dt, 60, out))
    print(f'dt={dt} T=60s: {out}')
    print()

print('\n=== ANALYSIS ===')
print('With saturation (reference): MAP=144.742 HR=180.15')
print()
for dt, T, out in results:
    if 'MAP=' in out:
        try:
            map_val = float(out.split('MAP=')[1].split()[0])
            hr_val = float(out.split('HR=')[1].split()[0])
            bias = map_val - 100.0
            print(f'dt={dt} T={T}s: MAP={map_val:.3f} HR={hr_val:.2f} bias={bias:+.3f}')
        except:
            pass

print()
print('If MAP grows without bound as dt decreases → saturation truncates divergence (CONFIRMED)')
print('If MAP converges to a finite value → different fixed point mechanism')
print('If MAP still plateaus at ~144.7 → HR=180 is NOT the primary truncation point')