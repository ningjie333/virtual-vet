#!/usr/bin/env python3
"""
Figure 1 — Spurious Steady State Schematic
Standalone script. Output: fig1_pseudo_convergence_schematic.png (300 DPI, Times New Roman)

Colorblind-friendly palette: blue/orange/teal (Wong 2011 inspired).
All boxes use FancyBboxPatch with rounded corners.
Critical alignment: elements sharing x or y coordinates align exactly.
"""

import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# ── Global style ────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

# ── Paths ───────────────────────────────────────────────────────────────────
PAPER_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Colorblind-friendly palette ─────────────────────────────────────────────
# Wong 2011 palette adapted: blue, orange, teal replace red/green pairs.
# Warm hues (orange) for drift/error states; cool hues (blue/teal) for correct.
BLUE     = "#0072B2"   # true blue      — True Fixed Point
ORANGE   = "#E69F00"   # orange          — Spurious Fixed Point, Discrete FC
TEAL     = "#009E73"   # bluish-green    — Continuous Path (replaces green)
AMBER    = "#F9A825"   # warm amber      — HR Saturation edge
GREY     = "#7F7F7F"   # subtle text

# ── Helper: FancyBox with text ──────────────────────────────────────────────
def fancybox(ax, xc, yc, w, h, text, subtext="",
             face="#e8f5e9", edge="#2e7d32", text_color="black",
             fontsize=9, sub_fontsize=8):
    """
    Draw a rounded FancyBboxPatch centered at (xc, yc).
    text  = bold title  (rendered at yc + offset)
    subtext = lighter subtitle (rendered at yc - offset)
    Offsets are computed as fractions of h so they stay proportional.
    """
    box = FancyBboxPatch(
        (xc - w / 2, yc - h / 2), w, h,
        boxstyle="round,pad=0.08",
        facecolor=face, edgecolor=edge, lw=2
    )
    ax.add_patch(box)

    # Title text — slightly above vertical center
    title_y = yc + (0.10 * h if subtext else 0)
    ax.text(xc, title_y, text,
            ha="center", va="center", fontsize=fontsize,
            fontweight="bold", color=text_color)

    # Subtitle text — below vertical center
    if subtext:
        ax.text(xc, yc - 0.22 * h, subtext,
                ha="center", va="center",
                fontsize=sub_fontsize, color="#555555")


