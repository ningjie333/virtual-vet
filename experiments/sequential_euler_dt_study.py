"""
Sequential Euler convergence study — does RMSE vary with step() dt?

The step() method uses a FIXED internal dt (vc.dt = 0.1s by default).
This test checks whether running step() with different internal dt values
produces different RMSE vs the BDF reference.

Key question: does "Sequential Euler" RMSE depend on the step() dt
even when both reach the same physical time?
"""
import os, sys, types, time as time_module, json
import numpy as np

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
_OUT_JSON = os.path.join(_EXPERIMENTS_DIR, "sequential_euler_dt_study.json")

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
SAVE_DT = 0.5  # record interval
DT_GRID = [0.1, 0.05, 0.025, 0.01]  # step() internal dt values to test

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

# BDF reference (same as convergence_study_v4)
def run_bdf_reference():
    print("  BDF reference...")
    vc = make_vc()
    y0 = pack(vc)
    _ = vc._unified_rhs(0.0, y0)

    def rhs(t, y):
        unpack_and_record(vc, y, t)
        return vc._unified_rhs(t, y)

    sol = solve_ivp(rhs, (0.0, T_END), y0, method="BDF",
                    rtol=1e-6, atol=1e-8, max_step=0.5, dense_output=True)
    t_dense = np.arange(0, T_END + SAVE_DT, SAVE_DT)
    y_dense = sol.sol(t_dense).T
    records = [unpack_and_record(vc, y_dense[i], t_dense[i]) for i in range(len(t_dense))]
    return records, t_dense

# Sequential Euler: run step() for a given internal dt
def run_sequential_euler(vc, steps, save_interval):
    """Run step() for `steps` iterations, record at save_interval."""
    records = []
    for i in range(steps):
        vc.step()
        if i % save_interval == 0:
            records.append({
                "t": float(vc.current_time_s),
                "MAP": float(vc.heart.mean_arterial_pressure),
                "HR": float(vc.heart.heart_rate),
                "BV": float(vc.heart.circulating_volume_ml),
            })
    return records

def main():
    print(f"\n=== Sequential Euler dt Sensitivity ===")
    print(f"T_END={T_END}s, step() dt grid: {DT_GRID}")

    # 1. BDF reference
    print("\n[1/2] BDF reference...")
    bdf_ts, t_bdf = run_bdf_reference()
    map_bdf = np.array([p["MAP"] for p in bdf_ts])
    print(f"  BDF MAP range: [{map_bdf.min():.2f}, {map_bdf.max():.2f}]")

    # 2. Sequential Euler at different step() dt values
    print("\n[2/2] Sequential Euler (step() dt sensitivity)...")
    results = []

    for step_dt in DT_GRID:
        n_steps = int(T_END / step_dt)
        save_interval = max(1, int(SAVE_DT / step_dt))

        vc = make_vc()
        vc.dt = step_dt  # set internal step size
        y0 = pack(vc)
        # Initialize module state
        _ = vc._unified_rhs(0.0, y0)

        t0 = time_module.time()
        seq_ts = run_sequential_euler(vc, n_steps, save_interval)
        elapsed = time_module.time() - t0

        map_vals = np.array([p["MAP"] for p in seq_ts])
        t_seq = np.array([p["t"] for p in seq_ts])

        # Interpolate to BDF time points for RMSE
        from scipy.interpolate import interp1d
        f_seq = interp1d(t_seq, map_vals, kind="linear", fill_value="extrapolate")
        n_common = min(len(t_bdf), len(t_seq))
        rmse = float(np.sqrt(np.mean((map_bdf[:n_common] - f_seq(t_bdf[:n_common]))**2)))

        results.append({
            "step_dt": step_dt,
            "n_steps": n_steps,
            "rmse_MAP": rmse,
            "MAP_range": [float(map_vals.min()), float(map_vals.max())],
            "time_s": elapsed,
        })
        print(f"  step_dt={step_dt:.4f}: RMSE={rmse:.4f}, MAP=[{map_vals.min():.2f},{map_vals.max():.2f}], {n_steps} steps, {elapsed:.1f}s")

    # Save
    output = {
        "metadata": {
            "T_END": T_END,
            "body_weight_kg": WEIGHT_KG,
            "blood_loss_ml": 400.0,
            "reference": "BDF rtol=1e-6",
            "step_dt_grid": DT_GRID,
            "note": "Sequential Euler uses vc.step() with vc.dt=step_dt",
        },
        "reference": {
            "method": "BDF rtol=1e-6",
            "time_series": bdf_ts,
            "MAP_range": [float(map_bdf.min()), float(map_bdf.max())],
        },
        "sequential_euler": results,
    }

    with open(_OUT_JSON, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to {_OUT_JSON}")

    # Analysis
    print("\n Analysis:")
    print(f"  {'step_dt':>8}  {'RMSE':>8}  {'ΔRMSE':>8}")
    prev_rmse = None
    for r in results:
        delta = f"{r['rmse_MAP'] - prev_rmse:+.4f}" if prev_rmse is not None else "  (base)"
        print(f"  {r['step_dt']:>8.4f}  {r['rmse_MAP']:>8.4f}  {delta:>8}")
        prev_rmse = r['rmse_MAP']

if __name__ == "__main__":
    main()