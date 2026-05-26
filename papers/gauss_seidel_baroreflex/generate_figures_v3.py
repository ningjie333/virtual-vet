#!/usr/bin/env python3
"""
Generate figures for the pseudo-convergence paper.
Figure 1: Pseudo-convergence schematic (drift → saturation → pseudo-fixed point)
Figure 2: MAP bias vs dt — pre-fix three regimes
Figure 3: Code diff — the 6-line fix
Figure 4: Before/after comparison — X/Y/Z MAP range bar chart
"""
import json, os, sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

PAPER_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_DIR = PAPER_DIR
EXP_DIR = os.path.join(os.path.dirname(PAPER_DIR), "..", "experiments")

# ── Load data ────────────────────────────────────────────────────────────────────
with open(os.path.join(EXP_DIR, "exp6_results.json")) as f:
    exp6 = json.load(f)
with open(os.path.join(EXP_DIR, "exp7_fixed_results.json")) as f:
    exp7 = json.load(f)
with open(os.path.join(EXP_DIR, "exp9_abc_results.json")) as f:
    exp9 = json.load(f)

DT_SWEEP = [0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]

# ────────────────────────────────────────────────────────────────────────────────
# Figure 1: Pseudo-convergence schematic
# ────────────────────────────────────────────────────────────────────────────────
fig1, ax1 = plt.subplots(figsize=(7, 4.5))
ax1.set_xlim(-0.5, 9)
ax1.set_ylim(-0.5, 5.5)
ax1.axis("off")
ax1.set_title("Figure 1: Pseudo-Convergence Mechanism", fontsize=12, fontweight="bold", pad=12)

# True fixed point
ax1.add_patch(mpatches.FancyBboxPatch((1.5, 3.8), 2.4, 1.1,
              boxstyle="round,pad=0.1", facecolor="#d4edda", edgecolor="#28a745", lw=2))
ax1.text(2.7, 4.35, "True Fixed Point", ha="center", va="center", fontsize=9, fontweight="bold")
ax1.text(2.7, 4.0, "(MAP ≈ 100 mmHg)", ha="center", va="center", fontsize=8, color="#555")

# Drift arrow (dt error)
ax1.annotate("", xy=(5.2, 3.5), xytext=(4.1, 3.9),
             arrowprops=dict(arrowstyle="->", lw=2, color="#dc3545"))
ax1.text(4.5, 3.55, "drift ∝ K·T/dt", ha="center", fontsize=8, color="#dc3545")
ax1.text(4.5, 3.25, "(FC as bpm/step)", ha="center", fontsize=7, color="#dc3545", style="italic")

# Pseudo-fixed point
ax1.add_patch(mpatches.FancyBboxPatch((6.5, 2.5), 2.4, 1.1,
              boxstyle="round,pad=0.1", facecolor="#f8d7da", edgecolor="#dc3545", lw=2))
ax1.text(7.7, 3.05, "Pseudo-Fixed Point", ha="center", va="center", fontsize=9, fontweight="bold")
ax1.text(7.7, 2.7, "(MAP ≈ 144.7 mmHg)", ha="center", va="center", fontsize=8, color="#555")

# Saturation cap
ax1.add_patch(mpatches.FancyBboxPatch((4.2, 1.2), 3.8, 0.9,
              boxstyle="round,pad=0.1", facecolor="#fff3cd", edgecolor="#ffc107", lw=2))
ax1.text(6.1, 1.65, "HR Saturation at 180 bpm (physiological ceiling)", ha="center", va="center", fontsize=8)
ax1.text(6.1, 1.35, "truncates drift → creates stable pseudo-state", ha="center", va="center", fontsize=7, color="#555")

# Vertical arrow from saturation to pseudo
ax1.annotate("", xy=(7.7, 2.5), xytext=(6.1, 2.1),
             arrowprops=dict(arrowstyle="->", lw=1.5, color="#ffc107"))

# Labels
ax1.text(0.2, 4.8, "A", fontsize=14, fontweight="bold")
ax1.text(0.2, 3.2, "B", fontsize=14, fontweight="bold")
ax1.text(0.2, 1.65, "C", fontsize=14, fontweight="bold")
ax1.text(0.2, 0.3, "D", fontsize=14, fontweight="bold")

# Correct steady state arrow
ax1.annotate("", xy=(4.0, 3.9), xytext=(1.5, 4.35),
             arrowprops=dict(arrowstyle="->", lw=1.5, color="#28a745", ls="dashed"))

