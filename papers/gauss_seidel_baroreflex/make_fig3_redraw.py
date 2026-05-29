#!/usr/bin/env python3
"""
Redraw Figure 3 — code diff BEFORE vs AFTER (7-line fix).
Can run standalone (python make_fig3_redraw.py) or be imported
as make_fig3() by generate_all_figures.py.

Key improvements over previous version:
  1. Taller figure (12x9) with uniform 0.5-spaced code lines
  2. Dedicated annotation zone at bottom (y < 1.8) — no code placed there
  3. Change-status badges (DEL, NEW, CHG) in the center divider column
  4. Clean red/green highlighting with controlled alpha
  5. No overlaps between annotation bboxes and code text

Output: papers/gauss_seidel_baroreflex/fig3_code_diff.png (300 DPI)
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import os

PAPER_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Global style ─────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 10,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

# ── Colors ───────────────────────────────────────────────────────────────────
C_RED      = "#D55E00"
C_GREEN    = "#009E73"
C_ORANGE   = "#E68A2E"
C_GREY     = "#7F7F7F"
C_DKGREY   = "#555555"
C_BLACK    = "#333333"
C_YELLOW_BG = "#FFF8E1"


def _highlight(ax, x, y, color, alpha):
    """Draw a rounded highlight rectangle around a code line."""
    rect = FancyBboxPatch((x - 0.15, y - 0.20), 5.2, 0.40,
                          boxstyle="round,pad=0.03",
                          facecolor=color, edgecolor="none", alpha=alpha)
    ax.add_patch(rect)


def _section_label(ax, x, y, text):
    """Draw a centred grey section label spanning the code area."""
    bg = FancyBboxPatch((x - 1.2, y - 0.18), 3.0, 0.36,
                        boxstyle="round,pad=0.04",
                        facecolor="#EEEEEE", edgecolor="#CCCCCC", lw=0.8)
    ax.add_patch(bg)
    ax.text(x, y, text, fontsize=8.5, color=C_DKGREY,
            ha="center", va="center", style="italic")


def _status_label(ax, x, y, text, color):
    """Draw a small status badge in the divider column."""
    bg = FancyBboxPatch((x - 0.01, y - 0.13), 1.0, 0.26,
                        boxstyle="round,pad=0.03",
                        facecolor=color, edgecolor="none", alpha=0.15)
    ax.add_patch(bg)
    ax.text(x + 0.5, y, text, fontsize=7, fontweight="bold",
            ha="center", va="center", color=color)


def make_fig3():
    fig, ax = plt.subplots(figsize=(12, 9))
    ax.axis("off")
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 11)

    ax.set_title("Figure 3: Code Fix — 7 Lines Changed  (src/neuro.py + src/heart.py)",
                 fontsize=13, fontweight="bold", pad=14)

    # ── Layout constants ─────────────────────────────────────────────────────
    LX = 1.8       # left-column code x
    RX = 9.5       # right-column code x
    DX = 5.6       # divider x
    SX = 5.9       # status-label x
    LH = 5.2       # highlight rect width

    Y_HDR = 10.0   # column-header y
    Y0    = 9.0    # first code line y
    YS    = 0.50   # vertical step between code lines
    Y_ANN = 1.8    # annotation zone starts here (no code below)

    def code_line(y, left, right,
                  lhl=None, rhl=None, lc=C_BLACK, rc=C_BLACK,
                  status=None):
        """Draw a two-column code line with optional highlights and status."""
        # Left column
        if left:
            if lhl == "remove":
                _highlight(ax, LX, y, C_RED, 0.18)
                ax.text(LX, y, left, fontsize=9.5, fontfamily="monospace",
                        color=C_RED, ha="left", va="center", style="italic")
            elif lhl == "change":
                _highlight(ax, LX, y, C_RED, 0.10)
                ax.text(LX, y, left, fontsize=9.5, fontfamily="monospace",
                        color=C_BLACK, ha="left", va="center")
            else:
                ax.text(LX, y, left, fontsize=9.5, fontfamily="monospace",
                        color=lc, ha="left", va="center")

        # Right column
        if right:
            if rhl == "add":
                _highlight(ax, RX, y, C_GREEN, 0.18)
                ax.text(RX, y, right, fontsize=9.5, fontfamily="monospace",
                        color=C_GREEN, ha="left", va="center", fontweight="bold")
            elif rhl == "change":
                _highlight(ax, RX, y, C_GREEN, 0.12)
                ax.text(RX, y, right, fontsize=9.5, fontfamily="monospace",
                        color=C_BLACK, ha="left", va="center", fontweight="bold")
            else:
                ax.text(RX, y, right, fontsize=9.5, fontfamily="monospace",
                        color=rc, ha="left", va="center")

        # Status badge in divider column
        if status:
            sc = C_RED if status == "DEL" else (C_GREEN if status == "NEW" else C_ORANGE)
            _status_label(ax, SX, y, status, sc)

    # ════════════════════════════════════════════════════════════════════════
    # HEADERS
    # ════════════════════════════════════════════════════════════════════════
    ax.text(LX, Y_HDR, "BEFORE (buggy)", fontsize=12, fontweight="bold",
            color=C_RED, ha="center", va="center")
    ax.text(RX, Y_HDR, "AFTER (fixed)", fontsize=12, fontweight="bold",
            color=C_GREEN, ha="center", va="center")

    ax.text(LX, Y_HDR - 0.45, "src/neuro.py + src/heart.py",
            fontsize=8, color=C_GREY, ha="center", va="center", style="italic")
    ax.text(RX, Y_HDR - 0.45, "src/neuro.py + src/heart.py",
            fontsize=8, color=C_GREY, ha="center", va="center", style="italic")

    # ── Central dashed divider ──────────────────────────────────────────────
    ax.plot([DX, DX], [0.8, Y_HDR - 0.7], color="#BBBBBB", lw=1.5, ls="--")

    # ════════════════════════════════════════════════════════════════════════
    # CODE LINES  (top to bottom, uniform YS spacing)
    # ════════════════════════════════════════════════════════════════════════
    y = Y0

    # --- net_HR_add block ---
    _section_label(ax, LX, y + 0.05, "# --- net_HR_add (neuro.py) ---")

    y -= YS; code_line(y, "net_HR_add = (",            "net_HR_add = (")
    y -= YS; code_line(y, "    pain_HR_add",           "    pain_HR_add")
    y -= YS; code_line(y, "    + seizure_HR_add",      "    + seizure_HR_add")
    y -= YS; code_line(y, "    + cns_HR_add",          "    + cns_HR_add")
    y -= YS; code_line(y, "    + chemo_HR_add)",       "",
                       lhl="remove", status="DEL")
    y -= YS; code_line(y, "# chemo_HR -> continuous path",
                       "# chemo_HR -> heart.py only",
                       lhl="change", rhl="change", status="CHG")

    # --- heart.py section ---
    y -= YS  # spacer
    _section_label(ax, LX, y + 0.05, "# --- _baroreceptor_feedback (heart.py) ---")

    y -= YS; code_line(y, "HR_delta = (HR_para + HR_symp) * dt",
                       "HR_delta = (HR_para + HR_symp")
    y -= YS; code_line(y, "", "        + chemo_HR) * dt",
                       rhl="add", status="NEW")

    # --- FC emission ---
    y -= YS
    _section_label(ax, LX, y + 0.05, "# --- FC emission (neuro.py) ---")

    y -= YS; code_line(y, "FC('heart.heart_rate', 'add',",
                       "FC('heart.heart_rate', 'add',")
    y -= YS; code_line(y, "    net_HR_add)", "    net_HR_add * dt)",
                       lhl="change", rhl="change", status="CHG")
    y -= YS; code_line(y, "FC('heart.svr', 'multiply',",
                       "FC('heart.svr', 'multiply',")
    y -= YS; code_line(y, "    net_SVR_mult)", "    net_SVR_mult ** dt)",
                       lhl="change", rhl="change", status="CHG")

    # ════════════════════════════════════════════════════════════════════════
    # ANNOTATION ZONE  (y < Y_ANN) — no code placed here
    # ════════════════════════════════════════════════════════════════════════

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Key insight callout box
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    box = FancyBboxPatch((3.0, 0.55), 6.0, 0.95,
                         boxstyle="round,pad=0.15",
                         facecolor=C_YELLOW_BG, edgecolor=C_ORANGE, lw=2.5)
    ax.add_patch(box)

    ax.text(6.0, 1.15, "Key fix: multiply FC delta by dt",
            fontsize=11, color=C_ORANGE, fontweight="bold",
            ha="center", va="center")
    ax.text(6.0, 0.80, "A: dt-scaling on FC add  |  B: remove redundant chemo  |  C: SVR exponentiation",
            fontsize=8, color="#666666", ha="center", va="center", style="italic")

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Arrows from insight box to the FC *dt / **dt lines
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Primary FC *dt fix is at rel_y=11: y = Y0 - 11*YS = 3.5
    # (the `net_HR_add)` -> `net_HR_add * dt)` line)
    fc_y = Y0 - 11 * YS   # = 3.5

    # Left arrow: from insight box to the left-column changed line
    ax.annotate("",
                xy=(LX, fc_y + 0.25),
                xytext=(6.0 - 0.3, 1.50),
                arrowprops=dict(arrowstyle="->", lw=1.8, color=C_ORANGE,
                                connectionstyle="arc3,rad=0.2"))
    # Right arrow
    ax.annotate("",
                xy=(RX, fc_y + 0.25),
                xytext=(6.0 + 0.3, 1.50),
                arrowprops=dict(arrowstyle="->", lw=1.8, color=C_ORANGE,
                                connectionstyle="arc3,rad=-0.2"))

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Dimension labels at very bottom
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Left: bpm/step
    bg_l = FancyBboxPatch((LX - 1.8, 0.08), 3.6, 0.35,
                          boxstyle="round,pad=0.06",
                          facecolor="white", edgecolor=C_RED, lw=1.2)
    ax.add_patch(bg_l)
    ax.text(LX, 0.25, "bpm/step  (wrong)", fontsize=9,
            color=C_RED, ha="center", va="center", style="italic")

    # Right: bpm/s
    bg_r = FancyBboxPatch((RX - 1.8, 0.08), 3.6, 0.35,
                          boxstyle="round,pad=0.06",
                          facecolor="white", edgecolor=C_GREEN, lw=1.2)
    ax.add_patch(bg_r)
    ax.text(RX, 0.25, "bpm/s  (correct)", fontsize=9,
            color=C_GREEN, ha="center", va="center", style="italic")

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Legend at top of annotation zone
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    leg_y = Y_ANN - 0.05
    leg_items = [
        ("DEL", C_RED, "Removed"),
        ("NEW", C_GREEN, "Added"),
        ("CHG", C_ORANGE, "Changed"),
    ]
    ax.text(DX + 0.2, leg_y, "Legend:", fontsize=7.5, color=C_DKGREY,
            ha="left", va="center", fontweight="bold")
    for i, (label, clr, desc) in enumerate(leg_items):
        lx = DX + 1.2 + i * 1.8
        rect = FancyBboxPatch((lx - 0.4, leg_y - 0.12), 0.4, 0.24,
                              boxstyle="round,pad=0.02",
                              facecolor=clr, edgecolor="none", alpha=0.25)
        ax.add_patch(rect)
        ax.text(lx + 0.45, leg_y, desc, fontsize=7, color=C_DKGREY,
                ha="left", va="center")

    # ── Save ──
    outpath = os.path.join(PAPER_DIR, "fig3_code_diff.png")
    fig.savefig(outpath, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] Figure 3 saved: {outpath}")


if __name__ == "__main__":
    make_fig3()
    print("Done.")
