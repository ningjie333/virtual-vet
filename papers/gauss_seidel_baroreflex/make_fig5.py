#!/usr/bin/env python3
"""
Figure 5: Toy model vs Virtual Vet side-by-side comparison.
Standalone generator for manuscript_v5.md.

Output: fig5_toy_model_comparison.png (300 DPI, Times New Roman)
Usage:  python papers/gauss_seidel_baroreflex/make_fig5.py
"""

import os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Paths ─────────────────────────────────────────────────────────────────────
PAPER_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PNG = os.path.join(PAPER_DIR, "fig5_toy_model_comparison.png")

# ── Style: Times New Roman, publication-grade ────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 11,
    "legend.fontsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

# ── Colorblind-friendly palette (Wong 2011 / IBM Carbon) ─────────────────────
CB_RED   = "#D55E00"   # buggy / pre-fix
CB_BLUE  = "#006BA6"   # fixed / post-fix
CB_GREEN = "#009E73"   # correct steady state line
CB_AMBER = "#E68A2E"   # saturated region annotation

# ── dt sweep (same as manuscript Table 1) ────────────────────────────────────
DTS = np.array([0.1, 0.05, 0.02, 0.01, 0.005, 0.001])

# ─────────────────────────────────────────────────────────────────────────────
# 1.  Toy model data
# ─────────────────────────────────────────────────────────────────────────────
def simulate_toy(K=0.5, dt=0.01, k=0.25, x_target=100.0,
                 x_ceiling=180.0, sensor_value=0.02,
                 sensor_threshold=0.01, T=60.0, buggy=True):
    """
    Minimal 2-variable ODE demonstrating the spurious steady state.
    Plant:  dx/dt = -k*(x - x_target)  (continuous homeostasis)
    Event:  when sensor > threshold  ->  FC('x', 'add', K)  [buggy]
                                         FC('x', 'add', K*dt) [fixed]
    """
    n = int(T / dt)
    x = float(x_target)
    for _ in range(n):
        dx = -k * (x - x_target) * dt
        event = 0.0
        if sensor_value > sensor_threshold:
            event = K if buggy else K * dt
        x = x + dx + event
        if x > x_ceiling:
            x = x_ceiling
    return x

TOY_PRE  = np.array([simulate_toy(dt=dt, buggy=True)  for dt in DTS])
TOY_POST = np.array([simulate_toy(dt=dt, buggy=False) for dt in DTS])

# ─────────────────────────────────────────────────────────────────────────────
# 2.  Virtual Vet data (from manuscript Table 1, DC=10)
# ─────────────────────────────────────────────────────────────────────────────
VT_PRE  = np.array([111.0, 121.1, 144.7, 144.7, 144.7, 144.7])
VT_POST = np.array([102.26, 102.26, 102.26, 102.26, 102.26, 102.26])

# ─────────────────────────────────────────────────────────────────────────────
# 3.  Build the figure
# ─────────────────────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))

# ═══════════════════════════════════════════════════════════════════════════
# Panel (a) — Toy Model
# ═══════════════════════════════════════════════════════════════════════════
ax1.semilogx(DTS, TOY_PRE,  "o-",  color=CB_RED,  lw=2,   ms=7,
             zorder=3, label="Buggy (unit/step)")
ax1.semilogx(DTS, TOY_POST, "s--", color=CB_BLUE, lw=1.8, ms=6,
             zorder=3, label="Fixed (unit/s)")
# Correct steady state (horizontal dotted line)
SS_TOY = TOY_POST[0]
ax1.axhline(y=SS_TOY, color=CB_BLUE, ls=":", alpha=0.45, lw=1.3,
            label=f"Correct SS = {SS_TOY:.0f}")

ax1.set_xlabel("Time step dt (s)")
ax1.set_ylabel("State x (a.u.)")
ax1.set_title(r"(a) Toy Model  [$\dot{x} = -k\,(x-x_0) + \mathrm{FC}$ events]",
              fontsize=11, pad=8)
ax1.set_ylim(90, 190)
ax1.set_xlim(0.0008, 0.2)
ax1.grid(True, alpha=0.2)
ax1.legend(fontsize=8.5, loc="lower left", frameon=False)

# --- Annotations (verified: no overlap with data) ---
# Unsaturated: buggy line at dt=0.07 has y ~ 129.
# Annot. bbox (~10 du tall) centered at y=118 spans 113--123.  Gap to data: ~6 du.
ax1.annotate("Unsaturated\n(bias ~ 1/dt)", xy=(0.07, 118),
             fontsize=9.5, ha="center", va="center",
             bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                       edgecolor=CB_RED, alpha=0.9))

# Saturated: plateau at y=180 for dt <= 0.02.
# Annot. bbox centered at y=168 spans 163--173.  Gap to plateau: ~7 du.
ax1.annotate("Saturated\n(ceiling = 180)", xy=(0.008, 168),
             fontsize=9.5, ha="center", va="center",
             bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                       edgecolor=CB_AMBER, alpha=0.9))

# ═══════════════════════════════════════════════════════════════════════════
# Panel (b) — Virtual Vet
# ═══════════════════════════════════════════════════════════════════════════
ax2.semilogx(DTS, VT_PRE,  "o-",  color=CB_RED,  lw=2,   ms=7,
             zorder=3, label="Pre-fix (buggy)")
ax2.semilogx(DTS, VT_POST, "s--", color=CB_BLUE, lw=1.8, ms=6,
             zorder=3, label="Post-fix (fixed)")
SS_VT = VT_POST[0]
ax2.axhline(y=SS_VT, color=CB_BLUE, ls=":", alpha=0.45, lw=1.3,
            label=f"Correct SS = {SS_VT:.1f} mmHg")

ax2.set_xlabel("Time step dt (s)")
ax2.set_ylabel("MAP (mmHg)")
ax2.set_title("(b) Virtual Vet\n11-organ canine cardiovascular simulation",
              fontsize=11, pad=8)
ax2.set_ylim(90, 190)
ax2.set_xlim(0.0008, 0.2)
ax2.grid(True, alpha=0.2)
ax2.legend(fontsize=8.5, loc="lower left", frameon=False)

# --- Annotations (verified: no overlap with data) ---
# Unsaturated: pre-fix line at dt=0.07 has y ~ 116.
# Annot. bbox centered at y=126 spans 121--131.  Gap to data: ~5 du.
ax2.annotate("Unsaturated\n(bias ~ 1/dt)", xy=(0.07, 126),
             fontsize=9.5, ha="center", va="center",
             bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                       edgecolor=CB_RED, alpha=0.9))

# Saturated: MAP plateaus at 144.7 (HR ceiling = 180 bpm).
# Annot. bbox centered at y=168 spans 163--173.  Well above plateau.
ax2.annotate("Saturated\n(HR ceiling = 180)", xy=(0.008, 168),
             fontsize=9.5, ha="center", va="center",
             bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                       edgecolor=CB_AMBER, alpha=0.9))

# ── Shared figure-level title ───────────────────────────────────────────────
fig.suptitle("Spurious Steady State: Domain-Independent Mechanism",
             fontsize=12, fontweight="bold", y=1.01)

# ─────────────────────────────────────────────────────────────────────────────
# 4.  Save
# ─────────────────────────────────────────────────────────────────────────────
fig.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {OUTPUT_PNG}")
