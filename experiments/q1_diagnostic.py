"""
Q1 Diagnostic: Pure Euler 60s stability — shape analysis

Compare Pure Euler vs Radau 60s MAP time series to determine:
  A) Reference drift: Pure Euler tracks a shifted Radau → reference problem (benign)
  B) Numerical instability: Pure Euler oscillates wildly → genuine instability (serious)
"""

import json, os, sys, types
import numpy as np

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
_DATA_IN = os.path.join(_EXPERIMENTS_DIR, "pure_vs_sequential_data.json")
_OUT_PNG = os.path.join(_EXPERIMENTS_DIR, "figure_q1_diagnostic.png")

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
DT_EULER = 0.01

def _make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return vc

def _blood_loss(vc):
    vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)

def run_pure_euler_60s(dt, t_end=T_END, save_dt=0.5):
    vc = _make_vc()
    _blood_loss(vc)
    y = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y)

    total_steps = int(t_end / dt)
    save_interval = max(1, int(save_dt / dt))
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

def run_radau_60s(t_end=T_END, rtol=1e-10, save_dt=0.5):
    from scipy.integrate import solve_ivp
    vc = _make_vc()
    _blood_loss(vc)
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)

    def rhs(t, y):
        vc._cached_inputs.clear()
        vc._unpack_unified_state(y)
        return vc._unified_rhs(t, y)

    sol = solve_ivp(rhs, (0.0, t_end), y0, method="Radau",
                    rtol=rtol, atol=1e-12, max_step=0.1, dense_output=True)

    t_dense = np.arange(0, t_end + save_dt, save_dt)
    y_dense = sol.sol(t_dense).T
    records = []
    for i in range(len(t_dense)):
        vc._unpack_unified_state(y_dense[i])
        records.append({
            "t": float(t_dense[i]),
            "MAP": float(vc.heart.mean_arterial_pressure),
            "HR": float(vc.heart.heart_rate),
            "BV": float(vc.heart.circulating_volume_ml),
        })
    return records

def run_bdf_60s(t_end=T_END, rtol=1e-6, save_dt=0.5):
    from scipy.integrate import solve_ivp
    vc = _make_vc()
    _blood_loss(vc)
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)

    def rhs(t, y):
        vc._cached_inputs.clear()
        vc._unpack_unified_state(y)
        return vc._unified_rhs(t, y)

    sol = solve_ivp(rhs, (0.0, t_end), y0, method="BDF",
                    rtol=rtol, atol=1e-6, max_step=0.5, dense_output=True)

    t_dense = np.arange(0, t_end + save_dt, save_dt)
    y_dense = sol.sol(t_dense).T
    records = []
    for i in range(len(t_dense)):
        vc._unpack_unified_state(y_dense[i])
        records.append({
            "t": float(t_dense[i]),
            "MAP": float(vc.heart.mean_arterial_pressure),
            "HR": float(vc.heart.heart_rate),
            "BV": float(vc.heart.circulating_volume_ml),
        })
    return records

