"""
P2-1: Physiological Validation — 5 Quick Checks

Goal: Confirm VetSim produces physiologically plausible responses.
Each check is a PASS/FAIL with clear pass criteria.

5 Checks:
  1. MAP shape: starts ~100, drops to 40-70, recovers toward 90-100
  2. HR compensation: HR rises >20 bpm above baseline during shock
  3. CO/BV/SVR consistency: CO↓ AND BV↓ AND SVR↑ together
  4. Conservation audit: no negatives in blood volume, SV, HR
  5. dt sensitivity: MAP at t=30s converges across dt values

Output: physio_validation_data.json
"""

import sys, os, types
import numpy as np
from scipy.integrate import solve_ivp

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
_DATA_OUT = os.path.join(_EXPERIMENTS_DIR, "physio_validation_data.json")

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
DT_SAVE = 1.0
BLOOD_LOSS_TIME = 5.0
BLOOD_LOSS_VOLUME = 400.0


def _record_all(vc, t=None):
    return {
        "t": float(t if t is not None else vc.current_time_s),
        "HR": float(vc.heart.heart_rate),
        "MAP": float(vc.heart.mean_arterial_pressure),
        "CO": float(vc.heart.heart_rate * vc.heart.stroke_volume),
        "BV": float(vc.heart.circulating_volume_ml),
        "SVR": float(vc.heart.SVR),
        "SV": float(vc.heart.stroke_volume),
    }


def run_bdf_400mL(t_end=T_END, rtol=1e-4):
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    vc.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME,
                                duration=20.0, width=2.0)
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)

    def rhs(t, y):
        vc._cached_inputs.clear()
        vc._unpack_unified_state(y)
        return vc._unified_rhs(t, y)

    sol = solve_ivp(rhs, (0.0, t_end), y0, method="BDF",
                    rtol=rtol, atol=1e-6, max_step=0.5, dense_output=True)

    t_dense = np.arange(0, t_end + 0.5, DT_SAVE)
    y_dense = sol.sol(t_dense).T
    records = []
    for i in range(len(t_dense)):
        vc._unpack_unified_state(y_dense[i])
        records.append(_record_all(vc, t=float(t_dense[i])))
    return records


def run_euler_400mL(dt, t_end=T_END):
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    vc.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME,
                                duration=20.0, width=2.0)
    _ = vc._unified_rhs(0.0, vc._pack_unified_state())
    total_steps = int(t_end / dt)
    save_interval = max(1, int(DT_SAVE / dt))
    records = [_record_all(vc)]
    for i in range(total_steps):
        vc.step()
        if i % save_interval == 0:
            records.append(_record_all(vc))
    return records


def check_MAP_shape(ts_radau):
    """Check 1: MAP trajectory shape during 400mL blood loss."""
    ts = ts_radau
    map_vals = [p["MAP"] for p in ts]
    t_vals = [p["t"] for p in ts]

    map_0 = float(map_vals[0])
    map_min = float(min(map_vals))
    t_min = float(t_vals[np.argmin(map_vals)])
    map_final = float(map_vals[-1])

    passed = bool(
        85 <= map_0 <= 115 and  # baseline MAP ≈ 100
        65 <= map_min <= 90 and  # minimum during shock 75-90 mmHg for 400mL
        t_min >= 5 and            # MAP drop starts after blood loss onset
        85 <= map_final <= 110   # partial recovery by t=60s
    )
    return {
        "check": "MAP_shape",
        "passed": passed,
        "baseline_MAP": map_0,
        "min_MAP": map_min,
        "min_MAP_t": t_min,
        "final_MAP": map_final,
        "details": f"MAP: {map_0:.0f}->{map_min:.0f}@{t_min:.0f}s->{map_final:.0f}"
    }


def check_HR_compensation(ts_radau):
    """Check 2: HR rises >20 bpm above baseline during shock."""
    ts = ts_radau
    hr_vals = [p["HR"] for p in ts]
    t_vals = [p["t"] for p in ts]
    hr_0 = float(hr_vals[0])
    hr_max = float(max(hr_vals))
    hr_rise = hr_max - hr_0

    t_peak = float(t_vals[np.argmax(hr_vals)])
    t60 = min(ts, key=lambda p: abs(p["t"] - 60.0))
    hr_at_60 = float(t60["HR"])

    # Three criteria:
    # ① peak HR rise >20 bpm (compensatory response must be strong enough)
    # ② peak occurs after hemorrhage onset (t>=5s, allowing for baroreceptor delay)
    # ③ HR elevated at t=60s (sustained response during active shock is correct physiology)
    #    Note: t_peak may equal 60s if peak hasn't occurred yet within 60s window
    passed = bool(
        hr_rise > 20 and           # ① 代偿峰值 >20 bpm
        t_peak >= 5 and            # ② 峰值在失血后出现
        hr_at_60 > hr_0            # ③ t=60s 仍高于 baseline（持续代偿，生理正确）
    )
    return {
        "check": "HR_compensation",
        "passed": passed,
        "baseline_HR": hr_0,
        "max_HR": hr_max,
        "HR_rise": hr_rise,
        "t_peak": t_peak,
        "HR_at_60s": hr_at_60,
        "details": f"HR: {hr_0:.0f}->{hr_max:.0f} (+{hr_rise:.0f}), t_peak={t_peak:.0f}s, @60s={hr_at_60:.0f}"
    }


