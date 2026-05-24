"""Quick convergence check after dt/dt bug fix — same module loading as convergence_study.py."""
import sys, os, types
import numpy as np
from scipy.interpolate import interp1d

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")

# Same module loader as convergence_study.py
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
T_END = 60.0
DT_SAVE = 2.0
BLOOD_LOSS_TIME = 5.0
BLOOD_LOSS_VOLUME = 400.0

def _make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return vc

def _record(vc, t):
    return dict(
        t=t,
        HR=vc.heart.heart_rate,
        MAP=vc.heart.mean_arterial_pressure,
        CO=vc.heart.heart_rate * vc.heart.stroke_volume,
        blood_volume_mL=vc.heart.circulating_volume_ml,
    )

def _pack_state(vc):
    return vc._pack_unified_state()

def _blood_loss(vc):
    vc.set_blood_loss_scenario(
        t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME,
        duration=20.0, width=2.0)

def run_pure_euler(dt):
    vc = _make_vc()
    _blood_loss(vc)
    y = _pack_state(vc)
    _ = vc._unified_rhs(0.0, y)
    save_interval = int(DT_SAVE / dt)
    total_steps = int(T_END / dt)
    time_series = [_record(vc, 0.0)]
    for step_i in range(total_steps):
        dydt = vc._unified_rhs(vc.current_time_s, y)
        y = y + dt * dydt
        vc._unpack_unified_state(y)
        vc.current_time_s += dt
        if step_i % save_interval == 0:
            time_series.append(_record(vc, vc.current_time_s))
    return time_series

def load_reference():
    with open(os.path.join(_EXPERIMENTS_DIR, 'convergence_study_data.json')) as f:
        data = json.load(f)
    return data['reference']['time_series']

import json

ref_ts = load_reference()
print("Reference loaded. Testing key dt values...")
print()

key_dts = [0.5, 0.25, 0.1, 0.05, 0.01, 0.005, 0.001]

for dt in key_dts:
    print(f"  dt={dt}...", end=" ", flush=True)
    ts = run_pure_euler(dt)
    test_t = np.array([p["t"] for p in ts])
    test_map = np.array([p["MAP"] for p in ts])
    co_vals = np.array([p["CO"] for p in ts])
    ref_t = np.array([p["t"] for p in ref_ts])
    ref_map = np.array([p["MAP"] for p in ref_ts])
    t_min = max(test_t.min(), ref_t.min())
    t_max = min(test_t.max(), ref_t.max())
    ref_clip = ref_t[(ref_t >= t_min) & (ref_t <= t_max)]
    f_map = interp1d(test_t, test_map, kind="linear", fill_value="extrapolate")
    test_map_interp = f_map(ref_clip)
    ref_map_clip = ref_map[(ref_t >= t_min) & (ref_t <= t_max)]
    max_dev = float(np.max(np.abs(test_map_interp - ref_map_clip)))
    has_nan = np.any(np.isnan(co_vals))
    has_neg = np.any(co_vals < 0)
    # Find last good point
    last_good_idx = 0
    for i, p in enumerate(ts):
        if not np.isnan(p["CO"]) and p["CO"] > 0:
            last_good_idx = i
    last_good_t = ts[last_good_idx]["t"]
    last_good_map = ts[last_good_idx]["MAP"]
    status = "NaN" if has_nan else ("NEG" if has_neg else "OK")
    print(f"max_dev={max_dev:.2f}, last_good_t={last_good_t:.1f}s MAP={last_good_map:.1f}, status={status}")

print()
print("If status=OK for all dt < 0.1, dt/dt fix worked.")
print("If status=NaN/NEG persists, Pure Euler still explodes (stiffness).")