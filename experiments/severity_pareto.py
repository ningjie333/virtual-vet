"""
P1-2: Severity Pareto — 200/400/800 mL Three-Level Comparison

Goal: Show that the Radau advantage holds across severity levels.
Mild (200 mL) / Moderate (400 mL) / Severe (800 mL) blood loss.

Design:
  200 mL: Full curves, dt={0.05, 0.01}
  400 mL: Full curves, dt={0.05, 0.01}
  800 mL: Spot check (3 time points: t=10, 30, 60)

Output: severity_pareto_data.json
"""

import sys, os, json, types, time, numpy as np
from scipy.integrate import solve_ivp

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
_DATA_OUT = os.path.join(_EXPERIMENTS_DIR, "severity_pareto_data.json")

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
DT_SAVE = 2.0
BLOOD_LOSS_TIME = 5.0


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


def _rhs_factory(vc):
    def rhs(t, y):
        vc._cached_inputs.clear()
        vc._unpack_unified_state(y)
        return vc._unified_rhs(t, y)
    return rhs


def run_radau(vc, t_end, rtol=1e-4):
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)
    rhs = _rhs_factory(vc)

    t0 = time.perf_counter()
    sol = solve_ivp(rhs, (0.0, t_end), y0, method="BDF",
                    rtol=rtol, atol=1e-6, max_step=0.5, dense_output=True)
    elapsed = time.perf_counter() - t0

    t_dense = np.arange(0, t_end + 0.5, DT_SAVE)
    y_dense = sol.sol(t_dense).T if sol.sol else np.zeros((len(t_dense), len(y0)))
    ts = []
    for i in range(len(t_dense)):
        vc._unpack_unified_state(y_dense[i])
        ts.append(_record(vc, t_dense[i]))
    return dict(success=sol.success, time_s=elapsed, time_series=ts, method=f"BDF rtol={rtol}")


def run_sequential_euler(vc, t_end, dt):
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)
    total_steps = int(t_end / dt)
    save_interval = max(1, int(DT_SAVE / dt))
    t0 = time.perf_counter()
    ts = [_record(vc, 0.0)]
    for i in range(total_steps):
        vc.step()
        if i % save_interval == 0:
            ts.append(_record(vc, vc.current_time_s))
    return dict(success=True, time_s=time.perf_counter() - t0,
                time_series=ts, method=f"Euler dt={dt}")


def spot_check_radau(vc, t_end):
    """Quick spot check at 3 time points."""
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)
    rhs = _rhs_factory(vc)
    sol = solve_ivp(rhs, (0.0, t_end), y0, method="BDF",
                    rtol=1e-4, atol=1e-6, max_step=0.5, dense_output=True)
    spot_t = np.array([10.0, 30.0, 60.0])
    spot_t = spot_t[spot_t <= t_end]
    if sol.sol:
        y_spots = sol.sol(spot_t).T
    else:
        y_spots = np.zeros((len(spot_t), len(y0)))
    ts = []
    for i in range(len(spot_t)):
        vc._unpack_unified_state(y_spots[i])
        ts.append(_record(vc, spot_t[i]))
    return dict(success=sol.success, time_series=ts,
                method="BDF (spot check)", n_spots=len(ts))


def run_scenario(volume_ml, dt_values, t_end=T_END, spot_only=False):
    """Run one severity scenario (200/400/800 mL)."""
    label = {200: "classI_mild", 400: "classII_moderate", 800: "classIII_severe"}[volume_ml]
    print(f"\n=== {volume_ml} mL blood loss ({label}) ===")
    vc_base = _make_vc()
    vc_base.set_blood_loss_scenario(
        t_onset=BLOOD_LOSS_TIME, total_ml=volume_ml,
        duration=20.0, width=2.0)

    results = {}

    # Radau reference
    print(f"  Radau reference...", end=" ", flush=True)
    vc_r = _make_vc()
    vc_r.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=volume_ml,
                                  duration=20.0, width=2.0)
    r_radau = run_radau(vc_r, t_end, rtol=1e-4)
    results["radau"] = r_radau
    print(f"done  time={r_radau['time_s']:.2f}s  min_MAP="
          f"{min(p['MAP'] for p in r_radau['time_series']):.1f}")

    if spot_only:
        print(f"  Spot check (3 pts)...", end=" ", flush=True)
        vc_s = _make_vc()
        vc_s.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=volume_ml,
                                     duration=20.0, width=2.0)
        r_spot = spot_check_radau(vc_s, t_end)
        results["spot_check"] = r_spot
        print(f"done  spots={r_spot['n_spots']}")
    else:
        for dt in dt_values:
            print(f"  Euler dt={dt}...", end=" ", flush=True)
            vc_e = _make_vc()
            vc_e.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=volume_ml,
                                         duration=20.0, width=2.0)
            r_euler = run_sequential_euler(vc_e, t_end, dt)
            results[f"euler_dt{dt}"] = r_euler
            print(f"done  time={r_euler['time_s']:.2f}s  min_MAP="
                  f"{min(p['MAP'] for p in r_euler['time_series']):.1f}")

    return results


def compute_pareto_metrics(r_ts, ref_ts):
    """Compute MAP accuracy metrics vs reference."""
    from scipy.interpolate import interp1d
    test_t = np.array([p["t"] for p in r_ts])
    test_map = np.array([p["MAP"] for p in r_ts])
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
        min_MAP=float(np.min(test_map)),
    )


def main():
    print("=== P1-2: Severity Pareto ===\n")

    scenarios = [
        (200, [0.05, 0.01], False),   # mild — full curves
        (400, [0.05, 0.01], False),   # moderate — full curves
        (800, [0.05], True),           # severe — spot check only
    ]

    all_results = {}
    for volume_ml, dt_vals, spot_only in scenarios:
        label = {200: "classI_mild", 400: "classII_moderate", 800: "classIII_severe"}[volume_ml]
        res = run_scenario(volume_ml, dt_vals, t_end=T_END, spot_only=spot_only)
        all_results[label] = res

    with open(_DATA_OUT, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n=== Severity Pareto Summary ===")
    print(f"{'Scenario':<20} {'Method':<20} {'Time(s)':>8} {'min MAP':>8} {'max dev':>8} {'RMSE':>7}")
    print("-" * 74)
    for label, res in all_results.items():
        ref_ts = res["radau"]["time_series"]
        for key, r in res.items():
            ts = r["time_series"]
            if key == "spot_check":
                min_map = min(p["MAP"] for p in ts)
                print(f"{label:<20} {r['method']:<20} {'spot':>8} {min_map:>8.1f} {'--':>8} {'--':>7}")
            else:
                mets = compute_pareto_metrics(ts, ref_ts)
                min_map = min(p["MAP"] for p in ts)
                print(f"{label:<20} {r['method']:<20} {r['time_s']:>8.2f} "
                      f"{min_map:>8.1f} {mets.get('max_MAP_dev', 0):>8.3f} {mets.get('RMSE_MAP', 0):>7.3f}")

    print(f"\nData → {_DATA_OUT}")


if __name__ == "__main__":
    main()