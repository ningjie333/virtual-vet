"""Systematic verification of unbounded divergence in sequential Euler without saturation.
Design:
1. Remove HR_max cap (set to 1e6)
2. Keep SVR_max as-is (physiological 3x baseline cap)
3. For each dt, simulate T=600s (same observation window)
4. Track: MAP, HR, SVR at t=60s and t=600s
5. Check: does bias grow as dt decreases, or converge to a finite value?
"""
import subprocess, os, json

src_dir = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\src'
out_file = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\experiments\unbounded_divergence_results.json'

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
vc.heart.HR_max = 1e6  # REMOVE HR saturation

for i in range(n_steps):
    vc.step()

map_val = vc.heart.mean_arterial_pressure
hr_val = vc.heart.heart_rate
svr_val = vc.heart.SVR
co_val = vc.heart.heart_rate * vc.heart.stroke_volume / 1000.0

# Record at T=60s and T=T_END
print("RESULT: dt=" + "DT_PLACEHOLDER" + " T=" + "T_END_PLACEHOLDER" + " MAP={:.3f} HR={:.2f} SVR={:.3f} CO={:.3f}".format(
    map_val, hr_val, svr_val, co_val), flush=True)
"""

print('=== UNBOUNDED DIVERGENCE VERIFICATION ===\n')

results = {}
# Test each dt at T=60s and T=600s
dts = [0.2, 0.1, 0.05, 0.02, 0.01, 0.005]
times = [60, 600]

for dt in dts:
    results[dt] = {}
    for T in times:
        script = SCRIPT_TEMPLATE.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('DT_PLACEHOLDER', str(dt)).replace('T_END_PLACEHOLDER', str(T))
        print(f'Running: dt={dt}, T={T}s...', flush=True)
        r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=600)
        out = r.stdout.strip()
        err = r.stderr.strip() if r.stderr else ''
        if 'RESULT:' in out:
            line = out.split('RESULT:')[1].strip()
            results[dt][T] = line
            print(f'  {line}')
        else:
            results[dt][T] = f'ERROR: {err[:200] if err else "no output"}'
            print(f'  ERROR: {err[:200] if err else out}')
        print()

# Reference: with HR saturation
print('=== WITH HR SATURATION (reference) ===\n')
for dt in [0.2, 0.1, 0.05, 0.02, 0.01]:
    script = SCRIPT_TEMPLATE.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('DT_PLACEHOLDER', str(dt)).replace('T_END_PLACEHOLDER', '60')
    script = script.replace('vc.heart.HR_max = 1e6', '# vc.heart.HR_max = 1e6')
    print(f'Running: dt={dt}, T=60s (WITH saturation)...', flush=True)
    r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=120)
    out = r.stdout.strip()
    if 'RESULT:' in out:
        print(f'  {out.split("RESULT:")[1].strip()}')
    print()

print('\n=== SUMMARY TABLE ===')
print(f'{"dt":>6} | {"T=60 w/o sat MAP":>18} | {"T=60 w/o sat HR":>14} | {"T=600 w/o sat MAP":>18} | {"T=600 w/o sat HR":>14} | {"T=60 w/ sat MAP":>14} | {"w/ sat HR":>10}')
print('-' * 110)

ref_data = {}
for dt in dts:
    t60 = results[dt].get(60, 'N/A')
    t600 = results[dt].get(600, 'N/A')

    def parse_result(s):
        if 'RESULT:' in s:
            parts = s.split('RESULT:')[1].strip().split()
            m = h = svr = co = 'N/A'
            for p in parts:
                if p.startswith('MAP='): m = float(p.split('=')[1])
                elif p.startswith('HR='): h = float(p.split('=')[1])
                elif p.startswith('SVR='): svr = float(p.split('=')[1])
                elif p.startswith('CO='): co = float(p.split('=')[1])
            return m, h, svr, co
        return None, None, None, None

    m60, h60, _, _ = parse_result(t60)
    m600, h600, _, _ = parse_result(t600)

    ref_script = SCRIPT_TEMPLATE.replace('SRC_DIR_PLACEHOLDER', src_dir).replace('DT_PLACEHOLDER', str(dt)).replace('T_END_PLACEHOLDER', '60').replace('vc.heart.HR_max = 1e6', '# vc.heart.HR_max = 1e6')
    r_ref = subprocess.run(['python', '-c', ref_script], capture_output=True, text=True, timeout=120)
    ref_out = r_ref.stdout.strip()
    m_ref, h_ref, _, _ = parse_result(ref_out)

    print(f'{dt:>6} | {str(round(m60,3)) if m60 else "N/A":>18} | {str(round(h60,1)) if h60 else "N/A":>14} | {str(round(m600,3)) if m600 else "N/A":>18} | {str(round(h600,1)) if h600 else "N/A":>14} | {str(round(m_ref,3)) if m_ref else "N/A":>14} | {str(round(h_ref,1)) if h_ref else "N/A":>10}')

print()

# Save raw results
with open(out_file, 'w') as f:
    json.dump(results, f, indent=2)
print(f'Results saved to: {out_file}')

print('\n=== KEY ANALYSIS ===')
print()
# Check convergence from T=60 to T=600
print('Convergence check (T=60 vs T=600):')
for dt in dts:
    t60 = results[dt].get(60, '')
    t600 = results[dt].get(600, '')
    m60, h60, _, _ = (parse_result(t60) if t60 else (None,None,None,None))
    m600, h600, _, _ = (parse_result(t600) if t600 else (None,None,None,None))
    if m60 and m600:
        delta_map = m600 - m60
        print(f'  dt={dt}: ΔMAP T60→600 = {delta_map:+.3f} mmHg  MAP 60s={m60:.1f} → 600s={m600:.1f}')

print()
print('Bias scaling (no saturation):')
for dt in dts:
    t60 = results[dt].get(60, '')
    m60, h60, _, _ = (parse_result(t60) if t60 else (None,None,None,None))
    if m60:
        bias = m60 - 100.0
        ratio = bias * dt if bias * dt else 0
        print(f'  dt={dt}: bias={bias:+.3f} mmHg, bias×dt={ratio:.4f}')

print()
print('Interpretation:')
print('  bias × dt ≈ const → bias ∝ 1/dt → unbounded as dt→0 (CONFIRMED if constant)')
print('  bias × dt → 0    → bias decreases with dt → bounded (CONTRADICTED)')
print('  bias × dt grows   → bias grows faster than 1/dt → super-unbounded')