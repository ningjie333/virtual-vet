#!/usr/bin/env python3
"""
Unified figure generator for manuscript_v5.md.
Generates Figures 1–5 with consistent style, colorblind-friendly palette,
and carefully computed coordinates for annotation alignment.

Usage:  python papers/gauss_seidel_baroreflex/generate_all_figures.py
Output: papers/gauss_seidel_baroreflex/fig{1..5}_*.png (300 DPI)
"""

import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

# ── Paths ───────────────────────────────────────────────────────────────────
PAPER_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT     = os.path.normpath(os.path.join(PAPER_DIR, "..", ".."))
EXP_DIR  = os.path.join(ROOT, "experiments")

# ── Shared style ────────────────────────────────────────────────────────────
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
})

# Colorblind-friendly palette (IBM Carbon / Wong 2011 inspired)
CB_BLUE   = "#006BA6"
CB_ORANGE = "#E68A2E"
CB_PURPLE = "#8A2BE2"
CB_TEAL   = "#009E73"
CB_RED    = "#D55E00"
CB_GREY   = "#7F7F7F"
CB_GREEN  = "#009E73"
CB_SKYBLUE= "#56B4E9"
CB_PINK   = "#CC79A7"

# ── Helper: FancyBox with text (Nature-style: white bg, thin border) ────────
def fancybox(ax, xc, yc, w, h, text, subtext="",
             face="white", edge=CB_BLUE, text_color="black",
             fontsize=9, sub_fontsize=8):
    """Draw a rounded box centered at (xc, yc) with optional sub-text."""
    box = FancyBboxPatch((xc - w/2, yc - h/2), w, h,
                         boxstyle="round,pad=0.12",
                         facecolor=face, edgecolor=edge, lw=1.2)
    ax.add_patch(box)
    ax.text(xc, yc + (0.06 * h if subtext else 0), text,
            ha="center", va="center", fontsize=fontsize,
            fontweight="bold", color=text_color)
    if subtext:
        ax.text(xc, yc - 0.25 * h, subtext,
                ha="center", va="center", fontsize=sub_fontsize, color="#444")

def arrow(ax, x1, y1, x2, y2, color="black", lw=1.5, style="-",
          connectionstyle="arc3,rad=0"):
    """Draw an arrow annotation from (x1,y1) to (x2,y2)."""
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", lw=lw,
                                color=color, linestyle=style,
                                connectionstyle=connectionstyle))


