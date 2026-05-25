"""Simple question: What does Radau (unified IVP solver) give as MAP at steady-state?
This is the "ground truth" we should compare against.
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

# Try to run the unified IVP solver
try:
    from scipy.integrate import Radau
    print("scipy.integrate.Radau available")

    vc = VirtualCreature(body_weight_kg=20.0)

    # Build state vector
    y0 = vc.get_state_vector()
    print(f"State vector size: {len(y0)}")

    # Run Radau
    def rhs(t, y):
        vc.load_state_vector(y)
        vc.engine_step(0.0)  # doesn't use dt in unified solver
        return vc.get_derivatives_vector()

    t_span = (0, 120)
    sol = Radau(rhs, t_span, y0, rtol=1e-6, atol=1e-9, max_step=0.1)

    vc.load_state_vector(sol.y[:, -1])
    map_radau = vc.heart.mean_arterial_pressure
    hr_radau = vc.heart.heart_rate

    print(f"Radau (T=120s): MAP={map_radau:.3f}, HR={hr_radau:.1f}")
    print(f"Reference bias: {map_radau - 100:.3f} mmHg")

except Exception as e:
    print(f"Radau not available or failed: {e}")
    print("Trying alternative: run_virtual_creature if available")

    # Try the run_unified_ivp approach
    try:
        result = VirtualCreature.run_unified_ivp(T=120.0, rtol=1e-6)
        print(f"run_unified_ivp result: {result}")
    except Exception as e2:
        print(f"Also failed: {e2}")
"""

script = SCRIPT.replace('SRC_DIR_PLACEHOLDER', src_dir)
r = subprocess.run(['python', '-c', script], capture_output=True, text=True, timeout=180)
print(r.stdout.strip())
if r.stderr and 'WARNING' not in r.stderr and 'Deprecation' not in r.stderr:
    print('ERR:', r.stderr[:500])