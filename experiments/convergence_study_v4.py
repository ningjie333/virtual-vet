"""
Convergence Study v4 — BDF reference, Pure Euler dt grid
After lung.py dRR/dTV fix: RMSE ∝ dt (1st order convergence confirmed)
"""
import os, sys, types, time as time_module, json
import numpy as np

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
_OUT_JSON = os.path.join(_EXPERIMENTS_DIR, "convergence_study_v4.json")

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
from scipy.integrate import solve_ivp

WEIGHT_KG = 20.0
T_END = 60.0
DT_GRID = [0.1, 0.05, 0.025, 0.01, 0.005, 0.002, 0.001, 0.0005, 0.0002, 0.0001]
SAVE_DT = 0.5

def make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)
    vc._cached_inputs.clear()
    return vc

def pack(vc):
    return vc._pack_unified_state()

def unpack_and_record(vc, y, t):
    vc._cached_inputs.clear()
    vc._unpack_unified_state(y)
    return {
        "t": float(t),
        "MAP": float(vc.heart.mean_arterial_pressure),
        "HR": float(vc.heart.heart_rate),
        "BV": float(vc.heart.circulating_volume_ml),
    }

def run_bdf_reference():
    print("  BDF reference (rtol=1e-6, max_step=0.5)...")
    vc = make_vc()
    y0 = pack(vc)
    _ = vc._unified_rhs(0.0, y0)

    def rhs(t, y):
        unpack_and_record(vc, y, t)
        return vc._unified_rhs(t, y)

    t0 = time_module.time()
    sol = solve_ivp(rhs, (0.0, T_END), y0, method="BDF",
                    rtol=1e-6, atol=1e-8, max_step=0.5, dense_output=True)
    print(f"    BDF done in {time_module.time()-t0:.1f}s, nfev={sol.nfev}")

    t_dense = np.arange(0, T_END + SAVE_DT, SAVE_DT)
    y_dense = sol.sol(t_dense).T
    records = [unpack_and_record(vc, y_dense[i], t_dense[i]) for i in range(len(t_dense))]
    return records, t_dense

def run_pure_euler(vc, y0, dt, t_end=T_END, save_dt=SAVE_DT):
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

def main():
    print(f"\n=== Convergence Study v4 ===")
    print(f"T_END={T_END}s, Pure Euler dt grid: {DT_GRID}")

    # 1. BDF reference
    print("\n[1/2] BDF reference...")
    bdf_ts, t_bdf = run_bdf_reference()
    map_bdf = np.array([p["MAP"] for p in bdf_ts])
    print(f"  BDF MAP range: [{map_bdf.min():.2f}, {map_bdf.max():.2f}]")

    # 2. Pure Euler dt grid
    print("\n[2/2] Pure Euler dt grid...")
    results = []
    for dt in DT_GRID:
        vc = make_vc()
        y0 = pack(vc)
        _ = vc._unified_rhs(0.0, y0)
        t0 = time_module.time()
        ts = run_pure_euler(vc, y0, dt, T_END, SAVE_DT)
        elapsed = time_module.time() - t0
        map_vals = np.array([p["MAP"] for p in ts])
        t_eul = np.array([p["t"] for p in ts])

        # Interpolate to BDF time points
        from scipy.interpolate import interp1d
        f_eul = interp1d(t_eul, map_vals, kind="linear", fill_value="extrapolate")
        n_common = min(len(t_bdf), len(t_eul))
        rmse = float(np.sqrt(np.mean((map_bdf[:n_common] - f_eul(t_bdf[:n_common]))**2)))

        results.append({
            "dt": dt,
            "rmse_MAP": rmse,
            "MAP_range": [float(map_vals.min()), float(map_vals.max())],
            "n_steps": int(T_END / dt),
        })
        print(f"  dt={dt:.4f}: RMSE={rmse:.6f}, MAP=[{map_vals.min():.2f},{map_vals.max():.2f}], {elapsed:.1f}s")

    # Save
    output = {
        "metadata": {
            "T_END": T_END,
            "body_weight_kg": WEIGHT_KG,
            "blood_loss_ml": 400.0,
            "reference": "BDF rtol=1e-6",
            "pure_euler_dt_grid": DT_GRID,
        },
        "reference": {
            "method": "BDF rtol=1e-6",
            "time_series": bdf_ts,
            "MAP_range": [float(map_bdf.min()), float(map_bdf.max())],
        },
        "pure_euler": results,
    }

    with open(_OUT_JSON, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to {_OUT_JSON}")

    # Convergence order
    print("\n Convergence order (log-log):")
    for i in range(1, len(results)):
        dt0, dt1 = results[i-1]["dt"], results[i]["dt"]
        e0, e1 = results[i-1]["rmse_MAP"], results[i]["rmse_MAP"]
        if e0 > 0 and dt0 > 0:
            order = np.log(e1/e0) / np.log(dt1/dt0)
            print(f"  dt {dt0:.4f} → {dt1:.4f}: order={order:.2f}")

if __name__ == "__main__":
    main()