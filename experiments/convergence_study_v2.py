"""
Convergence Study v2 — BDF reference, Pure Euler dt grid, one Sequential point

Redesigned per user Option A:
  - BDF rtol=1e-6, max_step=0.5s → reliable ~2s reference
  - Pure Euler: 11 dt values from 0.5 down to 0.0001
  - Sequential Euler: ONE point (dt=0.1, internal dt is FIXED at 0.1 per vc.step() bug)
  - Radau rtol=1e-4: secondary implicit method comparison
"""

import json, os, sys, types, time as time_module
import numpy as np

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
_OUT_JSON = os.path.join(_EXPERIMENTS_DIR, "convergence_study_v2.json")

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

WEIGHT_KG = 20.0
T_END = 60.0
DT_EULER_GRID = [0.1, 0.05, 0.025, 0.01, 0.005, 0.0025, 0.001]
SAVE_DT = 0.5

def _make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return vc

def _blood_loss(vc):
    vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)

def _pack_state(vc):
    return vc._pack_unified_state()

def _unpack_and_record(vc, y, t):
    vc._cached_inputs.clear()
    vc._unpack_unified_state(y)
    return {
        "t": float(t),
        "MAP": float(vc.heart.mean_arterial_pressure),
        "HR": float(vc.heart.heart_rate),
        "BV": float(vc.heart.circulating_volume_ml),
    }

def run_bdf_reference(t_end=T_END):
    from scipy.integrate import solve_ivp
    vc = _make_vc()
    _blood_loss(vc)
    y0 = _pack_state(vc)
    _ = vc._unified_rhs(0.0, y0)

    def rhs(t, y):
        _unpack_and_record(vc, y, t)
        return vc._unified_rhs(t, y)

    print("  BDF reference (rtol=1e-6, max_step=0.5)...")
    t0 = time_module.time()
    sol = solve_ivp(rhs, (0.0, t_end), y0, method="BDF",
                    rtol=1e-6, atol=1e-6, max_step=0.5, dense_output=True)
    print(f"    BDF done in {time_module.time()-t0:.1f}s")

    t_dense = np.arange(0, t_end + SAVE_DT, SAVE_DT)
    y_dense = sol.sol(t_dense).T
    records = [_unpack_and_record(vc, y_dense[i], t_dense[i]) for i in range(len(t_dense))]
    return sol, sol.y, records, t_dense

def run_pure_euler(vc, y0, dt, t_end=T_END, save_dt=SAVE_DT):
    """Pure Euler: y_new = y + dt * f_unified(t, y)"""
    total_steps = int(t_end / dt)
    save_interval = max(1, int(save_dt / dt))
    y = y0.copy()
    vc._cached_inputs.clear()
    vc._unpack_unified_state(y)
    vc.current_time_s = 0.0

    records = []
    for i in range(total_steps):
        dydt = vc._unified_rhs(vc.current_time_s, y)
        y = y + dt * dydt
        vc._unpack_unified_state(y)
        vc.current_time_s += dt
        if i % save_interval == 0:
            records.append({
                "t": float(vc.current_time_s),
                "MAP": float(vc.heart.mean_arterial_pressure),
                "HR": float(vc.heart.heart_rate),
                "BV": float(vc.heart.circulating_volume_ml),
            })
    return records

def run_sequential_euler(vc, t_end=T_END, save_dt=SAVE_DT, dt: float = None):
    """Sequential Euler via vc.step(dt) — respects external dt parameter."""
    step_dt = dt if dt is not None else 0.1
    save_interval = max(1, int(save_dt / step_dt))
    records = []
    n_steps = 0
    while vc.current_time_s < t_end:
        vc.step(dt=step_dt)
        n_steps += 1
        if n_steps % save_interval == 0:
            records.append({
                "t": float(vc.current_time_s),
                "MAP": float(vc.heart.mean_arterial_pressure),
                "HR": float(vc.heart.heart_rate),
                "BV": float(vc.heart.circulating_volume_ml),
            })
    return records

def run_radau_rtolve4(t_end=T_END):
    from scipy.integrate import solve_ivp
    vc = _make_vc()
    _blood_loss(vc)
    y0 = _pack_state(vc)
    _ = vc._unified_rhs(0.0, y0)

    def rhs(t, y):
        _unpack_and_record(vc, y, t)
        return vc._unified_rhs(t, y)

    print("  Radau rtol=1e-4...")
    t0 = time_module.time()
    sol = solve_ivp(rhs, (0.0, t_end), y0, method="Radau",
                    rtol=1e-4, atol=1e-8, max_step=0.5, dense_output=True)
    print(f"    Radau done in {time_module.time()-t0:.1f}s")

    t_dense = np.arange(0, t_end + SAVE_DT, SAVE_DT)
    y_dense = sol.sol(t_dense).T
    records = [_unpack_and_record(vc, y_dense[i], t_dense[i]) for i in range(len(t_dense))]
    return records, t_dense

def compute_rmse(map_ref, map_test):
    return float(np.sqrt(np.mean((np.array(map_ref) - np.array(map_test))**2)))

