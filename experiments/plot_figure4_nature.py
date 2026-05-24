"""
Figure 4 — Nature-style 4-Panel: Coupling Strategy Comparison
Generates: figure4_nature.svg | figure4_nature.pdf | figure4_nature.tiff
"""

import json, os
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_EXPERIMENTS_DIR, "coupling_comparison_data.json")
_OUT_BASE = os.path.join(_EXPERIMENTS_DIR, "figure4_nature")
_CLINICAL_THRESHOLD = 2.0

# ── Nature style defaults ──────────────────────────────────────────────
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 7,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.8,
    "legend.frameon": False,
    "axes.grid": False,
})
plt.rc("xtick", labelsize=7)
plt.rc("ytick", labelsize=7)

W, H = 183 / 25.4, 120 / 25.4   # Nature single-col inches (183 mm)
DPI_TIFF = 600


def _load():
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _extract(data, key, field):
    ts = data[key]["time_series"]
    filtered = [p for p in ts if p["t"] <= 62.0]
    t = np.array([p["t"] for p in filtered])
    v = np.array([p[field] for p in filtered])
    return t, v


def save_pub(fig, path_svg, path_pdf, path_tiff):
    fig.savefig(path_svg, bbox_inches="tight")
    fig.savefig(path_pdf, bbox_inches="tight")
    fig.savefig(path_tiff, dpi=DPI_TIFF, bbox_inches="tight")


