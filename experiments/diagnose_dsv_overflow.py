"""Diagnose where dSV overflow comes from."""
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
total_steps = 560  # up to t=5.6s (around崩溃点)

def compute_target_sv(heart_module, vol_ratio):
    base_SV = heart_module.base_SV
    contractility_factor = getattr(heart_module, 'contractility_factor', 1.0)
    if 0.5 <= vol_ratio <= 1.2:
        target_SV = base_SV * (0.05 + 0.95 * vol_ratio ** 2.5)
    elif vol_ratio < 0.5:
        target_SV = base_SV * 0.3
    else:
        target_SV = base_SV * 1.05
    return target_SV * contractility_factor

print("Tracing step by step, watching for overflow precursors...")
for step_i in range(total_steps):
    y_before = y.copy()
    dydt = vc._unified_rhs(vc.current_time_s, y)
    y = y + dt * dydt
    vc._unpack_unified_state(y)
    vc.current_time_s += dt

    if step_i % 50 == 0:
        has_nan = np.any(np.isnan(y[:4]))
        has_inf = np.any(np.isinf(y[:4]))
        vol_ratio = vc.heart.circulating_volume_ml / vc.heart.total_BV
        print(f"step={step_i:4d} t={vc.current_time_s:.2f}s | y[:4]={y[:4]} | nan={has_nan} inf={has_inf} vol_ratio={vol_ratio:.4f}")

    if np.any(np.isnan(y[:4])):
        print(f"\n⚠️  NaN at step={step_i} t={vc.current_time_s:.3f}s")
        print(f"  y_before={y_before[:4]}")
        print(f"  dydt[:4]={dydt[:4]}")
        print(f"  y[:4]={y[:4]}")
        hr = vc.heart.heart_rate
        sv = vc.heart.stroke_volume
        bv = vc.heart.circulating_volume_ml
        vol_ratio = bv / vc.heart.total_BV
        target = compute_target_sv(vc.heart, vol_ratio)
        print(f"  HR={hr:.2f} SV={sv:.4f} BV={bv:.2f} vol_ratio={vol_ratio:.4f}")
        print(f"  target_SV={target:.4f} diff={target-sv:.6f}")
        print(f"  dSV_numerator = (target - sv) * 0.3 = {(target-sv)*0.3:.4e}")
        print(f"  dSV = numerator / dt = {(target-sv)*0.3/dt:.4e}")
        break

print("\nDone.")