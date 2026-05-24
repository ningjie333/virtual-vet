"""
Minimal idempotency test for _unified_rhs
"""
import os, sys, types
import numpy as np

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")

sys.path.insert(0, _SRC_DIR)

def _read_patched(path):
    return open(path, encoding="utf-8").read().replace("from src.", "from ")

sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(_SRC_DIR, "parameters.py")),
             os.path.join(_SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _name in ["blood", "fluid", "cardiac_electrophysiology", "noble_purkinje",
    "respiratory_rhythm", "heart", "lung", "kidney", "gut", "liver",
    "endocrine", "neuro", "immune", "coagulation", "lymphatic",
    "lifecycle", "toxicology", "organ_health", "pharmacology", "simulation"]:
    _path = os.path.join(_SRC_DIR, f"{_name}.py")
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, "exec"), _mod.__dict__)

VirtualCreature = sys.modules["simulation"].VirtualCreature

vc = VirtualCreature(body_weight_kg=20.0)
vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)
vc._cached_inputs.clear()
y0 = vc._pack_unified_state()

# Check which state variable idx=5 is
state_map = vc._build_unified_state_map()
print("State map (first 15 entries):")
for key, idx in sorted(state_map.items(), key=lambda x: x[1])[:15]:
    print(f"  idx={idx}: {key}")

print()
# Call 1
vc._cached_inputs.clear()
vc._unpack_unified_state(y0)
print(f"Before call 1 — VDP x={vc.lung._vdp.x:.6f}, v={vc.lung._vdp.v:.6f}, amp={vc.lung._vdp.amplitude:.6f}, RR={vc.lung._vdp.respiratory_rate:.6f}")
print(f"Before call 1 — lung.TV={vc.lung.tidal_volume:.6f}")
dydt1 = vc._unified_rhs(0.0, y0)
print(f"After call 1  — VDP x={vc.lung._vdp.x:.6f}, v={vc.lung._vdp.v:.6f}, amp={vc.lung._vdp.amplitude:.6f}, RR={vc.lung._vdp.respiratory_rate:.6f}")
print(f"After call 1  — lung.TV={vc.lung.tidal_volume:.6f}")

# Call 2 (same y, fresh cache)
vc._cached_inputs.clear()
vc._unpack_unified_state(y0)
print(f"Before call 2 — VDP x={vc.lung._vdp.x:.6f}, v={vc.lung._vdp.v:.6f}, amp={vc.lung._vdp.amplitude:.6f}, RR={vc.lung._vdp.respiratory_rate:.6f}")
print(f"Before call 2 — lung.TV={vc.lung.tidal_volume:.6f}")
dydt2 = vc._unified_rhs(0.0, y0)
print(f"After call 2  — VDP x={vc.lung._vdp.x:.6f}, v={vc.lung._vdp.v:.6f}, amp={vc.lung._vdp.amplitude:.6f}, RR={vc.lung._vdp.respiratory_rate:.6f}")
print(f"After call 2  — lung.TV={vc.lung.tidal_volume:.6f}")

# Call 3
vc._cached_inputs.clear()
vc._unpack_unified_state(y0)
dydt3 = vc._unified_rhs(0.0, y0)
print(f"After call 3  — VDP x={vc.lung._vdp.x:.6f}, v={vc.lung._vdp.v:.6f}, amp={vc.lung._vdp.amplitude:.6f}")

print()
print(f"dydt1[5]={dydt1[5]:.6f}  dydt2[5]={dydt2[5]:.6f}  dydt3[5]={dydt3[5]:.6f}")

diff_12 = float(np.max(np.abs(dydt1 - dydt2)))
diff_13 = float(np.max(np.abs(dydt1 - dydt3)))
print(f"Max |dydt1 - dydt2|: {diff_12:.10f}")
print(f"Max |dydt1 - dydt3|: {diff_13:.10f}")