ax1.text(2.5, 5.1, "Correct\nsteady state", ha="center", fontsize=7, color="#28a745")

fig1.tight_layout()
fig1.savefig(os.path.join(PAPER_DIR, "fig1_pseudo_convergence_schematic.png"), dpi=300, bbox_inches="tight")
print("Saved fig1_pseudo_convergence_schematic.png")
plt.close(fig1)

# ────────────────────────────────────────────────────────────────────────────────
# Figure 2: MAP bias vs dt — three regimes (from exp6 pre-fix data)
# ────────────────────────────────────────────────────────────────────────────────
# Use DC=10 data from exp9 X condition as representative pre-fix data
DC_REP = 10
x_maps = [exp9["raw"]["X"][f"{DC_REP}_{dt}"]["MAP"] for dt in DT_SWEEP]

fig2, (ax2a, ax2b) = plt.subplots(1, 2, figsize=(10, 4))

# Left: MAP vs dt (linear)
ax2a.plot(DT_SWEEP, x_maps, "o-", color="#dc3545", lw=2, ms=6, label="Pre-fix MAP")
ax2a.axhline(y=100, color="#28a745", lw=1.5, ls="--", label="Physiological MAP (~100)")
ax2a.axhline(y=144.7, color="#6c757d", lw=1, ls=":", label="Saturation MAP")
ax2a.set_xscale("log")
ax2a.set_xlabel("dt (s)", fontsize=10)
ax2a.set_ylabel("MAP (mmHg)", fontsize=10)
ax2a.set_title("Figure 2a: MAP vs dt — Pre-fix (DC=10)", fontsize=11, fontweight="bold")
ax2a.legend(fontsize=8)
ax2a.grid(True, alpha=0.3)

# Right: bias × dt vs dt (log-log)
bias = [m - 100 for m in x_maps]  # bias relative to correct MAP
bias_dt = [b * d for b, d in zip(bias, DT_SWEEP)]
ax2b.loglog(DT_SWEEP, [abs(b) for b in bias], "o-", color="#dc3545", lw=2, ms=6, label="|bias|")
ax2b.loglog(DT_SWEEP, [b * d for b, d in zip(bias, DT_SWEEP) if b > 0], "s--",
            color="#17a2b8", lw=1.5, ms=5, label="bias × dt (∝ 1/dt → const)")
ax2b.set_xlabel("dt (s)", fontsize=10)
ax2b.set_ylabel("|bias| or bias×dt", fontsize=10)
ax2b.set_title("Figure 2b: Dimensional Analysis (bias ∝ 1/dt)", fontsize=11, fontweight="bold")
ax2b.legend(fontsize=8)
ax2b.grid(True, alpha=0.3)

# Annotate regions
ax2a.annotate("Unsaturated\n(bias∝1/dt)", xy=(0.08, 125), fontsize=7, color="#dc3545")
ax2a.annotate("Saturated\n(plateau)", xy=(0.002, 143), fontsize=7, color="#6c757d")

fig2.tight_layout()
fig2.savefig(os.path.join(PAPER_DIR, "fig2_map_bias_vs_dt.png"), dpi=300, bbox_inches="tight")
print("Saved fig2_map_bias_vs_dt.png")
plt.close(fig2)

# ────────────────────────────────────────────────────────────────────────────────
# Figure 3: Code diff — the 6-line fix
# ────────────────────────────────────────────────────────────────────────────────
fig3, ax3 = plt.subplots(figsize=(9, 5))
ax3.axis("off")
ax3.set_xlim(0, 10)
ax3.set_ylim(0, 10)
ax3.set_title("Figure 3: Code Fix — 6 Lines Changed (src/neuro.py + src/heart.py)", fontsize=12, fontweight="bold", pad=10)

Y = 9.2
# Header
ax3.text(0.3, Y, "BEFORE (buggy)", fontsize=10, fontweight="bold", color="#dc3545")
ax3.text(5.3, Y, "AFTER (fixed)", fontsize=10, fontweight="bold", color="#28a745")

old_snippets = [
    ("net_HR_add = (", "    pain_HR_add"),
    ("    + seizure_HR_add", "    + cns_HR_add"),
    ("    + chemo_HR_add)", "    # chemo_HR → continuous path"),
    ("", "net_HR_add = ("),
    ("    pain_HR_add", "    + seizure_HR_add"),
    ("    + seizure_HR_add", "    + cns_HR_add"),
    ("    + cns_HR_add", "    # no chemo here"),
    ("    + chemo_HR_add)", ""),
]
new_snippets = [
    ("net_HR_add = (", "    pain_HR_add"),
    ("    + seizure_HR_add", "    + cns_HR_add"),
    ("    # chemo_HR → heart.py)", ""),
    ("", "net_HR_add = ("),
    ("    pain_HR_add", "    + seizure_HR_add"),
    ("    + seizure_HR_add", "    + cns_HR_add"),
    ("    + cns_HR_add", "    # removed chemo_HR_add"),
    ("    + chemo_HR_add)", "    # now in heart.py only"),
]

