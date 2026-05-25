"""Critical diagnostic: measure filtered MAP vs raw_MAP at steady-state.

Two agents identified the key unknown:
  - If filtered MAP ≈ 100 (target) → error ≈ 0 → gain/gain sweep irrelevant
  - If filtered MAP ≈ 144 → error = -0.446 → baroreflex suppression should dominate

This experiment directly measures:
  1. raw_MAP (from CO × SVR formula used in _baroreceptor_feedback)
  2. MAP_display (low-pass filtered)
  3. error signal
  4. HR, SV, SVR, CO at steady-state

Run at dt=0.01 for T=120s to reach steady-state.
"""
import subprocess, os

src_dir = r'c:\Users\ZhuanZ（无密码）\Desktop\Claudecode\01_代码实验\virtual-vet\src'

SCRIPT = r"""
import sys, os, types, numpy as np
SRC_DIR = r"SRC_DIR_PLACEHOLDER"
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding='utf-8').read().replace('from src.', 'from ')

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
T_END = 120.0
n_steps = int(T_END / DT)

vc = VirtualCreature(body_weight_kg=20.0)
vc.dt = DT
vc.heart.HR_max = 1e6  # Remove saturation to see true steady-state

trace_steps = [1, 50, 100, 500, 1000, 2000, 4000, 6000, 8000, 10000, 12000]

print("Step | t(s)  | raw_MAP_calc | MAP_display | error | HR | SV | SVR | CO | HR_cap_flag", flush=True)
print("-" * 110, flush=True)

for i in range(n_steps):
    vc.step()

    if (i+1) in trace_steps:
        hr = vc.heart.heart_rate
        sv = vc.heart.stroke_volume
        svr = vc.heart.SVR

        # Compute CO and raw_MAP using the SAME formula as _baroreceptor_feedback
        co = hr * sv / 1000.0  # L/min
        # MAP_base + CO/60 * SVR (from heart.py line ~406)
        map_base = vc.heart.MAP_base if hasattr(vc.heart, 'MAP_base') else 60.0
        raw_map_calc = map_base + (co * svr)  # Same as in compute()

        map_display = vc.heart.mean_arterial_pressure

        MAP_target = 100.0
        error = (MAP_target - raw_map_calc) / MAP_target

        hr_cap_flag = "SATURATED" if hr >= 180 else "OK"

        print("{:5} | {:5.2f} | {:12.6f} | {:11.6f} | {:+7.4f} | {:6.1f} | {:.3f} | {:.4f} | {:.4f} | {}".format(
            i+1, vc.current_time_s, raw_map_calc, map_display, error,
            hr, sv, svr, co, hr_cap_flag
        ), flush=True)

print()
print("=== STEADY STATE CHECK ===")
hr = vc.heart.heart_rate
sv = vc.heart.stroke_volume
svr = vc.heart.SVR
co = hr * sv / 1000.0
map_base = vc.heart.MAP_base if hasattr(vc.heart, 'MAP_base') else 60.0
raw_map_calc = map_base + (co * svr)
map_display = vc.heart.mean_arterial_pressure
MAP_target = 100.0
error = (MAP_target - raw_map_calc) / MAP_target

print(f"raw_MAP_calc = MAP_base + CO*SVR = {map_base} + {co:.4f}*{svr:.4f} = {raw_map_calc:.6f}")
print(f"MAP_display (filtered) = {map_display:.6f}")
print(f"error = (100 - {raw_map_calc:.6f})/100 = {error:.6f}")
print(f"HR = {hr:.2f} (HR_max = {vc.heart.HR_max})")
print(f"SV = {sv:.4f} mL")
print(f"SVR = {svr:.4f} (baseline = {vc.heart.SVR_baseline})")
print()
print("KEY QUESTION: Is error positive or negative at steady-state?")
print(f"  error > 0 → baroreflex drives HR UP (sympathetic dominant)")
print(f"  error < 0 → baroreflex suppresses HR (parasympathetic dominant)")
print(f"  error = {error:.6f} → {'POSITIVE' if error > 0 else 'NEGATIVE' if error < 0 else 'ZERO'}")
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=180)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:500])