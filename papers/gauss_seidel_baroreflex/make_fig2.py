#!/usr/bin/env python3
"""
Figure 2: MAP bias vs dt -- pre-fix data from manuscript Table 1 (DC=10).

Two panels:
  (a) Left: semilogx MAP vs dt with nominal and saturation lines
  (b) Right: loglog dimensional analysis showing bias ~ 1/dt

Output: fig2_map_bias_vs_dt.png (300 DPI, Times New Roman)
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

# ── Paths ───────────────────────────────────────────────────────────────────
PAPER_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Shared style (Times New Roman, publication-ready) ────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "legend.fontsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.8,
})

# Markers and colors (colorblind-friendly, Wong 2011 / IBM Carbon)
CB_BLUE   = "#006BA6"
CB_ORANGE = "#E68A2E"
CB_RED    = "#D55E00"
CB_GREEN  = "#009E73"

# ── Data from manuscript Table 1 (DC=10, pre-fix) ────────────────────────────
dt       = np.array([0.1, 0.05, 0.02, 0.01, 0.005, 0.001])
map_pre  = np.array([111.0, 121.1, 144.7, 144.7, 144.7, 144.7])
CORRECT_MAP = 100.0
SAT_VAL     = 144.7

# ── Build figure ─────────────────────────────────────────────────────────────
fig, (axL, axR) = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)

# ═══════════════════════════════════════════════════════════════════════════
# Panel (a): semilogx MAP vs dt
# ═══════════════════════════════════════════════════════════════════════════
axL.semilogx(dt, map_pre, "o-", color=CB_BLUE, lw=2, ms=7, zorder=3)
axL.axhline(y=CORRECT_MAP, color=CB_GREEN, lw=1.5, ls="--",
            label=f"Nominal MAP ({CORRECT_MAP:.0f} mmHg)")
axL.axhline(y=SAT_VAL, color=CB_RED, lw=1, ls=":",
            label=f"Saturation plateau ({SAT_VAL:.1f} mmHg)")

axL.set_xlabel("Time step dt (s)")
axL.set_ylabel("MAP (mmHg)")
axL.set_title("(a) Pre-fix MAP vs dt  (DC=10)")
axL.legend(fontsize=9, loc="lower left")
axL.grid(True, alpha=0.25)
axL.set_xlim(0.0008, 0.15)
axL.set_ylim(90, 155)

# Annotation A: unsaturated regime (dt=0.05-0.1, bias ~ 1/dt)
# Data line at dt=0.065 (mid-log between 0.05 and 0.1) interpolates to ~117.3
# Place arrow tip on data line, text above with white bbox
axL.annotate(
    "Unsaturated\n(bias ~ 1/dt)",
    xy=(0.065, 117.3),          # arrow tip on data line
    xytext=(0.07, 132),         # text well above data
    fontsize=9, color=CB_BLUE, ha="center",
    arrowprops=dict(arrowstyle="->", color=CB_BLUE, lw=1.2),
    bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
              edgecolor=CB_BLUE, alpha=0.9)
)

# Annotation B: saturated regime (dt <= 0.02, MAP plateau at 144.7)
# Place arrow tip just below the 144.7 line, text below-left
axL.annotate(
    "Saturated\n(MAP plateau)",
    xy=(0.012, 143.5),          # just below plateau line
    xytext=(0.003, 134),        # text below and left
    fontsize=9, color=CB_RED, ha="center",
    arrowprops=dict(arrowstyle="->", color=CB_RED, lw=1.2),
    bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
              edgecolor=CB_RED, alpha=0.9)
)


# ═══════════════════════════════════════════════════════════════════════════
# Panel (b): loglog dimensional analysis (bias vs dt; bias*dt constant)
# ═══════════════════════════════════════════════════════════════════════════
bias       = map_pre - CORRECT_MAP
bias_dt    = bias * dt
unsat_mask = dt >= 0.02          # unsaturated (or transition) regime

axR.loglog(dt, bias, "o-", color=CB_BLUE, lw=2, ms=7,
           label="|bias| = |MAP − 100|")
axR.loglog(dt[unsat_mask], bias_dt[unsat_mask], "s--",
           color=CB_ORANGE, lw=1.8, ms=6,
           label="bias × dt  (constant → 1/dt)")

axR.set_xlabel("Time step dt (s)")
axR.set_ylabel("|bias| or bias × dt")
axR.set_title("(b) Dimensional Analysis  (bias ~ 1/dt)")
axR.legend(fontsize=9)
axR.grid(True, alpha=0.25)
axR.set_xlim(0.0008, 0.15)

# Annotation: constant bias × dt product
const_val = bias_dt[unsat_mask].mean()
# Arrow tip at the interpolated bias*dt value at dt=0.035
axR.annotate(
    f"bias × dt ~ {const_val:.2f}\n(constant → 1/dt)",
    xy=(0.035, 0.99),           # arrow tip on bias×dt line
    xytext=(0.045, 1.7),        # text above (visible between bias & bias*dt)
    fontsize=9, color=CB_ORANGE, ha="center",
    arrowprops=dict(arrowstyle="->", color=CB_ORANGE, lw=1.2),
    bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
              edgecolor=CB_ORANGE, alpha=0.9)
)

# ── Save ─────────────────────────────────────────────────────────────────────
fig.savefig(os.path.join(PAPER_DIR, "fig2_map_bias_vs_dt.png"),
            dpi=300, bbox_inches="tight")
plt.close(fig)
print("  fig2_map_bias_vs_dt.png  saved.")