# Simple two-column code diff
left_x = 0.3
right_x = 5.3
y_step = 0.6
y = 8.4

for i, (old, new_old) in enumerate(old_snippets):
    if old:
        ax3.text(left_x, y, old, fontsize=8, fontfamily="monospace",
                 color="#dc3545" if i in [0, 1, 2] else "#333")
    if new_old:
        ax3.text(right_x, y, new_old, fontsize=8, fontfamily="monospace",
                 color="#28a745" if i in [3, 4, 5] else "#333")
    y -= y_step

# Highlight box around key change
ax3.add_patch(mpatches.FancyBboxPatch((4.8, 4.5), 2.5, 1.0,
              boxstyle="round,pad=0.1", facecolor="#d4edda", edgecolor="#28a745", lw=1.5, alpha=0.3))
ax3.text(left_x, 4.0, "HR_delta = (HR_para + HR_symp) × dt", fontsize=8, fontfamily="monospace", color="#333")
ax3.text(right_x, 4.0, "HR_delta = (HR_para + HR_symp", fontsize=8, fontfamily="monospace", color="#28a745")
ax3.text(right_x + 2.5, 4.0, " + chemo_HR) × dt", fontsize=8, fontfamily="monospace", color="#28a745")

# Arrow showing key insight
ax3.annotate("", xy=(5.3, 5.5), xytext=(2.5, 5.5),
             arrowprops=dict(arrowstyle="->", lw=1.5, color="#17a2b8"))
ax3.text(3.9, 5.7, "chemo_HR moved to\ncontinuous path (heart.py)", fontsize=7, color="#17a2b8")

fig3.tight_layout()
fig3.savefig(os.path.join(PAPER_DIR, "fig3_code_diff.png"), dpi=300, bbox_inches="tight")
print("Saved fig3_code_diff.png")
plt.close(fig3)

# ────────────────────────────────────────────────────────────────────────────────
# Figure 4: Before/after comparison — X/Y/Z MAP range bar chart
# ────────────────────────────────────────────────────────────────────────────────
summary = exp9["summary"]
DCs = [s["dc"] for s in summary]
x_ranges = [s["X_range"] for s in summary]
y_ranges = [s["Y_range"] for s in summary]
z_ranges = [s["Z_range"] for s in summary]

x = np.arange(len(DCs))
width = 0.25

fig4, ax4 = plt.subplots(figsize=(8, 4.5))
bars1 = ax4.bar(x - width, x_ranges, width, label="X (buggy)", color="#dc3545", alpha=0.8)
bars2 = ax4.bar(x,          y_ranges, width, label="Y (A-only: FC×dt)", color="#17a2b8", alpha=0.8)
bars3 = ax4.bar(x + width,  z_ranges, width, label="Z (A+B: FC×dt + cont.)", color="#28a745", alpha=0.8)

ax4.set_xlabel("DC value (hypoxemia severity)", fontsize=10)
ax4.set_ylabel("MAP range across dt sweep (mmHg)", fontsize=10)
ax4.set_title("Figure 4: MAP Range — Three-Condition Isolation\n(X=buggy, Y=A-only, Z=A+B)", fontsize=11, fontweight="bold")
ax4.set_xticks(x)
ax4.set_xticklabels([f"DC={d}\n({'normal' if d==25 else 'mild' if d==15 else 'moderate' if d==10 else 'severe'})" for d in DCs])
ax4.legend(fontsize=9)
ax4.grid(True, alpha=0.3, axis="y")

# Annotate A_contrib
for i, (xr, yr) in enumerate(zip(x_ranges, y_ranges)):
    if xr > 1:
        ax4.annotate(f"A={xr-yr:.1f}", xy=(i - width, xr + 0.5), fontsize=7, color="#dc3545", ha="center")

fig4.tight_layout()
fig4.savefig(os.path.join(PAPER_DIR, "fig4_before_after_comparison.png"), dpi=300, bbox_inches="tight")
print("Saved fig4_before_after_comparison.png")
plt.close(fig4)

print("\nAll figures saved to", PAPER_DIR)