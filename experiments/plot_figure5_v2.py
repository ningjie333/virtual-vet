"""
Plot Figure 5: Convergence Study
Data: convergence_study_v2.json
"""

import json, os, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_EXPERIMENTS_DIR, "convergence_study_v2.json")
_OUT_PNG = os.path.join(_EXPERIMENTS_DIR, "figure5_convergence.png")

with open(_DATA, encoding="utf-8") as f:
    d = json.load(f)

meta = d["metadata"]
pure = d["pure_euler"]
seq = d["sequential_euler"]
ref = d["reference"]

# Extract pure euler data
dts = np.array([r["dt"] for r in pure])
rmses = np.array([r["rmse_MAP"] for r in pure])

# Convergence order
orders = []
for i in range(1, len(pure)):
    if rmses[i] > 1e-6 and rmses[i-1] > 1e-6:
        order = np.log(rmses[i-1] / rmses[i]) / np.log(dts[i-1] / dts[i])
        orders.append(float(order))
    else:
        orders.append(float("nan"))

# Sequential point
seq_rmse = seq["rmse_MAP"]

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# Panel A: Convergence curve (log-log)
ax = axes[0]
stable_mask = rmses < 10  # stable = RMSE < 10
unstable_mask = ~stable_mask

ax.scatter(dts[unstable_mask], rmses[unstable_mask], color="red", s=80, zorder=5, label="Unstable (dt≥0.1)")
ax.scatter(dts[stable_mask], rmses[stable_mask], color="#2196F3", s=80, zorder=5, label="Stable (dt≤0.05)")
ax.scatter([0.1], [seq_rmse], color="#FF9800", s=100, marker="D", zorder=5, label=f"Sequential Euler\n(dt=0.1 internal)")

ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("Timestep dt (s)", fontsize=11)
ax.set_ylabel("RMSE MAP vs BDF reference (mmHg)", fontsize=11)
ax.set_title("A. Convergence: Pure Euler vs BDF", fontsize=12, fontweight="bold")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3, which="both")

# Second-order reference line
dt_ref = np.array([0.1, 0.01])
ref_line = 0.27 * (dt_ref / 0.05) ** 2
ax.plot(dt_ref, ref_line, "k--", linewidth=1.5, alpha=0.5, label="O(dt²) reference")

# Stability threshold
ax.axvline(0.05, color="gray", linestyle=":", linewidth=1.5, alpha=0.7)
ax.text(0.055, 0.15, "stability\nthreshold", fontsize=8, color="gray", va="top")

# Panel B: MAP time series (BDF vs stable Pure Euler)
ax2 = axes[1]
ref_ts = ref["time_series"]
t_ref = np.array([p["t"] for p in ref_ts])
map_ref = np.array([p["MAP"] for p in ref_ts])

# Pure Euler dt=0.01 (stable, representative)
pe_ts = pure[3]["time_series"]  # dt=0.05 or dt=0.01
t_pe = np.array([p["t"] for p in pe_ts])
map_pe = np.array([p["MAP"] for p in pe_ts])

ax2.plot(t_ref, map_ref, "b-", linewidth=2.0, label="BDF rtol=1e-6", alpha=0.9)
ax2.plot(t_pe, map_pe, "r--", linewidth=1.5, label="Pure Euler dt=0.01", alpha=0.8)
ax2.axvline(5.0, color="gray", linestyle=":", linewidth=1.2, alpha=0.7)

# Annotation
min_idx = np.argmin(map_ref)
ax2.annotate(f"MAP_min={map_ref[min_idx]:.1f}", xy=(t_ref[min_idx], map_ref[min_idx]),
             xytext=(t_ref[min_idx]+5, map_ref[min_idx]+3),
             arrowprops=dict(arrowstyle="->", color="blue"), fontsize=9, color="blue")

ax2.set_xlabel("Time (s)", fontsize=11)
ax2.set_ylabel("MAP (mmHg)", fontsize=11)
ax2.set_title("B. MAP Time Series: BDF vs Pure Euler", fontsize=12, fontweight="bold")
ax2.legend(fontsize=9)
ax2.grid(True, alpha=0.3)
ax2.set_xlim(0, 60)

plt.suptitle("Figure 5: Convergence Study — Pure Euler vs BDF Reference\n"
             "20 kg dog, 400 mL blood loss at t=5 s, T_END=60 s",
             fontsize=11, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
print(f"Figure → {_OUT_PNG}")

# Summary table
print("\n=== Convergence Summary ===")
print(f"{'dt':>8}  {'RMSE':>10}  {'Order':>6}  {'Stable':>7}")
print("-" * 36)
for i, r in enumerate(pure):
    dt = r["dt"]
    rmse = r["rmse_MAP"]
    stable = "YES" if rmse < 10 else "NO"
    if i == 0:
        print(f"{dt:>8.4f}  {rmse:>10.4f}  {'--':>6}  {stable:>7}")
    else:
        prev_rmse = pure[i-1]["rmse_MAP"]
        prev_dt = pure[i-1]["dt"]
        if prev_rmse > 1e-6 and rmse > 1e-6:
            order = np.log(prev_rmse/rmse) / np.log(prev_dt/dt)
            print(f"{dt:>8.4f}  {rmse:>10.4f}  {order:>6.2f}  {stable:>7}")
        else:
            print(f"{dt:>8.4f}  {rmse:>10.4f}  {'--':>6}  {stable:>7}")
print(f"\nSequential Euler (dt=0.1 internal): RMSE={seq_rmse:.4f}")
print(f"\nBDF reference: MAP=[{ref['MAP_range'][0]:.1f}, {ref['MAP_range'][1]:.1f}] mmHg")

if __name__ == "__main__":
    pass