"""
P1-1: Stiffness Quantification via Radau Solver Stats

Goal: Quantify stiffness via Radau function evaluation count (nfev) and
Jacobian evaluation count (njev). More fevals/jevals = stiffer system.

Output: stiffness_data.json
"""

import sys, os, json, types, time as time_
import numpy as np
from scipy.integrate import solve_ivp

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
_DATA_OUT = os.path.join(_EXPERIMENTS_DIR, "stiffness_data.json")

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


def run_with_stats(vc, t_end=T_END, rtol=1e-4, label="run"):
    """Run Radau and collect solver statistics as stiffness proxy."""

    def rhs(t, y):
        vc._cached_inputs.clear()
        vc._unpack_unified_state(y)
        return vc._unified_rhs(t, y)

    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)

    t0 = time_.perf_counter()
    sol = solve_ivp(
        rhs, (0.0, t_end), y0,
        method="BDF",
        rtol=rtol, atol=1e-6,
        max_step=0.5,
        dense_output=True,
    )
    elapsed = time_.perf_counter() - t0

    if not sol.success:
        print(f"  WARNING: solver failed: {sol.message}")

    # Number of accepted steps = len(sol.t) - 1 (sol.t includes t0)
    n_accepted = len(sol.t) - 1 if len(sol.t) > 1 else 1
    njev = sol.njev if hasattr(sol, 'njev') else 0
    nfev = sol.nfev if hasattr(sol, 'nfev') else 0
    njev_per_step = njev / n_accepted if n_accepted > 0 else 0.0
    nfev_per_step = nfev / n_accepted if n_accepted > 0 else 0.0

    t_dense = np.arange(0, t_end + 0.5, DT_SAVE)
    if sol.sol is not None:
        y_dense = sol.sol(t_dense).T
    else:
        y_dense = np.zeros((len(t_dense), len(y0)))

    ts_dense = []
    for i in range(len(t_dense)):
        vc._unpack_unified_state(y_dense[i])
        ts_dense.append(dict(
            t=float(t_dense[i]),
            HR=vc.heart.heart_rate,
            MAP=vc.heart.mean_arterial_pressure,
            CO=vc.heart.heart_rate * vc.heart.stroke_volume,
            blood_volume_mL=vc.heart.circulating_volume_ml,
        ))

    return dict(
        label=label,
        success=sol.success,
        time_s=elapsed,
        n_accepted_steps=n_accepted,
        njev=njev,
        nfev=nfev,
        njev_per_step=njev_per_step,
        nfev_per_step=nfev_per_step,
        time_series=ts_dense,
    )


def run_baseline_no_shock():
    """Baseline: no blood loss, stiffness at rest."""
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return run_with_stats(vc, t_end=20.0, rtol=1e-4, label="baseline")


def run_shock_400mL():
    """400mL acute blood loss at t=5s."""
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    vc.set_blood_loss_scenario(
        t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME,
        duration=20.0, width=2.0)
    return run_with_stats(vc, t_end=T_END, rtol=1e-4, label="shock_400mL")


def run_shock_800mL():
    """800mL severe blood loss at t=5s."""
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    vc.set_blood_loss_scenario(
        t_onset=BLOOD_LOSS_TIME, total_ml=800.0,
        duration=20.0, width=2.0)
    return run_with_stats(vc, t_end=T_END, rtol=1e-4, label="shock_800mL")


def main():
    print("=== P1-1: Stiffness Analysis via Radau Solver Stats ===\n")

    print("Run 1: Baseline (no blood loss, t=0-20s)...")
    r_baseline = run_baseline_no_shock()
    print(f"  done  time={r_baseline['time_s']:.2f}s  "
          f"nfev={r_baseline['nfev']}  njev={r_baseline['njev']}  "
          f"steps={r_baseline['n_accepted_steps']}  "
          f"nfev/step={r_baseline['nfev_per_step']:.1f}")

    print("\nRun 2: 400mL blood loss (t=0-60s)...")
    r_400 = run_shock_400mL()
    print(f"  done  time={r_400['time_s']:.2f}s  "
          f"nfev={r_400['nfev']}  njev={r_400['njev']}  "
          f"steps={r_400['n_accepted_steps']}  "
          f"nfev/step={r_400['nfev_per_step']:.1f}")

    print("\nRun 3: 800mL blood loss (t=0-60s)...")
    r_800 = run_shock_800mL()
    print(f"  done  time={r_800['time_s']:.2f}s  "
          f"nfev={r_800['nfev']}  njev={r_800['njev']}  "
          f"steps={r_800['n_accepted_steps']}  "
          f"nfev/step={r_800['nfev_per_step']:.1f}")

    out = dict(baseline=r_baseline, shock_400mL=r_400, shock_800mL=r_800)
    with open(_DATA_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    baseline_njev = r_baseline['njev_per_step']
    baseline_nfev = r_baseline['nfev_per_step']
    shock400_njev = r_400['njev_per_step']
    shock400_nfev = r_400['nfev_per_step']
    shock800_njev = r_800['njev_per_step']
    shock800_nfev = r_800['nfev_per_step']

    print(f"\n=== Stiffness Proxy: FEvals & JEvals per Accepted Step ===")
    print(f"{'Scenario':<16} {'nfev/step':>10} {'ratio':>8} {'njev/step':>10} {'ratio':>8}")
    print("-" * 56)
    b_njev_r = 1.0
    b_nfev_r = 1.0
    s400_njev_r = shock400_njev / baseline_njev if baseline_njev > 0 else 0.0
    s400_nfev_r = shock400_nfev / baseline_nfev if baseline_nfev > 0 else 0.0
    s800_njev_r = shock800_njev / baseline_njev if baseline_njev > 0 else 0.0
    s800_nfev_r = shock800_nfev / baseline_nfev if baseline_nfev > 0 else 0.0
    print(f"{'Baseline':<16} {baseline_nfev:>10.1f} {'1.00':>8} {baseline_njev:>10.2f} {'1.00':>8}")
    print(f"{'Shock 400mL':<16} {shock400_nfev:>10.1f} {s400_nfev_r:>8.2f} {shock400_njev:>10.2f} {s400_njev_r:>8.2f}")
    print(f"{'Shock 800mL':<16} {shock800_nfev:>10.1f} {s800_nfev_r:>8.2f} {shock800_njev:>10.2f} {s800_njev_r:>8.2f}")

    print(f"\nInterpretation:")
    if s400_njev_r > 1.5:
        print("  Jacobian evals/step INCREASES under shock → system becomes stiffer")
        print("  Justifies implicit method need")
    else:
        print("  Jacobian eval increase under shock is modest (ratio={s400_njev_r:.2f})")
        print("  Note: stiffness may manifest in nfev more than njev")

    print(f"\nData → {_DATA_OUT}")


if __name__ == "__main__":
    main()