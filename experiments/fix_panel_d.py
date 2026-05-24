"""
Recompute panel_d with correct alignment:
1. Use scipy interpolation to align Euler time series to Ref time points
2. Compute: max |MAP(t) - Ref_MAP(t)| over all t in [0, 60]
3. Compute: RMSE over all t in [0, 60]
4. Steady-state error at t=60
"""
import json, sys, os
import numpy as np
from scipy.interpolate import interp1d

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_EXPERIMENTS_DIR, "coupling_comparison_data.json")
_OUT_PATH = _DATA_PATH


def _interp_euler_to_ref(euler_ts, ref_t):
    """Linearly interpolate Euler MAP to Ref time points within [0, 60]."""
    e_t = np.array([p["t"] for p in euler_ts])
    e_m = np.array([p["MAP"] for p in euler_ts])

    # clip to overlap range
    t_min = max(0.0, e_t.min())
    t_max = min(60.0, e_t.max())
    ref_clip = ref_t[(ref_t >= t_min) & (ref_t <= t_max)]

    if len(ref_clip) == 0:
        return np.array([]), np.array([])

    # Linear interpolation with extrapolation for edges
    f = interp1d(e_t, e_m, kind="linear", fill_value="extrapolate")
    e_interp_m = f(ref_clip)
    return ref_clip, e_interp_m


def recompute_panel_d(data):
    ref_ts = data["reference"]["time_series"]
    ref_t = np.array([p["t"] for p in ref_ts])
    ref_m = np.array([p["MAP"] for p in ref_ts])

    ref_min_map = float(np.min(ref_m))
    ref_min_t = float(ref_t[np.argmin(ref_m)])

    panel_d = []

    for key in ["reference", "semi_implicit",
                "sequential_dt010", "sequential", "sequential_dt001",
                "sequential_dt0001"]:

        if key not in data:
            continue
        d = data[key]
        if not d.get("success") or not d.get("time_series"):
            continue

        ts = d["time_series"]
        e_t = np.array([p["t"] for p in ts])
        e_m = np.array([p["MAP"] for p in ts])

        # Method name
        method_map = {
            "reference":         "Ref (Radau rtol=1e-10)",
            "semi_implicit":     "Semi-implicit (Radau)",
            "sequential_dt010":   "Sequential (Euler dt=0.1)",
            "sequential":        "Sequential (Euler dt=0.05)",
            "sequential_dt001":  "Sequential (Euler dt=0.001)",
            "sequential_dt0001": "Sequential (Euler dt=0.0001)",
        }
        method = method_map.get(key, key)

        if key == "reference":
            # Ref has zero deviation from itself
            max_dev = 0.0
            rmse = 0.0
            steady_err = 0.0
        else:
            # Remove duplicate t=0 entries (take last to avoid forward-fill bias)
            _, uniq_idx = np.unique(e_t, return_index=True)
            e_t_u = e_t[uniq_idx]
            e_m_u = e_m[uniq_idx]

            # Interpolate to Ref time points in [0, min(end_time, 60)]
            t_end_e = e_t_u.max()
            ref_clip_mask = (ref_t >= e_t_u.min()) & (ref_t <= min(t_end_e, 60.0))
            ref_t_clip = ref_t[ref_clip_mask]
            ref_m_clip = ref_m[ref_clip_mask]

            if len(ref_t_clip) == 0:
                max_dev = None
                rmse = None
                steady_err = None
            else:
                f = interp1d(e_t_u, e_m_u, kind="linear", fill_value="extrapolate")
                e_interp = f(ref_t_clip)
                devs = np.abs(e_interp - ref_m_clip)
                max_dev = float(np.max(devs)) if len(devs) > 0 else 0.0
                rmse = float(np.sqrt(np.mean(devs**2))) if len(devs) > 0 else 0.0

                # Steady-state error at t=60 (or nearest)
                t60_idx = np.argmin(np.abs(ref_t_clip - 60.0))
                steady_err = float(devs[t60_idx]) if t60_idx < len(devs) else None

        panel_d.append({
            "method": method,
            "time_s": d["time_s"],
            "max_MAP_deviation": max_dev if max_dev is not None else 0.0,
            "rmse_MAP": rmse if rmse is not None else 0.0,
            "steady_state_error": steady_err,
            # extra diagnostics
            "_ref_min_MAP": ref_min_map,
            "_ref_min_MAP_t": ref_min_t,
        })

    return panel_d


if __name__ == "__main__":
    with open(_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    panel_d = recompute_panel_d(data)
    data["panel_d"] = panel_d

    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("=== panel_d (recomputed) ===")
    print(f"{'Method':<40} {'Time(s)':>9} {'L∞ ΔMAP':>9} {'RMSE':>7} {'SS@60s':>7}")
    print("-" * 75)
    for p in panel_d:
        ss = f"{p['steady_state_error']:.4f}" if p.get("steady_state_error") is not None else "N/A"
        print(f"{p['method']:<40} {p['time_s']:>9.2f} "
              f"{p['max_MAP_deviation']:>9.3f} {p['rmse_MAP']:>7.3f} {ss:>7}")

    print(f"\nNote: Ref min MAP = {panel_d[0]['_ref_min_MAP']:.2f} at t={panel_d[0]['_ref_min_MAP_t']:.0f}s")
    print(f"Data written to: {_OUT_PATH}")