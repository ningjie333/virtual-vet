"""Check unified RHS: does PO2 oscillate? Does MAP converge to 100?"""
import sys, os, types, numpy as np

SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding="utf-8").read().replace("from src.", "from ")

sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(SRC_DIR, "parameters.py")),
             os.path.join(SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _name in ["blood", "fluid", "cardiac_electrophysiology", "noble_purkinje",
              "respiratory_rhythm", "heart", "lung", "kidney", "gut", "liver",
              "endocrine", "neuro", "immune", "coagulation", "lymphatic",
              "lifecycle", "toxicology", "organ_health", "pharmacology", "simulation"]:
    _path = os.path.join(SRC_DIR, f"{_name}.py")
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    _mod.__file__ = _path
    sys.modules[_name] = _mod
    exec(compile(_src, _path, "exec"), _mod.__dict__)

from simulation import VirtualCreature

creature = VirtualCreature(body_weight_kg=20)

# Run Radau unified solver
print("Running Radau unified IVP...")
sol = creature.run_unified_ivp(t_end=120.0, dt_save=1.0)
print(f"Radau success: {sol.success}, status={sol.message}")

# Extract final state
final_y = sol.y[:, -1]
# We need to inspect the state. Let's check final MAP, HR, and PO2
# The state map tells us which index corresponds to which variable

print(f"\nState vector size: {len(final_y)}")
print(f"Time points: {len(sol.t)}")

# Let's look at the state at t=120s by unpacking
from scipy.integrate import solve_ivp
# Actually, let's just use the stored results
# The state vector format is defined in _build_unified_state_map

# Check heart state at final time
HR_idx = None
SV_idx = None
SVR_idx = None
state_map = creature._build_unified_state_map()
for (mname, vname), idx in state_map.items():
    if mname == "heart" and vname == "HR":
        HR_idx = idx
    elif mname == "heart" and vname == "SV":
        SV_idx = idx
    elif mname == "heart" and vname == "SVR":
        SVR_idx = idx

final_HR = final_y[HR_idx] if HR_idx is not None else 0
final_SV = final_y[SV_idx] if SV_idx is not None else 0
final_SVR = final_y[SVR_idx] if SVR_idx is not None else 0

# Reconstruct MAP from state
# MAP = MAP_baseline + (HR * SV / 60) * SVR
co_ml_s = final_HR * final_SV / 60.0
map_radau = 60.0 + co_ml_s * final_SVR
print(f"\nRadau final (t=120s):")
print(f"  HR = {final_HR:.2f} bpm")
print(f"  SV = {final_SV:.2f} mL")
print(f"  SVR = {final_SVR:.4f} mmHg·s/mL")
print(f"  MAP = {map_radau:.2f} mmHg")

# Also check PO2 at the blood module
print(f"\nBlood state at end:")
print(f"  PO2 = {creature.blood.arterial_PO2_mmHg:.1f} mmHg")
print(f"  PCO2 = {creature.blood.arterial_PCO2_mmHg:.1f} mmHg")
print(f"  pH = {creature.blood.arterial_pH:.4f}")
print(f"  Chemo drive = {creature.neuro.chemoreceptor_drive:.6f}")

# Trace PO2 over time
print("\nTime course (every 10s):")
print(f"{'t':>6} {'HR':>8} {'MAP':>8} {'PO2':>7} {'PCO2':>7} {'pH':>7} {'chemo':>8}")
for i in range(0, len(sol.t), 10):
    t = sol.t[i]
    y = sol.y[:, i]
    hr = y[HR_idx]
    sv = y[SV_idx]
    svr = y[SVR_idx]
    map_val = 60.0 + (hr * sv / 60.0) * svr

    # Can't get blood values directly from state vector (blood not in unified state)
    # They're set during _unified_rhs calls, so the last call sets them
    # Let's print what we can
    chemo = creature.neuro.chemoreceptor_drive if i == len(sol.t) - 1 else 0

    print(f"{t:6.1f} {hr:8.2f} {map_val:8.2f}")