def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    print("Computing BDF (alternative reference, ~seconds)...")
    bdf_ts = run_bdf_60s()
    print(f"  BDF done: MAP range [{min(p['MAP'] for p in bdf_ts):.1f}, {max(p['MAP'] for p in bdf_ts):.1f}]")

    print("Computing Radau reference (rtol=1e-10, ~1-2 minutes)...")
    radau_ts = run_radau_60s()
    print(f"  Radau done: MAP range [{min(p['MAP'] for p in radau_ts):.1f}, {max(p['MAP'] for p in radau_ts):.1f}]")

    print("Computing Pure Euler (dt=0.01, ~seconds)...")
    euler_ts = run_pure_euler_60s(DT_EULER)
    print(f"  Pure Euler done: MAP range [{min(p['MAP'] for p in euler_ts):.1f}, {max(p['MAP'] for p in euler_ts):.1f}]")

    # Plot
    t_r = np.array([p["t"] for p in radau_ts])
    m_r = np.array([p["MAP"] for p in radau_ts])
    t_b = np.array([p["t"] for p in bdf_ts])
    m_b = np.array([p["MAP"] for p in bdf_ts])
    t_e = np.array([p["t"] for p in euler_ts])
    m_e = np.array([p["MAP"] for p in euler_ts])

    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)

    # Panel 1: all three overlaid
    axes[0].plot(t_r, m_r, "b-", linewidth=2.0, label="Radau rtol=1e-10", alpha=0.8)
    axes[0].plot(t_b, m_b, "g--", linewidth=1.5, label="BDF rtol=1e-6", alpha=0.7)
    axes[0].plot(t_e, m_e, "r-", linewidth=1.5, label=f"Pure Euler dt={DT_EULER}", alpha=0.9)
    axes[0].axvline(5.0, color="gray", linestyle=":", linewidth=1.2)
    axes[0].set_ylabel("MAP (mmHg)")
    axes[0].legend(fontsize=9)
    axes[0].set_title("Q1 Diagnostic: Pure Euler 60s MAP Time Series", fontsize=11, fontweight="bold")
    axes[0].grid(True, alpha=0.3)

    # Panel 2: Pure Euler only (zoomed to see oscillation)
    axes[1].plot(t_e, m_e, "r-", linewidth=1.5, alpha=0.9)
    axes[1].axhline(100.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    axes[1].axvline(5.0, color="gray", linestyle=":", linewidth=1.2)
    axes[1].set_ylabel("MAP (mmHg)")
    axes[1].set_title("Pure Euler MAP Detail (60s)", fontsize=10)
    axes[1].grid(True, alpha=0.3)

    # Panel 3: Euler - Radau deviation over time
    from scipy.interpolate import interp1d
    f_radau = interp1d(t_r, m_r, kind="linear", fill_value="extrapolate")
    devs = np.abs(m_e - f_radau(t_e))
    axes[2].plot(t_e, devs, "r-", linewidth=1.5, alpha=0.9)
    axes[2].axvline(5.0, color="gray", linestyle=":", linewidth=1.2)
    axes[2].set_ylabel("|MAP_euler − MAP_radau| (mmHg)")
    axes[2].set_xlabel("Time (s)")
    axes[2].set_title("Instantaneous MAP Error vs Radau Reference", fontsize=10)
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"\nFigure → {_OUT_PNG}")

    # Numerical summary
    print("\n=== Q1 Summary ===")
    print(f"Pure Euler MAP range:  [{m_e.min():.1f}, {m_e.max():.1f}] mmHg")
    print(f"Radau MAP range:      [{m_r.min():.1f}, {m_r.max():.1f}] mmHg")
    print(f"BDF MAP range:         [{m_b.min():.1f}, {m_b.max():.1f}] mmHg")

    e_min_map = m_e.min()
    r_min_map = m_r.min()
    deviation_at_r_min = abs(f_radau(t_e[np.argmin(m_e)]) - m_e[np.argmin(m_e)])

    # Determine A vs B
    print(f"\n--- Diagnosis ---")
    if m_e.max() > 150 or m_e.min() < 50:
        print(f"CONCLUSION B: Genuine numerical instability")
        print(f"  Pure Euler max MAP = {m_e.max():.1f} (>150 = unstable)")
        print(f"  Pure Euler min MAP = {m_e.min():.1f} (<50 = unstable)")
    elif abs(e_min_map - r_min_map) > 10:
        print(f"CONCLUSION A: Reference drift (benign)")
        print(f"  Pure Euler min MAP = {e_min_map:.1f}, Radau min MAP = {r_min_map:.1f}")
        print(f"  BDF min MAP = {m_b.min():.1f} (alternative reference)")
    else:
        print(f"CONCLUSION: Both paths agree (within 10 mmHg)")
        print(f"  Pure Euler min MAP = {e_min_map:.1f}, Radau min MAP = {r_min_map:.1f}")

if __name__ == "__main__":
    main()