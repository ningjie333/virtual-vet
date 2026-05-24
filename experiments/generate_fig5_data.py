"""Generate convergence data for Figure 5 after _EPS fix — T_END=10s (fast)."""
import sys, os, types, time, json
import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import interp1d

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
T_END = 10.0
DT_SAVE = 1.0
BLOOD_LOSS_TIME = 5.0
BLOOD_LOSS_VOLUME = 400.0

def _make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    vc.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME,
                               duration=20.0, width=2.0)
    return vc

def _record(vc, t):
    return dict(t=t, HR=vc.heart.heart_rate, MAP=vc.heart.mean_arterial_pressure,
               CO=vc.heart.heart_rate * vc.heart.stroke_volume,
               blood_volume_mL=vc.heart.circulating_volume_ml)

def _pack_state(vc):
    return vc._pack_unified_state()

# ── 1. Reference (Radau rtol=1e-5, fast) ───────────────────────────────────
print("=== Reference (Radau rtol=1e-5, T_END=10s) ===")
vc = _make_vc()
y0 = _pack_state(vc)
_ = vc._unified_rhs(0.0, y0)
def rhs(t, y):
    vc._cached_inputs.clear()
    vc._unpack_unified_state(y)
    return vc._unified_rhs(t, y)
sol = solve_ivp(rhs, (0.0, T_END), y0, method="Radau", rtol=1e-5, atol=1e-8, max_step=0.5, dense_output=True)
t_dense = np.linspace(0, T_END, 200)
y_ref = sol.sol(t_dense).T
ref_ts = []
for i, t in enumerate(t_dense):
    vc._unpack_unified_state(y_ref[i])
    ref_ts.append(_record(vc, t))
ref_t = np.array([p["t"] for p in ref_ts])
ref_map = np.array([p["MAP"] for p in ref_ts])
print(f"  Reference done: {len(ref_ts)} pts, min_MAP={ref_map.min():.2f}")

# ── 2. Pure Euler sweep ─────────────────────────────────────────────────────
print("\n=== Pure Euler ===")
DT_GRID = [0.5, 0.25, 0.1, 0.05, 0.025, 0.01, 0.005, 0.0025, 0.001]
pure_euler = []
for dt in DT_GRID:
    t0 = time.perf_counter()
    vc = _make_vc()
    y = _pack_state(vc)
    _ = vc._unified_rhs(0.0, y)
    total_steps = int(T_END / dt)
    save_interval = max(1, int(DT_SAVE / dt))
    ts = [_record(vc, 0.0)]
    for step_i in range(total_steps):
        dydt = vc._unified_rhs(vc.current_time_s, y)
        y = y + dt * dydt
        vc._unpack_unified_state(y)
        vc.current_time_s += dt
        if step_i % save_interval == 0:
            ts.append(_record(vc, vc.current_time_s))
    elapsed = time.perf_counter() - t0

    test_t = np.array([p["t"] for p in ts])
    test_map = np.array([p["MAP"] for p in ts])
    test_co = np.array([p["CO"] for p in ts])
    has_nan = np.any(np.isnan(test_co))

    common_t = ref_t[(ref_t >= test_t.min()) & (ref_t <= test_t.max())]
    rmse = 0.0
    max_dev = 0.0
    if len(common_t) > 0 and not has_nan:
        f = interp1d(test_t, test_map, kind="linear", fill_value="extrapolate", bounds_error=False)
        ref_mask = (ref_t >= common_t.min()) & (ref_t <= common_t.max())
        devs = np.abs(f(common_t) - ref_map[ref_mask])
        rmse = float(np.sqrt(np.mean(devs**2)))
        max_dev = float(np.max(devs))

    pure_euler.append({
        "dt": dt, "time_s": elapsed, "time_series": ts,
        "RMSE_MAP": rmse, "max_MAP_dev": max_dev,
        "success": not has_nan,
    })
    print(f"  dt={dt:.4f} t={vc.current_time_s:.2f}s RMSE={rmse:.3f} max_dev={max_dev:.3f} nan={has_nan} elapsed={elapsed:.1f}s")

# ── 3. Sequential Euler sweep ─────────────────────────────────────────────
print("\n=== Sequential Euler ===")
DT_SEQ = [0.1, 0.05, 0.01]
seq_euler = []
for dt in DT_SEQ:
    t0 = time.perf_counter()
    vc = _make_vc()
    y = _pack_state(vc)
    _ = vc._unified_rhs(0.0, y)
    save_interval = max(1, int(DT_SAVE / 0.01))  # internal dt=0.01 for step()
    n_steps = int(T_END / 0.01)
    ts = [_record(vc, 0.0)]
    for step_i in range(n_steps):
        vc.step()
        if step_i % save_interval == 0:
            ts.append(_record(vc, vc.current_time_s))
    elapsed = time.perf_counter() - t0

    test_t = np.array([p["t"] for p in ts])
    test_map = np.array([p["MAP"] for p in ts])
    common_t = ref_t[(ref_t >= test_t.min()) & (ref_t <= test_t.max())]
    rmse = 0.0
    max_dev = 0.0
    if len(common_t) > 0:
        f = interp1d(test_t, test_map, kind="linear", fill_value="extrapolate", bounds_error=False)
        ref_mask = (ref_t >= common_t.min()) & (ref_t <= common_t.max())
        devs = np.abs(f(common_t) - ref_map[ref_mask])
        rmse = float(np.sqrt(np.mean(devs**2)))
        max_dev = float(np.max(devs))

    seq_euler.append({
        "dt": dt, "time_s": elapsed, "time_series": ts,
        "RMSE_MAP": rmse, "max_MAP_dev": max_dev,
        "success": True,
    })
    print(f"  internal_dt={vc.dt} RMSE={rmse:.3f} max_dev={max_dev:.3f} elapsed={elapsed:.1f}s")

# ── Save ──────────────────────────────────────────────────────────────────────
out = {
    "reference": {"method": "Radau rtol=1e-5", "time_series": ref_ts, "t_end": T_END},
    "pure_euler": pure_euler,
    "sequential_euler": seq_euler,
}
out_path = os.path.join(_EXPERIMENTS_DIR, "convergence_study_data.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

print(f"\n=== Summary ===")
print(f"{'dt':>8} {'Pure Euler RMSE':>16} {'Seq Euler RMSE':>16}")
for i, dt in enumerate(DT_GRID):
    pe_rmse = pure_euler[i]["RMSE_MAP"]
    print(f"{dt:>8.4f} {pe_rmse:>16.3f}", end="")
    if i < len(seq_euler):
        print(f" {seq_euler[i]['RMSE_MAP']:>16.3f}")
    else:
        print()
print(f"\nData → {out_path}")