def plot_figure4():
    data = _load()

    # ── load all series ────────────────────────────────────────────────
    ref_t,  ref_map   = _extract(data, "reference",    "MAP")
    semi_t, semi_map  = _extract(data, "semi_implicit","MAP")
    semi_hr = _extract(data, "semi_implicit","HR")[1]
    seq_t,  seq_bv    = _extract(data, "sequential",   "blood_volume_mL")
    semi_t2, semi_bv  = _extract(data, "semi_implicit", "blood_volume_mL")

    euler_keys = [
        ("sequential_dt010", "Euler dt=0.10", "#2171B5"),
        ("sequential",       "Euler dt=0.05", "#6BAED6"),
        ("sequential_dt001", "Euler dt=0.01", "#BDD7E7"),
    ]

    # Panel (d) lookup
    panel_d_map = {p["method"]: p for p in data["panel_d"]}
    euler_pareto = [
        ("sequential_dt010", "Euler dt=0.1"),
        ("sequential",       "Euler dt=0.05"),
        ("sequential_dt001", "Euler dt=0.001"),
    ]

    # ── figure ────────────────────────────────────────────────────────
    fig, axs = plt.subplots(2, 2, figsize=(W, H))
    fig.subplots_adjust(left=0.07, right=0.97, top=0.93, bottom=0.10,
                        wspace=0.28, hspace=0.38)
    plt.rc("font", family="Arial", size=7)

    # ── Panel (a): MAP ────────────────────────────────────────────────
    ax = axs[0, 0]
    ax.plot(ref_t,  ref_map,  "k--", lw=1.0, label="Ref", zorder=5)
    for key, lbl, col in euler_keys:
        t, v = _extract(data, key, "MAP")
        if len(t): ax.plot(t, v, color=col, lw=1.2, label=lbl, zorder=3)
    ax.plot(semi_t, semi_map, color="#E6550D", lw=1.5, label="Radau", zorder=4)

    # annotations
    ri = np.argmin(ref_map)
    ax.annotate(f"min {ref_map[ri]:.1f}", xy=(ref_t[ri], ref_map[ri]),
                xytext=(ref_t[ri]+4, ref_map[ri]-4),
                fontsize=6.5, color="k",
                arrowprops=dict(arrowstyle="->", color="k", lw=0.6))
    ei = np.argmin(_extract(data, "sequential", "MAP")[1])
    e0_t, e0_v = _extract(data, "sequential", "MAP")
    ax.annotate(f"min {e0_v[ei]:.1f}", xy=(e0_t[ei], e0_v[ei]),
                xytext=(e0_t[ei]+4, e0_v[ei]+4),
                fontsize=6.5, color="#2171B5",
                arrowprops=dict(arrowstyle="->", color="#2171B5", lw=0.6))

    ax.axhline(100, color="0.6", ls=":", lw=0.6)
    ax.set_xlabel("Time (s)", fontsize=7)
    ax.set_ylabel("MAP (mmHg)", fontsize=7)
    ax.set_title("a", fontweight="bold", fontsize=8, pad=3)
    ax.set_xlim(0, 60)
    ax.set_ylim(78, 112)
    ax.legend(fontsize=6, loc="lower left", frameon=False)

    # ── Panel (b): HR ────────────────────────────────────────────────
    ax = axs[0, 1]
    for key, lbl, col in euler_keys:
        t, v = _extract(data, key, "HR")
        if len(t): ax.plot(t, v, color=col, lw=1.2, label=lbl, zorder=3)
    ax.plot(semi_t, semi_hr, color="#E6550D", lw=1.5, label="Radau", zorder=4)
    ax.axhline(85, color="k", ls="--", lw=0.8, label="HR₀=85")
    ax.set_xlabel("Time (s)", fontsize=7)
    ax.set_ylabel("HR (bpm)", fontsize=7)
    ax.set_title("b", fontweight="bold", fontsize=8, pad=3)
    ax.set_xlim(0, 60)
    ax.legend(fontsize=6, frameon=False)

    # ── Panel (c): BV ────────────────────────────────────────────────
    ax = axs[1, 0]
    ax.plot(seq_t,  seq_bv,  color="#2171B5", lw=1.2, label="Euler dt=0.05")
    ax.plot(semi_t2, semi_bv, color="#E6550D", lw=1.2, label="Radau")
    if len(seq_t) == len(semi_t2):
        diff = np.max(np.abs(seq_bv - semi_bv))
        ax.text(0.98, 0.06, f"max |ΔBV|={diff:.1f} mL",
                transform=ax.transAxes, fontsize=6.5, ha="right",
                color="green" if diff < 5 else "#D62728")
    ax.set_xlabel("Time (s)", fontsize=7)
    ax.set_ylabel("Blood Volume (mL)", fontsize=7)
    ax.set_title("c", fontweight="bold", fontsize=8, pad=3)
    ax.set_xlim(0, 60)
    ax.legend(fontsize=6, frameon=False)

    # ── Panel (d): Pareto ─────────────────────────────────────────────
    ax = axs[1, 1]

    # Euler Pareto frontier
    ep_times, ep_devs = [], []
    for key, lbl in euler_pareto:
        mn = f"Sequential ({lbl})"
        pt = panel_d_map.get(mn)
        if pt and pt["time_s"] > 0:
            ep_times.append(pt["time_s"])
            ep_devs.append(pt["max_MAP_deviation"])
    order = np.argsort(ep_times)
    ep_times = np.array(ep_times)[order]
    ep_devs  = np.array(ep_devs)[order]
    ax.plot(ep_times, ep_devs, color="#2171B5", lw=1.5, zorder=3)
    for t, d in zip(ep_times, ep_devs):
        ax.scatter(t, d, color="#2171B5", marker="s", s=40, zorder=4)
        ax.text(t, d*1.3, f"{t:.2f}s", fontsize=5.5, ha="center",
                color="#2171B5")

    # Radau
    radau_pt = panel_d_map.get("Semi-implicit (Radau)")
    if radau_pt:
        ax.scatter(radau_pt["time_s"], radau_pt["max_MAP_deviation"],
                   color="#E6550D", marker="o", s=50, zorder=5, label="Radau")
        ax.text(radau_pt["time_s"]*1.5, radau_pt["max_MAP_deviation"]*1.5,
                "Radau", fontsize=6, color="#E6550D")

    # Ref
    ref_pt = panel_d_map.get("Ref (Radau rtol=1e-10)")
    if ref_pt:
        ax.scatter(ref_pt["time_s"], ref_pt["max_MAP_deviation"],
                   color="k", marker="*", s=80, zorder=5, label="Ref")

    # clinical threshold
    ax.axhline(_CLINICAL_THRESHOLD, color="0.4", ls="--", lw=0.9,
               label=f"Clinical\nthreshold")

    # "unattainable zone" annotation
    ax.text(1.5, _CLINICAL_THRESHOLD * 2.5,
            "Euler\nUnattainable\nZone",
            fontsize=5.5, color="0.45", ha="center",
            style="italic")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Computing Time (s)", fontsize=7)
    ax.set_ylabel("Max |ΔMAP| vs Ref (mmHg)", fontsize=7)
    ax.set_title("d", fontweight="bold", fontsize=8, pad=3)
    ax.set_xlim(2e-2, 1e4)
    ax.set_ylim(5e-3, 2e2)
    ax.legend(fontsize=6, frameon=False, loc="upper left")

    # ── save ─────────────────────────────────────────────────────────
    save_pub(fig,
             f"{_OUT_BASE}.svg",
             f"{_OUT_BASE}.pdf",
             f"{_OUT_BASE}.tiff")

    print(f"Figure 4 Nature-style saved:")
    print(f"  {_OUT_BASE}.svg")
    print(f"  {_OUT_BASE}.pdf")
    print(f"  {_OUT_BASE}.tiff  (dpi={DPI_TIFF})")

    print("\n=== Panel (d) ===")
    print(f"{'Method':<38} {'Time(s)':>9} {'L∞ ΔMAP':>9} {'RMSE':>7}")
    print("-" * 65)
    for p in data["panel_d"]:
        print(f"{p['method']:<38} {p['time_s']:>9.2f} "
              f"{p['max_MAP_deviation']:>9.3f} {p['rmse_MAP']:>7.3f}")


if __name__ == "__main__":
    plot_figure4()