def main():
    print(f"\n=== Convergence Study v2 ===")
    print(f"T_END={T_END}s, Pure Euler dt grid: {DT_EULER_GRID}")

    # 1. BDF reference
    print("\n[1/4] BDF reference...")
    bdf_sol, bdf_y_full, bdf_ts, t_bdf = run_bdf_reference(T_END)
    map_bdf = np.array([p["MAP"] for p in bdf_ts])
    print(f"  BDF MAP range: [{map_bdf.min():.2f}, {map_bdf.max():.2f}] mmHg")

    # 2. Pure Euler dt grid
    print("\n[2/4] Pure Euler dt grid...")
    vc_euler = _make_vc()
    _blood_loss(vc_euler)
    y0_euler = _pack_state(vc_euler)
    _ = vc_euler._unified_rhs(0.0, y0_euler)

    # Need separate vc for each run to avoid state pollution
    pure_results = []
    for dt in DT_EULER_GRID:
        vc = _make_vc()
        _blood_loss(vc)
        y0 = _pack_state(vc)
        _ = vc._unified_rhs(0.0, y0)
        t0 = time_module.time()
        ts = run_pure_euler(vc, y0, dt, T_END, SAVE_DT)
        elapsed = time_module.time() - t0
        map_vals = np.array([p["MAP"] for p in ts])

        # Interpolate to BDF time points for RMSE
        from scipy.interpolate import interp1d
        t_eul = np.array([p["t"] for p in ts])
        f_eul = interp1d(t_eul, map_vals, kind="linear", fill_value="extrapolate")
        n_common = min(len(t_bdf), len(t_eul))
        common_t = t_bdf[:n_common]
        rmse = compute_rmse(map_bdf[:n_common], f_eul(common_t))

        pure_results.append({
            "dt": dt,
            "rmse_MAP": rmse,
            "time_s": elapsed,
            "MAP_range": [float(map_vals.min()), float(map_vals.max())],
            "n_steps": int(T_END / dt),
        })
        print(f"  dt={dt:.4f}: RMSE={rmse:.4f}, MAP=[{map_vals.min():.1f},{map_vals.max():.1f}], {elapsed:.1f}s")

    # 3. Sequential Euler (one point per dt grid, matching Pure Euler's dt)
    print("\n[3/4] Sequential Euler (dt-matching)...")
    vc_seq = _make_vc()
    _blood_loss(vc_seq)
    y0_seq = _pack_state(vc_seq)
    _ = vc_seq._unified_rhs(0.0, y0_seq)
    seq_results = []
    for dt in DT_EULER_GRID:
        vc = _make_vc()
        _blood_loss(vc)
        y0 = _pack_state(vc)
        _ = vc._unified_rhs(0.0, y0)
        t0 = time_module.time()
        ts = run_sequential_euler(vc, T_END, SAVE_DT, dt=dt)
        elapsed = time_module.time() - t0
        map_seq = np.array([p["MAP"] for p in ts])
        t_seq = np.array([p["t"] for p in ts])
        from scipy.interpolate import interp1d
        f_seq = interp1d(t_seq, map_seq, kind="linear", fill_value="extrapolate")
        n_common = min(len(t_bdf), len(t_seq))
        seq_rmse = compute_rmse(map_bdf[:n_common], f_seq(t_bdf[:n_common]))
        seq_results.append({
            "dt": dt,
            "rmse_MAP": seq_rmse,
            "time_s": elapsed,
            "MAP_range": [float(map_seq.min()), float(map_seq.max())],
        })
        print(f"  dt={dt:.4f}: RMSE={seq_rmse:.4f}, MAP=[{map_seq.min():.1f},{map_seq.max():.1f}], {elapsed:.1f}s")

    # 4. Radau rtol=1e-4 (secondary comparison)
    print("\n[4/4] Radau rtol=1e-4...")
    rad_ts, t_rad = run_radau_rtolve4(T_END)
    map_rad = np.array([p["MAP"] for p in rad_ts])
    f_rad = interp1d(t_rad, map_rad, kind="linear", fill_value="extrapolate")
    n_common = min(len(t_bdf), len(t_rad))
    rad_rmse = compute_rmse(map_bdf[:n_common], f_rad(t_bdf[:n_common]))
    print(f"  Radau rtol=1e-4 RMSE={rad_rmse:.4f}, MAP=[{map_rad.min():.1f},{map_rad.max():.1f}]")

    # Build output
    out = {
        "metadata": {
            "T_END": T_END,
            "body_weight_kg": WEIGHT_KG,
            "blood_loss_ml": 400.0,
            "reference": "BDF rtol=1e-6, max_step=0.5s",
            "pure_euler_dt_grid": DT_EULER_GRID,
            "save_dt": SAVE_DT,
        },
        "reference": {
            "method": "BDF rtol=1e-6",
            "time_series": bdf_ts,
            "MAP_range": [float(map_bdf.min()), float(map_bdf.max())],
        },
        "pure_euler": pure_results,
        "sequential_euler": {
            "dt_note": "vc.step(dt) now respects external dt param — fixed",
            "results_per_dt": seq_results,
        },
        "radau_rtolve4": {
            "rmse_MAP": rad_rmse,
            "MAP_range": [float(map_rad.min()), float(map_rad.max())],
            "time_series": rad_ts,
        },
    }

    with open(_OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Saved → {_OUT_JSON}")

    # Print summary
    print("\n=== Convergence Summary ===")
    print(f"{'dt':>10}  {'RMSE':>8}  {'Order':>6}")
    prev_rmse = None
    for r in pure_results:
        dt = r["dt"]
        rmse = r["rmse_MAP"]
        if prev_rmse is not None and rmse > 0 and prev_rmse > 0:
            order = float(np.log(prev_rmse / rmse) / np.log(2))
            print(f"{dt:>10.4f}  {rmse:>8.4f}  {order:>6.2f}")
        else:
            print(f"{dt:>10.4f}  {rmse:>8.4f}  {'--':>6}")
        prev_rmse = rmse
    print(f"\nSequential Euler (dt-respecting):")
    for r in seq_results:
        print(f"  dt={r['dt']:.4f}: RMSE={r['rmse_MAP']:.4f}")
    print(f"Radau rtol=1e-4: RMSE={rad_rmse:.4f}")

if __name__ == "__main__":
    main()