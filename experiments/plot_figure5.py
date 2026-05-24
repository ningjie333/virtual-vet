"""
Figure 5 — Convergence Analysis: Pure Euler vs Sequential Euler

Convergence plot: RMSE_MAP vs dt (log-log)
- Pure Euler (blue): First-order convergence for dt <= 0.05
- Sequential Euler (orange): Structural error floor O(1) independent of dt
- Vertical dashed line marking explosion threshold
- Shaded regions for unstable/converged/structural-error zones
"""

import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_EXPERIMENTS_DIR, "convergence_study_data.json")


def _load() -> dict:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def plot_figure5():
    data = _load()

    # Extract Pure Euler data
    pure_dt = np.array([e["dt"] for e in data["pure_euler"]])
    pure_rmse = np.array([e["RMSE_MAP"] for e in data["pure_euler"]])
    pure_success = np.array([e["success"] for e in data["pure_euler"]])

    # Extract Sequential Euler data
    seq_dt = np.array([e["dt"] for e in data["sequential_euler"]])
    seq_rmse = np.array([e["RMSE_MAP"] for e in data["sequential_euler"]])

    fig, ax = plt.subplots(figsize=(9, 6))

    # ── Shaded background regions ───────────────────────────────────────
    # Unstable region (Pure Euler dt >= 0.1 fails catastrophically)
    ax.axvspan(0.25, 0.5, alpha=0.15, color="red", label="Unstable (Pure Euler MAP=30)")
    ax.axvspan(0.1, 0.15, alpha=0.15, color="red")
    ax.axvline(0.1, color="gray", linestyle="--", linewidth=1.2, zorder=1)

    # Structural error floor zone (Sequential Euler)
    ax.axhspan(1.0, 2.0, alpha=0.08, color="orange", zorder=0)
    ax.annotate("", xy=(0.0008, 1.3), xytext=(0.0008, 0.4),
                arrowprops=dict(arrowstyle="<->", color="orange", lw=1.5))
    ax.text(0.0006, 0.7, "Structural\nError Floor\n(~1.3 mmHg)", fontsize=7,
            color="darkorange", ha="right", va="center", rotation=0)

    # ── Pure Euler markers ───────────────────────────────────────────────
    # Failed points (large RMSE, dt >= 0.1)
    failed_mask = pure_rmse > 5.0
    ax.scatter(pure_dt[failed_mask], pure_rmse[failed_mask],
               c="red", marker="x", s=120, linewidths=2, zorder=5,
               label="Pure Euler (unstable)", alpha=0.8)

    # Converged points (dt <= 0.05)
    conv_mask = pure_rmse <= 5.0
    ax.scatter(pure_dt[conv_mask], pure_rmse[conv_mask],
               c="blue", marker="o", s=80, zorder=4,
               label="Pure Euler (converged)", alpha=0.9)

    # Connecting line (convergence trend for dt <= 0.05)
    dt_conv = pure_dt[conv_mask]
    rmse_conv = pure_rmse[conv_mask]
    ax.plot(dt_conv, rmse_conv, "b-", linewidth=1.8, zorder=3, alpha=0.8)

    # First-order reference line (slope = 1)
    # Fit through dt=0.05 (RMSE=0.09) and dt=0.001 (RMSE=0.011)
    log_dt = np.log(dt_conv)
    log_rmse = np.log(rmse_conv)
    slope = (log_rmse[-1] - log_rmse[0]) / (log_dt[-1] - log_dt[0])
    intercept = log_rmse[0] - slope * log_dt[0]
    dt_ref = np.logspace(-3.5, -1, 50)
    rmse_ref = np.exp(intercept) * dt_ref ** slope
    ax.plot(dt_ref, rmse_ref, "b--", linewidth=1.2, alpha=0.5, label=f"1st-order slope={slope:.2f}")

    # ── Sequential Euler markers ────────────────────────────────────────
    ax.scatter(seq_dt, seq_rmse, c="darkorange", marker="s", s=90, zorder=4,
               label="Sequential Euler (vc.step)", alpha=0.9)
    ax.plot(seq_dt, seq_rmse, "orange", linewidth=1.8, linestyle="--", zorder=3, alpha=0.8)

    # ── Annotations ─────────────────────────────────────────────────────
    # Mark explosion threshold
    ax.annotate("Explosion\nThreshold", xy=(0.1, 30), xytext=(0.16, 18),
                fontsize=8, color="darkred",
                arrowprops=dict(arrowstyle="->", color="darkred", lw=1.2),
                ha="left")

    # Mark convergence
    ax.annotate("Converged\nRMSE<0.1", xy=(0.025, 0.002), xytext=(0.04, 0.015),
                fontsize=7, color="blue",
                arrowprops=dict(arrowstyle="->", color="blue", lw=1.0),
                ha="left")

    # Mark structural error of Sequential Euler
    ax.annotate("Sequential Euler\nStructural Error", xy=(0.005, 1.3),
                xytext=(0.002, 4.0),
                fontsize=7, color="darkorange",
                arrowprops=dict(arrowstyle="->", color="darkorange", lw=1.0),
                ha="left")

    # Reference info
    ref = data["reference"]
    ref_method = ref["method"]
    ax.text(0.98, 0.02, f"Reference: {ref_method}\n"
                         f"T_END=8s, 80 pts\n"
                         f"Blood loss: 400mL at t=5s\n"
                         f"20kg dog, Class II shock",
            transform=ax.transAxes, fontsize=7, va="bottom", ha="right",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.7))

    # ── Axes setup ──────────────────────────────────────────────────────
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Integration Step Size dt (s)", fontsize=11)
    ax.set_ylabel("RMSE MAP vs Reference (mmHg)", fontsize=11)
    ax.set_title("Figure 5: Convergence Analysis — Pure Euler vs Sequential Euler\n"
                 "Single-Step Euler Converges (1st-order) but Sequential Coupling Introduces O(1) Structural Error",
                 fontsize=10, fontweight="bold")
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(True, alpha=0.3, which="both")
    ax.set_xlim(3e-4, 0.7)
    ax.set_ylim(1e-4, 50)

    # Clinical threshold line
    ax.axhline(2.0, color="green", linestyle=":", linewidth=1.2, alpha=0.7,
               label="Clinical threshold |ΔMAP|<2mmHg")

    plt.tight_layout()

    out_path = os.path.join(_EXPERIMENTS_DIR, "figure5_convergence.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Figure 5 saved → {out_path}")

    # ── Print summary table ──────────────────────────────────────────────
    print("\n=== Convergence Summary ===")
    print(f"{'dt':>8} {'Pure Euler RMSE':>18} {'Seq Euler RMSE':>18}")
    print("-" * 50)
    for e in data["pure_euler"]:
        status = "FAIL" if e["RMSE_MAP"] > 5 else "OK"
        print(f"{e['dt']:>8.4f} {e['RMSE_MAP']:>18.4f}  {status}")
    for e in data["sequential_euler"]:
        print(f"{'seq':>8} {'':>18} {e['RMSE_MAP']:>18.4f}")
    print()
    print(f"Reference: {ref_method}, {len(ref['time_series'])} pts, T_END={ref['t_end']}s")
    print(f"Pure Euler 1st-order slope: {slope:.3f}")
    print(f"Sequential Euler structural error: {np.mean(seq_rmse):.3f} ± {np.std(seq_rmse):.3f} mmHg")


if __name__ == "__main__":
    plot_figure5()