# ═══════════════════════════════════════════════════════════════════════════
def make_fig1():
    """Build Figure 1 — Spurious steady state schematic."""

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.set_xlim(-0.3, 10.3)
    ax.set_ylim(-0.3, 6.3)
    ax.axis("off")

    # Title
    ax.set_title(
        "Figure 1: Spurious Steady State — Drift and Saturation Mechanism",
        fontsize=12, fontweight="bold", pad=10
    )

    # ── Coordinate system (for alignment verification) ──
    # True FP  — Cont. Path     share x = 2.3
    # Spur. FP — Saturation — DFC  share x = 7.7
    # True FP — Spur. FP         share y = 4.9
    # Cont. Path — DFC           share y = 1.8
    # All box edges are computed from (center, width, height).

    # ================================================================
    #  A. True Fixed Point  (top-left, blue)
    # ================================================================
    xc_tfp, yc_tfp = 2.3, 4.9
    w_tfp, h_tfp = 2.6, 0.9
    fancybox(ax, xc_tfp, yc_tfp, w_tfp, h_tfp,
             "True Fixed Point", "MAP ~ 100 mmHg",
             face="#E3F2FD", edge=BLUE, fontsize=10,
             sub_fontsize=8)

    # ================================================================
    #  B. Spurious Fixed Point  (top-right, orange)
    # ================================================================
    xc_sfp, yc_sfp = 7.7, 4.9
    w_sfp, h_sfp = 2.8, 0.9
    fancybox(ax, xc_sfp, yc_sfp, w_sfp, h_sfp,
             "Spurious Fixed Point", "MAP ~ 144.7 mmHg",
             face="#FFF3E0", edge=ORANGE, fontsize=10,
             sub_fontsize=8)

    # ================================================================
    #  C. HR Saturation  (mid-right, amber)
    # ================================================================
    xc_sat, yc_sat = 7.7, 3.2
    w_sat, h_sat = 3.4, 0.9
    fancybox(ax, xc_sat, yc_sat, w_sat, h_sat,
             "HR Saturation at 180 bpm",
             "physiological ceiling truncates drift",
             face="#FFF8E1", edge=AMBER, fontsize=9,
             sub_fontsize=8)

    # ================================================================
    #  D. Continuous Path  (bottom-left, teal)
    # ================================================================
    xc_con, yc_con = 2.3, 1.8
    w_con, h_con = 3.0, 0.8
    fancybox(ax, xc_con, yc_con, w_con, h_con,
             "Continuous Path",
             "HR_delta = (symp + para + chemo) x dt  ->  correct",
             face="#E8F5E9", edge=TEAL, fontsize=9,
             sub_fontsize=7.5)

    # ================================================================
    #  E. Discrete FC Path  (bottom-right, orange)
    # ================================================================
    xc_dfc, yc_dfc = 7.7, 1.8
    w_dfc, h_dfc = 3.0, 0.8
    fancybox(ax, xc_dfc, yc_dfc, w_dfc, h_dfc,
             "Discrete FC Path",
             "net_HR_add = K bpm/step  ->  K x T/dt total injection",
             face="#FFF3E0", edge=ORANGE, fontsize=9,
             sub_fontsize=7.5)

    # ================================================================
    #  Arrows  (computed from box edges)
    # ================================================================

    # Arrow 1: True FP right edge -> Spurious FP left edge  (horizontal drift)
    #   True FP  right edge = xc_tfp + w_tfp/2 = 2.3 + 1.3 = 3.6
    #   Spur. FP left  edge = xc_sfp - w_sfp/2 = 7.7 - 1.4 = 6.3
    ax.annotate("",
                xy=(6.3, 4.9), xytext=(3.6, 4.9),
                arrowprops=dict(arrowstyle="->", lw=2.0, color=ORANGE))
    # Label above the arrow
    ax.text(4.95, 5.20, "drift ~ K * T / dt",
            ha="center", fontsize=9, color=ORANGE, fontweight="bold")

    # Arrow 2: Saturation top edge -> Spurious FP bottom edge  (vertical up)
    #   Sat  top edge = yc_sat + h_sat/2 = 3.2 + 0.45 = 3.65
    #   SFP  bot edge = yc_sfp - h_sfp/2 = 4.9 - 0.45 = 4.45
    ax.annotate("",
                xy=(7.7, 4.45), xytext=(7.7, 3.65),
                arrowprops=dict(arrowstyle="->", lw=1.8, color=ORANGE))
    ax.text(8.40, 4.05, "truncates\ndrift",
            ha="left", va="center", fontsize=8, color=AMBER)

    # Arrow 3: Continuous Path top -> True FP bottom   (vertical up, x=2.3)
    #   Con top edge = yc_con + h_con/2 = 1.8 + 0.4 = 2.2
    #   TFP bot edge = yc_tfp - h_tfp/2 = 4.9 - 0.45 = 4.45
    ax.annotate("",
                xy=(2.3, 4.45), xytext=(2.3, 2.2),
                arrowprops=dict(arrowstyle="->", lw=1.5,
                                color=TEAL, ls="dashed"))

    # Arrow 4: Discrete FC Path top -> Saturation bottom   (vertical up, x=7.7)
    #   DFC top edge = yc_dfc + h_dfc/2 = 1.8 + 0.4 = 2.2
    #   Sat bot edge = yc_sat - h_sat/2 = 3.2 - 0.45 = 2.75
    ax.annotate("",
                xy=(7.7, 2.75), xytext=(7.7, 2.2),
                arrowprops=dict(arrowstyle="->", lw=1.5,
                                color=ORANGE, ls="dashed"))

    # ================================================================
    #  Panel labels  (A, B, C, D on the left margin)
    # ================================================================
    # y-positions chosen to sit beside each row
    ax.text(-0.1, 5.8, "A", fontsize=14, fontweight="bold", va="top")
    ax.text(-0.1, 4.2, "B", fontsize=14, fontweight="bold", va="center")
    ax.text(-0.1, 2.6, "C", fontsize=14, fontweight="bold", va="center")
    ax.text(-0.1, 1.0, "D", fontsize=14, fontweight="bold", va="center")

    # ================================================================
    #  Save
    # ================================================================
    outpath = os.path.join(PAPER_DIR, "fig1_pseudo_convergence_schematic.png")
    fig.savefig(outpath, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Done: {outpath}")


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    make_fig1()
