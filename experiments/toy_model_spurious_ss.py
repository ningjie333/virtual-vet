#!/usr/bin/env python3
"""
Toy Model: Spurious Steady State from dt-Dimensional Mismatch in Discrete Events.

A minimal 2-variable ODE system demonstrating that threshold-gated discrete events
without dt-normalization produce bias ∝ 1/dt — independent of the application domain.

    Plant:       dx/dt = -k * (x - x_target)          [continuous]
    Controller:  when sensor > threshold → FC("x", "add", K)
                 BUGGY: K in [unit]/step  →  bias ∝ 1/dt
                 FIXED: K×dt in [unit]/s  →  bias independent of dt

Run: python experiments/toy_model_spurious_ss.py
Output: prints steady-state values + generates fig5_toy_model_comparison.png
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "papers",
                                "gauss_seidel_baroreflex"))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Toy Model ────────────────────────────────────────────────────────────

def simulate_toy(K: float, dt: float = 0.01, k: float = 0.25,
                 x_target: float = 100.0, x_ceiling: float = 180.0,
                 sensor_value: float = 0.02, sensor_threshold: float = 0.01,
                 T: float = 60.0, buggy: bool = True) -> float:
    """Run toy model for T seconds; return final steady-state x."""
    n_steps = int(T / dt)
    x = float(x_target)

    for _ in range(n_steps):
        # continuous homeostatic dynamics
        dx = -k * (x - x_target) * dt

        # discrete event from controller
        event = 0.0
        if sensor_value > sensor_threshold:
            event = K if buggy else K * dt

        x = x + dx + event

        # saturation ceiling
        if x > x_ceiling:
            x = x_ceiling

    return x


# ── Virtual Vet reference data (from manuscript Table 1 & exp8_fixed_results.json) ───

VT_DTS = np.array([0.1, 0.05, 0.02, 0.01, 0.005, 0.001])

# Pre-fix (buggy) MAP from Table 1
VT_PRE = np.array([111.0, 121.1, 144.7, 144.7, 144.7, 144.7])

# Post-fix MAP from exp8 (DC=10, Z condition last/dt values)
VT_POST = np.array([102.26, 102.26, 102.26, 102.26, 102.26, 102.26])


# ── Run Toy Model ────────────────────────────────────────────────────────

PARAMS = [
    # (K_label, K, k, x_target, x_ceiling, sensor_value, threshold)
    ("K=0.5", 0.5, 0.25, 100.0, 180.0, 0.02, 0.01),
    ("K=1.0", 1.0, 0.25, 100.0, 180.0, 0.02, 0.01),
    ("K=2.0", 2.0, 0.35, 100.0, 180.0, 0.02, 0.01),
]

print("=" * 70)
print("Toy Model: Spurious Steady State from dt-Dimensional Mismatch")
print("=" * 70)

for label, K, k, x_t, x_c, sv, st in PARAMS:
    print(f"\n── {label} (k={k}, ceiling={x_c}) ──")
    print(f"{'dt (s)':>8}  {'Buggy':>10}  {'Fixed':>10}  {'Bias':>10}")
    print("-" * 42)
    for dt in [0.1, 0.05, 0.02, 0.01, 0.005, 0.001]:
        x_bug = simulate_toy(K, dt, k, x_t, x_c, sv, st, buggy=True)
        x_fix = simulate_toy(K, dt, k, x_t, x_c, sv, st, buggy=False)
        print(f"{dt:8.3f}  {x_bug:10.4f}  {x_fix:10.4f}  {x_bug - x_fix:10.4f}")


# ── Detailed results for Figure (K=0.5) ──────────────────────────────────

TOY_DTS = np.array([0.1, 0.05, 0.02, 0.01, 0.005, 0.001])
K_DEFAULT = 0.5
toy_pre = np.array([simulate_toy(K_DEFAULT, dt, buggy=True) for dt in TOY_DTS])
toy_post = np.array([simulate_toy(K_DEFAULT, dt, buggy=False) for dt in TOY_DTS])

print(f"\n\n── Figure data (K={K_DEFAULT}) ──")
print(f"{'dt (s)':>8}  {'Toy_buggy':>10}  {'Toy_fixed':>10}  {'VT_pre':>10}  {'VT_post':>10}")
print("-" * 54)
for i, dt in enumerate(TOY_DTS):
    print(f"{dt:8.3f}  {toy_pre[i]:10.4f}  {toy_post[i]:10.4f}  {VT_PRE[i]:10.1f}  {VT_POST[i]:10.2f}")

# Analytical check: unsaturated bias ∝ 1/dt
print("\n── Unsaturated regime check: bias × dt = constant? ──")
k = 0.25
for dt in [0.1, 0.05]:
    bias_analytical = K_DEFAULT / (k * dt)
    bias_numerical = toy_pre[TOY_DTS == dt][0] - toy_post[TOY_DTS == dt][0]
    print(f"  dt={dt}: analytical bias={bias_analytical:.2f}, "
          f"numerical bias={bias_numerical:.2f}, "
          f"bias*dt={bias_numerical * dt:.4f}")

print("\n── Saturated regime check: bias independent of dt ──")
for dt in [0.01, 0.005, 0.001]:
    bias = toy_pre[TOY_DTS == dt][0] - toy_post[TOY_DTS == dt][0]
    print(f"  dt={dt}: bias={bias:.2f} (ceiling={toy_pre[TOY_DTS == dt][0]:.1f})")


# ── Figure 5: side-by-side comparison ────────────────────────────────────

FIGS_DIR = os.path.join(os.path.dirname(__file__), "..",
                        "papers", "gauss_seidel_baroreflex")

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 12,
    "legend.fontsize": 10,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
})

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4), constrained_layout=True)

# ── Left: Toy Model ──
ax1.plot(TOY_DTS, toy_pre, "ro-", linewidth=1.5, markersize=6, label="Buggy (bpm/step)")
ax1.plot(TOY_DTS, toy_post, "bs--", linewidth=1.5, markersize=6, label="Fixed (bpm/s)")
ax1.axhline(toy_post[0], color="blue", linestyle=":", alpha=0.4,
            label=f"Correct SS ≈ {toy_post[0]:.0f}")
ax1.set_xlabel("Time step dt (s)")
ax1.set_ylabel("State x (a.u.)")
ax1.set_title("(a) Toy Model\n(dx/dt = −k·(x − x₀) + FC events)")
ax1.set_xscale("log")
ax1.set_ylim(90, 190)
ax1.grid(True, alpha=0.3)
ax1.legend()

# annotate regimes
ax1.annotate("Unsaturated\n(bias ∝ 1/dt)", xy=(0.08, 120), fontsize=9,
             ha="center", va="bottom",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
ax1.annotate("Saturated\n(ceiling = 180)", xy=(0.01, 178), fontsize=9,
             ha="center", va="top",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

# ── Right: Virtual Vet ──
ax2.plot(VT_DTS, VT_PRE, "ro-", linewidth=1.5, markersize=6, label="Pre-fix (buggy)")
ax2.plot(VT_DTS, VT_POST, "bs--", linewidth=1.5, markersize=6, label="Post-fix (fixed)")
ax2.axhline(VT_POST[0], color="blue", linestyle=":", alpha=0.4,
            label=f"Correct SS ≈ {VT_POST[0]:.0f}")
ax2.set_xlabel("Time step dt (s)")
ax2.set_ylabel("MAP (mmHg)")
ax2.set_title("(b) Virtual Vet (canine CV)\n11-organ cardiovascular simulation")
ax2.set_xscale("log")
ax2.set_ylim(90, 190)
ax2.grid(True, alpha=0.3)
ax2.legend()

ax2.annotate("Unsaturated\n(bias ∝ 1/dt)", xy=(0.08, 121), fontsize=9,
             ha="center", va="bottom",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
ax2.annotate("Saturated\n(HR ceiling = 180)", xy=(0.01, 178), fontsize=9,
             ha="center", va="top",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

fig.suptitle("Spurious Steady State: Toy Model vs Virtual Vet — Identical Pattern",
             fontsize=13, y=1.02)

save_path = os.path.join(FIGS_DIR, "fig5_toy_model_comparison.png")
fig.savefig(save_path, dpi=300, bbox_inches="tight")
print(f"\n✅ Figure saved: {save_path}")

# ── Numerical summary table ──────────────────────────────────────────────
print("\n\n── Final Comparison Table ──")
print(f"{'Regime':<15} {'dt (s)':<8} {'Toy buggy':<10} {'Toy fixed':<10} "
      f"{'VT pre':<10} {'VT post':<10}")
print("-" * 63)
regimes = ["Unsaturated", "Unsaturated", "Unsaturated", "Saturated", "Saturated", "Saturated"]
for i, dt in enumerate(TOY_DTS):
    print(f"{regimes[i]:<15} {dt:<8.3f} {toy_pre[i]:<10.4f} {toy_post[i]:<10.4f} "
          f"{VT_PRE[i]:<10.1f} {VT_POST[i]:<10.2f}")
