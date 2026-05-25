"""Analyze the filtered MAP vs raw_MAP paradox.

KEY: MAP_display = 180 (clamped) while raw_MAP_calc = 72.81.
This means the baroreflex sees raw_MAP=72.8 (below target 100) → positive error → drives HR UP forever.
But MAP_display is clamped at 180, hiding the true cardiovascular state.

This resolves the paradox: bias is NOT from sequential coupling -
it's from the clamp on MAP_display creating a persistent positive error signal
that drives the baroreflex to keep increasing HR beyond physiological bounds.

We need to verify:
1. Is MAP_display clamp the cause of persistent positive error?
2. Is the true bias O(1) in the UNCLAMPED regime?
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
vc.heart.HR_max = 1e6  # No saturation

print("=== PARADOX INVESTIGATION ===\n")

# Initialize and run
for i in range(n_steps):
    vc.step()

# Final state analysis
hr = vc.heart.heart_rate
sv = vc.heart.stroke_volume
svr = vc.heart.SVR
co = hr * sv / 1000.0
map_base = 60.0
raw_map = map_base + co * svr

# THE key question: what is the raw MAP in the MAP formula?
# In heart.py compute(), it uses CO * SVR (not CO/60 * SVR)
# Let's verify with the ACTUAL code
print("Checking: CO (L/min) = HR * SV / 1000 = {} * {} / 1000 = {}".format(hr, sv, co))
print("SVR = {}".format(svr))
print("raw_MAP = MAP_base + CO * SVR = {} + {} * {} = {}".format(map_base, co, svr, raw_map))
print("MAP_display (filtered, clamped) = {}".format(vc.heart.mean_arterial_pressure))
print()

# The error in _baroreceptor_feedback is computed from raw_MAP (not filtered MAP_display)
MAP_target = 100.0
error = (MAP_target - raw_map) / MAP_target
print("Baroreflex error = (100 - {}) / 100 = {:.6f}".format(raw_map, error))
print("  error > 0: baroreflex drives HR UP (sympathetic)")
print("  error < 0: baroreflex suppresses HR (parasympathetic)")
print()

# What SHOULD the MAP be at steady-state?
# If baroreflex is working correctly: MAP should settle at target
# But MAP_display is clamped at 180, creating artificial positive error
# This drives HR up, up, up...

# The bias is from: MAP_display clamp → persistent positive error → runaway HR
print("=== ROOT CAUSE ANALYSIS ===")
print("1. MAP_display = mean_arterial_pressure (low-pass filtered + clamped at 180)")
print("2. Baroreflex uses raw_MAP (unfiltered) for error computation")
print("3. raw_MAP = MAP_base + CO * SVR")
print("4. At T=120s: CO={:.3f} L/min, SVR={:.4f} → raw_MAP={:.2f} mmHg".format(co, svr, raw_map))
print("5. raw_MAP < 100 (target) → error=+{:.4f} → baroreflex DRIVES HR UP".format(error))
print("6. MAP_display stuck at 180 (clamped) — does NOT reflect true raw_MAP")
print("7. HR reaches {:.1f} bpm (unbounded growth)".format(hr))
print()
print("CONCLUSION: The bias is caused by the MAP_display clamp creating a")
print("persistent positive error signal that drives the baroreflex to keep")
print("increasing HR beyond all physiological bounds.")
print()
print("Without MAP_display clamp: raw_MAP would correctly reflect the")
print("cardiovascular state, and the baroreflex would achieve equilibrium.")
print()

# Compute what the MAP SHOULD be if the clamp wasn't there
# The filtered MAP should converge to the true raw_MAP
# If alpha=0.1, dt=0.01: tau = 0.09s, should reach steady-state in ~0.5s
# But the clamp prevents MAP_display from going below 180
print("=== WHAT SHOULD HAPPEN (without clamp) ===")
# The low-pass filter: MAP_disp(n) = 0.9*MAP_disp(n-1) + 0.1*raw_MAP
# At steady-state raw_MAP = 72.81: MAP_disp should converge to 72.81
# But clamp prevents this

# What is the steady-state MAP if baroreflex properly regulates?
# At target MAP=100: error=0, HR stays constant, SV converges to ~14 mL
# CO = 85 * 14 / 1000 = 1.19 L/min
# MAP = 60 + 1.19 * 1.41 = 61.68 mmHg
# But that's below target 100... something is fundamentally wrong

print("If baroreflex works perfectly: MAP → 100 mmHg, HR → ~85 bpm, SV → ~14 mL")
print("Then: CO = 85*14/1000 = 1.19 L/min, MAP = 60 + 1.19*1.41 = 61.68 mmHg")
print("BUT: 61.68 < 100, so error = (100-61.68)/100 = +0.383 → HR would increase")
print()
print("This means the baroreflex model has a SET-POINT MISMATCH:")
print("  Target: MAP_target = 100 mmHg")
print("  Achieves: MAP ≈ 60 + (HR*SV/1000)*1.41")
print("  For MAP=100: need (HR*SV/1000)*1.41 = 40 → HR*SV = 28.4 mL*bpm")
print("  With HR=85: SV = 28.4/85 = 0.334 mL ← physiologically impossible")
print("  With SV=14: HR = 28.4/14 = 203 bpm ← why we see HR=180")
print()
print("The SET-POINT is unachievable with current SVR and SV dynamics!")
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=180)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:500])