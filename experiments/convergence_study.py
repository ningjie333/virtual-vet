"""
P0-1: Convergence Study — State-Vector L2 Norm

Goal: Prove Euler convergence behavior and establish reference quality.
Two paths compared:
  1. Pure Euler: y_new = y + dt * f_unified(t, y)  [one unified RHS call]
  2. Sequential Euler: existing vc.step() [organ-by-organ loop]

dt grid: {0.5, 0.25, 0.1, 0.05, 0.025, 0.01, 0.005, 0.0025, 0.001, 0.0005, 0.0001}
Reference: Radau rtol=1e-10, atol=1e-12, max_step=0.1
Output: convergence_study_data.json
"""

import sys, os, time, json, types
import numpy as np
from scipy.integrate import solve_ivp

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
_DATA_OUT = os.path.join(_EXPERIMENTS_DIR, "convergence_study_data.json")

if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# ── minimal module loader ───────────────────────────────────────────────
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

# ── experiment config ────────────────────────────────────────────────────
WEIGHT_KG = 20.0
T_END = 60.0
DT_SAVE = 2.0
BLOOD_LOSS_TIME = 5.0
BLOOD_LOSS_VOLUME = 400.0

DT_GRID = [0.5, 0.25, 0.1, 0.05, 0.025, 0.01, 0.005, 0.0025,
           0.001, 0.0005, 0.0001]

# ── helpers ────────────────────────────────────────────────────────────
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
    """Pack full state vector y for L2 norm computation."""
    return vc._pack_unified_state()


def _blood_loss(vc):
    vc.set_blood_loss_scenario(
        t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME,
        duration=20.0, width=2.0)


# ── 1. Generate reference trajectory ──────────────────────────────────
def generate_reference():
    print("=== Generating reference trajectory (Radau rtol=1e-10)...")
    vc = _make_vc()
    _blood_loss(vc)
    y0 = _pack_state(vc)
    _ = vc._unified_rhs(0.0, y0)

    def rhs(t, y):
        vc._cached_inputs.clear()
        vc._unpack_unified_state(y)
        return vc._unified_rhs(t, y)

    sol = solve_ivp(
        rhs, (0.0, T_END), y0,
        method="Radau",
        rtol=1e-10, atol=1e-12,
        max_step=0.1,
        dense_output=True,
    )

    t_dense = np.linspace(0, T_END, 500)
    y_ref = sol.sol(t_dense).T   # shape (500, N)

    ref_ts = []
    for i, t in enumerate(t_dense):
        vc._unpack_unified_state(y_ref[i])
        ref_ts.append(_record(vc, t))

    # State vector norm baseline (L2 of reference at t=0 vs t=end)
    y_ref_T0 = y_ref[0]
    n_vars = len(y_ref_T0)

    ref_info = {
        "method": "Ref (Radau rtol=1e-10)",
        "time_s": 0.0,   # placeholder
        "n_vars": n_vars,
        "t_end": float(t_dense[-1]),
        "n_points": len(t_dense),
        "time_series": ref_ts,
    }

    print(f"  Reference: {n_vars} variables, {len(t_dense)} points, "
          f"min_MAP={min(p['MAP'] for p in ref_ts):.2f} mmHg")

    return ref_info, t_dense, y_ref


# ── 2. Pure Euler: single unified RHS call per step ─────────────────────
def run_pure_euler(vc_init, dt):
    vc = _make_vc()
    _blood_loss(vc)
    y = _pack_state(vc)
    _ = vc._unified_rhs(0.0, y)

    save_interval = int(DT_SAVE / dt)
    total_steps = int(T_END / dt)
    t0 = time.perf_counter()
    time_series = [_record(vc, 0.0)]

    for step_i in range(total_steps):
        dydt = vc._unified_rhs(vc.current_time_s, y)
        y = y + dt * dydt
        vc._unpack_unified_state(y)
        vc.current_time_s += dt
        if step_i % save_interval == 0:
            time_series.append(_record(vc, vc.current_time_s))

    elapsed = time.perf_counter() - t0
    return dict(success=True, time_s=elapsed, time_series=time_series)


