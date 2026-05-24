"""
P0-2: Pure Euler vs Sequential Euler vs Radau — Three-Way Comparison

Pure Euler:  y_new = y + dt * f_unified(t, y)   [ONE unified RHS call per step]
Sequential Euler: existing vc.step() loop         [organ-by-organ intermediate states]
Radau:       solve_ivp(..., method="Radau")        [reference implicit solver]

This script can run independently of convergence_study.py.
Output: pure_vs_sequential_data.json
"""

import sys, os, time, json, types
import numpy as np
from scipy.integrate import solve_ivp

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
_DATA_OUT = os.path.join(_EXPERIMENTS_DIR, "pure_vs_sequential_data.json")

if _SRC_DIR not in sys.path:
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
DT_EULER = 0.01   # moderate dt for Euler comparison
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


def _blood_loss(vc):
    vc.set_blood_loss_scenario(
        t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME,
        duration=20.0, width=2.0)


# ── Pure Euler: one unified RHS call per step ──────────────────────────
def run_pure_euler(dt, t_end=T_END):
    vc = _make_vc()
    _blood_loss(vc)
    y = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y)

    save_interval = max(1, int(DT_SAVE / dt))
    total_steps = int(t_end / dt)
    t0 = time.perf_counter()
    time_series = [_record(vc, 0.0)]

    for i in range(total_steps):
        dydt = vc._unified_rhs(vc.current_time_s, y)
        y = y + dt * dydt
        vc._unpack_unified_state(y)
        vc.current_time_s += dt
        if i % save_interval == 0:
            time_series.append(_record(vc, vc.current_time_s))

    return dict(success=True, time_s=time.perf_counter() - t0,
                 time_series=time_series)


# ── Sequential Euler: existing vc.step() ───────────────────────────────
def run_sequential_euler(dt, t_end=T_END):
    vc = _make_vc()
    _blood_loss(vc)
    _ = vc._unified_rhs(0.0, vc._pack_unified_state())

    save_interval = max(1, int(DT_SAVE / dt))
    total_steps = int(t_end / dt)
    t0 = time.perf_counter()
    time_series = [_record(vc, 0.0)]

    for i in range(total_steps):
        vc.step()
        if i % save_interval == 0:
            time_series.append(_record(vc, vc.current_time_s))

    return dict(success=True, time_s=time.perf_counter() - t0,
                 time_series=time_series)


# ── Radau reference ────────────────────────────────────────────────────
def run_radau_ref(t_end=T_END):
    vc = _make_vc()
    _blood_loss(vc)
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)

    def rhs(t, y):
        vc._cached_inputs.clear()
        vc._unpack_unified_state(y)
        return vc._unified_rhs(t, y)

    t0 = time.perf_counter()
    sol = solve_ivp(
        rhs, (0.0, t_end), y0,
        method="Radau",
        rtol=1e-10, atol=1e-12,
        max_step=0.1,
        dense_output=True,
    )
    elapsed = time.perf_counter() - t0

    t_dense = np.linspace(0, t_end, 300)
    y_ref = sol.sol(t_dense).T

    time_series = []
    for i, t in enumerate(t_dense):
        vc._unpack_unified_state(y_ref[i])
        time_series.append(_record(vc, t))

    return dict(success=True, time_s=elapsed,
                 time_series=time_series, n_vars=len(y0))


# ── error computation ───────────────────────────────────────────────────
def compute_errors(test_ts, ref_ts):
    from scipy.interpolate import interp1d
    test_t = np.array([p["t"] for p in test_ts])
    test_map = np.array([p["MAP"] for p in test_ts])
    ref_t = np.array([p["t"] for p in ref_ts])
    ref_map = np.array([p["MAP"] for p in ref_ts])

    t_min = max(test_t.min(), ref_t.min())
    t_max = min(test_t.max(), ref_t.max())
    ref_clip = ref_t[(ref_t >= t_min) & (ref_t <= t_max)]
    if len(ref_clip) == 0:
        return {}
    f = interp1d(test_t, test_map, kind="linear", fill_value="extrapolate")
    devs = np.abs(f(ref_clip) - ref_map[(ref_t >= t_min) & (ref_t <= t_max)])
    return dict(
        max_MAP_dev=float(np.max(devs)),
        RMSE_MAP=float(np.sqrt(np.mean(devs**2))),
    )


# ── main ────────────────────────────────────────────────────────────────
def main():
    print("=== Radau reference (rtol=1e-10) ===")
    r_radau = run_radau_ref()
    radau_ts = r_radau["time_series"]
    print(f"  done  time={r_radau['time_s']:.1f}s  "
          f"min_MAP={min(p['MAP'] for p in radau_ts):.2f} mmHg")

    print(f"\n=== Pure Euler (dt={DT_EULER}) ===")
    r_pure = run_pure_euler(DT_EULER)
    e_pure = compute_errors(r_pure["time_series"], radau_ts)
    r_pure.update(e_pure)
    print(f"  done  time={r_pure['time_s']:.2f}s  "
          f"max_dev={e_pure.get('max_MAP_dev', 'N/A')}  "
          f"RMSE={e_pure.get('RMSE_MAP', 'N/A'):.3f}")

    print(f"\n=== Sequential Euler (dt={DT_EULER}) ===")
    r_seq = run_sequential_euler(DT_EULER)
    e_seq = compute_errors(r_seq["time_series"], radau_ts)
    r_seq.update(e_seq)
    print(f"  done  time={r_seq['time_s']:.2f}s  "
          f"max_dev={e_seq.get('max_MAP_dev', 'N/A')}  "
          f"RMSE={e_seq.get('RMSE_MAP', 'N/A'):.3f}")

    # Save
    out = {
        "radau_ref": r_radau,
        "pure_euler": r_pure,
        "sequential_euler": r_seq,
    }
    with open(_DATA_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\n=== Three-way comparison (dt={DT_EULER}) ===")
    print(f"{'Method':<22} {'Time(s)':>8} {'Max|MAP-Mref|':>14} {'RMSE MAP':>10}")
    print("-" * 58)
    print(f"{'Radau rtol=1e-10':<22} {r_radau['time_s']:>8.1f} {'0.000':>14} {'0.000':>10}")
    print(f"{'Pure Euler':<22} {r_pure['time_s']:>8.2f} "
          f"{r_pure.get('max_MAP_dev', 0):>14.3f} {r_pure.get('RMSE_MAP', 0):>10.3f}")
    print(f"{'Sequential Euler':<22} {r_seq['time_s']:>8.2f} "
          f"{r_seq.get('max_MAP_dev', 0):>14.3f} {r_seq.get('RMSE_MAP', 0):>10.3f}")

    print(f"\nInterpretation:")
    pure_dev = r_pure.get('max_MAP_dev', 0)
    seq_dev = r_seq.get('max_MAP_dev', 0)
    if abs(pure_dev - seq_dev) < 0.5:
        print("  Pure Euler ≈ Sequential Euler: bottleneck is the explicit method itself")
    else:
        print(f"  Sequential Euler RMSE={seq_dev:.1f} vs Pure={pure_dev:.1f}: "
              "coupling strategy amplifies error")

    print(f"\nData → {_DATA_OUT}")


if __name__ == "__main__":
    main()