# ═══════════════════════════════════════════════════════════════════════════
# Figure 1 — Spurious steady state schematic
# ═══════════════════════════════════════════════════════════════════════════
def make_fig1():
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    ax.set_xlim(-0.5, 10.5)
    ax.set_ylim(-0.3, 6.5)
    ax.axis("off")
    ax.set_title("Figure 1: Spurious Steady State — Drift and Saturation Mechanism",
                 fontsize=12, fontweight="bold", pad=12)

    # ── Uniform box geometry: w=2.8, h=0.85 ───────────────────────────
    BOX_W = 2.8
    BOX_H = 0.85

    # ── Row 1: True Fixed Point (top-left) ──────────────────────────────
    xc_tfp, yc_tfp = 2.2, 5.2
    fancybox(ax, xc_tfp, yc_tfp, BOX_W, BOX_H,
             "True Fixed Point", "MAP ≈ 100 mmHg",
             face="white", edge=CB_BLUE, fontsize=10)

    # ── Row 2: Spurious Fixed Point (top-right) ─────────────────────────
    xc_sfp, yc_sfp = 7.8, 5.2
    fancybox(ax, xc_sfp, yc_sfp, BOX_W, BOX_H,
             "Spurious Fixed Point", "MAP ≈ 144.7 mmHg",
             face="white", edge=CB_RED, fontsize=10)

    # ── Row 3: HR Saturation (mid-right) ────────────────────────────────
    xc_sat, yc_sat = 7.8, 3.3
    fancybox(ax, xc_sat, yc_sat, BOX_W + 0.4, BOX_H,
             "HR Saturation at 180 bpm",
             "physiological ceiling truncates drift",
             face="white", edge="#c8860a", fontsize=9, sub_fontsize=8)

    # ── Row 4: Continuous Baroreflex Path (bottom-left) ────────────────
    xc_cbp, yc_cbp = 2.2, 1.8
    fancybox(ax, xc_cbp, yc_cbp, BOX_W, BOX_H,
             "Continuous Baroreflex Path",
             "HR_delta = (symp + para + chemo) × dt  →  correct",
             face="white", edge=CB_GREEN, fontsize=9, sub_fontsize=8)

    # ── Row 5: Discrete FC Path (bottom-right) ──────────────────────────
    xc_dfc, yc_dfc = 7.8, 1.8
    fancybox(ax, xc_dfc, yc_dfc, BOX_W, BOX_H,
             "Discrete FC Path (buggy)",
             "net_HR_add = K bpm/step  →  K × T/dt total injection",
             face="white", edge=CB_RED, fontsize=9, sub_fontsize=8)

    # ── Arrows (uniform style: solid filled triangle heads) ──────────────
    # Arrow 1: True FP → Spurious FP (main drift arrow, top)
    ax.annotate("", xy=(6.2, 5.2), xytext=(3.7, 5.2),
                arrowprops=dict(arrowstyle="-|>", lw=1.8, color=CB_RED,
                                mutation_scale=14))
    ax.text(4.95, 5.45, "drift ~ K × T / dt",
            ha="center", fontsize=9.5, color=CB_RED, fontweight="bold")
    ax.text(4.95, 4.95, "(FC emission as bpm/step, not bpm/s)",
            ha="center", fontsize=7.5, color=CB_RED, fontstyle="italic")

    # Arrow 2: Saturation → Spurious FP (upward, orange)
    ax.annotate("", xy=(7.8, 4.55), xytext=(7.8, 3.65),
                arrowprops=dict(arrowstyle="-|>", lw=1.5, color="#c8860a",
                                mutation_scale=12))
    ax.text(8.55, 4.1, "truncates drift",
            ha="left", va="center", fontsize=8.5, color="#c8860a", fontstyle="italic")

    # Arrow 3: Continuous path → True FP (up, dashed green)
    ax.annotate("", xy=(3.6, 2.55), xytext=(3.6, 2.15),
                arrowprops=dict(arrowstyle="-|>", lw=1.2, color=CB_GREEN,
                                ls="dashed", mutation_scale=10))

    # Arrow 4: Discrete FC → Saturation (up, dashed red)
    ax.annotate("", xy=(7.8, 2.55), xytext=(7.8, 2.15),
                arrowprops=dict(arrowstyle="-|>", lw=1.2, color=CB_RED,
                                ls="dashed", mutation_scale=10))

    # ── Panel labels A/B/C/D (sans-serif, top-left aligned) ──────────────
    ax.text(0.1, 5.7, "A", fontsize=13, fontweight="bold",
            va="top", ha="left", color="black",
            fontfamily="sans-serif")
    ax.text(0.1, 4.1, "B", fontsize=13, fontweight="bold",
            va="top", ha="left", color="black",
            fontfamily="sans-serif")
    ax.text(0.1, 2.7, "C", fontsize=13, fontweight="bold",
            va="top", ha="left", color="black",
            fontfamily="sans-serif")
    ax.text(0.1, 1.1, "D", fontsize=13, fontweight="bold",
            va="top", ha="left", color="black",
            fontfamily="sans-serif")

    fig.savefig(os.path.join(PAPER_DIR, "fig1_pseudo_convergence_schematic.png"),
                dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  ✅ fig1_pseudo_convergence_schematic.png")


# ═══════════════════════════════════════════════════════════════════════════
# Figure 2 — MAP bias vs dt (pre-fix, using manuscript Table 1 data)
# ═══════════════════════════════════════════════════════════════════════════
def make_fig2():
    # Pre-fix data from manuscript Table 1 (DC=10, original buggy code)
    DT_6  = np.array([0.1, 0.05, 0.02, 0.01, 0.005, 0.001])
    MAP_PRE = np.array([111.0, 121.1, 144.7, 144.7, 144.7, 144.7])
    CORRECT_MAP = 100.0  # nominal correct MAP

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)

    # ── Left: MAP vs dt (log x-axis) ──
    axL.semilogx(DT_6, MAP_PRE, "o-", color=CB_BLUE, lw=2, ms=7, zorder=3)
    axL.axhline(y=CORRECT_MAP, color=CB_GREEN, lw=1.5, ls="--",
                label=f"Nominal MAP ({CORRECT_MAP:.0f} mmHg)")
    # saturation plateau line
    sat_val = MAP_PRE[-1]
    axL.axhline(y=sat_val, color=CB_RED, lw=1, ls=":",
                label=f"Saturation plateau ({sat_val:.1f} mmHg)")

    axL.set_xlabel("Time step dt (s)")
    axL.set_ylabel("MAP (mmHg)")
    axL.set_title("(a) Pre-fix MAP vs dt  (DC=10)", fontsize=11)
    axL.legend(fontsize=8, loc="lower left")
    axL.grid(True, alpha=0.25)
    axL.set_xlim(0.0008, 0.15)

    # Annotations — careful coordinate alignment
    # Unsaturated region: dt = 0.1 and 0.05
    axL.annotate("Unsaturated\n(bias ~ 1/dt)",
                 xy=(0.065, 118), fontsize=8.5, color=CB_BLUE, ha="center",
                 bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=CB_BLUE, alpha=0.8))
    # Saturated region
    axL.annotate("Saturated\n(MAP plateau)",
                 xy=(0.005, 143), fontsize=8.5, color=CB_RED, ha="center",
                 bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=CB_RED, alpha=0.8))

    # ── Right: Dimensional analysis (bias × dt = const) ──
    bias = MAP_PRE - CORRECT_MAP
    bias_dt = bias * DT_6

    # Only show unsaturated points for bias×dt (saturated ones are truncated)
    unsat_mask = DT_6 >= 0.02  # dt >= 0.02

    axR.loglog(DT_6, np.maximum(bias, 0.1), "o-", color=CB_BLUE, lw=2, ms=7,
               label="|bias| = |MAP − 100|")
    axR.loglog(DT_6[unsat_mask], bias_dt[unsat_mask], "s--",
               color=CB_ORANGE, lw=1.8, ms=6, label="bias × dt  (constant → 1/dt)")
    axR.set_xlabel("Time step dt (s)")
    axR.set_ylabel("|bias| or bias × dt")
    axR.set_title("(b) Dimensional Analysis  (bias ~ 1/dt)", fontsize=11)
    axR.legend(fontsize=8)
    axR.grid(True, alpha=0.25)
    axR.set_xlim(0.0008, 0.15)

    # Annotation showing constant product
    const_val = bias_dt[unsat_mask].mean()
    axR.annotate(f"bias × dt ≈ {const_val:.2f}\n(constant ~ 1/dt)",
                 xy=(0.035, const_val * 1.8), fontsize=8.5,
                 bbox=dict(boxstyle="round,pad=0.25", facecolor="#fff8e1",
                           edgecolor=CB_ORANGE, alpha=0.9))

    fig.savefig(os.path.join(PAPER_DIR, "fig2_map_bias_vs_dt.png"),
                dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  ✅ fig2_map_bias_vs_dt.png")


# ═══════════════════════════════════════════════════════════════════════════
# Figure 3 — Code diff: BEFORE vs AFTER (7-line fix)
# ═══════════════════════════════════════════════════════════════════════════
def make_fig3():
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_title("Figure 3: Code Fix — 7 Lines Changed",
                 fontsize=12, fontweight="bold", pad=8)

    # Column headers
    ax.text(1.0, 9.6, "BEFORE (buggy)", fontsize=11, fontweight="bold",
            color=CB_RED, ha="center")
    ax.text(7.0, 9.6, "AFTER (fixed)", fontsize=11, fontweight="bold",
            color=CB_GREEN, ha="center")
    ax.plot([5.0, 5.0], [0.3, 9.3], color="#ccc", lw=1.5, ls="--")

    # Code lines: each entry is (side, y_pos, text, color, bg)
    # Format: ("L"|"R", y, text, color, bg_alpha)
    LEFT, RIGHT = "L", "R"
    code = [
        # ── Header comment ──
        (LEFT,  8.8, "# net_HR_add in neuro.py", "#666", 0),
        (RIGHT, 8.8, "# net_HR_add in neuro.py", "#666", 0),

        # ── Line 1: unchanged ──
        (LEFT,  8.2, "net_HR_add = (", "#333", 0),
        (RIGHT, 8.2, "net_HR_add = (", "#333", 0),

        # ── Line 2: unchanged ──
        (LEFT,  7.6, "    pain_HR_add", "#333", 0),
        (RIGHT, 7.6, "    pain_HR_add", "#333", 0),

        # ── Line 3: unchanged ──
        (LEFT,  7.0, "    + seizure_HR_add", "#333", 0),
        (RIGHT, 7.0, "    + seizure_HR_add", "#333", 0),

        # ── Line 4: unchanged ──
        (LEFT,  6.4, "    + cns_HR_add", "#333", 0),
        (RIGHT, 6.4, "    + cns_HR_add", "#333", 0),

        # ── Line 5: DELETED from LEFT (red bg), missing from RIGHT ──
        (LEFT,  5.8, "    + chemo_HR_add)", CB_RED, 0.12),
        # Right side: gap (no text)

        # ── Line 6: comment changed ──
        (LEFT,  5.2, "# chemo_HR → continuous path", CB_RED, 0.08),
        (RIGHT, 5.2, "# chemo_HR → heart.py only", CB_GREEN, 0.08),

        # ── Space ──
        # y=4.6: blank

        # ── heart.py code ──
        (LEFT,  4.2, "# In heart.py _baroreceptor_feedback:", "#666", 0),
        (RIGHT, 4.2, "# In heart.py _baroreceptor_feedback:", "#666", 0),

        (LEFT,  3.6, "HR_delta = (HR_para + HR_symp) × dt", "#333", 0),
        (RIGHT, 3.6, "HR_delta = (HR_para + HR_symp", "#333", 0),
        (RIGHT, 3.2, "           + chemo_HR) × dt", CB_GREEN, 0.12),

        # ── FC dt-scaling (the key fix) ──
        (LEFT,  2.4, "# FC emission (neuro.py) — NO dt factor", CB_RED, 0.12),
        (RIGHT, 2.4, "# FC emission — now scaled by dt", CB_GREEN, 0.12),

        (LEFT,  1.8, "FC('heart.heart_rate', 'add', net_HR_add)", "#333", 0),
        (RIGHT, 1.6, "FC('heart.heart_rate', 'add', net_HR_add * dt)", CB_GREEN, 0.10),

        # ── SVR multiply fix ──
        (LEFT,  0.8, "FC('heart.svr', 'multiply', net_SVR_mult)", "#333", 0),
        (RIGHT, 0.6, "FC('heart.svr', 'multiply', net_SVR_mult ** dt)", CB_GREEN, 0.10),
    ]

    for side, y, text, color, bg_alpha in code:
        x = 1.0 if side == LEFT else 7.0
        ha = "center"
        if bg_alpha > 0:
            # Background highlight
            w = 4.5
            rect = FancyBboxPatch((x - w/2, y - 0.18), w, 0.42,
                                  boxstyle="round,pad=0.05",
                                  facecolor=color, edgecolor="none",
                                  alpha=bg_alpha)
            ax.add_patch(rect)
        ax.text(x, y, text, fontsize=8.5, fontfamily="monospace",
                color=color, ha=ha, va="center")

    # ── Key insight callout ──
    # Arrow pointing to the FC dt change
    ax.annotate("", xy=(1.0, 1.7), xytext=(1.0, 2.1),
                arrowprops=dict(arrowstyle="->", lw=2, color=CB_ORANGE))
    ax.annotate("", xy=(7.0, 1.5), xytext=(7.0, 1.9),
                arrowprops=dict(arrowstyle="->", lw=2, color=CB_ORANGE))
    ax.text(4.0, 1.1, "Key fix: multiply FC delta by dt",
            ha="center", fontsize=10, color=CB_ORANGE, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff8e1",
                      edgecolor=CB_ORANGE, lw=1.5))

    # Dimension labels
    ax.text(1.0, 0.1, "bpm/step  (wrong)", ha="center", fontsize=8,
            color=CB_RED, fontstyle="italic")
    ax.text(7.0, 0.1, "bpm/s  (correct)", ha="center", fontsize=8,
            color=CB_GREEN, fontstyle="italic")

    fig.savefig(os.path.join(PAPER_DIR, "fig3_code_diff.png"),
                dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  ✅ fig3_code_diff.png")


# ═══════════════════════════════════════════════════════════════════════════
# Figure 4 — X/Y/Z MAP range bar chart (exp9 isolation experiment)
# ═══════════════════════════════════════════════════════════════════════════
def make_fig4():
    with open(os.path.join(EXP_DIR, "exp9_abc_results.json")) as f:
        exp9 = json.load(f)

    summary = exp9["summary"]
    dcs = [s["dc"] for s in summary]
    x_vals = np.array([s["X_range"] for s in summary])
    y_vals = np.array([s["Y_range"] for s in summary])
    z_vals = np.array([s["Z_range"] for s in summary])
    a_contrib = np.array([s["A_contrib"] for s in summary])

    severity_map = {25: "normal", 15: "mild", 10: "moderate", 5: "severe"}
    labels = [f"DC={d}\n({severity_map[d]})" for d in dcs]

    n_groups = len(dcs)
    x = np.arange(n_groups)
    width = 0.22
    gap = 0.05

    fig, ax = plt.subplots(figsize=(8.5, 4.8))

    bar_positions = {
        "X": x - width - gap / 2,
        "Y": x,
        "Z": x + width + gap / 2,
    }

    ax.bar(bar_positions["X"], x_vals, width,
           label="X (buggy: FC bpm/step)", color=CB_RED, alpha=0.88,
           edgecolor="white", linewidth=0.4)
    ax.bar(bar_positions["Y"], y_vals, width,
           label="Y (A-only: FC x dt)", color=CB_ORANGE, alpha=0.88,
           edgecolor="white", linewidth=0.4)
    ax.bar(bar_positions["Z"], z_vals, width,
           label="Z (A+B: FC x dt + cont.)", color=CB_GREEN, alpha=0.88,
           edgecolor="white", linewidth=0.4)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel("Hypoxemia severity (DC value)")
    ax.set_ylabel("MAP range across dt sweep (mmHg)")
    ax.set_title("Figure 4: MAP Range — Three-Condition Isolation",
                 fontsize=12, fontweight="bold", pad=10)
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(True, alpha=0.2, axis="y", linestyle=":")

    # Annotations: A_contrib on X bars where > 1
    max_bar = max(x_vals.max(), y_vals.max(), z_vals.max())
    pad = 0.12 * max_bar
    annotation_heights = []

    for i in range(n_groups):
        grp_h = []
        if a_contrib[i] > 1:
            y_pos = x_vals[i] + pad * 0.9
            ax.annotate(f"A = {a_contrib[i]:.1f}",
                        xy=(bar_positions["X"][i] + width / 2, x_vals[i]),
                        xytext=(bar_positions["X"][i] + width / 2, y_pos),
                        fontsize=8.5, color=CB_RED, ha="center", va="bottom",
                        fontweight="bold",
                        arrowprops=dict(arrowstyle="-", color=CB_RED, lw=0.5, alpha=0.4))
            grp_h.append(y_pos)

        if y_vals[i] > 0.5 and y_vals[i] < x_vals[i] * 0.5:
            y_off = y_vals[i] + pad * 0.6
            ax.text(bar_positions["Y"][i] + width / 2, y_off,
                    f"{y_vals[i]:.2f}", fontsize=7.5, color=CB_ORANGE,
                    ha="center", va="bottom")
            grp_h.append(y_off)

        if z_vals[i] > 0.5 and z_vals[i] < x_vals[i] * 0.5:
            z_off = z_vals[i] + pad * 0.6
            ax.text(bar_positions["Z"][i] + width / 2, z_off,
                    f"{z_vals[i]:.2f}", fontsize=7.5, color=CB_GREEN,
                    ha="center", va="bottom")
            grp_h.append(z_off)

        annotation_heights.append(grp_h)

    # Set y-limit to accommodate annotations
    all_ah = [max(grp) if grp else 0 for grp in annotation_heights]
    max_ah = max(all_ah) if any(all_ah) else max_bar
    ax.set_ylim(0, max_ah + 0.20 * max_bar)

    # Green bracket highlight for DC=10 and DC=5 (the fix region)
    for idx in [2, 3]:
        if idx < n_groups:
            xc = x[idx]
            by = max_bar * 1.02
            ax.plot([xc - width - gap / 2, xc + width + gap / 2], [by, by],
                    color=CB_GREEN, lw=1.0, alpha=0.5)
            ax.plot([xc - width - gap / 2, xc - width - gap / 2],
                    [by, by - max_bar * 0.015], color=CB_GREEN, lw=0.8, alpha=0.5)
            ax.plot([xc + width + gap / 2, xc + width + gap / 2],
                    [by, by - max_bar * 0.015], color=CB_GREEN, lw=0.8, alpha=0.5)

    # Caption-style note
    ax.text(0.98, 0.98,
            "A = X_range − Y_range  (FC dt-scaling eliminates the bias)",
            transform=ax.transAxes, fontsize=8, fontstyle="italic",
            ha="right", va="top", color=CB_GREY,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=CB_GREY, alpha=0.7))

    fig.savefig(os.path.join(PAPER_DIR, "fig4_before_after_comparison.png"),
                dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  ✅ fig4_before_after_comparison.png")


# ═══════════════════════════════════════════════════════════════════════════
# Figure 5 — Toy model vs Virtual Vet — side-by-side comparison
# ═══════════════════════════════════════════════════════════════════════════
def make_fig5():
    # ── Toy model data (computed) ──
    def simulate_toy(K=0.5, dt=0.01, k=0.25, x_target=100.0,
                     x_ceiling=180.0, sensor_value=0.02,
                     sensor_threshold=0.01, T=60.0, buggy=True):
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

    TOY_DTS = np.array([0.1, 0.05, 0.02, 0.01, 0.005, 0.001])
    K_DEFAULT = 0.5
    toy_pre  = np.array([simulate_toy(K_DEFAULT, dt, buggy=True)  for dt in TOY_DTS])
    toy_post = np.array([simulate_toy(K_DEFAULT, dt, buggy=False) for dt in TOY_DTS])

    # ── Virtual Vet data (from manuscript Table 1 + exp8) ──
    VT_PRE  = np.array([111.0, 121.1, 144.7, 144.7, 144.7, 144.7])
    VT_POST = np.array([102.26, 102.26, 102.26, 102.26, 102.26, 102.26])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.2), constrained_layout=True)

    # ── Left: Toy Model ──
    ax1.plot(TOY_DTS, toy_pre,  "o-",  color=CB_RED,   lw=2, ms=7, label="Buggy (unit/step)")
    ax1.plot(TOY_DTS, toy_post, "s--", color=CB_BLUE,  lw=2, ms=6, label="Fixed (unit/s)")
    ax1.axhline(y=toy_post[0], color=CB_BLUE, ls=":", alpha=0.4,
                label=f"Correct SS ≈ {toy_post[0]:.0f}")
    ax1.set_xlabel("Time step dt (s)")
    ax1.set_ylabel("State x (a.u.)")
    ax1.set_title("(a) Toy Model\n(dx/dt = −k·(x−x₀) + FC event)", fontsize=11)
    ax1.set_xscale("log")
    ax1.set_ylim(90, 190)
    ax1.grid(True, alpha=0.25)
    ax1.legend(fontsize=8, loc="lower left")

    ax1.annotate("Unsaturated\n(bias ~ 1/dt)", xy=(0.07, 125),
                 fontsize=8.5, ha="center",
                 bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                           edgecolor=CB_RED, alpha=0.8))
    ax1.annotate("Saturated\n(ceiling=180)", xy=(0.008, 178),
                 fontsize=8.5, ha="center", va="top",
                 bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                           edgecolor="#f9a825", alpha=0.8))

    # ── Right: Virtual Vet ──
    ax2.plot(TOY_DTS, VT_PRE,  "o-",  color=CB_RED,   lw=2, ms=7, label="Pre-fix (buggy)")
    ax2.plot(TOY_DTS, VT_POST, "s--", color=CB_BLUE,  lw=2, ms=6, label="Post-fix (fixed)")
    ax2.axhline(y=VT_POST[0], color=CB_BLUE, ls=":", alpha=0.4,
                label=f"Correct SS ≈ {VT_POST[0]:.0f}")
    ax2.set_xlabel("Time step dt (s)")
    ax2.set_ylabel("MAP (mmHg)")
    ax2.set_title("(b) Virtual Vet (canine CV)\n11-organ cardiovascular simulation",
                  fontsize=11)
    ax2.set_xscale("log")
    ax2.set_ylim(90, 190)
    ax2.grid(True, alpha=0.25)
    ax2.legend(fontsize=8, loc="lower left")

    ax2.annotate("Unsaturated\n(bias ~ 1/dt)", xy=(0.07, 121),
                 fontsize=8.5, ha="center",
                 bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                           edgecolor=CB_RED, alpha=0.8))
    ax2.annotate("Saturated\n(HR ceiling=180)", xy=(0.008, 178),
                 fontsize=8.5, ha="center", va="top",
                 bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                           edgecolor="#f9a825", alpha=0.8))

    fig.suptitle("Spurious Steady State: Toy Model vs Virtual Vet — Identical Pattern",
                 fontsize=12, fontweight="bold", y=1.02)

    fig.savefig(os.path.join(PAPER_DIR, "fig5_toy_model_comparison.png"),
                dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  ✅ fig5_toy_model_comparison.png")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Generating all figures with unified style...")
    os.makedirs(PAPER_DIR, exist_ok=True)
    make_fig1()
    make_fig2()
    make_fig3()
    make_fig4()
    make_fig5()
    print("Done!")
