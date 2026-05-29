#!/usr/bin/env python3
"""
Standalone Figure 4 generator — X/Y/Z MAP range bar chart.

Usage:  python papers/gauss_seidel_baroreflex/make_fig4.py
Output: papers/gauss_seidel_baroreflex/fig4_before_after_comparison.png (300 DPI)
"""

import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Paths ──
PAPER_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT      = os.path.normpath(os.path.join(PAPER_DIR, "..", ".."))
EXP_DIR   = os.path.join(ROOT, "experiments")
DATA_PATH = os.path.join(EXP_DIR, "exp9_abc_results.json")
OUT_PATH  = os.path.join(PAPER_DIR, "fig4_before_after_comparison.png")

# ── Style ──
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
    "legend.frameon": False,
})

# Colorblind-friendly palette (Wong 2011 / IBM Carbon)
CB_RED    = "#D55E00"
CB_ORANGE = "#E68A2E"
CB_GREEN  = "#009E73"
CB_BLUE   = "#006BA6"
CB_GREY   = "#7F7F7F"


def main():
    # ── Load data ──
    with open(DATA_PATH) as f:
        exp9 = json.load(f)

    summary = exp9["summary"]
    dcs = [s["dc"] for s in summary]
    x_vals = np.array([s["X_range"] for s in summary])
    y_vals = np.array([s["Y_range"] for s in summary])
    z_vals = np.array([s["Z_range"] for s in summary])
    a_contrib = np.array([s["A_contrib"] for s in summary])

    severity_map = {25: "normal", 15: "mild", 10: "moderate", 5: "severe"}
    labels = [f"DC={d}\n({severity_map[d]})" for d in dcs]

    # ── Layout ──
    n_groups = len(dcs)
    x = np.arange(n_groups)
    width = 0.22          # bar width per group (3 bars → total 0.66)
    gap = 0.05            # small gap between bars within a group

    fig, ax = plt.subplots(figsize=(8.5, 4.8))

    bar_positions = {
        "X": x - width - gap / 2,
        "Y": x,
        "Z": x + width + gap / 2,
    }

    bars_x = ax.bar(bar_positions["X"], x_vals, width,
                    label="X (buggy: FC bpm/step)", color=CB_RED, alpha=0.88,
                    edgecolor="white", linewidth=0.4)
    bars_y = ax.bar(bar_positions["Y"], y_vals, width,
                    label="Y (A-only: FC x dt)", color=CB_ORANGE, alpha=0.88,
                    edgecolor="white", linewidth=0.4)
    bars_z = ax.bar(bar_positions["Z"], z_vals, width,
                    label="Z (A+B: FC x dt + cont.)", color=CB_GREEN, alpha=0.88,
                    edgecolor="white", linewidth=0.4)

    # ── Axes ──
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel("Hypoxemia severity (DC value)")
    ax.set_ylabel("MAP range across dt sweep (mmHg)")
    ax.set_title("Figure 4: MAP Range — Three-Condition Isolation",
                 fontsize=12, fontweight="bold", pad=10)
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(True, alpha=0.2, axis="y", linestyle=":")

    # ── Annotations: A_contrib on X bars where > 1 ──
    # Compute required y-limit first to avoid clipping
    max_bar = max(x_vals.max(), y_vals.max(), z_vals.max())
    annotation_base_padding = 0.12 * max_bar  # 12% headroom for annotations
    annotation_offsets = []  # track per-group offsets for collision avoidance

    for i in range(n_groups):
        group_annotations = []

        # --- X bar annotation (A_contrib) ---
        if a_contrib[i] > 1:
            txt = f"A = {a_contrib[i]:.1f}"
            y_pos = x_vals[i] + annotation_base_padding * 0.9
            ax.annotate(
                txt,
                xy=(bar_positions["X"][i] + width / 2, x_vals[i]),
                xytext=(bar_positions["X"][i] + width / 2, y_pos),
                fontsize=8.5, color=CB_RED, ha="center", va="bottom",
                fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=CB_RED, lw=0.5, alpha=0.4),
            )
            group_annotations.append(y_pos)

        # --- Value labels on Y and Z bars (for bars > 0.5 mmHg) ---
        # Only label Y and Z when they are short relative to X (storytelling emphasis)
        if y_vals[i] > 0.5 and y_vals[i] < x_vals[i] * 0.5:
            txt_y = f"{y_vals[i]:.2f}"
            y_off = y_vals[i] + annotation_base_padding * 0.6
            ax.text(bar_positions["Y"][i] + width / 2, y_off, txt_y,
                    fontsize=7.5, color=CB_ORANGE, ha="center", va="bottom")
            group_annotations.append(y_off)

        if z_vals[i] > 0.5 and z_vals[i] < x_vals[i] * 0.5:
            txt_z = f"{z_vals[i]:.2f}"
            z_off = z_vals[i] + annotation_base_padding * 0.6
            ax.text(bar_positions["Z"][i] + width / 2, z_off, txt_z,
                    fontsize=7.5, color=CB_GREEN, ha="center", va="bottom")
            group_annotations.append(z_off)

        annotation_offsets.append(group_annotations)

    # ── Set y-limit with headroom for annotations ──
    # Find the tallest annotation across all groups
    all_annotation_heights = [max(grp) if grp else 0 for grp in annotation_offsets]
    max_annotation_y = max(all_annotation_heights) if any(all_annotation_heights) else max_bar
    y_padding = 0.20 * max_bar
    ax.set_ylim(0, max_annotation_y + y_padding)

    # ── Key insight callout ──
    # A bracket above the DC=10 and DC=5 groups to highlight the fix region
    for idx in [2, 3]:
        if idx < n_groups:
            xc = x[idx]
            bracket_y = max_bar * 1.02
            ax.plot([xc - width - gap / 2, xc + width + gap / 2],
                    [bracket_y, bracket_y],
                    color=CB_GREEN, lw=1.0, alpha=0.5)
            ax.plot([xc - width - gap / 2, xc - width - gap / 2],
                    [bracket_y, bracket_y - max_bar * 0.015],
                    color=CB_GREEN, lw=0.8, alpha=0.5)
            ax.plot([xc + width + gap / 2, xc + width + gap / 2],
                    [bracket_y, bracket_y - max_bar * 0.015],
                    color=CB_GREEN, lw=0.8, alpha=0.5)

    # ── Caption-style note ──
    ax.text(
        0.98, 0.98,
        "A = X_range − Y_range  (FC dt-scaling eliminates the bias)",
        transform=ax.transAxes, fontsize=8, fontstyle="italic",
        ha="right", va="top", color=CB_GREY,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=CB_GREY, alpha=0.7),
    )

    # ── Save ──
    os.makedirs(PAPER_DIR, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {OUT_PATH}")


if __name__ == "__main__":
    main()
