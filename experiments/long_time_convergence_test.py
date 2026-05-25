"""Long-time convergence test at dt=0.01 without HR saturation.
Does MAP converge to a finite value, or keep drifting?"""
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
T_END = T_END_PLACEHOLDER
n_steps = int(T_END / DT)

vc = VirtualCreature(body_weight_kg=20.0)
vc.dt = DT
vc.heart.HR_max = 1e6  # REMOVE HR saturation

for i in range(n_steps):
    vc.step()

map_val = vc.heart.mean_arterial_pressure
hr_val = vc.heart.heart_rate
sv_val = vc.heart.stroke_volume
svr_val = vc.heart.SVR
co_val = hr_val * sv_val / 1000.0

print("MAP={:.3f} HR={:.2f} SV={:.3f} SVR={:.3f} CO={:.3f} T={:.1f}s steps={}".format(
    map_val, hr_val, sv_val, svr_val, co_val, vc.current_time_s, n_steps), flush=True)
"""

print('=== LONG-TIME CONVERGENCE TEST (dt=0.01, no HR saturation) ===\n')

times = [60, 120, 300, 600, 1200, 2400]
results = []
for T in times:
    script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('T_END_PLACEHOLDER', str(T))
    print(f'T={T}s ({int(T/0.01)} steps)...', end=' ', flush=True)
    r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=600)
    out = r.stdout.strip()
    if 'MAP=' in out:
        print(out)
        results.append((T, out))
    else:
        print(f'ERROR: {r.stderr[:200] if r.stderr else out}')
    print()

print('\n=== CONVERGENCE ANALYSIS ===')
print(f'{"T(s)":>6} | {"MAP":>8} | {"HR":>8} | {"CO":>8} | {"ΔMAP from T=60":>15}')
prev_map = None
for T, out in results:
    if 'MAP=' in out:
        parts = {}
        for p in out.split():
            if '=' in p:
                k, v = p.split('=')
                try: parts[k] = float(v)
                except: pass
        m = parts.get('MAP', 0)
        h = parts.get('HR', 0)
        co = parts.get('CO', 0)
        delta = m - prev_map if prev_map else 0
        print(f'{T:>6} | {m:>8.3f} | {h:>8.2f} | {co:>8.3f} | {delta:>+15.3f}')
        prev_map = m

print()
print('If MAP stabilizes (ΔMAP→0): bounded bias, different fixed point')
print('If MAP keeps changing: still drifting or oscillating')
print('If MAP goes negative or NaN: model breakdown')