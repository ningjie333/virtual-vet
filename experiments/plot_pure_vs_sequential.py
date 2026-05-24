"""
Plot P0-2: Three-way time series — Pure Euler vs Sequential Euler vs Radau
Data: pure_vs_sequential_data.json (already computed)
"""

import json, os, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_OUT = os.path.join(_EXPERIMENTS_DIR, "pure_vs_sequential_data.json")

def load():
    with open(_DATA_OUT, encoding="utf-8") as f:
        return json.load(f)

def plot_three_way():
    d = load()

    methods = {
        "Radau (reference)": d["radau_ref"],
        "Pure Euler": d["pure_euler"],
        "Sequential Euler": d["sequential_euler"],
    }
    colors = {"Radau (reference)": "#2196F3", "Pure Euler": "#FF5722", "Sequential Euler": "#4CAF50"}

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    for name, mdata in methods.items():
        ts = mdata["time_series"]
        t = np.array([p["t"] for p in ts])
        map_vals = np.array([p["MAP"] for p in ts])
        hr_vals = np.array([p["HR"] for p in ts])

        lc = colors[name]
        lw = 2.0 if name != "Radau (reference)" else 1.5
        alpha = 0.9 if name != "Radau (reference)" else 0.6
        ls = "-" if name != "Radau (reference)" else "--"

        axes[0].plot(t, map_vals, color=lc, linewidth=lw, linestyle=ls, alpha=alpha, label=name)
        axes[1].plot(t, hr_vals, color=lc, linewidth=lw, linestyle=ls, alpha=alpha, label=name)

    # Blood loss annotation
    for ax in axes:
        ax.axvline(5.0, color="red", linestyle=":", linewidth=1.2, alpha=0.7)
        ax.text(5.1, ax.get_ylim()[0] + 0.05 * (ax.get_ylim()[1] - ax.get_ylim()[0]),
               "Blood loss\n400 mL", fontsize=7, color="red", va="bottom")

    axes[0].set_ylabel("MAP (mmHg)", fontsize=11)
    axes[0].legend(fontsize=9, loc="upper right")
    axes[0].grid(True, alpha=0.3)
    axes[0].set_title("Three-Way Comparison: Pure Euler vs Sequential Euler vs Radau\n"
                      "20 kg dog, 400 mL blood loss at t=5s", fontsize=10, fontweight="bold")

    axes[1].set_ylabel("HR (bpm)", fontsize=11)
    axes[1].set_xlabel("Time (s)", fontsize=11)
    axes[1].legend(fontsize=9, loc="upper right")
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(_EXPERIMENTS_DIR, "figure_pure_vs_sequential.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Figure → {out}")

    # Summary table
    print("\n=== Three-way summary (T_END=60s, dt=0.01 Euler) ===")
    print(f"{'Method':<22} {'Time(s)':>8} {'RMSE MAP':>10} {'Max|MAP-Mref|':>14}")
    print("-" * 58)
    for name, mdata in methods.items():
        rmse = mdata.get("RMSE_MAP", float("nan"))
        mx = mdata.get("max_MAP_dev", float("nan"))
        ts = mdata["time_series"]
        t_end = max(p["t"] for p in ts)
        print(f"{name:<22} {mdata.get('time_s', 0):>8.1f} {rmse:>10.2f} {mx:>14.2f}")
    print()
    print("Note: Pure Euler RMSE huge because MAP oscillates 30-180 mmHg at dt=0.01 over 60s")
    print("      Sequential Euler maintains stability with ~9.6 mmHg structural error")

if __name__ == "__main__":
    plot_three_way()