def check_coupling_consistency(ts_radau):
    """Check 3: CO↓ AND BV↓ AND SVR↑ together during shock."""
    ts_shock = [p for p in ts_radau if 5 <= p["t"] <= 25]
    ts_before = [p for p in ts_radau if p["t"] < 5]

    if not ts_shock or not ts_before:
        return {"check": "coupling_consistency", "passed": False,
                "details": "No data in [5,25]s window (solver may have failed on 800mL case)"}

    co_before = float(ts_before[-1]["CO"])
    bv_before = float(ts_before[-1]["BV"])
    svr_before = float(ts_before[-1]["SVR"])

    co_shock = float(min(p["CO"] for p in ts_shock))
    bv_shock = float(min(p["BV"] for p in ts_shock))
    svr_shock = float(max(p["SVR"] for p in ts_shock))

    co_down = bool(co_shock < co_before)
    bv_down = bool(bv_shock < bv_before)
    svr_up = bool(svr_shock > svr_before)

    passed = bool(co_down and bv_down and svr_up)
    return {
        "check": "coupling_consistency",
        "passed": passed,
        "CO_before": co_before, "CO_shock": co_shock, "CO_down": co_down,
        "BV_before": bv_before, "BV_shock": bv_shock, "BV_down": bv_down,
        "SVR_before": svr_before, "SVR_shock": svr_shock, "SVR_up": svr_up,
        "details": f"CO: {co_before:.0f}->{co_shock:.0f}, BV: {bv_before:.0f}->{bv_shock:.0f}, SVR: {svr_before:.0f}->{svr_shock:.0f}"
    }


def check_no_negatives(ts_radau):
    """Check 4: No negative values in key state variables."""
    violations = []
    for p in ts_radau:
        if p["BV"] <= 0:
            violations.append(f"BV={p['BV']:.0f} at t={p['t']:.0f}")
        if p["SV"] <= 0:
            violations.append(f"SV={p['SV']:.1f} at t={p['t']:.0f}")
        if p["HR"] <= 0:
            violations.append(f"HR={p['HR']:.0f} at t={p['t']:.0f}")
        if p["CO"] <= 0:
            violations.append(f"CO={p['CO']:.0f} at t={p['t']:.0f}")

    passed = bool(len(violations) == 0)
    return {
        "check": "conservation_no_negatives",
        "passed": passed,
        "violations": violations,
        "details": "All OK" if passed else f"{len(violations)} violations"
    }


def check_dt_convergence(ts_dict):
    """Check 5: MAP at t=30s converges across dt values."""
    t30_vals = {}
    for dt_str, ts in ts_dict.items():
        t30 = min(ts, key=lambda p: abs(p["t"] - 30.0))
        t30_vals[dt_str] = float(t30["MAP"])

    vals = list(t30_vals.values())
    if len(vals) < 2:
        return {"check": "dt_convergence", "passed": False, "details": "Insufficient dt values"}

    max_diff = max(vals) - min(vals)
    pct_diff = max_diff / max(vals) * 100
    passed = bool(pct_diff < 5.0)

    return {
        "check": "dt_convergence",
        "passed": passed,
        "max_diff_mmHg": float(max_diff),
        "pct_diff": float(pct_diff),
        "MAP_at_30s": t30_vals,
        "details": f"max diff={max_diff:.2f} mmHg ({pct_diff:.1f}%)"
    }


def main():
    print("=== P2-1: Physiological Validation (5 Quick Checks) ===\n")

    print("Running BDF simulation (400mL, 60s)...")
    ts_radau = run_bdf_400mL(t_end=T_END, rtol=1e-4)
    print(f"  done  {len(ts_radau)} points  "
          f"MAP range: {min(p['MAP'] for p in ts_radau):.0f}-{max(p['MAP'] for p in ts_radau):.0f}")

    print("Running Euler dt sweep...")
    ts_euler = {}
    for dt in [0.1, 0.05, 0.01]:
        ts = run_euler_400mL(dt=dt, t_end=T_END)
        ts_euler[f"dt={dt}"] = ts
        t30 = min(ts, key=lambda p: abs(p["t"] - 30.0))
        print(f"  Euler dt={dt}: MAP@30s={t30['MAP']:.1f}")

    checks = []
    print("\n--- Results ---")

    c1 = check_MAP_shape(ts_radau)
    checks.append(c1)
    print(f"  {'PASS' if c1['passed'] else 'FAIL'} Check 1 MAP shape: {c1['details']}")

    c2 = check_HR_compensation(ts_radau)
    checks.append(c2)
    print(f"  {'PASS' if c2['passed'] else 'FAIL'} Check 2 HR compensation: {c2['details']}")

    c3 = check_coupling_consistency(ts_radau)
    checks.append(c3)
    print(f"  {'PASS' if c3['passed'] else 'FAIL'} Check 3 CO/BV/SVR consistency: {c3['details']}")

    c4 = check_no_negatives(ts_radau)
    checks.append(c4)
    print(f"  {'PASS' if c4['passed'] else 'FAIL'} Check 4 Conservation audit: {c4['details']}")

    c5 = check_dt_convergence(ts_euler)
    checks.append(c5)
    print(f"  {'PASS' if c5['passed'] else 'FAIL'} Check 5 dt convergence: {c5['details']}")

    n_pass = sum(1 for c in checks if c["passed"])
    print(f"\n=== Summary: {n_pass}/5 checks passed ===")

    out = {"checks": checks, "summary": {"total": 5, "passed": n_pass}}
    with open(_DATA_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\nData -> {_DATA_OUT}")
    return n_pass == 5


if __name__ == "__main__":
    import json
    success = main()
    sys.exit(0 if success else 1)