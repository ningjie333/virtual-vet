"""
Figure 4 — 4-Panel Visualization: 耦合策略对比

Panel (a): MAP 时序 — Euler (3档dt), Radau, Ref
Panel (b): HR 时序 — Euler (3档dt), Radau
Panel (c): BV 时序 — 验证模型一致性
Panel (d): 精度-效率 Pareto 曲线 — log(time) vs max |ΔMAP|
"""

import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_EXPERIMENTS_DIR, "coupling_comparison_data.json")
_CLINICAL_THRESHOLD = 2.0  # mmHg，临床可接受误差


def _load() -> dict:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _get_ts(data: dict, key: str) -> list[dict]:
    return data[key]["time_series"]


def _extract(data: dict, key: str, field: str):
    """提取时间序列，只取 0-60s 范围内的点"""
    ts = _get_ts(data, key)
    # dt=0.001 的数据末端时间异常，只取 0-62s 范围内的点
    filtered = [p for p in ts if p["t"] <= 62.0]
    t = [p["t"] for p in filtered]
    v = [p[field] for p in filtered]
    return np.array(t), np.array(v)


def plot_figure4():
    data = _load()

    ref_t, ref_map = _extract(data, "reference", "MAP")
    semi_t, semi_map = _extract(data, "semi_implicit", "MAP")

    euler_keys = [
        ("sequential_dt010", "Euler dt=0.10", "lightblue", "-"),
        ("sequential", "Euler dt=0.05", "b", "-"),
        ("sequential_dt001", "Euler dt=0.01", "darkslateblue", "-"),
        # dt=0.001 数值崩溃，跳过
    ]

    fig, axs = plt.subplots(2, 2, figsize=(14, 11))
    fig.suptitle(
        "Figure 4: Coupling Strategy Comparison — Acute Hemorrhagic Shock Transient\n"
        "20 kg dog, blood loss 400 mL at t=5s (23.5% BV = Class II shock)",
        fontsize=12, fontweight="bold",
    )

    # ── Panel (a): MAP 时序 ────────────────────────────────────────────
    ax = axs[0, 0]
    ax.plot(ref_t, ref_map, "k--", linewidth=1.5, label="Ref (Radau rtol=1e-10)", zorder=5)

    for key, lbl, color, ls in euler_keys:
        t, v = _extract(data, key, "MAP")
        if len(t) > 0:
            ax.plot(t, v, color=color, linestyle=ls, linewidth=1.8, label=lbl, zorder=3)

    ax.plot(semi_t, semi_map, "orange", linewidth=2.2, label="Radau rtol=1e-4", zorder=4)

    # 标注 Ref min MAP
    ref_min_idx = np.argmin(ref_map)
    ax.annotate(
        f"Ref min\n{ref_map[ref_min_idx]:.1f}",
        xy=(ref_t[ref_min_idx], ref_map[ref_min_idx]),
        xytext=(ref_t[ref_min_idx] + 3, ref_map[ref_min_idx] - 4),
        fontsize=8, color="black",
        arrowprops=dict(arrowstyle="->", color="black", lw=0.8),
    )
    # 标注 Euler min MAP
    e0_t, e0_v = _extract(data, "sequential", "MAP")
    e0_min_idx = np.argmin(e0_v)
    ax.annotate(
        f"Euler min\n{e0_v[e0_min_idx]:.1f}",
        xy=(e0_t[e0_min_idx], e0_v[e0_min_idx]),
        xytext=(e0_t[e0_min_idx] + 3, e0_v[e0_min_idx] + 4),
        fontsize=8, color="blue",
        arrowprops=dict(arrowstyle="->", color="blue", lw=0.8),
    )

    ax.axhline(100, color="gray", linestyle=":", linewidth=0.8, zorder=1)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("MAP (mmHg)")
    ax.set_title("(a) MAP Time Series — Radau Captures Deeper Transient (81.7 vs 85.0 mmHg)")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 60)
    ax.set_ylim(75, 110)

    # ── Panel (b): HR 时序 ────────────────────────────────────────────
    ax = axs[0, 1]
    for key, lbl, color, ls in euler_keys:
        t, v = _extract(data, key, "HR")
        if len(t) > 0:
            ax.plot(t, v, color=color, linestyle=ls, linewidth=1.8, label=lbl, zorder=3)

    _, semi_hr_arr = _extract(data, "semi_implicit", "HR")
    ax.plot(semi_t, semi_hr_arr, "orange", linewidth=2.2, label="Radau rtol=1e-4", zorder=4)
    ax.axhline(85, color="k", linestyle="--", linewidth=1, label="HR₀=85 bpm", zorder=1)

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("HR (bpm)")
    ax.set_title("(b) HR Time Series — Euler HR Compensatory Overload")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 60)

    # ── Panel (c): BV 时序 ────────────────────────────────────────────
    ax = axs[1, 0]
    seq_t, seq_bv = _extract(data, "sequential", "blood_volume_mL")
    semi_t, semi_bv = _extract(data, "semi_implicit", "blood_volume_mL")

    ax.plot(seq_t, seq_bv, "b-", linewidth=1.8, label="Euler dt=0.05", zorder=2)
    ax.plot(semi_t, semi_bv, "orange", linewidth=1.8, label="Radau", zorder=2)

    if len(seq_t) == len(semi_t):
        bv_diff = np.abs(seq_bv - semi_bv)
        max_diff = float(np.max(bv_diff))
        ax.text(
            0.98, 0.05,
            f"BV Deviation max={max_diff:.1f} mL",
            transform=ax.transAxes,
            fontsize=8, ha="right",
            color="red" if max_diff > 5 else "green",
        )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Blood Volume (mL)")
    ax.set_title("(c) Blood Volume Time Series — Model Consistency Check")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 60)

    # ── Panel (d): 精度-效率 Pareto 曲线 ───────────────────────────────
    ax = axs[1, 1]

    # 按方法分组画 Pareto 曲线
    # Panel (d) data — use exact method names from panel_d
    panel_d_map = {p["method"]: p for p in data["panel_d"]}

    # Euler 三个变体
    euler_keys_ordered = [
        ("sequential_dt010", "Euler dt=0.1", "b"),
        ("sequential",       "Euler dt=0.05", "b"),
        ("sequential_dt001", "Euler dt=0.001", "b"),
    ]

    euler_times, euler_devs, euler_labels = [], [], []
    for key, lbl, color in euler_keys_ordered:
        if key in data:
            # Exact method name format in panel_d: "Sequential (Euler dt=0.05)"
            method_name = f"Sequential ({lbl})"
            pt = panel_d_map.get(method_name)
            if pt and pt["time_s"] > 0:
                euler_times.append(pt["time_s"])
                euler_devs.append(pt["max_MAP_deviation"])
                euler_labels.append(lbl)

    # 按时间排序
    euler_order = np.argsort(euler_times)
    euler_times = np.array(euler_times)[euler_order]
    euler_devs = np.array(euler_devs)[euler_order]
    euler_labels = [euler_labels[i] for i in euler_order]

    # 折线
    ax.plot(euler_times, euler_devs, "b-", linewidth=2, zorder=3, alpha=0.7)
    for t, d, lbl in zip(euler_times, euler_devs, euler_labels):
        ax.scatter(t, d, c="b", marker="s", s=100, zorder=4)
        ax.annotate(lbl, xy=(t, d), xytext=(5, 5),
                     textcoords="offset points", fontsize=7, color="blue")

    # Radau 点 — 精确查找
    radau_pt = panel_d_map.get("Semi-implicit (Radau)")
    if radau_pt:
        ax.scatter(radau_pt["time_s"], radau_pt["max_MAP_deviation"],
                   c="orange", marker="o", s=150, zorder=5, label="Radau")
        ax.annotate("Radau", xy=(radau_pt["time_s"], radau_pt["max_MAP_deviation"]),
                    xytext=(5, 5), textcoords="offset points", fontsize=8, color="orange")

    # Ref 点（原点）
    ref_pt = panel_d_map.get("Ref (Radau rtol=1e-10)")
    if ref_pt:
        ax.scatter(ref_pt["time_s"], ref_pt["max_MAP_deviation"],
                   c="black", marker="*", s=200, zorder=5, label="Ref (0,0)")

    # 临床误差阈值线
    ax.axhline(_CLINICAL_THRESHOLD, color="green", linestyle="--", linewidth=1.5,
               zorder=2, label=f"Clinical Threshold |dMAP|<{_CLINICAL_THRESHOLD} mmHg")

    # Euler unattainable zone annotation
    ax.annotate(
        "Euler Unattainable Zone\n(cost unacceptable)",
        xy=(0.5, _CLINICAL_THRESHOLD + 0.01),
        xytext=(2.0, _CLINICAL_THRESHOLD + 0.08),
        fontsize=8, color="gray",
        arrowprops=dict(arrowstyle="->", color="gray", lw=1.5),
    )

    ax.set_xscale("log")
    ax.set_xlabel("Computing Time (s, log scale)")
    ax.set_ylabel("Max |MAP − Ref| (mmHg)")
    ax.set_title("(d) Accuracy-Efficiency Pareto — Radau Dominates Euler")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3, which="both")
    ax.set_xlim(1e-2, 1e4)
    ax.set_ylim(5e-3, 1e2)

    plt.tight_layout()

    out_path = os.path.join(_EXPERIMENTS_DIR, "figure4.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Figure 4 saved → {out_path}")

    # Print panel (d) data table
    print("\n=== Panel (d) Data ===")
    print(f"{'Method':<35} {'Time (s)':>10} {'L∞ ΔMAP':>10} {'RMSE':>8} {'SS Err':>8}")
    print("-" * 73)
    for p in data["panel_d"]:
        ss = f"{p['steady_state_error']:.4f}" if p["steady_state_error"] is not None else "N/A"
        print(f"{p['method']:<35} {p['time_s']:>10.3f} {p['max_MAP_deviation']:>10.3f} "
              f"{p['rmse_MAP']:>8.3f} {ss:>8}")


if __name__ == "__main__":
    plot_figure4()