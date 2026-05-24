"""Trace what happens 5 steps before NaN to see the explosion."""
import sys, os, types
import numpy as np

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")

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

WEIGHT_KG = 20.0
BLOOD_LOSS_TIME = 5.0
BLOOD_LOSS_VOLUME = 400.0

vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
vc._cached_inputs.clear()
vc.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME,
                            duration=20.0, width=2.0)
y = vc._pack_unified_state()
_ = vc._unified_rhs(0.0, y)

dt = 0.01

print("Tracing 543-549 (around explosion)...")
for step_i in range(543, 550):
    y_before = y.copy()
    dydt = vc._unified_rhs(vc.current_time_s, y)
    y_new = y + dt * dydt
    vc._unpack_unified_state(y)
    vc.current_time_s += dt
    y = y_new

    vol_ratio = vc.heart.circulating_volume_ml / vc.heart.total_BV
    print(f"step={step_i} t={vc.current_time_s:.3f}s")
    print(f"  y_before[:4]={y_before[:4]}")
    print(f"  dydt[:4]={dydt[:4]}")
    print(f"  y_new[:4]={y[:4]}")
    print(f"  HR={vc.heart.heart_rate:.2f} SV={vc.heart.stroke_volume:.4f} vol_ratio={vol_ratio:.4f} BV={vc.heart.circulating_volume_ml:.2f}")
    print()

print("Done.")