# ── 3. Sequential Euler: existing vc.step() loop ──────────────────────
def run_sequential_euler(dt):
    vc = _make_vc()
    _blood_loss(vc)
    y0 = _pack_state(vc)
    _ = vc._unified_rhs(0.0, y0)

    save_interval = int(DT_SAVE / dt)
    total_steps = int(T_END / dt)
    t0 = time.perf_counter()
    time_series = [_record(vc, 0.0)]

    for step_i in range(total_steps):
        vc.step()
        if step_i % save_interval == 0:
            time_series.append(_record(vc, vc.current_time_s))

    elapsed = time.perf_counter() - t0
    return dict(success=True, time_s=elapsed, time_series=time_series)


# ── 4. Compute L2 / MAP errors vs reference ──────────────────────────
def compute_errors(test_ts, ref_ts, n_vars):
    """Interpolate test trajectory to reference time points, compute norms."""
    test_t = np.array([p["t"] for p in test_ts])
    test_map = np.array([p["MAP"] for p in test_ts])
    ref_t = np.array([p["t"] for p in ref_ts])
    ref_map = np.array([p["MAP"] for p in ref_ts])

    # Align: clip to common time range
    t_min = max(test_t.min(), ref_t.min())
    t_max = min(test_t.max(), ref_t.max())
    ref_clip = ref_t[(ref_t >= t_min) & (ref_t <= t_max)]
    if len(ref_clip) == 0:
        return None

    from scipy.interpolate import interp1d
    f_map = interp1d(test_t, test_map, kind="linear", fill_value="extrapolate")
    test_map_interp = f_map(ref_clip)
    ref_map_clip = ref_map[(ref_t >= t_min) & (ref_t <= t_max)]

    map_devs = np.abs(test_map_interp - ref_map_clip)
    max_map_dev = float(np.max(map_devs))
    rmse_map = float(np.sqrt(np.mean(map_devs**2)))

    return dict(max_MAP_dev=max_map_dev, RMSE_MAP=rmse_map)


# ── main ────────────────────────────────────────────────────────────────
def main():
    ref_info, ref_tDense, y_ref = generate_reference()

    # Build ref lookup
    ref_ts = ref_info["time_series"]
    n_vars = ref_info["n_vars"]

    results = {
        "reference": ref_info,
        "pure_euler": [],
        "sequential_euler": [],
    }

    # Run Pure Euler sweep
    print("\n=== Pure Euler dt sweep ===")
    for dt in DT_GRID:
        print(f"  dt={dt}...", end=" ", flush=True)
        r = run_pure_euler(None, dt)
        errs = compute_errors(r["time_series"], ref_ts, n_vars)
        r["max_MAP_dev"] = errs["max_MAP_dev"] if errs else None
        r["RMSE_MAP"] = errs["RMSE_MAP"] if errs else None
        r["dt"] = dt
        results["pure_euler"].append(r)
        print(f"done  time={r['time_s']:.2f}s  max_dev={r['max_MAP_dev']:.3f}")

    # Run Sequential Euler sweep
    print("\n=== Sequential Euler dt sweep ===")
    for dt in DT_GRID:
        print(f"  dt={dt}...", end=" ", flush=True)
        r = run_sequential_euler(dt)
        errs = compute_errors(r["time_series"], ref_ts, n_vars)
        r["max_MAP_dev"] = errs["max_MAP_dev"] if errs else None
        r["RMSE_MAP"] = errs["RMSE_MAP"] if errs else None
        r["dt"] = dt
        results["sequential_euler"].append(r)
        print(f"done  time={r['time_s']:.2f}s  max_dev={r['max_MAP_dev']:.3f}")

    # Save
    with open(_DATA_OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n=== Summary (RMSE_MAP vs Ref rtol=1e-10) ===")
    print(f"{'dt':>8} {'Pure Euler RMSE':>16} {'Seq Euler RMSE':>16}")
    print("-" * 42)
    for pe, se in zip(results["pure_euler"], results["sequential_euler"]):
        print(f"{pe['dt']:>8.4f} {pe['RMSE_MAP']:>16.3f} {se['RMSE_MAP']:>16.3f}")

    print(f"\nData → {_DATA_OUT}")


if __name__ == "__main__":
    main()