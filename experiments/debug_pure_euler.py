"""Debug: trace Pure Euler step by step to find where it fails."""
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
print(f"Initial y[0:4] (HR, SV, SVR, BV): {y[0:4]}")
print(f"Initial heart_rate={vc.heart.heart_rate}, stroke_volume={vc.heart.stroke_volume}, circulating_volume={vc.heart.circulating_volume_ml}")

# Call rhs once to init
dydt0 = vc._unified_rhs(0.0, y)
print(f"\nAfter first rhs call at t=0:")
print(f"  dydt[0:4]: {dydt0[0:4]}")
print(f"  heart_rate={vc.heart.heart_rate}, MAP={vc.heart.mean_arterial_pressure}, CO={vc.heart.heart_rate*vc.heart.stroke_volume}")

# Now step manually with dt=0.01, checking every step
dt = 0.01
total_steps = 500  # up to t=5s (blood loss onset)

print(f"\nTracing first {total_steps} steps with dt={dt}...")
for step_i in range(total_steps):
    t_before = vc.current_time_s
    y_before = y.copy()
    dydt = vc._unified_rhs(vc.current_time_s, y)
    y = y + dt * dydt
    vc._unpack_unified_state(y)
    vc.current_time_s += dt

    # Check every 50 steps
    if step_i % 50 == 0 or step_i < 5:
        hr = vc.heart.heart_rate
        sv = vc.heart.stroke_volume
        bv = vc.heart.circulating_volume_ml
        map_v = vc.heart.mean_arterial_pressure
        co = hr * sv
        has_nan = any(np.isnan(y[:4]))
        print(f"  step={step_i:4d} t={vc.current_time_s:.2f}s HR={hr:.1f} SV={sv:.3f} BV={bv:.1f} MAP={map_v:.1f} CO={co:.1f} y_nan={has_nan}")
        if has_nan:
            print(f"    y_before={y_before[:4]}")
            print(f"    dydt={dydt[:4]}")
            print(f"    y_after={y[:4]}")
            break

print("\nDone tracing.")